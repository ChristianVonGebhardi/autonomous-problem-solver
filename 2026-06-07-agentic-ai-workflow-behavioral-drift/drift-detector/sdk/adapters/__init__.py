"""Adapters for common agentic frameworks."""

from .generic import instrument_function, GenericAgentAdapter

__all__ = ["instrument_function", "GenericAgentAdapter"]