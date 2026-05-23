"""
shared/claude_client.py

Thin wrapper around the Anthropic Python SDK.
All three steps use this module. Web search is enabled for Steps 1 and 2.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

import anthropic

logger = logging.getLogger(__name__)
# Force this logger to INFO level regardless of parent config
logger.setLevel(logging.INFO)

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 8192
MAX_RETRIES = 3
RETRY_BACKOFF = [30, 60, 120]  # seconds between retries


class ClaudeClient:
    """
    Wraps the Anthropic Messages API with retry logic and optional web search.
    """

    def __init__(self, api_key: str):
        self._client = anthropic.Anthropic(api_key=api_key)

    def complete(
            self,
            system: str,
            messages: list[dict],
            use_web_search: bool = False,
            use_streaming: bool = False,
            max_tokens: int = MAX_TOKENS,
        ) -> tuple[str, str]:  # (text, stop_reason)
            """
            Returns (response_text, stop_reason).
            stop_reason is one of: 'end_turn', 'stop_sequence', 'max_tokens', 'tool_use'
            """
            tools = []
            if use_web_search:
                tools = [{"type": "web_search_20250305", "name": "web_search"}]

            for attempt in range(MAX_RETRIES):
                try:
                    return self._run_completion(
                        system=system,
                        messages=messages,
                        tools=tools,
                        max_tokens=max_tokens,
                        use_streaming=use_streaming,
                    )
                except anthropic.RateLimitError as e:
                    wait = RETRY_BACKOFF[min(attempt, len(RETRY_BACKOFF) - 1)]
                    if attempt == MAX_RETRIES - 1:
                        logger.warning("Rate limit persists after %d retries. Reducing prompt size...", MAX_RETRIES)
                        messages_reduced = self._reduce_prompt_size(messages)
                        if messages_reduced != messages:
                            logger.warning("Retrying with reduced prompt size after 60s wait...")
                            time.sleep(60)
                            try:
                                return self._run_completion(
                                    system=system,
                                    messages=messages_reduced,
                                    tools=tools,
                                    max_tokens=max_tokens,
                                    use_streaming=use_streaming,
                                )
                            except Exception as e2:
                                logger.error("Reduced prompt retry failed: %s", e2)
                                raise
                    logger.warning("Rate limit hit (attempt %d/%d). Waiting %ds. %s", attempt + 1, MAX_RETRIES, wait, e)
                    time.sleep(wait)
                except anthropic.APIStatusError as e:
                    if e.status_code >= 500:
                        wait = RETRY_BACKOFF[min(attempt, len(RETRY_BACKOFF) - 1)]
                        logger.warning("Server error %d (attempt %d/%d). Waiting %ds.", e.status_code, attempt + 1, MAX_RETRIES, wait)
                        time.sleep(wait)
                    else:
                        raise
                except anthropic.APIConnectionError as e:
                    wait = RETRY_BACKOFF[min(attempt, len(RETRY_BACKOFF) - 1)]
                    logger.warning("Connection error (attempt %d/%d). Waiting %ds. %s", attempt + 1, MAX_RETRIES, wait, e)
                    time.sleep(wait)

            raise RuntimeError(f"Claude API failed after {MAX_RETRIES} attempts.")

    def _reduce_prompt_size(self, messages: list[dict]) -> list[dict]:
        """
        Reduces message size by truncating long content.
        Returns modified messages list, or original if already small.
        """
        reduced = []
        for msg in messages:
            if isinstance(msg.get("content"), str) and len(msg["content"]) > 500:
                # Truncate to 500 chars with ellipsis
                truncated = msg["content"][:500] + "...\n[content truncated due to rate limiting]"
                reduced.append({
                    "role": msg["role"],
                    "content": truncated,
                })
            else:
                reduced.append(msg)
        if reduced == messages:
            logger.warning("Prompt already minimal — cannot reduce further.")
        return reduced

    def _run_completion(
        self,
        system: str,
        messages: list[dict],
        tools: list[dict],
        max_tokens: int,
        use_streaming: bool = False,
    ) -> str:
        """
        Runs the full agentic loop until stop_reason is 'end_turn' or 'stop_sequence'.
        When use_streaming=True, uses the streaming API to avoid SDK timeout errors
        for large max_tokens values. Web search tools are incompatible with streaming
        and must use use_streaming=False.
        """
        local_messages = list(messages)

        kwargs: dict = dict(
            model=MODEL,
            max_tokens=max_tokens,
            system=system,
            messages=local_messages,
        )
        if tools:
            kwargs["tools"] = tools

        accumulated_text: list[str] = []

        logger.debug("=== REQUEST KWARGS ===")
        logger.debug("Model: %s | Max tokens: %s | Messages: %d", kwargs["model"], kwargs["max_tokens"], len(kwargs["messages"]))
        logger.debug("System (first 200 chars): %s", kwargs["system"][:200])
        for i, msg in enumerate(kwargs["messages"]):
            if isinstance(msg.get("content"), str):
                logger.debug("  Msg %d: role=%s, content length=%d", i, msg["role"], len(msg["content"]))

        while True:
            if use_streaming:
                logger.info("Starting streaming request (max_tokens=%d)...", max_tokens)
                with self._client.messages.stream(**kwargs) as stream:
                    for event in stream:
                        pass  # let the stream progress
                    response = stream.get_final_message()
                logger.info("Streaming complete. stop_reason=%s", response.stop_reason)
            else:
                response = self._client.messages.create(**kwargs)

            logger.debug("Claude response stop_reason=%s content_blocks=%d", response.stop_reason, len(response.content))

            tool_uses: list = []
            for block in response.content:
                if hasattr(block, 'type'):
                    if block.type == "text":
                        accumulated_text.append(block.text)
                    elif block.type == "tool_use":
                        tool_uses.append(block)

            if response.stop_reason in ("end_turn", "stop_sequence") or not tool_uses:
                result = "\n".join(accumulated_text).strip()
                if not result:
                    logger.error("Claude returned empty response (stop_reason=%s, content_blocks=%d)",
                                response.stop_reason, len(response.content))
                    raise RuntimeError("Claude API returned empty response. Check logs for details.")
                if response.stop_reason == "max_tokens":
                    logger.warning(
                        "Claude response was truncated (stop_reason=max_tokens). "
                        "Files committed so far are partial. Consider increasing max_tokens "
                        "or resuming this cycle to continue implementation."
                    )
                return result, response.stop_reason

            # Client-side tool_use loop (web_search never reaches here)
            local_messages.append({
                "role": "assistant",
                "content": response.content,
            })
            tool_results = []
            for tu in tool_uses:
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tu.id,
                    "content": f"Tool '{tu.name}' is not implemented on the client side.",
                })
            local_messages.append({
                "role": "user",
                "content": tool_results,
            })
            kwargs["messages"] = local_messages
