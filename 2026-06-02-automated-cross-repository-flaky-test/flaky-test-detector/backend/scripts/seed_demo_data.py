#!/usr/bin/env python3
"""
Seed the database with realistic demo data for the dashboard.

Simulates:
- 3 repositories
- ~15 tests with varying flakiness patterns
- Historical run data spanning 30 days
- Root cause analyses
- Fix proposals (some with feedback)
"""
import sys
import os
import json
import random
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2
import psycopg2.extras

from app.config import settings
from app.services.flakiness_detector import detect_flakiness
from app.services.root_cause_classifier import classify_failure

random.seed(42)

REPOS = [
    {"full_name": "acme/backend-api", "ci_system": "github_actions", "default_branch": "main"},
    {"full_name": "acme/frontend-web", "ci_system": "github_actions", "default_branch": "main"},
    {"full_name": "acme/data-pipeline", "ci_system": "gitlab_ci", "default_branch": "main"},
]

FLAKY_TESTS = [
    # backend-api
    {
        "repo": "acme/backend-api",
        "test_name": "tests/test_auth.py::TestAuth::test_user_login_concurrent",
        "test_file": "tests/test_auth.py",
        "flakiness_pattern": "intermittent",  # ~40% fail rate
        "root_cause_logs": [
            "ThreadSanitizer: data race on shared session counter",
            "concurrent access: multiple threads writing to session_store",
        ],
    },
    {
        "repo": "acme/backend-api",
        "test_name": "tests/test_payments.py::TestPayments::test_webhook_processing",
        "test_file": "tests/test_payments.py",
        "flakiness_pattern": "timing",
        "root_cause_logs": [
            "TimeoutError: Expected webhook callback within 2000ms but timed out",
            "Webhook delivery took 3200ms, exceeded timeout of 2000ms",
        ],
    },
    {
        "repo": "acme/backend-api",
        "test_name": "tests/test_database.py::TestDB::test_unique_constraint",
        "test_file": "tests/test_database.py",
        "flakiness_pattern": "mostly_pass",
        "root_cause_logs": [
            "IntegrityError: duplicate key value violates unique constraint 'users_email_key'",
            "psycopg2.errors.UniqueViolation: already exists",
        ],
    },
    {
        "repo": "acme/backend-api",
        "test_name": "tests/test_cache.py::TestCache::test_redis_connection",
        "test_file": "tests/test_cache.py",
        "flakiness_pattern": "environment",
        "root_cause_logs": [
            "ConnectionRefusedError: [Errno 111] Connection refused to redis:6379",
            "redis.exceptions.ConnectionError: Error connecting to redis:6379",
        ],
    },
    {
        "repo": "acme/backend-api",
        "test_name": "tests/test_api.py::TestAPI::test_rate_limiting",
        "test_file": "tests/test_api.py",
        "flakiness_pattern": "intermittent",
        "root_cause_logs": [
            "AssertionError: Expected 429 but got 200 - rate limit window reset between tests",
            "test_order dependency: rate limit state not reset between test runs",
        ],
    },
    # frontend-web
    {
        "repo": "acme/frontend-web",
        "test_name": "tests/e2e/test_checkout.py::TestCheckout::test_payment_form",
        "test_file": "tests/e2e/test_checkout.py",
        "flakiness_pattern": "timing",
        "root_cause_logs": [
            "TimeoutException: Message: element not interactable: Element is not currently visible within 2000ms",
            "StaleElementReferenceException: element is not attached to the page document",
        ],
    },
    {
        "repo": "acme/frontend-web",
        "test_name": "tests/e2e/test_login.py::TestLogin::test_oauth_flow",
        "test_file": "tests/e2e/test_login.py",
        "flakiness_pattern": "environment",
        "root_cause_logs": [
            "ConnectionError: Failed to connect to oauth.provider.example.com:443",
            "SSL handshake timeout: certificate verification failed",
        ],
    },
    {
        "repo": "acme/frontend-web",
        "test_name": "tests/unit/test_store.py::TestStore::test_cart_state",
        "test_file": "tests/unit/test_store.py",
        "flakiness_pattern": "mostly_pass",
        "root_cause_logs": [
            "AssertionError: Cart has 3 items, expected 1. Previous test left items in global store.",
            "global state leakage: store not reset between test modules",
        ],
    },
    {
        "repo": "acme/frontend-web",
        "test_name": "tests/e2e/test_search.py::TestSearch::test_autocomplete_timing",
        "test_file": "tests/e2e/test_search.py",
        "flakiness_pattern": "timing",
        "root_cause_logs": [
            "Element 'autocomplete-dropdown' not visible within 1500ms",
            "Expected dropdown to appear but timeout elapsed: response took 2100ms",
        ],
    },
    # data-pipeline
    {
        "repo": "acme/data-pipeline",
        "test_name": "tests/test_ingestion.py::TestIngestion::test_kafka_consumer",
        "test_file": "tests/test_ingestion.py",
        "flakiness_pattern": "environment",
        "root_cause_logs": [
            "NoBrokersAvailable: Unable to connect to kafka broker localhost:9092",
            "kafka.errors.NoBrokersAvailable: NoBrokersAvailable",
        ],
    },
    {
        "repo": "acme/data-pipeline",
        "test_name": "tests/test_transform.py::TestTransform::test_parallel_processing",
        "test_file": "tests/test_transform.py",
        "flakiness_pattern": "intermittent",
        "root_cause_logs": [
            "Race condition: parallel workers writing to same output partition",
            "concurrent modification of shared results dict across worker threads",
        ],
    },
    {
        "repo": "acme/data-pipeline",
        "test_name": "tests/test_db_write.py::TestDBWrite::test_bulk_insert",
        "test_file": "tests/test_db_write.py",
        "flakiness_pattern": "mostly_pass",
        "root_cause_logs": [
            "psycopg2.InterfaceError: connection already closed",
            "database connection dropped mid-transaction, data from previous test not cleaned up",
        ],
    },
    {
        "repo": "acme/data-pipeline",
        "test_name": "tests/test_scheduler.py::TestScheduler::test_job_timing",
        "test_file": "tests/test_scheduler.py",
        "flakiness_pattern": "timing",
        "root_cause_logs": [
            "AssertionError: Job ran at 10:00:03.450 but expected at 10:00:03.000 (±200ms)",
            "scheduler timing drift: sleep(1) actual duration was 1.6s under CI load",
        ],
    },
    {
        "repo": "acme/data-pipeline",
        "test_name": "tests/test_cleanup.py::TestCleanup::test_temp_file_removal",
        "test_file": "tests/test_cleanup.py",
        "flakiness_pattern": "environment",
        "root_cause_logs": [
            "FileNotFoundError: /tmp/pipeline_output_abc123.parquet: No such file or directory",
            "ENOENT: temp directory not available in CI container",
        ],
    },
    {
        "repo": "acme/data-pipeline",
        "test_name": "tests/test_state.py::TestState::test_checkpoint_recovery",
        "test_file": "tests/test_state.py",
        "flakiness_pattern": "intermittent",
        "root_cause_logs": [
            "AssertionError: Checkpoint state mismatch - previous test modified global checkpoint store",
            "transaction not rolled back: uncommitted changes visible to next test",
        ],
    },
]


