import pytest

from codeforge.gitlab_client import GitLabClient, UnsafeFilePathError


def test_get_issue_context_reads_real_data(gitlab_client, fake_issue):
    ctx = gitlab_client.get_issue_context(fake_issue.iid)
    assert ctx.iid == fake_issue.iid
    assert ctx.title == fake_issue.title
    assert ctx.description == fake_issue.description


def test_get_repo_file_existing_and_missing(gitlab_client):
    assert gitlab_client.get_repo_file("README.md", ref="main") == "# Demo project\nConventions..."
    assert gitlab_client.get_repo_file("does/not/exist.py", ref="main") is None


def test_constructs_real_sdk_with_timeout_and_retry_enabled(settings, audit_logger, monkeypatch):
    captured = {}

    class FakeGitlabCtor:
        def __init__(self, url, private_token=None, timeout=None, retry_transient_errors=None):
            captured.update(
                url=url, timeout=timeout, retry_transient_errors=retry_transient_errors
            )
            self.projects = None

    monkeypatch.setattr("codeforge.gitlab_client.gitlab.Gitlab", FakeGitlabCtor)
    GitLabClient(settings=settings, audit_logger=audit_logger)

    assert captured == {
        "url": settings.gitlab_url,
        "timeout": settings.request_timeout_seconds,
        "retry_transient_errors": True,
    }


def test_dry_run_ensure_branch_does_not_touch_project(gitlab_client, fake_project):
    result = gitlab_client.ensure_branch("feature/x")
    assert result.dry_run is True
    assert fake_project.branches.created == []


def test_dry_run_commit_files_does_not_touch_project(gitlab_client, fake_project):
    result = gitlab_client.commit_files("feature/x", "msg", {"a.py": "pass\n"})
    assert result.dry_run is True
    assert fake_project.commits.commits == []


def test_dry_run_open_merge_request_does_not_touch_project(gitlab_client, fake_project):
    result = gitlab_client.open_merge_request("feature/x", "main", "title", "desc")
    assert result.dry_run is True
    assert fake_project.mergerequests.created == []


@pytest.mark.parametrize(
    "unsafe_path",
    [
        "/etc/passwd",
        "../../etc/passwd",
        "src/../../outside.py",
        "~/secrets.py",
    ],
)
def test_commit_files_rejects_unsafe_paths(gitlab_client, fake_project, unsafe_path):
    with pytest.raises(UnsafeFilePathError):
        gitlab_client.commit_files("feature/x", "msg", {unsafe_path: "pass\n"})
    assert fake_project.commits.commits == []


def test_commit_files_allows_normal_relative_paths(gitlab_client, fake_project):
    result = gitlab_client.commit_files("feature/x", "msg", {"src/api/new_file.py": "pass\n"})
    assert result.dry_run is True


def test_dry_run_add_issue_comment_and_set_labels(gitlab_client, fake_project, fake_issue):
    gitlab_client.add_issue_comment(fake_issue.iid, "hello")
    gitlab_client.set_issue_labels(fake_issue.iid, ["a", "b"])
    assert fake_project.issue.notes.list() == []
    assert fake_project.issue.labels == []


def test_live_writes_reach_the_fake_sdk_when_dry_run_disabled(settings, audit_logger, fake_gl, fake_project):
    settings.dry_run = False
    client = GitLabClient(settings=settings, audit_logger=audit_logger, gl=fake_gl)

    client.ensure_branch("feature/x", ref="main")
    assert fake_project.branches.created == [{"branch": "feature/x", "ref": "main"}]

    client.add_issue_comment(fake_project.issue.iid, "hello")
    assert [n.body for n in fake_project.issue.notes.list()] == ["hello"]

    client.commit_files("feature/x", "msg", {"a.py": "pass\n"}, actions_by_path={"a.py": "update"})
    assert fake_project.commits.commits[0]["actions"][0]["action"] == "update"

    client.open_merge_request("feature/x", "main", "title", "desc")
    assert len(fake_project.mergerequests.created) == 1
