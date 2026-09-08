"""LLM provider factory: swap providers by changing this module, agents stay unchanged."""
from __future__ import annotations

from codeforge.config import Settings, get_settings
from codeforge.llm.base import LLMClient, LLMResponse, ToolCall
from codeforge.llm.claude import ClaudeClient


def get_llm_client(settings: Settings | None = None) -> LLMClient:
    settings = settings or get_settings()
    return ClaudeClient(api_key=settings.anthropic_api_key, model=settings.claude_model)


__all__ = ["LLMClient", "LLMResponse", "ToolCall", "ClaudeClient", "get_llm_client"]