def generate_statuses(pattern: str, n: int = 25) -> list:
    """Generate a realistic status sequence for different flakiness patterns."""
    if pattern == "intermittent":
        # ~40% fail rate with some clustering
        statuses = []
        for _ in range(n):
            r = random.random()
            if r < 0.38:
                statuses.append("failed")
            elif r < 0.42:
                statuses.append("error")
            else:
                statuses.append("passed")
        return statuses
    elif pattern == "timing":
        # ~25% fail rate, tends to cluster during "busy" periods
        statuses = []
        i = 0
        while i < n:
            if random.random() < 0.25:
                # Cluster of failures
                burst = random.randint(1, 3)
                for _ in range(burst):
                    if i < n:
                        statuses.append("failed")
                        i += 1
            else:
                statuses.append("passed")
                i += 1
        return statuses[:n]
    elif pattern == "mostly_pass":
        # ~15% fail, happens rarely but is very flaky when it does
        statuses = []
        for _ in range(n):
            if random.random() < 0.15:
                statuses.append("failed")
            else:
                statuses.append("passed")
        return statuses
    elif pattern == "environment":
        # ~30% fail rate, more random
        return [
            "failed" if random.random() < 0.30 else "passed"
            for _ in range(n)
        ]
    else:
        return ["passed"] * n


def generate_run_timestamps(n: int, days_back: int = 30) -> list:
    """Generate n timestamps spread over the last `days_back` days."""
    now = datetime.now(timezone.utc)
    timestamps = []
    for i in range(n):
        offset_days = random.uniform(0, days_back)
        ts = now - timedelta(days=offset_days)
        timestamps.append(ts)
    return sorted(timestamps)


