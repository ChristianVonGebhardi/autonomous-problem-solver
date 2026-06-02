"""
Flakiness Detection Worker

Polls Redis queue for new test run events, runs statistical flakiness detection,
triggers root-cause classification, and queues fix synthesis jobs.
"""
import asyncio
import json
import sys
import os
import time

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import psycopg2
import psycopg2.extras
import redis as redis_lib
import structlog

from app.config import settings
from app.services.flakiness_detector import detect_flakiness
from app.services.root_cause_classifier import classify_failure

logger = structlog.get_logger()


def get_db_conn():
    return psycopg2.connect(settings.database_url)


def get_redis():
    return redis_lib.from_url(settings.redis_url)


def get_recent_statuses(conn, repo_id: int, test_name: str, limit: int = 20) -> list:
    """Fetch recent test run statuses for a test."""
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT status, created_at FROM test_runs
            WHERE repo_id = %s AND test_name = %s
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (repo_id, test_name, limit),
        )
        rows = cur.fetchall()
    # Return in chronological order (oldest first for RLE analysis)
    return [row["status"] for row in reversed(rows)]


def upsert_flaky_test(conn, repo_id: int, test_name: str, test_file: str, signal) -> int:
    """Insert or update a flaky test record. Returns the flaky_test_id."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO flaky_tests (repo_id, test_name, test_file, flakiness_score, 
                                    total_runs, failed_runs, pass_rate, last_seen_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (repo_id, test_name) DO UPDATE SET
                flakiness_score = EXCLUDED.flakiness_score,
                total_runs = EXCLUDED.total_runs,
                failed_runs = EXCLUDED.failed_runs,
                pass_rate = EXCLUDED.pass_rate,
                last_seen_at = NOW(),
                is_active = TRUE
            RETURNING id
            """,
            (
                repo_id, test_name, test_file,
                signal.flakiness_score, signal.total_runs,
                signal.failed_runs, signal.pass_rate,
            ),
        )
        result = cur.fetchone()
        conn.commit()
        return result[0]


def save_root_cause_analysis(conn, flaky_test_id: int, classification, run_ids: list):
    """Save root cause analysis results."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO root_cause_analyses 
                (flaky_test_id, primary_cause, confidence, secondary_causes, evidence, classifier_version)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                flaky_test_id,
                classification.primary_cause,
                classification.confidence,
                json.dumps(classification.secondary_causes),
                json.dumps(classification.evidence),
                classification.classifier_version,
            ),
        )
        conn.commit()


def get_failure_logs(conn, repo_id: int, test_name: str, limit: int = 5) -> list:
    """Get recent failure logs for a test."""
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT log_output, error_message, stack_trace
            FROM test_runs
            WHERE repo_id = %s AND test_name = %s AND status != 'passed'
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (repo_id, test_name, limit),
        )
        return cur.fetchall()


def queue_fix_job(redis_client, flaky_test_id: int, test_name: str, 
                  test_file: str, root_cause: str, repo_full_name: str,
                  log_output: str, error_message: str):
    """Queue a fix synthesis job."""
    job = {
        "flaky_test_id": flaky_test_id,
        "test_name": test_name,
        "test_file": test_file,
        "root_cause": root_cause,
        "repo": repo_full_name,
        "log_output": log_output,
        "error_message": error_message,
    }
    redis_client.lpush("fix_synthesis_queue", json.dumps(job))
    logger.info("fix_job_queued", flaky_test_id=flaky_test_id, test=test_name)


def process_test_event(conn, redis_client, event: dict):
    """Process a single test execution event."""
    repo_full_name = event.get("repo")
    test_name = event.get("test_name")
    test_file = event.get("test_file", "")
    
    if not repo_full_name or not test_name:
        logger.warning("invalid_event", event=event)
        return
    
    # Get or create repository
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM repositories WHERE full_name = %s",
            (repo_full_name,),
        )
        row = cur.fetchone()
        if row:
            repo_id = row[0]
        else:
            cur.execute(
                "INSERT INTO repositories (full_name, ci_system) VALUES (%s, %s) RETURNING id",
                (repo_full_name, event.get("ci_system", "unknown")),
            )
            repo_id = cur.fetchone()[0]
            conn.commit()
    
    # Get recent statuses for this test
    statuses = get_recent_statuses(conn, repo_id, test_name)
    
    if len(statuses) < settings.min_runs_for_detection:
        logger.debug(
            "insufficient_runs",
            test=test_name,
            runs=len(statuses),
            min_required=settings.min_runs_for_detection,
        )
        return
    
    # Run flakiness detection
    signal = detect_flakiness(
        statuses=statuses,
        test_name=test_name,
        min_runs=settings.min_runs_for_detection,
        flakiness_threshold=settings.flakiness_threshold,
    )
    
    if not signal.is_flaky:
        logger.debug("test_not_flaky", test=test_name, score=signal.flakiness_score)
        return
    
    logger.info(
        "flaky_test_detected",
        test=test_name,
        score=signal.flakiness_score,
        confidence=signal.confidence,
    )
    
    # Upsert flaky test record
    flaky_test_id = upsert_flaky_test(conn, repo_id, test_name, test_file, signal)
    
    # Get failure logs for classification
    failure_logs = get_failure_logs(conn, repo_id, test_name)
    combined_log = "\n".join(
        f"{row.get('log_output', '')} {row.get('error_message', '')}"
        for row in failure_logs
    )
    latest_error = failure_logs[0].get("error_message", "") if failure_logs else ""
    
    # Run root cause classification
    classification = classify_failure(
        log_output=combined_log,
        error_message=latest_error,
        use_ml=False,  # Use rule-based for speed in worker; ML available as option
    )
    
    logger.info(
        "root_cause_classified",
        test=test_name,
        cause=classification.primary_cause,
        confidence=classification.confidence,
    )
    
    # Save analysis
    save_root_cause_analysis(conn, flaky_test_id, classification, [])
    
    # Update last_analyzed_at
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE flaky_tests SET last_analyzed_at = NOW() WHERE id = %s",
            (flaky_test_id,),
        )
        conn.commit()
    
    # Queue fix synthesis if confidence is high enough
    if classification.confidence >= settings.confidence_threshold:
        queue_fix_job(
            redis_client=redis_client,
            flaky_test_id=flaky_test_id,
            test_name=test_name,
            test_file=test_file,
            root_cause=classification.primary_cause,
            repo_full_name=repo_full_name,
            log_output=combined_log[:2000],
            error_message=latest_error[:500],
        )


def run_worker():
    """Main worker loop."""
    logger.info("flakiness_worker_starting")
    
    conn = get_db_conn()
    redis_client = get_redis()
    
    logger.info("flakiness_worker_ready", 
                poll_interval=settings.worker_poll_interval)
    
    while True:
        try:
            # Poll Redis queue for test events
            result = redis_client.brpop("test_events_queue", timeout=settings.worker_poll_interval)
            
            if result:
                _, raw_event = result
                event = json.loads(raw_event)
                logger.debug("processing_event", test=event.get("test_name"))
                process_test_event(conn, redis_client, event)
            
        except psycopg2.OperationalError as e:
            logger.error("db_connection_error", error=str(e))
            time.sleep(5)
            try:
                conn = get_db_conn()
            except Exception:
                pass
        except Exception as e:
            logger.error("worker_error", error=str(e), exc_info=True)
            time.sleep(1)


if __name__ == "__main__":
    run_worker()