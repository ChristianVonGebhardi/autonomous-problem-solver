"""
Fix Synthesizer — generates targeted code-level fix proposals using GPT-4o (or mock).

Implements the FlakyGuard-inspired approach:
1. Assemble scoped context based on root cause
2. Construct a targeted prompt with fix templates per cause category
3. Call LLM with structured output request
4. Parse and validate the returned patch diff
"""
import json
import re
from typing import Optional, Dict, Any
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings

logger = structlog.get_logger()


# Fix templates per root cause — seed the LLM with known good patterns
FIX_TEMPLATES = {
    "timing": """
Common fixes for timing-related flakiness:
1. Replace hardcoded sleeps with explicit waits/polling:
   - `time.sleep(2)` → `wait_for_condition(lambda: check(), timeout=10, poll_interval=0.5)`
2. Increase timeout values with configurable defaults
3. Add retry decorators for transient failures
4. Use `async`/`await` properly instead of blocking calls
5. For Selenium: use `WebDriverWait` with `expected_conditions`
""",
    "concurrency": """
Common fixes for concurrency-related flakiness:
1. Add proper locking around shared state: `threading.Lock()`, `asyncio.Lock()`
2. Use thread-safe data structures: `queue.Queue`, `collections.deque`
3. Avoid sharing mutable state between test threads
4. Use `asyncio.gather()` with proper error handling
5. Replace global variables with thread-local storage
""",
    "environment": """
Common fixes for environment-related flakiness:
1. Mock external service calls in tests
2. Add `@pytest.mark.skipif` for environment-specific tests
3. Use environment variable defaults: `os.getenv('HOST', 'localhost')`
4. Add retry logic for network calls with exponential backoff
5. Use `docker-compose` or testcontainers for service dependencies
""",
    "state_leakage": """
Common fixes for state leakage:
1. Use database transactions that roll back after each test
2. Reset mock objects in teardown: `mock.reset_mock()`  
3. Use pytest fixtures with proper scope: `@pytest.fixture(autouse=True)`
4. Clear module-level state in `setUp`/`tearDown`
5. Use `monkeypatch` for temporary state changes
""",
}

SYSTEM_PROMPT = """You are an expert software engineer specializing in fixing flaky tests.
Your task is to analyze a failing test and propose a specific, minimal code fix.

Rules:
- Propose the smallest change that addresses the root cause
- Provide a unified diff format patch
- Explain WHY this fix addresses the flakiness
- Do not change test logic or assertions — only fix the flakiness mechanism
- Output valid JSON with keys: patch_diff, explanation, affected_files, confidence
"""


def build_fix_prompt(
    root_cause: str,
    context: str,
    log_output: str,
    error_message: str,
    test_name: str,
) -> str:
    template = FIX_TEMPLATES.get(root_cause, "")
    
    return f"""Analyze this flaky test and propose a fix.

Root cause category: {root_cause}

{template}

## Test Information
Test: {test_name}
Error: {error_message[:500] if error_message else 'N/A'}

## Log Output (last 500 chars)
```
{log_output[-500:] if log_output else 'N/A'}
```

## Code Context
{context}

## Task
Provide a fix as JSON with this exact structure:
{{
  "patch_diff": "--- a/tests/test_file.py\\n+++ b/tests/test_file.py\\n@@ ... @@\\n...",
  "explanation": "Explanation of what causes flakiness and how the fix addresses it",
  "affected_files": ["tests/test_file.py"],
  "confidence": 0.75
}}

The patch_diff should be a valid unified diff. If you cannot determine the exact patch without more context, provide a pseudocode diff with explanatory comments.
"""


async def synthesize_fix_openai(
    root_cause: str,
    context: str,
    log_output: str,
    error_message: str,
    test_name: str,
    file_path: str,
) -> Dict[str, Any]:
    """Call OpenAI GPT-4o to synthesize a fix."""
    from openai import AsyncOpenAI
    
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    
    prompt = build_fix_prompt(root_cause, context, log_output, error_message, test_name)
    
    response = await client.chat.completions.create(
        model=settings.llm_model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        max_tokens=settings.llm_max_tokens,
        temperature=0.1,  # Low temperature for deterministic code fixes
        response_format={"type": "json_object"},
    )
    
    content = response.choices[0].message.content
    result = json.loads(content)
    result["llm_model"] = settings.llm_model
    return result


