"""
Generic adapter — wraps any callable as an instrumented agent step.

Usage:
    from sdk.adapters.generic import instrument_function

    @instrument_function(tracer, step_name="retrieve", step_index=0, tool="vector_search")
    def my_retrieval_step(query: str):
        ...
"""

import functools
import logging
from typing import Optional, Callable, Any

logger = logging.getLogger(__name__)


def instrument_function(
    tracer,
    step_name: str,
    step_index: int = 0,
    tool: Optional[str] = None,
    extract_reasoning: Optional[Callable[[Any], str]] = None,
    extract_confidence: Optional[Callable[[Any], float]] = None,
):
    """
    Decorator factory that wraps a function as an instrumented agent step.

    Args:
        tracer: BehaviorTracer instance
        step_name: Human-readable step name
        step_index: Ordinal position in the workflow
        tool: Tool name if this step uses a specific tool
        extract_reasoning: Optional callable to extract reasoning string from result
        extract_confidence: Optional callable to extract confidence float from result
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            with tracer.trace_step(step_name, step_index=step_index) as span:
                if tool:
                    span.set_tool(tool)

                # Capture input as reasoning hint
                if args:
                    span.set_reasoning(str(args[0])[:500])

                result = func(*args, **kwargs)

                # Extract output metadata
                if result is not None:
                    span.set_output(result)

                if extract_reasoning and result is not None:
                    try:
                        reasoning = extract_reasoning(result)
                        if reasoning:
                            span.set_reasoning(reasoning)
                    except Exception:
                        pass

                if extract_confidence and result is not None:
                    try:
                        conf = extract_confidence(result)
                        if conf is not None:
                            span.set_confidence(conf)
                    except Exception:
                        pass

                return result

        return wrapper

    return decorator


class GenericAgentAdapter:
    """
    Adapter for wrapping a multi-step agent pipeline.

    Usage:
        adapter = GenericAgentAdapter(tracer)

        with adapter.run() as run:
            with adapter.step("step_1", 0) as span:
                span.set_tool("web_search")
                result = search(query)
                span.set_output(result)
    """

    def __init__(self, tracer):
        self.tracer = tracer

    def run(self):
        """Context manager that wraps an entire workflow run."""
        return _RunContext(self.tracer)

    def step(self, step_name: str, step_index: int = 0):
        """Context manager for a single step (must be inside a run context)."""
        return self.tracer.trace_step(step_name, step_index=step_index)


class _RunContext:
    def __init__(self, tracer):
        self.tracer = tracer
        self.run = None

    def __enter__(self):
        self.run = self.tracer.start_run()
        return self.run

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.tracer.finish_run(self.run)
        return False