"""Anthropic Claude implementation of LLMClient (tool calling / function calling)."""
from __future__ import annotations

from typing import Any

import anthropic

from codeforge.llm.base import LLMClient, LLMResponse, ToolCall


class ClaudeClient(LLMClient):
    def __init__(
        self,
        api_key: str,
        model: str,
        timeout_seconds: float = 30.0,
        max_retries: int = 3,
    ):
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY is not set (check your .env)")
        # anthropic's SDK already retries connection errors, 429s, and 5xx with backoff.
        self._client = anthropic.Anthropic(
            api_key=api_key, timeout=timeout_seconds, max_retries=max_retries
        )
        self._model = model

    def create_message(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        response = self._client.messages.create(
            model=self._model,
            system=system,
            messages=messages,
            tools=tools or [],
            max_tokens=max_tokens,
        )

        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(ToolCall(id=block.id, name=block.name, input=block.input))

        return LLMResponse(
            text="".join(text_parts),
            tool_calls=tool_calls,
            stop_reason=response.stop_reason,
            raw=response,
        )
