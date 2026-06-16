"""
ATCAP Python SDK — WorkflowContext propagator + LLM client interceptor.

Usage:
    from atcap_sdk import WorkflowContext, instrument_openai

    # Instrument your OpenAI client
    import openai
    client = instrument_openai(openai.OpenAI(), collector_url="http://localhost:8000")

    # Set context before making calls
    with WorkflowContext(team="platform", feature="ai-search", workflow_id="wf-123"):
        response = client.chat.completions.create(...)
"""

from sdk.context import WorkflowContext
from sdk.interceptors import instrument_openai, instrument_anthropic, ATCAPClient

__all__ = ["WorkflowContext", "instrument_openai", "instrument_anthropic", "ATCAPClient"]