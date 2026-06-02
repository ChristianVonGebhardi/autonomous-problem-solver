"""Tests for the context assembler."""
import pytest
from app.services.context_assembler import (
    assemble_context,
    extract_imports,
    extract_fixtures,
    find_timing_patterns,
    find_concurrency_patterns,
    find_environment_patterns,
    find_state_leakage_patterns,
    find_shared_state,
    format_context_for_llm,
)

SAMPLE_PYTHON = '''
import time
import threading
import os
import pytest

shared_counter = 0
_lock = threading.Lock()

@pytest.fixture(autouse=True)
def reset_state():
    global shared_counter
    shared_counter = 0
    yield
    shared_counter = 0

class TestConcurrent:
    def test_counter(self):
        global shared_counter
        time.sleep(2)
        with _lock:
            shared_counter += 1
        assert shared_counter == 1

    def test_env(self):
        host = os.environ.get("HOST", "localhost")
        import requests
        response = requests.get(f"http://{host}/api")
        assert response.status_code == 200
'''


def test_extract_imports():
    imports = extract_imports(SAMPLE_PYTHON)
    assert any("import time" in imp for imp in imports)
    assert any("import threading" in imp for imp in imports)
    assert any("import os" in imp for imp in imports)


def test_extract_fixtures():
    fixtures = extract_fixtures(SAMPLE_PYTHON)
    assert len(fixtures) >= 1
    assert any("reset_state" in f for f in fixtures)


def test_find_timing_patterns():
    patterns = find_timing_patterns(SAMPLE_PYTHON)
    assert any("sleep" in p for p in patterns)


def test_find_concurrency_patterns():
    patterns = find_concurrency_patterns(SAMPLE_PYTHON)
    assert any("threading" in p or "lock" in p.lower() for p in patterns)


def test_find_environment_patterns():
    patterns = find_environment_patterns(SAMPLE_PYTHON)
    assert any("environ" in p for p in patterns)


def test_find_state_leakage_patterns():
    patterns = find_state_leakage_patterns(SAMPLE_PYTHON)
    assert any("autouse" in p or "fixture" in p.lower() for p in patterns)


def test_find_shared_state():
    state = find_shared_state(SAMPLE_PYTHON)
    assert any("shared_counter" in s for s in state)


def test_assemble_context_timing():
    ctx = assemble_context(
        source_code=SAMPLE_PYTHON,
        test_name="TestConcurrent::test_counter",
        file_path="tests/test_concurrent.py",
        root_cause="timing",
    )
    assert ctx.file_path == "tests/test_concurrent.py"
    assert ctx.language == "python"
    assert len(ctx.imports) > 0


def test_assemble_context_state_leakage():
    ctx = assemble_context(
        source_code=SAMPLE_PYTHON,
        test_name="TestConcurrent::test_counter",
        file_path="tests/test_concurrent.py",
        root_cause="state_leakage",
    )
    assert len(ctx.fixtures) > 0
    assert len(ctx.shared_state) > 0


def test_format_context_for_llm():
    ctx = assemble_context(
        source_code=SAMPLE_PYTHON,
        test_name="TestConcurrent::test_counter",
        file_path="tests/test_concurrent.py",
        root_cause="timing",
    )
    formatted = format_context_for_llm(
        ctx=ctx,
        root_cause="timing",
        failure_evidence={"log": "TimeoutError: sleep too long"},
    )
    assert "timing" in formatted.lower()
    assert "tests/test_concurrent.py" in formatted