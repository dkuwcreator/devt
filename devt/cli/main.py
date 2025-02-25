#!/usr/bin/env python
"""
devt/cli/main.py

Entry point for the DevT CLI.
"""

import typer
from devt.cli.helpers import setup_app_context
from devt.cli.commands.config import config_app
from devt.cli.commands.repo import is_git_installed, repo_app, start_background_auto_sync
from devt.cli.commands.tool import tool_app
from devt.cli.commands.project import project_app
from devt.cli.commands.self import self_app
from devt.cli.commands.execute import execute_app  # Import the execute app

app = typer.Typer(help="DevT: A CLI tool for managing development tool packages.")

@app.callback()
def main(
    ctx: typer.Context,
    scope: str = typer.Option(None, help="Scope: user or workspace.", show_default=False),
    log_level: str = typer.Option(None, help="Global log level.", show_default=False),
    log_format: str = typer.Option(None, help="Log format: default or detailed.", show_default=False),
    auto_sync: bool = typer.Option(None, "--auto-sync", help="Enable background auto-sync for repositories.", show_default=False),
):
    """
    Configure environment and initialize managers before any command runs.
    """
    setup_app_context(ctx, scope, log_level, log_format)
    if not ctx.invoked_subcommand:
        typer.echo("No command provided. Use --help for usage.")
        raise typer.Exit(code=1)
    # Don't auto sync if the invoked subcommand is repo
    if auto_sync and is_git_installed() and ctx.invoked_subcommand != "repo":
        start_background_auto_sync(ctx)

# Add grouped commands
app.add_typer(config_app, name="config")
app.add_typer(repo_app, name="repo")
app.add_typer(tool_app, name="tool")
app.add_typer(project_app, name="project")
app.add_typer(self_app, name="self")

# Flatten the execute commands into the main app
app.add_typer(execute_app, name="")

if __name__ == "__main__":
    app()