FIX_PROPOSALS = {
    "timing": {
        "patch_diff": """--- a/tests/test_payments.py
+++ b/tests/test_payments.py
@@ -5,8 +5,16 @@ import time
+from functools import wraps
+import time as _time
+
+def wait_for_condition(cond, timeout=10.0, interval=0.2):
+    deadline = _time.monotonic() + timeout
+    while _time.monotonic() < deadline:
+        if cond(): return True
+        _time.sleep(interval)
+    raise TimeoutError(f"Condition not met within {timeout}s")
+
 class TestPayments:
-    def test_webhook_processing(self):
-        trigger_webhook()
-        time.sleep(2)
-        assert webhook_received()
+    def test_webhook_processing(self):
+        trigger_webhook()
+        wait_for_condition(webhook_received, timeout=10.0)
+        assert webhook_received()""",
        "explanation": "Replace hardcoded sleep with polling wait to handle variable CI latency.",
        "confidence": 0.84,
    },
    "concurrency": {
        "patch_diff": """--- a/tests/test_auth.py
+++ b/tests/test_auth.py
@@ -1,6 +1,8 @@
+import threading
+_lock = threading.Lock()
+_session_counter = 0
 class TestAuth:
-    session_counter = 0
-    def increment_session(self):
-        self.session_counter += 1
+    def increment_session(self):
+        global _session_counter
+        with _lock:
+            _session_counter += 1""",
        "explanation": "Protect shared counter with threading.Lock() to eliminate data race.",
        "confidence": 0.79,
    },
    "state_leakage": {
        "patch_diff": """--- a/tests/test_database.py
+++ b/tests/test_database.py
@@ -1,4 +1,10 @@
+import pytest
+
+@pytest.fixture(autouse=True)
+def clean_db(db_session):
+    yield
+    db_session.rollback()
+    db_session.expunge_all()
+
 class TestDB:
     def test_unique_constraint(self, db_session):""",
        "explanation": "Add autouse fixture to roll back DB transactions after each test.",
        "confidence": 0.87,
    },
    "environment": {
        "patch_diff": """--- a/tests/test_cache.py
+++ b/tests/test_cache.py
@@ -1,6 +1,10 @@
+from unittest.mock import patch, MagicMock
+
 class TestCache:
-    def test_redis_connection(self):
-        client = redis.Redis(host='redis', port=6379)
-        assert client.ping()
+    @patch('redis.Redis')
+    def test_redis_connection(self, mock_redis):
+        mock_redis.return_value.ping.return_value = True
+        client = redis.Redis(host='redis', port=6379)
+        assert client.ping()""",
        "explanation": "Mock Redis client to avoid environment dependency in unit tests.",
        "confidence": 0.88,
    },
    "unknown": {
        "patch_diff": """--- a/tests/test_api.py
+++ b/tests/test_api.py
@@ -1,4 +1,6 @@
+import pytest
+
 class TestAPI:
+    @pytest.mark.flaky(reruns=3, reruns_delay=1)
     def test_rate_limiting(self):""",
        "explanation": "Added retry as temporary mitigation; root cause under investigation.",
        "confidence": 0.45,
    },
}


