from codeforge.agents.intake import IntakeAgent


def test_intake_gathers_readme_and_referenced_files(gitlab_client, settings, audit_logger, fake_issue):
    agent = IntakeAgent(gitlab_client, settings=settings, audit_logger=audit_logger)
    result = agent.run(fake_issue.iid)

    assert result.issue.iid == fake_issue.iid
    assert result.default_branch == "main"
    assert result.readme == "# Demo project\nConventions..."
    assert "src/api/users.py" in result.referenced_files


def test_intake_skips_referenced_paths_that_do_not_exist(gitlab_client, settings, audit_logger, fake_project):
    fake_project.issue.description = "See tests/test_users.py for expectations."
    agent = IntakeAgent(gitlab_client, settings=settings, audit_logger=audit_logger)
    result = agent.run(fake_project.issue.iid)

    assert "tests/test_users.py" not in result.referenced_files
