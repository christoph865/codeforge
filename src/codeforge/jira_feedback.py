"""Jira feedback loop.

Real Jira credentials/API access are out of scope for this portfolio project, so this module
defines the adapter interface described in the pipeline (status updates written back to the
originating story) and a logging-only implementation. Swapping in a real Jira REST client later
means implementing `JiraFeedbackClient` — the Orchestrator doesn't change.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from codeforge.audit import AuditLogger, get_audit_logger
from codeforge.config import Settings, get_settings


class JiraFeedbackClient(ABC):
    @abstractmethod
    def post_status(self, story_key: str, status: str, detail: str) -> None: ...


class LoggingJiraFeedback(JiraFeedbackClient):
    """Writes Jira status updates to the audit log instead of a real Jira instance."""

    AGENT_NAME = "jira-feedback"

    def __init__(self, settings: Settings | None = None, audit_logger: AuditLogger | None = None):
        self._settings = settings or get_settings()
        self._audit = audit_logger or get_audit_logger(self._settings)

    def post_status(self, story_key: str, status: str, detail: str) -> None:
        # Always logged as dry-run: no real Jira write path exists in this stub.
        self._audit.log(
            self.AGENT_NAME,
            "status_update",
            dry_run=True,
            story_key=story_key,
            status=status,
            detail=detail,
        )
