from unittest.mock import MagicMock

from codeforge.config import Settings
from codeforge.llm import get_llm_client
from codeforge.llm.budget import BudgetedLLMClient
from codeforge.llm.claude import ClaudeClient
from codeforge.llm.gemini import GeminiClient


def test_get_llm_client_wraps_claude_with_a_budget(monkeypatch):
    settings = Settings(
        anthropic_api_key="key",
        max_llm_calls_per_run=7,
        request_timeout_seconds=12.0,
        max_retries=5,
        _env_file=None,
    )

    captured = {}
    real_init = ClaudeClient.__init__

    def spy_init(self, api_key, model, timeout_seconds=30.0, max_retries=3):
        captured["timeout_seconds"] = timeout_seconds
        captured["max_retries"] = max_retries
        # avoid constructing a real anthropic.Anthropic client
        self._client = MagicMock()
        self._model = model

    monkeypatch.setattr(ClaudeClient, "__init__", spy_init)
    try:
        client = get_llm_client(settings)
    finally:
        monkeypatch.setattr(ClaudeClient, "__init__", real_init)

    assert isinstance(client, BudgetedLLMClient)
    assert captured == {"timeout_seconds": 12.0, "max_retries": 5}
    assert client._max_calls == 7


def test_get_llm_client_uses_gemini_when_selected(monkeypatch):
    settings = Settings(
        llm_provider="gemini",
        gemini_api_key="key",
        max_llm_calls_per_run=3,
        request_timeout_seconds=9.0,
        max_retries=2,
        _env_file=None,
    )

    captured = {}
    real_init = GeminiClient.__init__

    def spy_init(self, api_key, model, timeout_seconds=30.0, max_retries=3):
        captured["timeout_seconds"] = timeout_seconds
        captured["max_retries"] = max_retries
        self._client = MagicMock()  # avoid constructing a real genai.Client
        self._model = model

    monkeypatch.setattr(GeminiClient, "__init__", spy_init)
    try:
        client = get_llm_client(settings)
    finally:
        monkeypatch.setattr(GeminiClient, "__init__", real_init)

    assert isinstance(client, BudgetedLLMClient)
    assert captured == {"timeout_seconds": 9.0, "max_retries": 2}
    assert client._max_calls == 3
