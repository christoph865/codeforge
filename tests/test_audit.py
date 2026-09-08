import json

from codeforge.audit import AuditLogger


def test_log_redacts_secret_like_keys(tmp_path):
    logger = AuditLogger(tmp_path / "audit.log")
    logger.log("agent", "action", dry_run=True, gitlab_token="glpat-secret", note="ok")

    entry = json.loads((tmp_path / "audit.log").read_text().splitlines()[0])
    assert entry["gitlab_token"] == "<redacted>"
    assert entry["note"] == "ok"
    assert entry["agent"] == "agent"
    assert entry["action"] == "action"
    assert entry["dry_run"] is True


def test_log_appends_one_json_line_per_call(tmp_path):
    logger = AuditLogger(tmp_path / "audit.log")
    logger.log("a", "one", dry_run=True)
    logger.log("a", "two", dry_run=False)

    lines = (tmp_path / "audit.log").read_text().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[1])["action"] == "two"


def test_log_creates_parent_directories(tmp_path):
    path = tmp_path / "nested" / "dir" / "audit.log"
    AuditLogger(path).log("a", "one", dry_run=True)
    assert path.exists()
