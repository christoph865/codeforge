from types import SimpleNamespace

import anthropic
import gitlab
from typer.testing import CliRunner

from codeforge.agents.specification import SpecificationResult, TechnicalSpec
from codeforge.cli import app
from codeforge.gitlab_client import ActionResult, UnsafeFilePathError
from codeforge.llm.budget import LLMBudgetExceeded
from codeforge.orchestrator import PipelineResult

runner = CliRunner()


class _FakeOrchestrator:
    """Stands in for codeforge.cli.Orchestrator so the CLI can be tested without any real
    GitLab/Claude credentials or network access."""

    def __init__(self, result=None, exc=None):
        self._result = result
        self._exc = exc

    def run(self, issue_iid, jira_story_key=None):
        if self._exc is not None:
            raise self._exc
        return self._result


def _spec_result(summary: str = "Add pagination to the users API") -> SpecificationResult:
    spec = TechnicalSpec(summary=summary, affected_components=["src/api/users.py"], test_cases=["t1"])
    return SpecificationResult(spec=spec, posted=True)


def test_run_issue_reports_awaiting_approval(monkeypatch):
    result = PipelineResult(
        intake=None, specification=_spec_result(), implementation=None, awaiting_approval=True
    )
    monkeypatch.setattr("codeforge.cli.Orchestrator", lambda: _FakeOrchestrator(result=result))

    outcome = runner.invoke(app, ["run-issue", "42"])

    assert outcome.exit_code == 0
    assert "Awaiting human approval" in outcome.stdout


def test_run_issue_reports_implementation_complete(monkeypatch):
    impl = SimpleNamespace(
        branch="codeforge/42-add-pagination",
        files=["src/api/users.py"],
        merge_request=ActionResult(dry_run=True, detail={"title": "Draft: Add pagination"}),
    )
    result = PipelineResult(
        intake=None, specification=_spec_result(), implementation=impl, awaiting_approval=False
    )
    monkeypatch.setattr("codeforge.cli.Orchestrator", lambda: _FakeOrchestrator(result=result))

    outcome = runner.invoke(app, ["run-issue", "42"])

    assert outcome.exit_code == 0
    assert "Implementation complete" in outcome.stdout
    assert "codeforge/42-add-pagination" in outcome.stdout


def test_run_issue_handles_gitlab_errors_cleanly(monkeypatch):
    monkeypatch.setattr(
        "codeforge.cli.Orchestrator",
        lambda: _FakeOrchestrator(exc=gitlab.exceptions.GitlabGetError("404 Issue Not Found")),
    )

    outcome = runner.invoke(app, ["run-issue", "999"])

    assert outcome.exit_code == 1
    assert "GitLab API error" in outcome.stdout


def test_run_issue_handles_claude_errors_cleanly(monkeypatch):
    monkeypatch.setattr(
        "codeforge.cli.Orchestrator",
        lambda: _FakeOrchestrator(exc=anthropic.AnthropicError("rate limited")),
    )

    outcome = runner.invoke(app, ["run-issue", "42"])

    assert outcome.exit_code == 1
    assert "Claude API error" in outcome.stdout


def test_run_issue_handles_budget_exceeded_cleanly(monkeypatch):
    monkeypatch.setattr(
        "codeforge.cli.Orchestrator",
        lambda: _FakeOrchestrator(exc=LLMBudgetExceeded("LLM call budget exceeded: 20 calls")),
    )

    outcome = runner.invoke(app, ["run-issue", "42"])

    assert outcome.exit_code == 1
    assert "budget exceeded" in outcome.stdout


def test_run_issue_handles_unsafe_path_cleanly(monkeypatch):
    monkeypatch.setattr(
        "codeforge.cli.Orchestrator",
        lambda: _FakeOrchestrator(exc=UnsafeFilePathError("unsafe file path: '/etc/passwd'")),
    )

    outcome = runner.invoke(app, ["run-issue", "42"])

    assert outcome.exit_code == 1
    assert "unsafe file path" in outcome.stdout


def test_mcp_server_command_reports_config_error_cleanly(monkeypatch):
    def _boom():
        raise ValueError("ANTHROPIC_API_KEY is not set (check your .env)")

    monkeypatch.setattr("codeforge.mcp_server.run_server", _boom)

    outcome = runner.invoke(app, ["mcp-server"])

    assert outcome.exit_code == 1
    assert "Configuration error" in outcome.stdout
