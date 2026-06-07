"""
LLM client interceptors — wraps OpenAI and Anthropic clients to
automatically capture token usage and emit cost events to ATCAP.
"""
import time
import uuid
import logging
import asyncio
from typing import Optional, Callable, Any
import httpx
from sdk.context import WorkflowContext

logger = logging.getLogger(__name__)


class ATCAPClient:
    """HTTP client for sending events to the ATCAP collector."""

    def __init__(self, collector_url: str = "http://localhost:8000", api_key: Optional[str] = None):
        self.collector_url = collector_url.rstrip("/")
        self.headers = {"Content-Type": "application/json"}
        if api_key:
            self.headers["X-API-Key"] = api_key

    def emit(self, event: dict) -> bool:
        """Synchronously emit a token event to the collector."""
        try:
            with httpx.Client(timeout=5.0) as client:
                resp = client.post(
                    f"{self.collector_url}/api/v1/events",
                    json=event,
                    headers=self.headers,
                )
                resp.raise_for_status()
                return True
        except Exception as e:
            logger.warning(f"ATCAP emit failed (non-blocking): {e}")
            return False

    async def emit_async(self, event: dict) -> bool:
        """Asynchronously emit a token event."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(
                    f"{self.collector_url}/api/v1/events",
                    json=event,
                    headers=self.headers,
                )
                resp.raise_for_status()
                return True
        except Exception as e:
            logger.warning(f"ATCAP async emit failed (non-blocking): {e}")
            return False


def _build_event(provider: str, model: str, usage: dict, latency_ms: int) -> dict:
    """Build an ATCAP event dict from call details."""
    ctx = WorkflowContext.require()
    return {
        "trace_id": str(uuid.uuid4()),
        "span_id": str(uuid.uuid4()),
        "team": ctx.team,
        "feature": ctx.feature,
        "workflow_id": ctx.workflow_id,
        "agent_run_id": ctx.agent_run_id,
        "business_entity_id": ctx.business_entity_id,
        "business_entity_type": ctx.business_entity_type,
        "provider": provider,
        "model": model,
        "prompt_tokens": usage.get("prompt_tokens", 0),
        "completion_tokens": usage.get("completion_tokens", 0),
        "latency_ms": latency_ms,
    }


class InstrumentedOpenAICompletions:
    """Proxies openai.chat.completions.create() to intercept usage."""

    def __init__(self, original_completions, atcap: ATCAPClient):
        self._completions = original_completions
        self._atcap = atcap

    def create(self, *args, **kwargs):
        start = time.time()
        response = self._completions.create(*args, **kwargs)
        latency_ms = int((time.time() - start) * 1000)

        try:
            usage = {}
            if hasattr(response, "usage") and response.usage:
                usage = {
                    "prompt_tokens": response.usage.prompt_tokens or 0,
                    "completion_tokens": response.usage.completion_tokens or 0,
                }
            model = getattr(response, "model", kwargs.get("model", "unknown"))
            event = _build_event("openai", model, usage, latency_ms)
            self._atcap.emit(event)
        except Exception as e:
            logger.warning(f"Failed to emit ATCAP event: {e}")

        return response

    async def acreate(self, *args, **kwargs):
        start = time.time()
        response = await self._completions.acreate(*args, **kwargs)
        latency_ms = int((time.time() - start) * 1000)

        try:
            usage = {}
            if hasattr(response, "usage") and response.usage:
                usage = {
                    "prompt_tokens": response.usage.prompt_tokens or 0,
                    "completion_tokens": response.usage.completion_tokens or 0,
                }
            model = getattr(response, "model", kwargs.get("model", "unknown"))
            event = _build_event("openai", model, usage, latency_ms)
            await self._atcap.emit_async(event)
        except Exception as e:
            logger.warning(f"Failed to emit ATCAP event: {e}")

        return response


class InstrumentedOpenAIChat:
    def __init__(self, original_chat, atcap: ATCAPClient):
        self.completions = InstrumentedOpenAICompletions(original_chat.completions, atcap)


class InstrumentedOpenAIClient:
    """Wrapped OpenAI client that intercepts all completions calls."""

    def __init__(self, original_client, atcap: ATCAPClient):
        self._client = original_client
        self.chat = InstrumentedOpenAIChat(original_client.chat, atcap)

    def __getattr__(self, name):
        return getattr(self._client, name)


def instrument_openai(
    client,
    collector_url: str = "http://localhost:8000",
    api_key: Optional[str] = None,
) -> InstrumentedOpenAIClient:
    """
    Wrap an OpenAI client to automatically emit ATCAP cost events.

    Usage:
        import openai
        from atcap_sdk import instrument_openai, WorkflowContext

        client = instrument_openai(openai.OpenAI(), collector_url="http://localhost:8000")

        with WorkflowContext(team="platform", feature="summarization"):
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": "Hello"}]
            )
    """
    atcap = ATCAPClient(collector_url=collector_url, api_key=api_key)
    return InstrumentedOpenAIClient(client, atcap)


class InstrumentedAnthropicMessages:
    """Proxies anthropic.messages.create() to intercept usage."""

    def __init__(self, original_messages, atcap: ATCAPClient):
        self._messages = original_messages
        self._atcap = atcap

    def create(self, *args, **kwargs):
        start = time.time()
        response = self._messages.create(*args, **kwargs)
        latency_ms = int((time.time() - start) * 1000)

        try:
            usage = {}
            if hasattr(response, "usage") and response.usage:
                usage = {
                    "prompt_tokens": getattr(response.usage, "input_tokens", 0),
                    "completion_tokens": getattr(response.usage, "output_tokens", 0),
                }
            model = getattr(response, "model", kwargs.get("model", "unknown"))
            event = _build_event("anthropic", model, usage, latency_ms)
            self._atcap.emit(event)
        except Exception as e:
            logger.warning(f"Failed to emit ATCAP event: {e}")

        return response


class InstrumentedAnthropicClient:
    def __init__(self, original_client, atcap: ATCAPClient):
        self._client = original_client
        self.messages = InstrumentedAnthropicMessages(original_client.messages, atcap)

    def __getattr__(self, name):
        return getattr(self._client, name)


def instrument_anthropic(
    client,
    collector_url: str = "http://localhost:8000",
    api_key: Optional[str] = None,
) -> InstrumentedAnthropicClient:
    """Wrap an Anthropic client to automatically emit ATCAP cost events."""
    atcap = ATCAPClient(collector_url=collector_url, api_key=api_key)
    return InstrumentedAnthropicClient(client, atcap)