def synthesize_fix_mock(
    root_cause: str,
    test_name: str,
    file_path: str,
    log_output: str = "",
    error_message: str = "",
) -> Dict[str, Any]:
    """
    Mock fix synthesizer for development/testing without OpenAI API key.
    Returns realistic-looking but template-based fixes.
    """
    mock_fixes = {
        "timing": {
            "patch_diff": f"""--- a/{file_path}
+++ b/{file_path}
@@ -1,5 +1,8 @@
+import time
+from typing import Callable
+
+def wait_for_condition(condition: Callable, timeout: float = 10.0, poll_interval: float = 0.5) -> bool:
+    \"\"\"Wait for a condition to become true, polling at intervals.\"\"\"
+    deadline = time.monotonic() + timeout
+    while time.monotonic() < deadline:
+        if condition():
+            return True
+        time.sleep(poll_interval)
+    raise TimeoutError(f"Condition not met within {{timeout}}s")
+
 class TestCase:
-    def {test_name.split("::")[-1]}(self):
-        time.sleep(2)  # Wait for element
-        assert element.is_visible()
+    def {test_name.split("::")[-1]}(self):
+        # Replace fixed sleep with explicit wait
+        wait_for_condition(lambda: element.is_visible(), timeout=10.0)
+        assert element.is_visible()
""",
            "explanation": (
                f"The test '{test_name}' fails intermittently due to a race condition between "
                "the test assertion and the application's async operations. The hardcoded "
                "`time.sleep()` is insufficient when the system is under load. "
                "Fix: Replace with `wait_for_condition()` that polls until the condition is met "
                "or a configurable timeout expires. This adapts to system load rather than "
                "assuming a fixed response time."
            ),
            "affected_files": [file_path],
            "confidence": 0.82,
        },
        "concurrency": {
            "patch_diff": f"""--- a/{file_path}
+++ b/{file_path}
@@ -1,10 +1,15 @@
+import threading
+
+_shared_state_lock = threading.Lock()
+_shared_counter = 0
+
 class TestCase:
-    shared_counter = 0  # BUG: Not thread-safe!
-    
-    def increment(self):
-        self.shared_counter += 1
+    def increment(self):
+        global _shared_counter
+        with _shared_state_lock:
+            _shared_counter += 1
     
-    def {test_name.split("::")[-1]}(self):
-        threads = [threading.Thread(target=self.increment) for _ in range(10)]
+    def {test_name.split("::")[-1]}(self):
+        global _shared_counter
+        _shared_counter = 0  # Reset before test
+        threads = [threading.Thread(target=self.increment) for _ in range(10)]
         [t.start() for t in threads]
         [t.join() for t in threads]
-        assert self.shared_counter == 10
+        assert _shared_counter == 10
""",
            "explanation": (
                f"The test '{test_name}' has a data race on shared mutable state accessed "
                "by multiple threads simultaneously. The class variable `shared_counter` is "
                "read-modify-written without synchronization, causing lost updates. "
                "Fix: Protect all accesses with a `threading.Lock()` and reset state before "
                "each test run to prevent leakage from parallel test workers."
            ),
            "affected_files": [file_path],
            "confidence": 0.78,
        },
        "environment": {
            "patch_diff": f"""--- a/{file_path}
+++ b/{file_path}
@@ -1,12 +1,20 @@
+import os
+from unittest.mock import patch, MagicMock
+
 class TestCase:
-    def {test_name.split("::")[-1]}(self):
-        response = requests.get("http://external-service/api/data")
-        assert response.status_code == 200
+    @patch('requests.get')
+    def {test_name.split("::")[-1]}(self, mock_get):
+        # Mock external service to avoid environment dependency
+        mock_response = MagicMock()
+        mock_response.status_code = 200
+        mock_response.json.return_value = {{"data": "test_value"}}
+        mock_get.return_value = mock_response
+        
+        response = requests.get("http://external-service/api/data")
+        assert response.status_code == 200
+        mock_get.assert_called_once_with("http://external-service/api/data")
""",
            "explanation": (
                f"The test '{test_name}' makes real HTTP calls to an external service, "
                "causing failures when: the service is down, rate limits are hit, "
                "network is unavailable in CI, or response times are slow. "
                "Fix: Mock the external HTTP call using `unittest.mock.patch`. "
                "This makes the test deterministic and independent of external systems."
            ),
            "affected_files": [file_path],
            "confidence": 0.88,
        },
        "state_leakage": {
            "patch_diff": f"""--- a/{file_path}
+++ b/{file_path}
@@ -1,15 +1,25 @@
+import pytest
+
+@pytest.fixture(autouse=True)
+def reset_database_state(db_session):
+    \"\"\"Ensure each test starts with a clean database state.\"\"\"
+    yield  # Run the test
+    db_session.rollback()  # Roll back any changes
+    # Clear any cached state
+    db_session.expunge_all()
+
 class TestCase:
-    def setUp(self):
-        # BUG: Missing cleanup of previous test's data
-        self.user = User.create(name="test_user")
-    
-    def {test_name.split("::")[-1]}(self):
-        users = User.query.all()
-        assert len(users) == 1  # Fails if previous test left data!
+    def {test_name.split("::")[-1]}(self, db_session):
+        # Create test data within transaction scope
+        user = User(name="test_user")
+        db_session.add(user)
+        db_session.flush()
+        
+        users = db_session.query(User).all()
+        assert len(users) == 1  # Safe: transaction will roll back after test
""",
            "explanation": (
                f"The test '{test_name}' fails intermittently because database records "
                "created in previous tests are not cleaned up, causing the assertion "
                "`len(users) == 1` to fail when run after another test that creates users. "
                "Fix: Add an `autouse` pytest fixture that wraps each test in a database "
                "transaction and rolls it back afterward, ensuring test isolation."
            ),
            "affected_files": [file_path],
            "confidence": 0.85,
        },
        "unknown": {
            "patch_diff": f"""--- a/{file_path}
+++ b/{file_path}
@@ -1,8 +1,15 @@
+import pytest
+
 class TestCase:
-    def {test_name.split("::")[-1]}(self):
-        result = flaky_operation()
-        assert result == expected_value
+    @pytest.mark.flaky(reruns=3, reruns_delay=1)
+    def {test_name.split("::")[-1]}(self):
+        \"\"\"
+        NOTE: This test has been marked as intermittently failing.
+        Root cause is under investigation. Added retry decorator as temporary mitigation.
+        TODO: Investigate and fix the underlying cause.
+        \"\"\"
+        result = flaky_operation()
+        assert result == expected_value
""",
            "explanation": (
                f"The test '{test_name}' shows intermittent failures but the specific "
                "root cause could not be confidently determined from the available logs. "
                "Applied a temporary mitigation using `pytest-rerunfailures` to add "
                "controlled retries. Further investigation recommended: check for "
                "timing dependencies, shared state, or external service calls."
            ),
            "affected_files": [file_path],
            "confidence": 0.45,
        },
    }
    
    fix = mock_fixes.get(root_cause, mock_fixes["unknown"])
    fix["llm_model"] = "mock"
    return fix


async def synthesize_fix(
    root_cause: str,
    context: str,
    log_output: str,
    error_message: str,
    test_name: str,
    file_path: str,
) -> Dict[str, Any]:
    """
    Main fix synthesis entry point. Uses OpenAI if configured, otherwise mock.
    """
    if settings.mock_llm or not settings.openai_api_key:
        logger.info("using_mock_fix_synthesizer", test=test_name, cause=root_cause)
        return synthesize_fix_mock(
            root_cause=root_cause,
            test_name=test_name,
            file_path=file_path or "tests/test_file.py",
            log_output=log_output,
            error_message=error_message,
        )
    
    try:
        logger.info("calling_openai_fix_synthesizer", test=test_name, model=settings.llm_model)
        return await synthesize_fix_openai(
            root_cause=root_cause,
            context=context,
            log_output=log_output,
            error_message=error_message,
            test_name=test_name,
            file_path=file_path,
        )
    except Exception as e:
        logger.error("openai_synthesis_failed", error=str(e), fallback="mock")
        return synthesize_fix_mock(
            root_cause=root_cause,
            test_name=test_name,
            file_path=file_path or "tests/test_file.py",
            log_output=log_output,
            error_message=error_message,
        )