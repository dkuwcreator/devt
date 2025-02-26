#!/usr/bin/env python
"""
devt/cli/main.py

Entry point for the DevT CLI.
"""

import typer
import logging
from pathlib import Path
from typing import Optional, Dict, Any

from devt.cli.helpers import setup_app_context, get_managers
from devt.cli.sync_service import SyncManager
from devt.cli.commands.config import config_app
from devt.cli.commands.repo import is_git_installed, repo_app
from devt.cli.commands.tool import tool_app
from devt.cli.commands.project import project_app
from devt.cli.commands.self import self_app
from devt.cli.commands.execute import execute_app

from devt.config_manager import USER_REGISTRY_DIR, CONFIG_FILE
from devt.registry.manager import RegistryManager
from devt.package.manager import PackageManager
from devt.repo_manager import RepoManager
from devt.utils import load_json

logger = logging.getLogger(__name__)
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
    Configure environment, load persistent configuration, and initialize managers before any command runs.
    """
    logger.info("Initializing application context with scope=%s, log_level=%s, log_format=%s", scope, log_level, log_format)
    setup_app_context(ctx, scope, log_level, log_format, auto_sync)
    logger.info("App context successfully set up.")

    if not ctx.invoked_subcommand:
        typer.echo("No command provided. Use --help for usage.")
        logger.warning("No subcommand invoked. Exiting.")
        raise typer.Exit(code=1)

    # Determine auto_sync setting from CLI or persisted configuration.
    config: Dict[str, Any] = ctx.obj.get("config", {})
    # If auto_sync is enabled and Git is installed, use the managers already in the context.
    if config.get("auto_sync", False):
        logger.info("Auto-sync option is enabled.")
        if is_git_installed():
            if ctx.invoked_subcommand != "repo":
                logger.info("Git is installed and subcommand is not 'repo'; starting auto-sync.")
                sync_manager = SyncManager.from_context(ctx)
                sync_manager.start_background_sync(ctx)
            else:
                logger.info("Subcommand is 'repo'; skipping auto-sync.")
        else:
            logger.warning("Git is not installed; auto-sync will not be started.")


# Add grouped commands
app.add_typer(config_app, name="config")
app.add_typer(repo_app, name="repo")
app.add_typer(tool_app, name="tool")
app.add_typer(project_app, name="project")
app.add_typer(self_app, name="self")

# Flatten the execute commands into the main app
app.add_typer(execute_app, name="")

if __name__ == "__main__":
    logger.info("Starting DevT CLI application.")
    app()
