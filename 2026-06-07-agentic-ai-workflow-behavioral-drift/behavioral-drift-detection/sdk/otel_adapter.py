"""
OpenTelemetry adapter for BehaviorTrace SDK.

Wraps BehaviorTracer spans in OTEL-compatible span format so that
teams already using OTEL collectors can ingest behavioral traces
alongside infrastructure traces with zero new pipelines.
"""

from __future__ import annotations

from typing import Optional

try:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
    from opentelemetry.trace import SpanKind
    OTEL_AVAILABLE = True
except ImportError:
    OTEL_AVAILABLE = False

from sdk.behavior_trace import BehaviorTracer, RunSpan, StepSpan
import structlog

logger = structlog.get_logger(__name__)


class OTELBehaviorTracer(BehaviorTracer):
    """
    BehaviorTracer that additionally emits OTEL spans.
    
    Use this when you already have an OTEL collector and want behavioral
    attributes alongside infrastructure spans in the same trace context.
    """

    def __init__(self, *args, otel_exporter=None, **kwargs):
        super().__init__(*args, **kwargs)
        
        if not OTEL_AVAILABLE:
            logger.warning("opentelemetry not installed; OTEL emission disabled")
            self._otel_tracer = None
            return

        provider = TracerProvider()
        exporter = otel_exporter or ConsoleSpanExporter()
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)
        self._otel_tracer = trace.get_tracer("behavior-drift-detector")

    def _emit_step_to_otel(self, step: StepSpan) -> None:
        """Emit a step span with behavioral attributes to OTEL."""
        if not self._otel_tracer:
            return
        
        with self._otel_tracer.start_as_current_span(
            f"agent.step.{step.tool_name}",
            kind=SpanKind.INTERNAL,
        ) as span:
            span.set_attribute("agent.workflow_id", step.workflow_id)
            span.set_attribute("agent.run_id", step.run_id)
            span.set_attribute("agent.step_index", step.step_index)
            span.set_attribute("agent.tool_name", step.tool_name)
            if step.confidence is not None:
                span.set_attribute("agent.confidence", step.confidence)
            if step.output_text:
                # Truncate for OTEL attribute limits
                span.set_attribute("agent.output_preview", step.output_text[:256])
            span.set_attribute("agent.retrieved_chunk_count", len(step.retrieved_chunks))
            if step.error:
                span.set_attribute("agent.error", step.error)