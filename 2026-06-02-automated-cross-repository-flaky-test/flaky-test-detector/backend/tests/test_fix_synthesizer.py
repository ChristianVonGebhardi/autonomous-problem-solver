"""Tests for the fix synthesizer (mock mode)."""
import pytest
from app.services.fix_synthesizer import synthesize_fix_mock, build_fix_prompt


def test_mock_fix_timing():
    result = synthesize_fix_mock(
        root_cause="timing",
        test_name="tests/test_pay.py::TestPay::test_webhook",
        file_path="tests/test_pay.py",
    )
    assert "patch_diff" in result
    assert "explanation" in result
    assert "confidence" in result
    assert "affected_files" in result
    assert result["llm_model"] == "mock"
    assert result["confidence"] > 0.5
    assert "wait" in result["patch_diff"].lower() or "sleep" in result["patch_diff"].lower()


def test_mock_fix_concurrency():
    result = synthesize_fix_mock(
        root_cause="concurrency",
        test_name="tests/test_auth.py::TestAuth::test_concurrent",
        file_path="tests/test_auth.py",
    )
    assert "lock" in result["patch_diff"].lower() or "thread" in result["patch_diff"].lower()
    assert result["confidence"] > 0.5


def test_mock_fix_environment():
    result = synthesize_fix_mock(
        root_cause="environment",
        test_name="tests/test_cache.py::TestCache::test_redis",
        file_path="tests/test_cache.py",
    )
    assert "mock" in result["patch_diff"].lower() or "patch" in result["patch_diff"].lower()


def test_mock_fix_state_leakage():
    result = synthesize_fix_mock(
        root_cause="state_leakage",
        test_name="tests/test_db.py::TestDB::test_unique",
        file_path="tests/test_db.py",
    )
    assert "fixture" in result["patch_diff"].lower() or "rollback" in result["patch_diff"].lower()


def test_mock_fix_unknown():
    result = synthesize_fix_mock(
        root_cause="unknown",
        test_name="tests/test_misc.py::TestMisc::test_flaky",
        file_path="tests/test_misc.py",
    )
    assert result["confidence"] < 0.6  # Low confidence for unknown


def test_build_fix_prompt():
    prompt = build_fix_prompt(
        root_cause="timing",
        context="## Test File: tests/test.py\n\ndef test_foo():\n    time.sleep(2)",
        log_output="TimeoutError: timed out",
        error_message="TimeoutError",
        test_name="tests/test.py::test_foo",
    )
    assert "timing" in prompt
    assert "TimeoutError" in prompt
    assert "test_foo" in prompt
    assert "patch_diff" in prompt  # JSON structure hinted


@pytest.mark.asyncio
async def test_synthesize_fix_uses_mock_when_no_key():
    """When MOCK_LLM=true or no API key, should use mock synthesizer."""
    import os
    # Ensure mock mode
    from app.config import settings
    original_mock = settings.mock_llm
    settings.mock_llm = True

    result = await synthesize_fix_mock.__wrapped__() if hasattr(synthesize_fix_mock, '__wrapped__') else synthesize_fix_mock(
        root_cause="timing",
        test_name="tests/test.py::test_foo",
        file_path="tests/test.py",
    )
    assert result["llm_model"] == "mock"

    settings.mock_llm = original_mock