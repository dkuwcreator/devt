#!/usr/bin/env python3
"""
dev/cli/commands/dev.py

Development Commands

Provides commands to create, run, customize, and import tool packages.
"""

import json
import logging
from typing import Optional, List

from typing_extensions import Annotated
import yaml
import typer

from devt.cli.tool_service import ToolServiceWrapper
from devt.package.builder import PackageBuilder
from devt.utils import find_file_type
from devt.config_manager import WORKSPACE_APP_DIR

dev_app = typer.Typer(help="Tool development commands")
logger = logging.getLogger(__name__)

DEVELOP_DIR = WORKSPACE_APP_DIR / "devtlap"

def generate_workspace_template(command: str = "workspace") -> dict:
    cmd_display = command.capitalize()
    return {
        "name": f"{cmd_display} Wizard",
        "description": (
            f"Welcome to {cmd_display} Wizard, your hub for organized creativity! "
            f"Transform your {command} into a realm of efficiency and innovation, where every project finds its place."
        ),
        "command": command,
        "dependencies": {},
        "scripts": {
            "test": f"echo 'Verifying {command} integrity... All systems operational!'"
        },
    }

@dev_app.command("create")
def dev_create(
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
    target_ext = "json" if file_format_lower == "json" else "yaml"
    target_file = DEVELOP_DIR / command / f"manifest.{target_ext}"

    tool_template_dict = generate_workspace_template(command)
    if file_format_lower == "json":
        tool_template = json.dumps(tool_template_dict, indent=4)
    else:
        tool_template = yaml.dump(tool_template_dict, sort_keys=False)

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
    typer.echo(f"Tool '{command}' created successfully.")

@dev_app.command("customize")
def dev_customize(
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
    service = ToolServiceWrapper.from_context(ctx)
    service.export_tool(
        command, DEVELOP_DIR / command, as_zip=False, force=force
    )
    logger.info("Tool customization completed successfully for command: %s", command)
    typer.echo("Tool customization completed successfully.")

@dev_app.command("do")
def dev_do(
    command: str = typer.Argument(..., help="Unique tool command"),
    script_name: str = typer.Argument(..., help="Name of the script to execute"),
    extra_args: Annotated[
        Optional[List[str]], typer.Argument(help="Extra arguments")
    ] = None,
):
    """
    Executes a script from an installed tool package.
    """
    workspace_file = find_file_type("manifest", DEVELOP_DIR / command)
    pb = PackageBuilder(package_path=workspace_file.parent)
    if script_name not in pb.scripts:
        logger.error("Script '%s' not found in the workspace package.", script_name)
        raise ValueError(f"Script '{script_name}' not found in the workspace package.")

    script = pb.scripts[script_name]
    extra_args = extra_args or []
    logger.info("Executing script '%s' with parameters: %s", script_name, extra_args)

    base_dir = workspace_file.parent.resolve()
    script.execute(base_dir, extra_args=extra_args)
    logger.info("Script execution completed successfully.")

@dev_app.command("import")
def dev_import(
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
    service = ToolServiceWrapper.from_context(ctx)
    tool_path = DEVELOP_DIR / command
    service.import_tool(tool_path, group or "default", force)
    logger.info("Tool import completed successfully for command: %s", command)
    typer.echo("Tool import completed successfully.")
