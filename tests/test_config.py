from codeforge.config import Settings


def test_defaults_are_safe():
    s = Settings(_env_file=None)
    assert s.dry_run is True
    assert s.gitlab_url == "https://gitlab.com"
    assert s.llm_provider == "claude"
    assert s.claude_model == "claude-sonnet-5"
    assert s.gemini_model == "gemini-2.5-flash"
    assert s.max_llm_calls_per_run == 20
    assert s.max_retries == 3
    assert s.request_timeout_seconds == 30.0


def test_env_vars_override_defaults(monkeypatch):
    monkeypatch.setenv("DRY_RUN", "false")
    monkeypatch.setenv("GITLAB_PROJECT_ID", "12345")
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    s = Settings(_env_file=None)
    assert s.dry_run is False
    assert s.gitlab_project_id == "12345"
    assert s.llm_provider == "gemini"
