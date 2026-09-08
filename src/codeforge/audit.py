"""Append-only JSON-lines audit log for every agent action (spec drafts, branches, commits, MRs, comments)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from codeforge.config import Settings, get_settings

_REDACT_KEYS = ("token", "api_key", "authorization", "password", "secret")


class AuditLogger:
    """Writes one JSON object per line; redacts any detail key that looks like a secret."""

    def __init__(self, log_path: Path):
        self.log_path = log_path
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def log(self, agent: str, action: str, *, dry_run: bool, **details: Any) -> None:
        safe_details = {
            key: ("<redacted>" if any(r in key.lower() for r in _REDACT_KEYS) else value)
            for key, value in details.items()
        }
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "agent": agent,
            "action": action,
            "dry_run": dry_run,
            **safe_details,
        }
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, default=str) + "\n")


_logger: AuditLogger | None = None


def get_audit_logger(settings: Settings | None = None) -> AuditLogger:
    """Process-wide singleton so every agent writes to the same audit trail."""
    global _logger
    if _logger is None:
        _logger = AuditLogger((settings or get_settings()).audit_log_path)
    return _logger
