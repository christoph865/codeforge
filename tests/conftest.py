"""Shared test doubles for GitLab and the LLM client — no real network calls anywhere."""
from __future__ import annotations

from types import SimpleNamespace

import gitlab
import pytest

from codeforge.audit import AuditLogger
from codeforge.config import Settings
from codeforge.gitlab_client import GitLabClient
from codeforge.llm.base import LLMClient, LLMResponse, ToolCall


class FakeNote:
    def __init__(self, body: str, system: bool = False):
        self.body = body
        self.system = system


class FakeNotesManager:
    def __init__(self, notes: list[str] | None = None):
        self._notes = [FakeNote(n) for n in (notes or [])]

    def list(self, all=True):
        return self._notes

    def create(self, data):
        self._notes.append(FakeNote(data["body"]))
        return SimpleNamespace(id=len(self._notes))


class FakeIssue:
    def __init__(
        self,
        iid: int = 42,
        title: str = "Add pagination to users API",
        description: str = "Update src/api/users.py to support offset/limit pagination.",
        labels: list[str] | None = None,
        notes: list[str] | None = None,
        web_url: str = "https://gitlab.example.com/group/proj/-/issues/42",
    ):
        self.iid = iid
        self.title = title
        self.description = description
        self.labels = labels if labels is not None else []
        self.web_url = web_url
        self.notes = FakeNotesManager(notes)
        self.saved = False

    def save(self):
        self.saved = True


class FakeFile:
    def __init__(self, content: str):
        self._content = content

    def decode(self) -> bytes:
        # python-gitlab's ProjectFile.decode() already returns the base64-decoded raw bytes.
        return self._content.encode()


class FakeFilesManager:
    def __init__(self, files: dict[str, str] | None = None):
        self._files = files or {}

    def get(self, file_path: str, ref: str):
        if file_path not in self._files:
            raise gitlab.exceptions.GitlabGetError("not found")
        return FakeFile(self._files[file_path])


class FakeBranchesManager:
    def __init__(self):
        self.created: list[dict] = []

    def get(self, name: str):
        raise gitlab.exceptions.GitlabGetError("not found")

    def create(self, data: dict):
        self.created.append(data)


class FakeCommitsManager:
    def __init__(self):
        self.commits: list[dict] = []

    def create(self, data: dict):
        self.commits.append(data)
        return SimpleNamespace(id="deadbeef")


class FakeMergeRequestsManager:
    def __init__(self):
        self.created: list[dict] = []

    def create(self, data: dict):
        self.created.append(data)
        return SimpleNamespace(iid=1, web_url="https://gitlab.example.com/group/proj/-/merge_requests/1")


class FakeProject:
    default_branch = "main"

    def __init__(self, issue: FakeIssue, files: dict[str, str] | None = None):
        self.issue = issue
        self.issues = SimpleNamespace(get=lambda iid: self.issue)
        self.files = FakeFilesManager(files)
        self.branches = FakeBranchesManager()
        self.commits = FakeCommitsManager()
        self.mergerequests = FakeMergeRequestsManager()


class FakeGitlabSdk:
    def __init__(self, project: FakeProject):
        self.project = project
        self.projects = SimpleNamespace(get=lambda pid: self.project)


class FakeLLMClient(LLMClient):
    """Returns a canned tool call keyed by the tool name the caller requested."""

    def __init__(self, tool_responses: dict[str, dict]):
        self._tool_responses = tool_responses

    def create_message(self, *, system, messages, tools=None, max_tokens=4096) -> LLMResponse:
        assert tools, "expected at least one tool definition"
        name = tools[0]["name"]
        if name not in self._tool_responses:
            raise AssertionError(f"no fake response configured for tool {name!r}")
        return LLMResponse(
            text="",
            tool_calls=[ToolCall(id="fake-call-1", name=name, input=self._tool_responses[name])],
            stop_reason="tool_use",
        )


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        anthropic_api_key="test-key",
        claude_model="claude-test",
        gitlab_url="https://gitlab.example.com",
        gitlab_token="test-token",
        gitlab_project_id="1",
        dry_run=True,
        audit_log_path=tmp_path / "audit.log",
        _env_file=None,
    )


@pytest.fixture
def audit_logger(settings) -> AuditLogger:
    return AuditLogger(settings.audit_log_path)


@pytest.fixture
def fake_issue() -> FakeIssue:
    return FakeIssue()


@pytest.fixture
def fake_project(fake_issue) -> FakeProject:
    return FakeProject(
        fake_issue,
        files={
            "README.md": "# Demo project\nConventions...",
            "src/api/users.py": "def list_users(): ...\n",
        },
    )


@pytest.fixture
def fake_gl(fake_project) -> FakeGitlabSdk:
    return FakeGitlabSdk(fake_project)


@pytest.fixture
def gitlab_client(settings, audit_logger, fake_gl) -> GitLabClient:
    return GitLabClient(settings=settings, audit_logger=audit_logger, gl=fake_gl)


@pytest.fixture
def fake_llm_factory():
    def _make(tool_responses: dict[str, dict]) -> FakeLLMClient:
        return FakeLLMClient(tool_responses)

    return _make
