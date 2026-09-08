from codeforge.agents.implementation import ImplementationAgent
from codeforge.agents.intake import IntakeAgent
from codeforge.agents.specification import TechnicalSpec
from codeforge.gitlab_client import GitLabClient

SCAFFOLD_PAYLOAD = {
    "commit_summary": "Add pagination to users API",
    "files": [
        {"path": "src/api/users.py", "content": "def list_users(offset=0, limit=20): ...\n"},
        {"path": "tests/test_users.py", "content": "def test_list_users_paginates(): ...\n"},
    ],
    "mr_description": "Adds offset/limit pagination as specified.",
}


def _intake(gitlab_client, settings, audit_logger, issue_iid):
    return IntakeAgent(gitlab_client, settings=settings, audit_logger=audit_logger).run(issue_iid)


def test_run_creates_branch_commits_and_opens_mr(
    gitlab_client, settings, audit_logger, fake_project, fake_llm_factory
):
    intake = _intake(gitlab_client, settings, audit_logger, fake_project.issue.iid)
    spec = TechnicalSpec(
        summary="Add pagination", affected_components=["src/api/users.py"], test_cases=["t1"]
    )
    llm = fake_llm_factory({"submit_code_scaffold": SCAFFOLD_PAYLOAD})
    agent = ImplementationAgent(llm, gitlab_client, settings=settings, audit_logger=audit_logger)

    result = agent.run(intake, spec)

    assert result.branch.startswith(f"codeforge/{fake_project.issue.iid}-")
    assert result.files == ["src/api/users.py", "tests/test_users.py"]
    assert result.commit.dry_run is True
    assert result.merge_request.dry_run is True


def test_existing_file_is_updated_new_file_is_created(
    settings, audit_logger, fake_gl, fake_project, fake_llm_factory
):
    settings.dry_run = False
    client = GitLabClient(settings=settings, audit_logger=audit_logger, gl=fake_gl)
    intake = _intake(client, settings, audit_logger, fake_project.issue.iid)
    spec = TechnicalSpec(
        summary="Add pagination", affected_components=["src/api/users.py"], test_cases=["t1"]
    )
    llm = fake_llm_factory({"submit_code_scaffold": SCAFFOLD_PAYLOAD})
    agent = ImplementationAgent(llm, client, settings=settings, audit_logger=audit_logger)

    agent.run(intake, spec)

    actions = {a["file_path"]: a["action"] for a in fake_project.commits.commits[0]["actions"]}
    assert actions["src/api/users.py"] == "update"  # already existed in the repo
    assert actions["tests/test_users.py"] == "create"  # brand new file
