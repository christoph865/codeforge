import pytest

from codeforge.agents.intake import IntakeAgent
from codeforge.agents.specification import APPROVAL_LABEL, SpecificationAgent, TechnicalSpec
from codeforge.llm.base import LLMClient, LLMResponse

SPEC_PAYLOAD = {
    "summary": "Add offset/limit pagination to the users list endpoint.",
    "affected_components": ["src/api/users.py"],
    "test_cases": ["test_list_users_paginates_with_offset_and_limit"],
}


def _intake(gitlab_client, settings, audit_logger, issue_iid):
    return IntakeAgent(gitlab_client, settings=settings, audit_logger=audit_logger).run(issue_iid)


def test_run_drafts_spec_posts_comment_and_labels(
    gitlab_client, settings, audit_logger, fake_project, fake_llm_factory
):
    intake = _intake(gitlab_client, settings, audit_logger, fake_project.issue.iid)
    settings.dry_run = False  # verify the comment/labels are actually written, not just logged
    llm = fake_llm_factory({"submit_technical_spec": SPEC_PAYLOAD})
    agent = SpecificationAgent(llm, gitlab_client, settings=settings, audit_logger=audit_logger)

    result = agent.run(intake)

    assert isinstance(result.spec, TechnicalSpec)
    assert result.spec.summary == SPEC_PAYLOAD["summary"]
    assert result.posted is True
    assert len(fake_project.issue.notes.list()) == 1
    assert "codeforge::spec-drafted" in fake_project.issue.labels


def test_run_without_posting_does_not_touch_the_issue(
    gitlab_client, settings, audit_logger, fake_project, fake_llm_factory
):
    intake = _intake(gitlab_client, settings, audit_logger, fake_project.issue.iid)
    llm = fake_llm_factory({"submit_technical_spec": SPEC_PAYLOAD})
    agent = SpecificationAgent(llm, gitlab_client, settings=settings, audit_logger=audit_logger)

    result = agent.run(intake, post_to_issue=False)

    assert result.posted is False
    assert fake_project.issue.notes.list() == []


def test_is_approved_reflects_label(gitlab_client, settings, audit_logger, fake_project, fake_llm_factory):
    agent = SpecificationAgent(fake_llm_factory({}), gitlab_client, settings=settings, audit_logger=audit_logger)

    assert agent.is_approved(fake_project.issue.iid) is False
    fake_project.issue.labels.append(APPROVAL_LABEL)
    assert agent.is_approved(fake_project.issue.iid) is True


def test_raises_if_model_never_calls_the_tool(gitlab_client, settings, audit_logger, fake_project):
    class NoToolLLM(LLMClient):
        def create_message(self, **kwargs):
            return LLMResponse(text="I have thoughts but no tool call.", tool_calls=[], stop_reason="end_turn")

    intake = _intake(gitlab_client, settings, audit_logger, fake_project.issue.iid)
    agent = SpecificationAgent(NoToolLLM(), gitlab_client, settings=settings, audit_logger=audit_logger)

    with pytest.raises(RuntimeError, match="did not call submit_technical_spec"):
        agent.run(intake)
