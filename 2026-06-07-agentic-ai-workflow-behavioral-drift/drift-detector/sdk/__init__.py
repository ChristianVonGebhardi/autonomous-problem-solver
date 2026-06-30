"""
BehaviorTrace SDK — OTEL-compatible instrumentation for agentic AI workflows.

Usage:
    from sdk import BehaviorTracer

    tracer = BehaviorTracer(workflow_id="customer-service-v1", endpoint="http://localhost:8000")

    with tracer.trace_step("retrieve_docs", step_index=0) as span:
        span.set_tool("vector_search")
        span.set_reasoning("Looking up customer history...")
        result = my_retrieval_function(query)
        span.set_output(result)
        span.set_confidence(0.87)
"""

from .tracer import BehaviorTracer, BehaviorSpan
from .enricher import SpanEnricher

__all__ = ["BehaviorTracer", "BehaviorSpan", "SpanEnricher"]
__version__ = "0.1.0"