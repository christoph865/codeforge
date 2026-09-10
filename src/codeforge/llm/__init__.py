"""LLM provider factory: swap providers by changing this module, agents stay unchanged."""
from __future__ import annotations

from codeforge.config import Settings, get_settings
from codeforge.llm.base import LLMClient, LLMResponse, ToolCall
from codeforge.llm.budget import BudgetedLLMClient, LLMBudgetExceeded
from codeforge.llm.claude import ClaudeClient


def get_llm_client(settings: Settings | None = None) -> LLMClient:
    settings = settings or get_settings()
    claude = ClaudeClient(
        api_key=settings.anthropic_api_key,
        model=settings.claude_model,
        timeout_seconds=settings.request_timeout_seconds,
        max_retries=settings.max_retries,
    )
    return BudgetedLLMClient(claude, max_calls=settings.max_llm_calls_per_run)


__all__ = [
    "BudgetedLLMClient",
    "ClaudeClient",
    "LLMBudgetExceeded",
    "LLMClient",
    "LLMResponse",
    "ToolCall",
    "get_llm_client",
]
