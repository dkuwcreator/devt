#!/usr/bin/env python3
"""
devt/cli/commands/workspace.py

Workspace Management Commands

Provides commands to initialize, customize, and manage the workspace package.
"""

import json
import logging
from typing import Optional, List

from typing_extensions import Annotated
import yaml
from pathlib import Path
import typer

from devt.cli.tool_service import ToolService
from devt.package.builder import PackageBuilder
from devt.utils import find_file_type
from devt.config_manager import WORKSPACE_APP_DIR

workspace_app = typer.Typer(help="Project-level commands")
logger = logging.getLogger(__name__)

WORKSPACE_TEMPLATE = {
    "name": "Workspace Wizard",
    "description": "Welcome to Workspace Wizard, your hub for organized creativity! Transform your workspace into a realm of efficiency and innovation, where every project finds its place.",
    "command": "workspace",
    "dependencies": {},
    "scripts": {
        "test": "echo 'Verifying workspace integrity... All systems operational!'"
    },
}


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
        workspace_content = json.dumps(WORKSPACE_TEMPLATE, indent=4)
    else:
        target_file = WORKSPACE_APP_DIR / "manifest.yaml"
        workspace_content = yaml.dump(WORKSPACE_TEMPLATE, sort_keys=False)

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

    logger.info(
        "Project initialized successfully with %s format.", file_format_lower.upper()
    )


@workspace_app.command("info")
def workspace_info():
    """
    Displays workspace configuration settings (read-only).
    """
    workspace_file = find_file_type("manifest", WORKSPACE_APP_DIR)
    if workspace_file.exists():
        typer.echo(workspace_file.read_text())
    else:
        typer.echo("No workspace file found. Run 'devt workspace init' first.")


@workspace_app.command("create")
def workspace_create(
    command: str = typer.Argument(..., help="Name of the new local tool command"),
    file_format: str = typer.Option(
        "yaml", "--format", help="File format: 'yaml' (default) or 'json'."
    ),
    force: bool = typer.Option(
        False, "--force", help="Force creation even if the tool exists"
    ),
):
    """
    Creates a new local tool in the develop folder.
    """
    file_format_lower = file_format.lower()
    if file_format_lower == "json":
        target_file = WORKSPACE_APP_DIR / "develop" / command / "manifest.json"
        tool_template = json.dumps(
            {
                "name": command,
                "description": f"A new tool for command '{command}'.",
                "command": command,
                "dependencies": {},
                "scripts": {},
            },
            indent=4,
        )
    else:
        target_file = WORKSPACE_APP_DIR / "develop" / command / "manifest.yaml"
        tool_template = yaml.dump(
            {
                "name": command,
                "description": f"A new tool for command '{command}'.",
                "command": command,
                "dependencies": {},
                "scripts": {},
            },
            sort_keys=False,
        )

    target_dir = target_file.parent
    target_dir.mkdir(parents=True, exist_ok=True)

    if target_file.exists() and not force:
        logger.warning("Tool '%s' already exists. Use --force to overwrite.", command)
        raise ValueError(f"Tool '{command}' already exists. Use --force to overwrite.")

    target_file.write_text(tool_template)
    logger.info(
        "Tool '%s' created successfully with %s format.",
        command,
        file_format_lower.upper(),
    )


@workspace_app.command("customize")
def workspace_customize(
    ctx: typer.Context,
    command: str = typer.Argument(..., help="Name of the tool in the develop folder"),
    force: bool = typer.Option(
        False, "--force", help="Force overwrite if the tool already exists"
    ),
):
    """
    Copies a tool package to the develop folder for customization.
    """
    logger.info("Starting tool customization: command=%s, force=%s", command, force)
    service = ToolService.from_context(ctx)
    service.export_tool(
        command, WORKSPACE_APP_DIR / "develop", as_zip=False, force=force
    )
    logger.info("Tool customization completed successfully for command: %s", command)


@workspace_app.command("do")
def workspace_do(
    command: str = typer.Argument(..., help="Unique tool command"),
    script_name: str = typer.Argument(..., help="Name of the script to execute"),
    extra_args: Annotated[
        Optional[List[str]], typer.Argument(help="Extra arguments")
    ] = None,
):
    """
    Executes a script from an installed tool package.
    """
    workspace_file = find_file_type("manifest", WORKSPACE_APP_DIR / "develop" / command)
    pb = PackageBuilder(package_path=workspace_file.parent)
    if script_name not in pb.scripts:
        logger.error("Script '%s' not found in the workspace package.", script_name)
        raise ValueError(f"Script '{script_name}' not found in the workspace package.")

    script = pb.scripts[script_name]
    extra_args = extra_args or []
    logger.info("Executing script '%s' with parameters: %s", script_name, extra_args)

    base_dir = workspace_file.parent.resolve()
    result = script.execute(base_dir, extra_args=extra_args)
    logger.info(
        "Script '%s' executed with return code %s", script_name, result.returncode
    )


@workspace_app.command("import")
def workspace_import(
    ctx: typer.Context,
    command: str = typer.Argument(..., help="Name of the tool in the develop folder"),
    force: bool = typer.Option(
        False, "--force", help="Force overwrite if the tool already exists"
    ),
    group: str = typer.Option(
        None, "--group", help="Custom group name for the tool package (optional)"
    ),
):
    """
    Imports a local tool package from the develop folder.
    """
    logger.info(
        "Starting tool import: command=%s, force=%s, group=%s", command, force, group
    )
    service = ToolService.from_context(ctx)
    tool_path = WORKSPACE_APP_DIR / "develop" / command
    service.import_tool(tool_path, group or "default", force)
    logger.info("Tool import completed successfully for command: %s", command)
