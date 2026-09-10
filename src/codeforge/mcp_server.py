"""MCP server exposing the codeforge pipeline as tools for any MCP-compatible client
(Claude Desktop, custom agents, etc.), built on the official Model Context Protocol SDK.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any

from mcp.server.mcpserver import MCPServer

from codeforge.agents.implementation import ImplementationAgent
from codeforge.agents.intake import IntakeAgent
from codeforge.agents.specification import SpecificationAgent
from codeforge.config import get_settings
from codeforge.gitlab_client import GitLabClient
from codeforge.llm import get_llm_client
from codeforge.llm.base import LLMClient
from codeforge.orchestrator import Orchestrator

mcp_server = MCPServer("codeforge")


@lru_cache
def _gitlab_client() -> GitLabClient:
    return GitLabClient(settings=get_settings())


@lru_cache
def _llm_client() -> LLMClient:
    # Shared (and budgeted) across every agent for the lifetime of the server process.
    return get_llm_client(get_settings())


@lru_cache
def _intake_agent() -> IntakeAgent:
    return IntakeAgent(_gitlab_client(), settings=get_settings())


@lru_cache
def _spec_agent() -> SpecificationAgent:
    return SpecificationAgent(_llm_client(), _gitlab_client(), settings=get_settings())


@lru_cache
def _impl_agent() -> ImplementationAgent:
    return ImplementationAgent(_llm_client(), _gitlab_client(), settings=get_settings())


@mcp_server.tool()
def fetch_issue(issue_iid: int) -> dict[str, Any]:
    """Fetch a GitLab issue plus repo context (README, referenced files) via the Intake Agent."""
    result = _intake_agent().run(issue_iid)
    return {
        "iid": result.issue.iid,
        "title": result.issue.title,
        "description": result.issue.description,
        "labels": result.issue.labels,
        "default_branch": result.default_branch,
        "referenced_files": list(result.referenced_files.keys()),
        "has_readme": result.readme is not None,
    }


@mcp_server.tool()
def draft_spec(issue_iid: int) -> dict[str, Any]:
    """Draft a technical spec for a GitLab issue and post it as an issue comment for approval."""
    intake = _intake_agent().run(issue_iid)
    result = _spec_agent().run(intake)
    return result.spec.model_dump()


@mcp_server.tool()
def check_spec_approval(issue_iid: int) -> dict[str, Any]:
    """Check whether a human has approved the drafted spec (added the approval label)."""
    return {"approved": _spec_agent().is_approved(issue_iid)}


@mcp_server.tool()
def implement(issue_iid: int) -> dict[str, Any]:
    """Generate a code scaffold + tests and open a Merge Request. Requires an approved spec."""
    if not _spec_agent().is_approved(issue_iid):
        return {"status": "blocked", "reason": "spec not yet approved by a human reviewer"}

    intake = _intake_agent().run(issue_iid)
    # Recovered from the issue thread itself so it's exactly what was approved, not a fresh re-draft.
    spec = _spec_agent().get_posted_spec(issue_iid)
    if spec is None:
        spec = _spec_agent().run(intake, post_to_issue=False).spec

    result = _impl_agent().run(intake, spec)
    return {
        "branch": result.branch,
        "files": result.files,
        "merge_request": result.merge_request.detail,
    }


@mcp_server.tool()
def run_pipeline(issue_iid: int) -> dict[str, Any]:
    """Run the full intake -> spec -> approval gate -> implementation pipeline for one issue."""
    result = Orchestrator().run(issue_iid)
    return {
        "awaiting_approval": result.awaiting_approval,
        "spec_summary": result.specification.spec.summary,
        "implementation": (
            None
            if result.implementation is None
            else {
                "branch": result.implementation.branch,
                "files": result.implementation.files,
                "merge_request": result.implementation.merge_request.detail,
            }
        ),
    }


def run_server() -> None:
    mcp_server.run()
