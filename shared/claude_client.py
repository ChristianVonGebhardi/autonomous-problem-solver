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

MODEL = "claude-sonnet-4-5"
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
        max_tokens: int = MAX_TOKENS,
    ) -> str:
        """
        Calls the Claude API and returns the final assistant text.

        If use_web_search=True, the web_search tool is registered and the method
        handles the full tool-use loop automatically (tool_use → tool_result → text).

        Retries up to MAX_RETRIES times on transient API errors.
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
                )
            except anthropic.RateLimitError as e:
                wait = RETRY_BACKOFF[min(attempt, len(RETRY_BACKOFF) - 1)]
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

    def _run_completion(
        self,
        system: str,
        messages: list[dict],
        tools: list[dict],
        max_tokens: int,
    ) -> str:
        """
        Runs the full agentic loop: keeps calling the API until stop_reason is
        'end_turn' or 'stop_sequence'. Handles tool_use blocks transparently.

        For web_search_20250305: this is a "server-side" tool. The API handles
        the search internally and returns results as web_search_tool_result blocks
        in the response content. We simply accumulate all text blocks across turns
        until stop_reason is 'end_turn'.
        """
        local_messages = list(messages)  # don't mutate caller's list

        kwargs: dict = dict(
            model=MODEL,
            max_tokens=max_tokens,
            system=system,
            messages=local_messages,
        )
        if tools:
            kwargs["tools"] = tools

        accumulated_text: list[str] = []

        while True:
            response = self._client.messages.create(**kwargs)
            logger.debug("Claude response stop_reason=%s content_blocks=%d", response.stop_reason, len(response.content))

            # Collect text blocks from this response turn
            tool_uses: list = []
            for block in response.content:
                if hasattr(block, 'type'):
                    if block.type == "text":
                        accumulated_text.append(block.text)
                    elif block.type == "tool_use":
                        # Client-side tool use (not web_search, which is server-side)
                        tool_uses.append(block)

            if response.stop_reason in ("end_turn", "stop_sequence") or not tool_uses:
                # Done — return all accumulated text
                return "\n".join(accumulated_text).strip()

            # Client-side tool_use loop (future extensibility — web_search never reaches here)
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
