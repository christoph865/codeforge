"""codeforge CLI: run the intake -> specification -> implementation pipeline against a GitLab
issue, or start the MCP server for external agent clients."""
from __future__ import annotations

import anthropic
import gitlab
import typer
from rich.console import Console

from codeforge.gitlab_client import UnsafeFilePathError
from codeforge.llm.budget import LLMBudgetExceeded
from codeforge.orchestrator import Orchestrator

app = typer.Typer(help="codeforge: automated spec-to-code AI agent chain for GitLab.")
console = Console()


@app.command("run-issue")
def run_issue(
    issue_iid: int = typer.Argument(..., help="GitLab issue IID to run the pipeline against."),
    jira_story_key: str = typer.Option(None, help="Optional Jira story key for the feedback loop."),
) -> None:
    """Run the full pipeline (intake -> spec -> approval gate -> implementation) for one issue."""
    try:
        result = Orchestrator().run(issue_iid, jira_story_key=jira_story_key)
    except ValueError as exc:
        console.print(f"[red]Configuration error:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    except gitlab.exceptions.GitlabError as exc:
        console.print(f"[red]GitLab API error:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    except anthropic.AnthropicError as exc:
        console.print(f"[red]Claude API error:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    except LLMBudgetExceeded as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    except UnsafeFilePathError as exc:
        console.print(f"[red]Refused to write an unsafe file path:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    console.print(f"[bold]Spec drafted:[/bold] {result.specification.spec.summary}")
    if result.awaiting_approval:
        console.print(
            "[yellow]Awaiting human approval[/yellow] — add the "
            "'codeforge::spec-approved' label to the issue, then re-run this command."
        )
        raise typer.Exit(code=0)

    impl = result.implementation
    console.print(f"[green]Implementation complete:[/green] branch {impl.branch}")
    console.print(f"Files: {', '.join(impl.files)}")
    console.print(f"Merge request: {impl.merge_request.detail}")


@app.command("mcp-server")
def mcp_server() -> None:
    """Start the MCP server so external MCP-compatible clients can drive the pipeline."""
    from codeforge.mcp_server import run_server

    try:
        run_server()
    except ValueError as exc:
        console.print(f"[red]Configuration error:[/red] {exc}")
        raise typer.Exit(code=1) from exc


if __name__ == "__main__":
    app()
