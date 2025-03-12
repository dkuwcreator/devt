#!/usr/bin/env python3
"""
devt/cli/commands/workspace.py

Workspace Management Commands

Provides commands to initialize, customize, and manage the workspace package.
"""

import json
import logging

import yaml
from pathlib import Path
import typer

from devt.constants import WORKSPACE_REGISTRY_DIR
from devt.utils import find_file_type, force_remove
from devt.config_manager import WORKSPACE_APP_DIR

workspace_app = typer.Typer(help="Project-level commands")
logger = logging.getLogger(__name__)

def generate_workspace_template(command: str = "workspace") -> dict:
    cmd_display = command.capitalize()
    return {
        "name": f"{cmd_display} Wizard",
        "description":f"Welcome to {cmd_display} Wizard, your hub for organized creativity!",
        "command": command,
        "dependencies": {},
        "scripts": {
            "test": f"echo 'Verifying {command} integrity... All systems operational!'"
        },
    }

@workspace_app.callback()
def main(ctx: typer.Context) -> None:
    """
    Manage repositories containing tool packages.
    """
    # Determine registry directory based on effective scope.
    effective_scope: str = ctx.obj.get("scope")
    if effective_scope.lower() == "workspace" and ctx.invoked_subcommand != "init":
        # Verify the current directory is a Git repository (optional check).
        git_repo = Path.cwd() / ".git"
        if not git_repo.exists():
            logger.debug("Workspace scope selected, but no Git repository found.")
            # Check if there's at least a workspace registry with a manifest.
            has_registry = WORKSPACE_REGISTRY_DIR.exists() and find_file_type("manifest", WORKSPACE_APP_DIR)
            if not has_registry:
                logger.error("No workspace registry found. Run 'devt workspace init' to create one.")
                raise FileNotFoundError("No workspace registry found. Run 'devt workspace init' first.")




@workspace_app.command("init")
def workspace_init(
    file_format: str = typer.Option(
        "yaml",
        "--format",
        help="File format to initialize the workspace. Options: 'yaml' (default) or 'json'.",
    ),
    force: bool = typer.Option(False, "--force", help="Force initialization"),
):
    """
    Initializes a new development environment in the current workspace.
    """
    file_format_lower = file_format.lower()
    if file_format_lower == "json":
        target_file = WORKSPACE_APP_DIR / "manifest.json"
        workspace_content = json.dumps(generate_workspace_template(), indent=4)
    else:
        target_file = WORKSPACE_APP_DIR / "manifest.yaml"
        workspace_content = yaml.dump(generate_workspace_template(), sort_keys=False)

    if target_file.exists() and not force:
        logger.warning("Project already initialized. Use --force to overwrite.")
        raise ValueError("Project already initialized. Use --force to overwrite.")

    target_file.write_text(workspace_content)
    logger.info("Workspace manifest file created at: %s", target_file)

    # If a .gitignore file exists, attempt to add DevTools entries automatically.
    gitignore_file = Path(".gitignore")
    if gitignore_file.exists():
        content = gitignore_file.read_text()
        append_lines = ""
        if "# DevTools" not in content:
            append_lines += "\n# DevTools"
        if ".registry" not in content:
            append_lines += "\n.registry"
        if append_lines:
            with gitignore_file.open("a") as f:
                f.write(append_lines)
            logger.info("Added DevTools entries to .gitignore")

    WORKSPACE_REGISTRY_DIR.mkdir(parents=True, exist_ok=True)

    logger.info(
        "Project initialized successfully with %s format.", file_format_lower.upper()
    )
    typer.echo("Project initialized successfully.")


@workspace_app.command("show")
def workspace_show():
    """
    Displays workspace configuration settings (read-only).
    """
    workspace_file = find_file_type("manifest", WORKSPACE_APP_DIR)
    if workspace_file.exists():
        typer.echo(workspace_file.read_text())
    else:
        typer.echo("No workspace file found. Run 'devt workspace init' first.")

@workspace_app.command("reset")
def workspace_reset():
    """
    Reset the workspace by removing the Registry directory.
    """
    logger.info("Resetting the application to its initial state.")
    # Delete the User Registry folder
    force_remove(WORKSPACE_REGISTRY_DIR)
    logger.info("Workspace Registry folder removed.")
    WORKSPACE_REGISTRY_DIR.mkdir(parents=True, exist_ok=True)
