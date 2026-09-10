"""Caps LLM calls per pipeline run/server session — a cheap guardrail against a runaway
loop or a crafted issue designed to rack up API cost."""
from __future__ import annotations

from typing import Any

from codeforge.llm.base import LLMClient, LLMResponse


class LLMBudgetExceeded(RuntimeError):
    """Raised when a client has made more calls than its configured budget allows."""


class BudgetedLLMClient(LLMClient):
    def __init__(self, delegate: LLMClient, max_calls: int):
        self._delegate = delegate
        self._max_calls = max_calls
        self._calls_made = 0

    def create_message(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        if self._calls_made >= self._max_calls:
            raise LLMBudgetExceeded(
                f"LLM call budget exceeded: {self._max_calls} calls per pipeline run/session"
            )
        self._calls_made += 1
        return self._delegate.create_message(
            system=system, messages=messages, tools=tools, max_tokens=max_tokens
        )
