from codeforge.agents.specification import APPROVAL_LABEL
from codeforge.orchestrator import Orchestrator

SPEC_PAYLOAD = {
    "summary": "Add offset/limit pagination to the users list endpoint.",
    "affected_components": ["src/api/users.py"],
    "test_cases": ["test_list_users_paginates_with_offset_and_limit"],
}
SCAFFOLD_PAYLOAD = {
    "commit_summary": "Add pagination to users API",
    "files": [{"path": "src/api/users.py", "content": "def list_users(offset=0, limit=20): ...\n"}],
    "mr_description": "Adds offset/limit pagination as specified.",
}


def test_pipeline_stops_after_spec_when_not_approved(
    gitlab_client, settings, audit_logger, fake_project, fake_llm_factory
):
    settings.dry_run = False  # verify the spec-drafted label is actually written
    llm = fake_llm_factory({"submit_technical_spec": SPEC_PAYLOAD})
    orchestrator = Orchestrator(
        settings=settings, gitlab_client=gitlab_client, llm_client=llm, audit_logger=audit_logger
    )

    result = orchestrator.run(fake_project.issue.iid)

    assert result.awaiting_approval is True
    assert result.implementation is None
    assert "codeforge::spec-drafted" in fake_project.issue.labels


def test_pipeline_implements_once_approved(
    gitlab_client, settings, audit_logger, fake_project, fake_llm_factory
):
    fake_project.issue.labels.append(APPROVAL_LABEL)
    llm = fake_llm_factory(
        {"submit_technical_spec": SPEC_PAYLOAD, "submit_code_scaffold": SCAFFOLD_PAYLOAD}
    )
    orchestrator = Orchestrator(
        settings=settings, gitlab_client=gitlab_client, llm_client=llm, audit_logger=audit_logger
    )

    result = orchestrator.run(fake_project.issue.iid)

    assert result.awaiting_approval is False
    assert result.implementation is not None
    assert result.implementation.branch.startswith(f"codeforge/{fake_project.issue.iid}-")


def test_status_updates_are_written_for_every_stage(
    gitlab_client, settings, audit_logger, fake_project, fake_llm_factory
):
    fake_project.issue.labels.append(APPROVAL_LABEL)
    llm = fake_llm_factory(
        {"submit_technical_spec": SPEC_PAYLOAD, "submit_code_scaffold": SCAFFOLD_PAYLOAD}
    )
    orchestrator = Orchestrator(
        settings=settings, gitlab_client=gitlab_client, llm_client=llm, audit_logger=audit_logger
    )

    orchestrator.run(fake_project.issue.iid)

    log_lines = settings.audit_log_path.read_text().splitlines()
    jira_actions = [
        line for line in log_lines if '"agent": "jira-feedback"' in line
    ]
    assert len(jira_actions) >= 6  # one per pipeline stage
