"""Specification Agent: derives a technical spec from intake context via Claude tool-calling,
posts it to the GitLab issue as a comment, and gates the Implementation Agent behind a human
approval label (nothing proceeds automatically).
"""
from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, Field

from codeforge.agents.intake import IntakeResult
from codeforge.audit import AuditLogger, get_audit_logger
from codeforge.config import Settings, get_settings
from codeforge.gitlab_client import GitLabClient
from codeforge.llm.base import LLMClient

AGENT_NAME = "specification-agent"

# A human adds this label to the issue to let the Implementation Agent proceed.
APPROVAL_LABEL = "codeforge::spec-approved"

_SUBMIT_SPEC_TOOL_NAME = "submit_technical_spec"

_SYSTEM_PROMPT = """You are the Specification Agent in an automated GitLab development pipeline.
Given a GitLab issue and repository context, derive a precise, minimal technical specification.
Be concrete: name real files/functions where possible, keep scope tight to what the issue asks for,
and always propose concrete unit test cases. If requirements are ambiguous, list them as open
questions instead of guessing. Respond only by calling the submit_technical_spec tool."""


class TechnicalSpec(BaseModel):
    summary: str = Field(description="One paragraph summary of the proposed technical approach.")
    affected_components: list[str] = Field(description="Files/modules/services that need to change.")
    api_interfaces: list[str] = Field(
        default_factory=list, description="New or changed API endpoints/functions, one per entry."
    )
    data_models: list[str] = Field(
        default_factory=list, description="New or changed data models/schemas, one per entry."
    )
    test_cases: list[str] = Field(
        description="Concrete unit test cases the Implementation Agent should scaffold."
    )
    open_questions: list[str] = Field(
        default_factory=list,
        description="Ambiguities that need human clarification before implementation.",
    )

    def to_markdown(self) -> str:
        def section(title: str, items: list[str]) -> str:
            if not items:
                return ""
            bullets = "\n".join(f"- {item}" for item in items)
            return f"### {title}\n{bullets}\n\n"

        md = "## 🤖 Technical Specification (drafted by codeforge)\n\n"
        md += f"{self.summary}\n\n"
        md += section("Affected components", self.affected_components)
        md += section("API interfaces", self.api_interfaces)
        md += section("Data models", self.data_models)
        md += section("Test cases", self.test_cases)
        md += section("Open questions", self.open_questions)
        md += (
            f"\n---\n_Add the `{APPROVAL_LABEL}` label to this issue to approve this spec "
            "and let the Implementation Agent proceed._"
        )
        return md


@dataclass
class SpecificationResult:
    spec: TechnicalSpec
    posted: bool


class SpecificationAgent:
    def __init__(
        self,
        llm_client: LLMClient,
        gitlab_client: GitLabClient,
        settings: Settings | None = None,
        audit_logger: AuditLogger | None = None,
    ):
        self._llm = llm_client
        self._gitlab = gitlab_client
        self._settings = settings or get_settings()
        self._audit = audit_logger or get_audit_logger(self._settings)

    def run(self, intake: IntakeResult, *, post_to_issue: bool = True) -> SpecificationResult:
        spec = self._draft_spec(intake)

        self._audit.log(
            AGENT_NAME,
            "spec_drafted",
            dry_run=self._settings.dry_run,
            issue_iid=intake.issue.iid,
            affected_components=spec.affected_components,
            test_case_count=len(spec.test_cases),
        )

        posted = False
        if post_to_issue:
            self._gitlab.add_issue_comment(intake.issue.iid, spec.to_markdown())
            self._gitlab.set_issue_labels(
                intake.issue.iid, [*intake.issue.labels, "codeforge::spec-drafted"]
            )
            posted = True

        return SpecificationResult(spec=spec, posted=posted)

    def is_approved(self, issue_iid: int) -> bool:
        """Approval gate: a human must add APPROVAL_LABEL before the Implementation Agent runs."""
        issue = self._gitlab.get_issue_context(issue_iid)
        return APPROVAL_LABEL in issue.labels

    def _draft_spec(self, intake: IntakeResult) -> TechnicalSpec:
        tool = {
            "name": _SUBMIT_SPEC_TOOL_NAME,
            "description": "Submit the structured technical specification for this issue.",
            "input_schema": TechnicalSpec.model_json_schema(),
        }

        response = self._llm.create_message(
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": self._build_user_message(intake)}],
            tools=[tool],
            max_tokens=2048,
        )

        for call in response.tool_calls:
            if call.name == _SUBMIT_SPEC_TOOL_NAME:
                return TechnicalSpec.model_validate(call.input)

        raise RuntimeError(
            "Specification Agent: model did not call submit_technical_spec "
            f"(stop_reason={response.stop_reason!r}, text={response.text!r})"
        )

    @staticmethod
    def _build_user_message(intake: IntakeResult) -> str:
        parts = [
            f"## Issue #{intake.issue.iid}: {intake.issue.title}",
            intake.issue.description or "(no description)",
        ]
        if intake.issue.notes:
            parts.append("### Discussion\n" + "\n".join(f"- {n}" for n in intake.issue.notes))
        if intake.readme:
            parts.append("### Repository README\n" + intake.readme)
        for path, content in intake.referenced_files.items():
            parts.append(f"### Referenced file: {path}\n```\n{content}\n```")
        return "\n\n".join(parts)
