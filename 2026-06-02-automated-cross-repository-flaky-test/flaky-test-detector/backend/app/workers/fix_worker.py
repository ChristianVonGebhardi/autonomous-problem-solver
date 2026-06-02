"""
Fix Synthesis Worker

Polls Redis queue for flaky test fix jobs, assembles context, calls LLM,
and creates PR proposals.
"""
import asyncio
import json
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import psycopg2
import psycopg2.extras
import redis as redis_lib
import structlog

from app.config import settings
from app.services.context_assembler import assemble_context, format_context_for_llm
from app.services.fix_synthesizer import synthesize_fix
from app.services.pr_bot import post_fix_proposal

logger = structlog.get_logger()


def get_db_conn():
    return psycopg2.connect(settings.database_url)


def get_redis():
    return redis_lib.from_url(settings.redis_url)


SAMPLE_SOURCE_CODE = {
    "timing": """
import time
import requests
from selenium import webdriver
from selenium.webdriver.support.ui import WebDriverWait

class TestUserFlow:
    def setUp(self):
        self.driver = webdriver.Chrome()
    
    def tearDown(self):
        self.driver.quit()
    
    def test_user_login(self):
        self.driver.get("http://localhost:3000/login")
        time.sleep(2)  # Wait for page to load
        self.driver.find_element_by_id("username").send_keys("testuser")
        self.driver.find_element_by_id("password").send_keys("password123")
        self.driver.find_element_by_id("submit").click()
        time.sleep(1)  # Wait for redirect
        assert "dashboard" in self.driver.current_url
    
    def test_api_response(self):
        response = requests.get("http://api.service/data", timeout=1)
        assert response.json()["status"] == "ok"
""",
    "concurrency": """
import threading
import time
from queue import Queue

shared_counter = 0
results = []

class TestConcurrentOperations:
    def test_counter_increment(self):
        global shared_counter
        
        def increment_worker():
            global shared_counter
            for _ in range(100):
                temp = shared_counter
                time.sleep(0.001)  # Simulate work
                shared_counter = temp + 1
        
        threads = [threading.Thread(target=increment_worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        # This often fails due to race condition
        assert shared_counter == 500
    
    def test_shared_results(self):
        global results
        
        def append_result(value):
            results.append(value)  # Not thread-safe!
        
        threads = [threading.Thread(target=append_result, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        assert len(results) == 10
""",
    "environment": """
import os
import requests
import subprocess

class TestExternalService:
    def test_api_health(self):
        host = os.environ.get("API_HOST", "localhost")
        response = requests.get(f"http://{host}:8080/health")
        assert response.status_code == 200
    
    def test_database_connection(self):
        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        cur = conn.cursor()
        cur.execute("SELECT 1")
        assert cur.fetchone()[0] == 1
        conn.close()
    
    def test_file_processing(self):
        # Depends on /tmp/test_data existing
        with open("/tmp/test_data/input.csv") as f:
            data = f.read()
        assert len(data) > 0
""",
    "state_leakage": """
import pytest
from myapp.models import User, Order
from myapp.database import db

class TestUserOrders:
    def test_create_user(self):
        user = User(name="test_user", email="test@example.com")
        db.session.add(user)
        db.session.commit()
        
        found = User.query.filter_by(email="test@example.com").first()
        assert found is not None
    
    def test_user_count(self):
        # Fails if test_create_user ran first and left data!
        count = User.query.count()
        assert count == 0
    
    def test_order_creation(self):
        user = User.query.first()  # Depends on users existing from other tests!
        order = Order(user_id=user.id, amount=100.00)
        db.session.add(order)
        db.session.commit()
        assert order.id is not None
""",
}


def get_source_code(repo: str, test_file: str, root_cause: str) -> str:
    """
    Fetch source code for context assembly.
    In production: clone repo or use GitHub API.
    In MVP: return representative sample code based on root cause.
    """
    # Check if we have a mock for this root cause
    if root_cause in SAMPLE_SOURCE_CODE:
        return SAMPLE_SOURCE_CODE[root_cause]
    
    # Try to get from GitHub API if token available
    if settings.github_token and test_file:
        try:
            import httpx
            headers = {"Authorization": f"Bearer {settings.github_token}"}
            url = f"https://api.github.com/repos/{repo}/contents/{test_file}"
            resp = httpx.get(url, headers=headers)
            if resp.status_code == 200:
                import base64
                content = resp.json().get("content", "")
                return base64.b64decode(content).decode("utf-8")
        except Exception as e:
            logger.warning("github_fetch_failed", error=str(e))
    
    return SAMPLE_SOURCE_CODE.get("state_leakage", "# Source code unavailable")


