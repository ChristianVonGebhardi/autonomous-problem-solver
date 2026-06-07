"""Tests for the BehaviorTrace SDK."""

from __future__ import annotations

import json
import time
import uuid

import pytest
import respx
import httpx

from sdk.behavior_trace import BehaviorTracer, RunSpan, StepSpan


class TestStepSpan:
    def test_set_output_string(self):
        step = StepSpan(step_index=0, tool_name="search", run_id="r1", workflow_id="w1")
        step.set_output("found something")
        assert step.output_text == "found something"

    def test_set_output_dict(self):
        step = StepSpan(step_index=0, tool_name="search", run_id="r1", workflow_id="w1")
        step.set_output({"key": "value"})
        assert step.output_text == '{"key": "value"}'

    def test_set_confidence(self):
        step = StepSpan(step_index=0, tool_name="search", run_id="r1", workflow_id="w1")
        step.set_confidence(0.92)
        assert step.confidence == 0.92

    def test_add_retrieved_chunk_hashes(self):
        step = StepSpan(step_index=0, tool_name="search", run_id="r1", workflow_id="w1")
        step.add_retrieved_chunk("sensitive document content")
        assert len(step.retrieved_chunks) == 1
        # Should be a hash, not raw content
        assert "sensitive" not in step.retrieved_chunks[0]

    def test_finalize_sets_end_time(self):
        step = StepSpan(step_index=0, tool_name="search", run_id="r1", workflow_id="w1")
        t0 = time.time()
        step._finalize()
        assert step.end_time is not None
        assert step.end_time >= t0

    def test_to_dict_shape(self):
        step = StepSpan(step_index=1, tool_name="classify", run_id="r1", workflow_id="w1")
        step.set_output("classified")
        step.set_confidence(0.88)
        step._finalize()
        d = step.to_dict()
        assert d["step_index"] == 1
        assert d["tool_name"] == "classify"
        assert d["output_text"] == "classified"
        assert d["confidence"] == 0.88
        assert d["duration_ms"] is not None


class TestRunSpan:
    def test_trace_step_context_manager(self):
        run = RunSpan(workflow_id="w1")
        with run.trace_step(step_index=0, tool_name="search") as step:
            step.set_output("result")
        assert len(run.steps) == 1
        assert run.steps[0].tool_name == "search"
        assert run.steps[0].end_time is not None

    def test_step_error_captured(self):
        run = RunSpan(workflow_id="w1")
        with pytest.raises(ValueError):
            with run.trace_step(step_index=0, tool_name="search") as step:
                raise ValueError("tool failed")
        assert run.steps[0].error == "tool failed"

    def test_multiple_steps(self):
        run = RunSpan(workflow_id="w1")
        for i, tool in enumerate(["search", "retrieve", "respond"]):
            with run.trace_step(step_index=i, tool_name=tool) as step:
                step.set_output(f"output {i}")
        assert len(run.steps) == 3

    def test_to_dict_includes_tool_sequence(self):
        run = RunSpan(workflow_id="w1")
        with run.trace_step(0, "search"):
            pass
        with run.trace_step(1, "respond"):
            pass
        run._finalize()
        d = run.to_dict()
        assert d["tool_sequence"] == ["search", "respond"]
        assert d["step_count"] == 2


class TestBehaviorTracer:
    @respx.mock
    def test_trace_emitted_on_completion(self):
        route = respx.post("http://localhost:8000/api/v1/traces").mock(
            return_value=httpx.Response(202, json={"status": "accepted", "run_id": "test"})
        )

        tracer = BehaviorTracer(workflow_id="w1", api_endpoint="http://localhost:8000")
        with tracer.trace_run() as run:
            with run.trace_step(0, "search") as step:
                step.set_output("result")
                step.set_confidence(0.9)
        tracer.close()

        assert route.called
        payload = json.loads(route.calls[0].request.content)
        assert payload["workflow_id"] == "w1"
        assert payload["tool_sequence"] == ["search"]

    @respx.mock
    def test_api_failure_does_not_crash_agent(self):
        """SDK must never crash the agent even if the API is down."""
        respx.post("http://localhost:8000/api/v1/traces").mock(
            side_effect=httpx.ConnectError("connection refused")
        )

        tracer = BehaviorTracer(workflow_id="w1", api_endpoint="http://localhost:8000")
        # Should not raise
        with tracer.trace_run() as run:
            with run.trace_step(0, "search") as step:
                step.set_output("result")
        tracer.close()

    @respx.mock
    def test_run_error_still_emits(self):
        """Even if the agent run fails, the trace should be emitted."""
        route = respx.post("http://localhost:8000/api/v1/traces").mock(
            return_value=httpx.Response(202, json={"status": "accepted", "run_id": "test"})
        )

        tracer = BehaviorTracer(workflow_id="w1", api_endpoint="http://localhost:8000")
        with pytest.raises(RuntimeError):
            with tracer.trace_run() as run:
                with run.trace_step(0, "search") as step:
                    step.set_output("partial")
                raise RuntimeError("agent exploded")
        tracer.close()

        assert route.called
        payload = json.loads(route.calls[0].request.content)
        assert payload["error"] == "agent exploded"