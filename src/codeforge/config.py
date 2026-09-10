"""Centralized settings loaded from environment variables / .env (never hard-code secrets)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    anthropic_api_key: str = ""
    # "claude-sonnet-5" is the current model alias as of writing (verified against
    # platform.claude.com/docs). Re-check docs before relying on this if it's been a while —
    # Anthropic retires/renames models on a schedule.
    claude_model: str = "claude-sonnet-5"
    # Caps LLM calls per pipeline run/server session as a cost/abuse guardrail.
    max_llm_calls_per_run: int = 20

    gitlab_url: str = "https://gitlab.com"
    gitlab_token: str = ""
    gitlab_project_id: str = ""

    # Applied to both the Claude and GitLab clients: request timeout and retries on
    # transient errors (connection errors, 429s, 5xx).
    request_timeout_seconds: float = 30.0
    max_retries: int = 3

    # Safety default: no writes reach GitLab until explicitly disabled.
    dry_run: bool = True
    audit_log_path: Path = Path(".codeforge/audit.log")


@lru_cache
def get_settings() -> Settings:
    return Settings()
