import pytest

from codeforge.llm.base import LLMClient, LLMResponse
from codeforge.llm.budget import BudgetedLLMClient, LLMBudgetExceeded


class _CountingLLM(LLMClient):
    def __init__(self):
        self.calls = 0

    def create_message(self, **kwargs):
        self.calls += 1
        return LLMResponse(text="ok", tool_calls=[], stop_reason="end_turn")


def test_allows_calls_up_to_the_budget():
    delegate = _CountingLLM()
    client = BudgetedLLMClient(delegate, max_calls=2)

    client.create_message(system="s", messages=[])
    client.create_message(system="s", messages=[])

    assert delegate.calls == 2


def test_raises_once_budget_is_exceeded():
    delegate = _CountingLLM()
    client = BudgetedLLMClient(delegate, max_calls=1)

    client.create_message(system="s", messages=[])
    with pytest.raises(LLMBudgetExceeded):
        client.create_message(system="s", messages=[])

    assert delegate.calls == 1  # the second call never reached the delegate
