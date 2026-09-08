"""Intake Agent: pulls a validated GitLab issue and gathers the context the
Specification Agent needs (repo README + any files referenced in the discussion).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from codeforge.audit import AuditLogger, get_audit_logger
from codeforge.config import Settings, get_settings
from codeforge.gitlab_client import GitLabClient, IssueContext

AGENT_NAME = "intake-agent"

# Matches path-like tokens in issue text, e.g. `src/foo/bar.py` or `app/models.ts`.
_FILE_REF_PATTERN = re.compile(r"[\w./-]+\.(?:py|ts|tsx|js|jsx|java|go|rb|yaml|yml|json|md)")


@dataclass
class IntakeResult:
    issue: IssueContext
    default_branch: str
    readme: str | None
    referenced_files: dict[str, str] = field(default_factory=dict)


class IntakeAgent:
    def __init__(
        self,
        gitlab_client: GitLabClient,
        settings: Settings | None = None,
        audit_logger: AuditLogger | None = None,
    ):
        self._gitlab = gitlab_client
        self._settings = settings or get_settings()
        self._audit = audit_logger or get_audit_logger(self._settings)

    def run(self, issue_iid: int) -> IntakeResult:
        issue = self._gitlab.get_issue_context(issue_iid)
        default_branch = self._gitlab.project.default_branch or "main"
        readme = self._gitlab.get_repo_file("README.md", ref=default_branch)

        referenced_files: dict[str, str] = {}
        for path in self._extract_file_references(issue):
            content = self._gitlab.get_repo_file(path, ref=default_branch)
            if content is not None:
                referenced_files[path] = content

        self._audit.log(
            AGENT_NAME,
            "intake_complete",
            dry_run=self._settings.dry_run,
            issue_iid=issue_iid,
            referenced_files=list(referenced_files.keys()),
            has_readme=readme is not None,
        )

        return IntakeResult(
            issue=issue,
            default_branch=default_branch,
            readme=readme,
            referenced_files=referenced_files,
        )

    @staticmethod
    def _extract_file_references(issue: IssueContext) -> set[str]:
        text = "\n".join([issue.title, issue.description, *issue.notes])
        return set(_FILE_REF_PATTERN.findall(text))