def seed():
    conn = psycopg2.connect(settings.database_url)
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    print("🌱 Seeding demo data...")

    # Insert repositories
    repo_id_map = {}
    for repo_data in REPOS:
        cur.execute(
            """
            INSERT INTO repositories (full_name, ci_system, default_branch)
            VALUES (%s, %s, %s)
            ON CONFLICT (full_name) DO UPDATE SET ci_system = EXCLUDED.ci_system
            RETURNING id
            """,
            (repo_data["full_name"], repo_data["ci_system"], repo_data["default_branch"]),
        )
        repo_id = cur.fetchone()["id"]
        repo_id_map[repo_data["full_name"]] = repo_id
        print(f"  ✓ Repository: {repo_data['full_name']} (id={repo_id})")

    conn.commit()

    # Insert test runs and detect flakiness
    for test_def in FLAKY_TESTS:
        repo_id = repo_id_map[test_def["repo"]]
        test_name = test_def["test_name"]
        test_file = test_def["test_file"]
        pattern = test_def["flakiness_pattern"]
        logs = test_def["root_cause_logs"]

        # Generate 20-30 historical runs
        n_runs = random.randint(20, 30)
        statuses = generate_statuses(pattern, n_runs)
        timestamps = generate_run_timestamps(n_runs)

        run_ids = []
        for ts, status in zip(timestamps, statuses):
            log = random.choice(logs) if status != "passed" else "All assertions passed."
            err = log if status != "passed" else None
            dur = random.randint(500, 5000)

            cur.execute(
                """
                INSERT INTO test_runs (
                    repo_id, test_name, test_file, branch, commit_sha,
                    pipeline_id, status, duration_ms, log_output, error_message,
                    ci_system, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    repo_id, test_name, test_file,
                    "main",
                    f"sha{random.randint(100000, 999999)}",
                    f"pipeline-{random.randint(1000, 9999)}",
                    status, dur, log, err,
                    REPOS[0]["ci_system"],  # simplified
                    ts,
                ),
            )
            run_ids.append(cur.fetchone()["id"])

        conn.commit()

        # Detect flakiness
        signal = detect_flakiness(statuses, test_name)
        if not signal.is_flaky:
            print(f"  - {test_name.split('::')[-1]}: not detected as flaky (score={signal.flakiness_score:.2f})")
            continue

        # Upsert flaky test
        failure_ts = [ts for ts, s in zip(timestamps, statuses) if s != "passed"]
        last_seen = max(failure_ts) if failure_ts else timestamps[-1]

        cur.execute(
            """
            INSERT INTO flaky_tests (
                repo_id, test_name, test_file, flakiness_score, total_runs,
                failed_runs, pass_rate, is_active, first_detected_at, last_seen_at, last_analyzed_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, TRUE, %s, %s, NOW())
            ON CONFLICT (repo_id, test_name) DO UPDATE SET
                flakiness_score = EXCLUDED.flakiness_score,
                total_runs = EXCLUDED.total_runs,
                failed_runs = EXCLUDED.failed_runs,
                pass_rate = EXCLUDED.pass_rate,
                last_seen_at = EXCLUDED.last_seen_at
            RETURNING id
            """,
            (
                repo_id, test_name, test_file,
                signal.flakiness_score, signal.total_runs,
                signal.failed_runs, signal.pass_rate,
                timestamps[0], last_seen,
            ),
        )
        flaky_test_id = cur.fetchone()["id"]
        conn.commit()

        # Classify root cause
        combined_log = "\n".join(logs)
        classification = classify_failure(
            log_output=combined_log,
            error_message=logs[0],
            use_ml=False,
        )

        cur.execute(
            """
            INSERT INTO root_cause_analyses (
                flaky_test_id, primary_cause, confidence,
                secondary_causes, evidence, classifier_version
            ) VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                flaky_test_id, classification.primary_cause, classification.confidence,
                json.dumps(classification.secondary_causes),
                json.dumps(classification.evidence),
                classification.classifier_version,
            ),
        )
        conn.commit()

        # Create fix proposal
        cause = classification.primary_cause
        fix_template = FIX_PROPOSALS.get(cause, FIX_PROPOSALS["unknown"])

        feedback_options = [None, None, True, True, True, False]  # mostly accepted, some rejected
        feedback = random.choice(feedback_options)

        status_val = "proposed"
        if feedback is True:
            status_val = "accepted"
        elif feedback is False:
            status_val = "rejected"

        pr_num = random.randint(100, 500)
        repo_name = test_def["repo"]

        cur.execute(
            """
            INSERT INTO fix_proposals (
                flaky_test_id, status, root_cause, patch_diff, explanation,
                affected_files, confidence, pr_url, pr_number,
                feedback_accepted, llm_model, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
            """,
            (
                flaky_test_id, status_val, cause,
                fix_template["patch_diff"], fix_template["explanation"],
                json.dumps([test_file]),
                fix_template["confidence"],
                f"https://github.com/{repo_name}/pull/{pr_num}",
                pr_num,
                feedback,
                "mock" if random.random() < 0.7 else "gpt-4o",
            ),
        )
        conn.commit()

        print(
            f"  ✓ Flaky: {test_name.split('::')[-1]} "
            f"(score={signal.flakiness_score:.2f}, cause={classification.primary_cause}, "
            f"pr=#{pr_num})"
        )

    cur.close()
    conn.close()
    print("\n✅ Demo data seeded successfully!")


if __name__ == "__main__":
    seed()