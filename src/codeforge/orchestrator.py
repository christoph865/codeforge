"""Orchestrator: wires Intake -> Specification -> (human approval gate) -> Implementation
for a single GitLab issue, writing status updates to the Jira feedback stub at each stage.
"""
from __future__ import annotations

from dataclasses import dataclass

from codeforge.agents.implementation import ImplementationAgent, ImplementationResult
from codeforge.agents.intake import IntakeAgent, IntakeResult
from codeforge.agents.specification import SpecificationAgent, SpecificationResult
from codeforge.config import Settings, get_settings
from codeforge.gitlab_client import GitLabClient
from codeforge.jira_feedback import JiraFeedbackClient, LoggingJiraFeedback
from codeforge.llm import get_llm_client
from codeforge.llm.base import LLMClient


@dataclass
class PipelineResult:
    intake: IntakeResult
    specification: SpecificationResult
    implementation: ImplementationResult | None
    awaiting_approval: bool


class Orchestrator:
    def __init__(
        self,
        settings: Settings | None = None,
        gitlab_client: GitLabClient | None = None,
        llm_client: LLMClient | None = None,
        jira_feedback: JiraFeedbackClient | None = None,
    ):
        self._settings = settings or get_settings()
        self._gitlab = gitlab_client or GitLabClient(settings=self._settings)
        self._llm = llm_client or get_llm_client(self._settings)
        self._jira = jira_feedback or LoggingJiraFeedback(self._settings)

        self._intake_agent = IntakeAgent(self._gitlab, settings=self._settings)
        self._spec_agent = SpecificationAgent(self._llm, self._gitlab, settings=self._settings)
        self._impl_agent = ImplementationAgent(self._llm, self._gitlab, settings=self._settings)

    def run(self, issue_iid: int, *, jira_story_key: str | None = None) -> PipelineResult:
        story_key = jira_story_key or f"GITLAB-{issue_iid}"

        self._jira.post_status(story_key, "intake_started", f"Pulling GitLab issue #{issue_iid}")
        intake = self._intake_agent.run(issue_iid)
        self._jira.post_status(story_key, "intake_complete", f"Context gathered for issue #{issue_iid}")

        self._jira.post_status(story_key, "spec_started", "Drafting technical specification")
        spec_result = self._spec_agent.run(intake)
        self._jira.post_status(story_key, "spec_drafted", "Technical spec posted, awaiting approval")

        if not self._spec_agent.is_approved(issue_iid):
            self._jira.post_status(story_key, "awaiting_approval", "Waiting for human approval label")
            return PipelineResult(
                intake=intake, specification=spec_result, implementation=None, awaiting_approval=True
            )

        self._jira.post_status(story_key, "implementation_started", "Generating code scaffold")
        implementation = self._impl_agent.run(intake, spec_result.spec)
        self._jira.post_status(
            story_key,
            "implementation_complete",
            f"Merge Request opened on branch {implementation.branch}",
        )

        return PipelineResult(
            intake=intake,
            specification=spec_result,
            implementation=implementation,
            awaiting_approval=False,
        )
