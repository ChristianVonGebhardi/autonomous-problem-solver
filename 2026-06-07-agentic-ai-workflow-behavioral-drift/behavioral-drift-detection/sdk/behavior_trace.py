"""
BehaviorTrace SDK

Lightweight instrumentation middleware for agentic AI workflows.
Emits OpenTelemetry-compatible spans enriched with behavioral attributes:
  - tool names and call sequences
  - step indices and ordering
  - output text (for embedding generation, done async off critical path)
  - confidence scores
  - retrieved chunk hashes

Usage:
    tracer = BehaviorTracer(workflow_id="my-workflow", api_endpoint="http://localhost:8000")
    
    with tracer.trace_run() as run:
        with run.trace_step(step_index=0, tool_name="search") as step:
            result = search_tool(query)
            step.set_output(result)
            step.set_confidence(0.92)
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

import httpx
import structlog

logger = structlog.get_logger(__name__)


@dataclass
class StepSpan:
    """Represents a single step in an agent run."""
    step_index: int
    tool_name: str
    run_id: str
    workflow_id: str
    span_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    output_text: Optional[str] = None
    confidence: Optional[float] = None
    retrieved_chunks: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

    def set_output(self, output: Any) -> None:
        """Set the output of this step. Accepts str or JSON-serializable objects."""
        if isinstance(output, str):
            self.output_text = output
        else:
            try:
                self.output_text = json.dumps(output)
            except (TypeError, ValueError):
                self.output_text = str(output)

    def set_confidence(self, confidence: float) -> None:
        """Set confidence score (0.0–1.0) for this step's output."""
        self.confidence = float(confidence)

    def add_retrieved_chunk(self, chunk: str) -> None:
        """Register a retrieved document chunk (stored as hash for privacy)."""
        chunk_hash = hashlib.sha256(chunk.encode()).hexdigest()[:16]
        self.retrieved_chunks.append(chunk_hash)

    def set_metadata(self, key: str, value: Any) -> None:
        """Attach arbitrary metadata to the step span."""
        self.metadata[key] = value

    def _finalize(self) -> None:
        self.end_time = time.time()

    def to_dict(self) -> dict:
        return {
            "span_id": self.span_id,
            "run_id": self.run_id,
            "workflow_id": self.workflow_id,
            "step_index": self.step_index,
            "tool_name": self.tool_name,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_ms": (
                (self.end_time - self.start_time) * 1000
                if self.end_time else None
            ),
            "output_text": self.output_text,
            "confidence": self.confidence,
            "retrieved_chunks": self.retrieved_chunks,
            "metadata": self.metadata,
            "error": self.error,
        }


@dataclass
class RunSpan:
    """Represents a complete agent run (one end-to-end execution)."""
    workflow_id: str
    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    steps: list[StepSpan] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    _tracer: Optional["BehaviorTracer"] = field(default=None, repr=False)

    @contextmanager
    def trace_step(self, step_index: int, tool_name: str):
        """Context manager for tracing an individual agent step."""
        step = StepSpan(
            step_index=step_index,
            tool_name=tool_name,
            run_id=self.run_id,
            workflow_id=self.workflow_id,
        )
        self.steps.append(step)
        logger.debug(
            "step_start",
            run_id=self.run_id,
            step_index=step_index,
            tool_name=tool_name,
        )
        try:
            yield step
        except Exception as exc:
            step.error = str(exc)
            logger.error("step_error", run_id=self.run_id, step_index=step_index, error=str(exc))
            raise
        finally:
            step._finalize()
            logger.debug(
                "step_end",
                run_id=self.run_id,
                step_index=step_index,
                tool_name=tool_name,
                duration_ms=step.to_dict().get("duration_ms"),
            )

    def set_metadata(self, key: str, value: Any) -> None:
        self.metadata[key] = value

    def _finalize(self) -> None:
        self.end_time = time.time()

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "workflow_id": self.workflow_id,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_ms": (
                (self.end_time - self.start_time) * 1000
                if self.end_time else None
            ),
            "steps": [s.to_dict() for s in self.steps],
            "metadata": self.metadata,
            "error": self.error,
            "tool_sequence": [s.tool_name for s in self.steps],
            "step_count": len(self.steps),
        }


class BehaviorTracer:
    """
    Main entry point for the BehaviorTrace SDK.
    
    Instruments agent runs and emits behavioral spans to the drift detection
    control plane. Embedding generation happens async in the worker, not here,
    so there is zero latency added to the agent critical path beyond a single
    HTTP POST of the trace JSON.
    """

    def __init__(
        self,
        workflow_id: str,
        api_endpoint: str = "http://localhost:8000",
        api_timeout: float = 5.0,
        emit_sync: bool = True,
    ):
        self.workflow_id = workflow_id
        self.api_endpoint = api_endpoint.rstrip("/")
        self.api_timeout = api_timeout
        self.emit_sync = emit_sync
        self._client = httpx.Client(timeout=api_timeout)

    @contextmanager
    def trace_run(self, metadata: Optional[dict] = None):
        """Context manager for tracing a complete agent run."""
        run = RunSpan(workflow_id=self.workflow_id, _tracer=self)
        if metadata:
            run.metadata.update(metadata)

        logger.info("run_start", run_id=run.run_id, workflow_id=self.workflow_id)
        try:
            yield run
        except Exception as exc:
            run.error = str(exc)
            logger.error("run_error", run_id=run.run_id, error=str(exc))
            raise
        finally:
            run._finalize()
            logger.info(
                "run_end",
                run_id=run.run_id,
                steps=len(run.steps),
                duration_ms=run.to_dict().get("duration_ms"),
            )
            self._emit_run(run)

    def _emit_run(self, run: RunSpan) -> None:
        """Send the completed run trace to the control plane API."""
        payload = run.to_dict()
        try:
            response = self._client.post(
                f"{self.api_endpoint}/api/v1/traces",
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            response.raise_for_status()
            logger.info("trace_emitted", run_id=run.run_id, status=response.status_code)
        except httpx.HTTPError as exc:
            # SDK must never crash the agent — log and continue
            logger.warning("trace_emit_failed", run_id=run.run_id, error=str(exc))

    def close(self) -> None:
        """Clean up HTTP client resources."""
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()