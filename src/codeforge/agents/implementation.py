"""Implementation Agent: creates a branch, generates code scaffolding + unit tests via
Claude tool-calling, commits them, and opens a Merge Request with a change summary.

Callers must confirm SpecificationAgent.is_approved(issue_iid) before invoking this agent —
it does not re-check the approval gate itself, keeping the human-in-the-loop decision in one place.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from pydantic import BaseModel, Field

from codeforge.agents.intake import IntakeResult
from codeforge.agents.specification import TechnicalSpec
from codeforge.audit import AuditLogger, get_audit_logger
from codeforge.config import Settings, get_settings
from codeforge.gitlab_client import ActionResult, GitLabClient
from codeforge.llm.base import LLMClient

AGENT_NAME = "implementation-agent"

_SUBMIT_SCAFFOLD_TOOL_NAME = "submit_code_scaffold"

_SYSTEM_PROMPT = """You are the Implementation Agent in an automated GitLab development pipeline.
You are given an approved technical spec and repository context. Generate a minimal, runnable code
scaffold that satisfies the spec: implement the affected components and include at least one unit
test file per test case in the spec. Follow the conventions visible in the referenced files/README
(naming, style, framework). Do not invent files unrelated to the spec. Respond only by calling the
submit_code_scaffold tool."""


class ScaffoldFile(BaseModel):
    path: str = Field(description="Repo-relative file path, e.g. src/api/users.py or tests/test_users.py")
    content: str = Field(description="Full file content to commit.")


class CodeScaffold(BaseModel):
    commit_summary: str = Field(description="One-line commit message subject, e.g. 'Add pagination to users API'.")
    files: list[ScaffoldFile] = Field(description="Code and unit test files to create or update.")
    mr_description: str = Field(
        description="Merge Request description: what changed, why, and how it maps to the spec."
    )


@dataclass
class ImplementationResult:
    branch: str
    files: list[str]
    commit: ActionResult
    merge_request: ActionResult


class ImplementationAgent:
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

    def run(self, intake: IntakeResult, spec: TechnicalSpec) -> ImplementationResult:
        scaffold = self._generate_scaffold(intake, spec)

        branch = self._branch_name(intake)
        self._gitlab.ensure_branch(branch, ref=intake.default_branch)

        files = {f.path: f.content for f in scaffold.files}
        actions_by_path = {
            path: ("update" if path in intake.referenced_files else "create") for path in files
        }
        commit = self._gitlab.commit_files(
            branch,
            commit_message=f"codeforge: {scaffold.commit_summary} (#{intake.issue.iid})",
            files=files,
            actions_by_path=actions_by_path,
        )

        mr = self._gitlab.open_merge_request(
            source_branch=branch,
            target_branch=intake.default_branch,
            title=f"Draft: {intake.issue.title} (closes #{intake.issue.iid})",
            description=self._mr_description(scaffold, list(files.keys())),
            labels=["codeforge::implemented"],
        )

        self._gitlab.add_issue_comment(
            intake.issue.iid,
            self._status_comment(branch, list(files.keys()), mr),
        )

        self._audit.log(
            AGENT_NAME,
            "implementation_complete",
            dry_run=self._settings.dry_run,
            issue_iid=intake.issue.iid,
            branch=branch,
            files=list(files.keys()),
        )

        return ImplementationResult(
            branch=branch, files=list(files.keys()), commit=commit, merge_request=mr
        )

    def _generate_scaffold(self, intake: IntakeResult, spec: TechnicalSpec) -> CodeScaffold:
        tool = {
            "name": _SUBMIT_SCAFFOLD_TOOL_NAME,
            "description": "Submit the generated code scaffold and unit tests for this spec.",
            "input_schema": CodeScaffold.model_json_schema(),
        }

        response = self._llm.create_message(
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": self._build_user_message(intake, spec)}],
            tools=[tool],
            max_tokens=8192,
        )

        for call in response.tool_calls:
            if call.name == _SUBMIT_SCAFFOLD_TOOL_NAME:
                return CodeScaffold.model_validate(call.input)

        raise RuntimeError(
            "Implementation Agent: model did not call submit_code_scaffold "
            f"(stop_reason={response.stop_reason!r}, text={response.text!r})"
        )

    @staticmethod
    def _build_user_message(intake: IntakeResult, spec: TechnicalSpec) -> str:
        parts = [
            f"## Approved technical spec for issue #{intake.issue.iid}: {intake.issue.title}",
            spec.model_dump_json(indent=2),
        ]
        if intake.readme:
            parts.append("### Repository README\n" + intake.readme)
        for path, content in intake.referenced_files.items():
            parts.append(f"### Existing file: {path}\n```\n{content}\n```")
        return "\n\n".join(parts)

    @staticmethod
    def _mr_description(scaffold: CodeScaffold, file_paths: list[str]) -> str:
        file_list = "\n".join(f"- `{path}`" for path in file_paths)
        return (
            f"{scaffold.mr_description}\n\n"
            f"### Files changed\n{file_list}\n\n"
            "---\n_Generated by codeforge's Implementation Agent. Review carefully before merging: "
            "AI-generated code and tests must be verified like any other contribution._"
        )

    @staticmethod
    def _status_comment(branch: str, file_paths: list[str], mr: ActionResult) -> str:
        header = "🚧 Dry run: would have opened a Merge Request" if mr.dry_run else "✅ Merge Request opened"
        mr_line = mr.detail.get("web_url", "(dry-run, no MR created)")
        return (
            f"{header}\n\n"
            f"- Branch: `{branch}`\n"
            f"- Files: {', '.join(f'`{p}`' for p in file_paths)}\n"
            f"- Merge Request: {mr_line}"
        )

    @staticmethod
    def _branch_name(intake: IntakeResult) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", intake.issue.title.lower()).strip("-")[:40].strip("-")
        return f"codeforge/{intake.issue.iid}-{slug}"
