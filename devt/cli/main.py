#!/usr/bin/env python
"""
devt/cli/main.py

Entry point for the DevT CLI.
"""

import typer
import logging

from devt.cli.helpers import is_git_installed, setup_app_context
from devt.cli.commands.config import config_app
from devt.cli.commands.tool import tool_app
from devt.cli.commands.workspace import workspace_app
from devt.cli.commands.self import self_app
from devt.cli.commands.execute import execute_app

logger = logging.getLogger(__name__)
app = typer.Typer(help="DevT: A CLI tool for managing development tool packages.")


@app.callback()
def main(
    ctx: typer.Context,
    scope: str = typer.Option(
        None, help="Scope: user or workspace.", show_default=False
    ),
    log_level: str = typer.Option(None, help="Global log level.", show_default=False),
    log_format: str = typer.Option(
        None, help="Log format: default or detailed.", show_default=False
    ),
    auto_sync: bool = typer.Option(
        None,
        "--auto-sync",
        help="Enable background auto-sync for repositories.",
        show_default=False,
    ),
):
    """
    Configure environment, load persistent configuration, and initialize managers before any command runs.
    """
    logger.info(
        "Initializing application context with scope=%s, log_level=%s, log_format=%s",
        scope,
        log_level,
        log_format,
    )
    setup_app_context(ctx, scope, log_level, log_format, auto_sync)
    logger.info("App context successfully set up.")

    if not ctx.invoked_subcommand:
        typer.echo("No command provided. Use --help for usage.")
        logger.warning("No subcommand invoked. Exiting.")
        raise typer.Exit(code=1)


# Add grouped commands
app.add_typer(config_app, name="config")
app.add_typer(tool_app, name="tool")
app.add_typer(workspace_app, name="workspace")
app.add_typer(self_app, name="self")

if is_git_installed():
    from devt.cli.commands.repo import repo_app
    app.add_typer(repo_app, name="repo")


# Flatten the execute commands into the main app
app.add_typer(execute_app, name="")

if __name__ == "__main__":
    logger.info("Starting DevT CLI application.")
    app()