async def process_fix_job(conn, job: dict):
    """Process a single fix synthesis job."""
    flaky_test_id = job["flaky_test_id"]
    test_name = job["test_name"]
    test_file = job.get("test_file", "tests/test_file.py")
    root_cause = job["root_cause"]
    repo = job["repo"]
    log_output = job.get("log_output", "")
    error_message = job.get("error_message", "")
    
    # Check if we already have a non-rejected fix for this test
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id FROM fix_proposals 
            WHERE flaky_test_id = %s AND status NOT IN ('rejected', 'applied')
            """,
            (flaky_test_id,),
        )
        if cur.fetchone():
            logger.debug("fix_already_exists", flaky_test_id=flaky_test_id)
            return
    
    # Create pending fix proposal
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO fix_proposals (flaky_test_id, status, root_cause)
            VALUES (%s, 'synthesizing', %s)
            RETURNING id
            """,
            (flaky_test_id, root_cause),
        )
        fix_id = cur.fetchone()[0]
        conn.commit()
    
    try:
        # Fetch source code
        source_code = get_source_code(repo, test_file, root_cause)
        
        # Assemble context
        ctx = assemble_context(
            source_code=source_code,
            test_name=test_name,
            file_path=test_file or "tests/test_file.py",
            root_cause=root_cause,
            log_output=log_output,
            error_message=error_message,
        )
        
        formatted_context = format_context_for_llm(
            ctx=ctx,
            root_cause=root_cause,
            failure_evidence={"log": log_output[:500]},
        )
        
        # Synthesize fix
        fix_result = await synthesize_fix(
            root_cause=root_cause,
            context=formatted_context,
            log_output=log_output,
            error_message=error_message,
            test_name=test_name,
            file_path=test_file or "tests/test_file.py",
        )
        
        patch_diff = fix_result.get("patch_diff", "")
        explanation = fix_result.get("explanation", "")
        confidence = fix_result.get("confidence", 0.5)
        affected_files = fix_result.get("affected_files", [test_file])
        llm_model = fix_result.get("llm_model", "unknown")
        
        # Create PR (mock or real)
        # Get repo details
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT r.full_name, r.default_branch
                FROM flaky_tests ft
                JOIN repositories r ON ft.repo_id = r.id
                WHERE ft.id = %s
                """,
                (flaky_test_id,),
            )
            repo_info = cur.fetchone()
        
        repo_name = repo_info["full_name"] if repo_info else repo
        base_branch = repo_info["default_branch"] if repo_info else "main"
        
        pr_result = await post_fix_proposal(
            repo=repo_name,
            fix_proposal_id=fix_id,
            test_name=test_name,
            root_cause=root_cause,
            patch_diff=patch_diff,
            explanation=explanation,
            confidence=confidence,
            base_branch=base_branch,
        )
        
        # Update fix proposal
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE fix_proposals SET
                    status = 'proposed',
                    patch_diff = %s,
                    explanation = %s,
                    affected_files = %s,
                    confidence = %s,
                    pr_url = %s,
                    pr_number = %s,
                    llm_model = %s,
                    context_used = %s,
                    updated_at = NOW()
                WHERE id = %s
                """,
                (
                    patch_diff,
                    explanation,
                    json.dumps(affected_files),
                    confidence,
                    pr_result.get("pr_url"),
                    pr_result.get("pr_number"),
                    llm_model,
                    formatted_context[:5000],
                    fix_id,
                ),
            )
            conn.commit()
        
        logger.info(
            "fix_synthesized",
            fix_id=fix_id,
            test=test_name,
            cause=root_cause,
            pr_url=pr_result.get("pr_url"),
        )
        
        # Publish real-time event to Redis pub/sub
        event_data = json.dumps({
            "type": "fix_proposed",
            "fix_id": fix_id,
            "test_name": test_name,
            "root_cause": root_cause,
            "pr_url": pr_result.get("pr_url"),
        })
        get_redis().publish("flaky_events", event_data)
        
    except Exception as e:
        logger.error("fix_synthesis_failed", fix_id=fix_id, error=str(e), exc_info=True)
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE fix_proposals SET status = 'pending', updated_at = NOW() WHERE id = %s",
                (fix_id,),
            )
            conn.commit()


def get_redis():
    return redis_lib.from_url(settings.redis_url)


def run_worker():
    """Main fix worker loop."""
    logger.info("fix_worker_starting")
    
    conn = get_db_conn()
    redis_client = get_redis()
    
    logger.info("fix_worker_ready")
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    while True:
        try:
            result = redis_client.brpop(
                "fix_synthesis_queue",
                timeout=settings.fix_worker_poll_interval,
            )
            
            if result:
                _, raw_job = result
                job = json.loads(raw_job)
                logger.info("processing_fix_job", test=job.get("test_name"))
                loop.run_until_complete(process_fix_job(conn, job))
        
        except psycopg2.OperationalError as e:
            logger.error("db_connection_error", error=str(e))
            time.sleep(5)
            try:
                conn = get_db_conn()
            except Exception:
                pass
        except Exception as e:
            logger.error("fix_worker_error", error=str(e), exc_info=True)
            time.sleep(1)


if __name__ == "__main__":
    run_worker()