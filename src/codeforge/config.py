"""Centralized settings loaded from environment variables / .env (never hard-code secrets)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    anthropic_api_key: str = ""
    claude_model: str = "claude-sonnet-4-5-20250929"

    gitlab_url: str = "https://gitlab.com"
    gitlab_token: str = ""
    gitlab_project_id: str = ""

    # Safety default: no writes reach GitLab until explicitly disabled.
    dry_run: bool = True
    audit_log_path: Path = Path(".codeforge/audit.log")


@lru_cache
def get_settings() -> Settings:
    return Settings()
