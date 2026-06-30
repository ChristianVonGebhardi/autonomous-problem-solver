"""
BehaviorTrace SDK — Core tracer and span implementation.

Captures behavioral telemetry from agentic workflow steps with
OTEL-compatible span structure. Enrichment (embeddings) is async
and off the critical path.
"""

import time
import uuid
import asyncio
import threading
import logging
from contextlib import contextmanager
from typing import Optional, Any, Dict, List
from dataclasses import dataclass, field

import httpx

from .enricher import SpanEnricher

logger = logging.getLogger(__name__)


@dataclass
class BehaviorSpan:
    """A single behavioral observation within an agent workflow step."""

    span_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    workflow_id: str = ""
    step_name: str = ""
    step_index: int = 0
    tool_name: Optional[str] = None
    tool_input: Optional[str] = None
    reasoning: Optional[str] = None
    output: Optional[str] = None
    confidence: Optional[float] = None
    retrieved_chunk_hashes: List[str] = field(default_factory=list)
    token_count: Optional[int] = None
    latency_ms: Optional[float] = None
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    attributes: Dict[str, Any] = field(default_factory=dict)
    # Enriched async
    reasoning_embedding: Optional[List[float]] = None

    def set_tool(self, tool_name: str, tool_input: Optional[str] = None):
        self.tool_name = tool_name
        self.tool_input = tool_input

    def set_reasoning(self, reasoning: str):
        self.reasoning = reasoning

    def set_output(self, output: Any):
        self.output = str(output) if output is not None else None

    def set_confidence(self, confidence: float):
        self.confidence = float(confidence)

    def set_retrieved_chunks(self, chunk_hashes: List[str]):
        self.retrieved_chunk_hashes = chunk_hashes

    def set_token_count(self, count: int):
        self.token_count = count

    def set_attribute(self, key: str, value: Any):
        self.attributes[key] = value

    def finish(self):
        self.end_time = time.time()
        self.latency_ms = (self.end_time - self.start_time) * 1000

    def to_dict(self) -> Dict[str, Any]:
        return {
            "span_id": self.span_id,
            "trace_id": self.trace_id,
            "workflow_id": self.workflow_id,
            "step_name": self.step_name,
            "step_index": self.step_index,
            "tool_name": self.tool_name,
            "tool_input": self.tool_input,
            "reasoning": self.reasoning,
            "output": self.output,
            "confidence": self.confidence,
            "retrieved_chunk_hashes": self.retrieved_chunk_hashes,
            "token_count": self.token_count,
            "latency_ms": self.latency_ms,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "attributes": self.attributes,
            "reasoning_embedding": self.reasoning_embedding,
        }


class TraceRun:
    """Collects all spans for a single end-to-end agent workflow execution."""

    def __init__(self, workflow_id: str, run_id: Optional[str] = None):
        self.run_id = run_id or str(uuid.uuid4())
        self.workflow_id = workflow_id
        self.spans: List[BehaviorSpan] = []
        self.start_time = time.time()
        self.metadata: Dict[str, Any] = {}

    def add_span(self, span: BehaviorSpan):
        span.trace_id = self.run_id
        span.workflow_id = self.workflow_id
        self.spans.append(span)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "workflow_id": self.workflow_id,
            "start_time": self.start_time,
            "end_time": time.time(),
            "span_count": len(self.spans),
            "spans": [s.to_dict() for s in self.spans],
            "metadata": self.metadata,
            # Derived structural features
            "tool_sequence": [s.tool_name for s in self.spans if s.tool_name],
            "step_sequence": [s.step_name for s in self.spans],
            "avg_confidence": (
                sum(s.confidence for s in self.spans if s.confidence is not None)
                / max(1, sum(1 for s in self.spans if s.confidence is not None))
            ),
        }


class BehaviorTracer:
    """
    Main entry point for the BehaviorTrace SDK.

    Instruments agent workflow steps and ships behavioral traces
    to the drift detection backend asynchronously.
    """

    def __init__(
        self,
        workflow_id: str,
        endpoint: str = "http://localhost:8000",
        enricher: Optional[SpanEnricher] = None,
        sync_mode: bool = False,
    ):
        self.workflow_id = workflow_id
        self.endpoint = endpoint.rstrip("/")
        self.enricher = enricher or SpanEnricher()
        self.sync_mode = sync_mode
        self._current_run: Optional[TraceRun] = None
        self._lock = threading.Lock()

    def start_run(self, run_id: Optional[str] = None) -> TraceRun:
        """Begin a new trace run for one end-to-end workflow execution."""
        run = TraceRun(workflow_id=self.workflow_id, run_id=run_id)
        with self._lock:
            self._current_run = run
        return run

    def finish_run(self, run: Optional[TraceRun] = None) -> None:
        """Finish the run and ship the trace to the backend."""
        with self._lock:
            target = run or self._current_run
            if target is None:
                logger.warning("finish_run called with no active run")
                return
            if run is None:
                self._current_run = None

        # Async enrichment + submission
        if self.sync_mode:
            asyncio.run(self._enrich_and_submit(target))
        else:
            thread = threading.Thread(
                target=asyncio.run,
                args=(self._enrich_and_submit(target),),
                daemon=True,
            )
            thread.start()

    @contextmanager
    def trace_step(
        self,
        step_name: str,
        step_index: int = 0,
        run: Optional[TraceRun] = None,
    ):
        """Context manager for instrumenting a single agent step."""
        span = BehaviorSpan(
            workflow_id=self.workflow_id,
            step_name=step_name,
            step_index=step_index,
        )
        try:
            yield span
        finally:
            span.finish()
            target_run = run or self._current_run
            if target_run is not None:
                target_run.add_span(span)
            else:
                logger.warning(
                    "trace_step: no active run — call start_run() first"
                )

    async def _enrich_and_submit(self, run: TraceRun) -> None:
        """Enrich spans with embeddings, then POST trace to backend."""
        try:
            # Enrich each span's reasoning with embeddings (async, off hot path)
            await self.enricher.enrich_run(run)
        except Exception as e:
            logger.warning(f"Enrichment failed (non-fatal): {e}")

        try:
            await self._submit_trace(run)
        except Exception as e:
            logger.error(f"Failed to submit trace: {e}")

    async def _submit_trace(self, run: TraceRun) -> None:
        """POST the completed trace run to the control plane API."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.endpoint}/api/traces",
                json=run.to_dict(),
            )
            if response.status_code not in (200, 201):
                logger.error(
                    f"Trace submission failed: {response.status_code} {response.text}"
                )
            else:
                logger.debug(f"Trace {run.run_id} submitted successfully")