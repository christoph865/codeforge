from codeforge.config import Settings


def test_defaults_are_safe():
    s = Settings(_env_file=None)
    assert s.dry_run is True
    assert s.gitlab_url == "https://gitlab.com"
    assert s.claude_model == "claude-sonnet-4-5-20250929"


def test_env_vars_override_defaults(monkeypatch):
    monkeypatch.setenv("DRY_RUN", "false")
    monkeypatch.setenv("GITLAB_PROJECT_ID", "12345")
    s = Settings(_env_file=None)
    assert s.dry_run is False
    assert s.gitlab_project_id == "12345"
