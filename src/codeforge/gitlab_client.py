"""GitLab API wrapper. All writes respect DRY_RUN and are recorded in the audit log.

Reads (fetching issue context) always hit the real API since they are non-destructive and are
needed even in dry-run mode to demo the pipeline end to end.
"""
from __future__ import annotations

import posixpath
from dataclasses import dataclass, field
from typing import Any

import gitlab

from codeforge.audit import AuditLogger, get_audit_logger
from codeforge.config import Settings, get_settings


class UnsafeFilePathError(ValueError):
    """Raised when a generated file path would escape the repo root or is absolute."""


def _assert_safe_repo_path(path: str) -> None:
    if not path or path.startswith(("/", "~")) or "\x00" in path:
        raise UnsafeFilePathError(f"unsafe file path: {path!r}")
    normalized = posixpath.normpath(path)
    if normalized == ".." or normalized.startswith("../"):
        raise UnsafeFilePathError(f"path escapes the repository root: {path!r}")


@dataclass
class IssueContext:
    iid: int
    title: str
    description: str
    labels: list[str]
    notes: list[str]
    web_url: str


@dataclass
class ActionResult:
    """Result of a write action. `dry_run=True` means nothing was actually sent to GitLab."""

    dry_run: bool
    detail: dict[str, Any] = field(default_factory=dict)


class GitLabClient:
    AGENT_NAME = "gitlab-client"

    def __init__(
        self,
        settings: Settings | None = None,
        audit_logger: AuditLogger | None = None,
        gl: gitlab.Gitlab | None = None,
    ):
        self._settings = settings or get_settings()
        self._audit = audit_logger or get_audit_logger(self._settings)
        self._gl = gl or gitlab.Gitlab(
            self._settings.gitlab_url,
            private_token=self._settings.gitlab_token,
            timeout=self._settings.request_timeout_seconds,
            retry_transient_errors=True,
        )
        self._project = None

    @property
    def project(self):
        if self._project is None:
            self._project = self._gl.projects.get(self._settings.gitlab_project_id)
        return self._project

    def _log(self, action: str, **details: Any) -> None:
        self._audit.log(self.AGENT_NAME, action, dry_run=self._settings.dry_run, **details)

    # ---- reads: no writes involved, always executed for real ----

    def get_issue_context(self, issue_iid: int) -> IssueContext:
        issue = self.project.issues.get(issue_iid)
        notes = [n.body for n in issue.notes.list(all=True) if not n.system]
        context = IssueContext(
            iid=issue.iid,
            title=issue.title,
            description=issue.description or "",
            labels=list(issue.labels),
            notes=notes,
            web_url=issue.web_url,
        )
        self._log("read_issue", issue_iid=issue_iid, title=context.title)
        return context

    def get_repo_file(self, file_path: str, ref: str = "main") -> str | None:
        """Returns decoded file content, or None if the file doesn't exist at `ref`."""
        try:
            f = self.project.files.get(file_path=file_path, ref=ref)
        except gitlab.exceptions.GitlabGetError:
            return None
        return f.decode().decode("utf-8")

    # ---- writes: short-circuit and log when dry_run is enabled ----

    def add_issue_comment(self, issue_iid: int, body: str) -> ActionResult:
        self._log("add_issue_comment", issue_iid=issue_iid, body_preview=body[:200])
        if self._settings.dry_run:
            return ActionResult(dry_run=True, detail={"issue_iid": issue_iid, "body": body})
        issue = self.project.issues.get(issue_iid)
        note = issue.notes.create({"body": body})
        return ActionResult(dry_run=False, detail={"note_id": note.id})

    def set_issue_labels(self, issue_iid: int, labels: list[str]) -> ActionResult:
        self._log("set_issue_labels", issue_iid=issue_iid, labels=labels)
        if self._settings.dry_run:
            return ActionResult(dry_run=True, detail={"issue_iid": issue_iid, "labels": labels})
        issue = self.project.issues.get(issue_iid)
        issue.labels = labels
        issue.save()
        return ActionResult(dry_run=False, detail={"labels": labels})

    def ensure_branch(self, branch_name: str, ref: str = "main") -> ActionResult:
        self._log("ensure_branch", branch_name=branch_name, ref=ref)
        if self._settings.dry_run:
            return ActionResult(dry_run=True, detail={"branch": branch_name, "ref": ref})
        try:
            self.project.branches.get(branch_name)
        except gitlab.exceptions.GitlabGetError:
            self.project.branches.create({"branch": branch_name, "ref": ref})
        return ActionResult(dry_run=False, detail={"branch": branch_name})

    def commit_files(
        self,
        branch: str,
        commit_message: str,
        files: dict[str, str],
        default_action: str = "create",
        actions_by_path: dict[str, str] | None = None,
    ) -> ActionResult:
        """`default_action` applies unless a path has an override in `actions_by_path`
        (e.g. "update" for a file that already exists vs "create" for a new one)."""
        try:
            for path in files:
                _assert_safe_repo_path(path)
        except UnsafeFilePathError as exc:
            self._log("commit_files_rejected", branch=branch, reason=str(exc))
            raise

        overrides = actions_by_path or {}
        actions = [
            {
                "action": overrides.get(path, default_action),
                "file_path": path,
                "content": content,
            }
            for path, content in files.items()
        ]
        self._log(
            "commit_files", branch=branch, files=list(files.keys()), commit_message=commit_message
        )
        if self._settings.dry_run:
            return ActionResult(dry_run=True, detail={"branch": branch, "files": list(files.keys())})
        commit = self.project.commits.create(
            {"branch": branch, "commit_message": commit_message, "actions": actions}
        )
        return ActionResult(dry_run=False, detail={"commit_sha": commit.id})

    def open_merge_request(
        self,
        source_branch: str,
        target_branch: str,
        title: str,
        description: str,
        labels: list[str] | None = None,
    ) -> ActionResult:
        self._log(
            "open_merge_request",
            source_branch=source_branch,
            target_branch=target_branch,
            title=title,
        )
        if self._settings.dry_run:
            return ActionResult(
                dry_run=True,
                detail={
                    "source_branch": source_branch,
                    "target_branch": target_branch,
                    "title": title,
                },
            )
        mr = self.project.mergerequests.create(
            {
                "source_branch": source_branch,
                "target_branch": target_branch,
                "title": title,
                "description": description,
                "labels": labels or [],
            }
        )
        return ActionResult(dry_run=False, detail={"mr_iid": mr.iid, "web_url": mr.web_url})
