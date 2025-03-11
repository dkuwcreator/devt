#!/usr/bin/env python3
"""
devt/cli/commands/execute.py

DevT Execute Commands

Provides commands to execute scripts from installed tools and the workspace package.
"""
import logging
from pathlib import Path
from typing import List, Optional
from typing_extensions import Annotated
import typer

# Removed: from devt.error_wrapper import handle_errors

from devt.cli.helpers import get_package_from_registries
from devt.config_manager import WORKSPACE_APP_DIR
from devt.package.manager import PackageBuilder
from devt.package.script import Script
from devt.utils import find_file_type

execute_app = typer.Typer(help="[Execute] Execution and utility commands")
logger = logging.getLogger(__name__)


@execute_app.command("do")
def run_script(
    command: str = typer.Argument(..., help="Unique tool command"),
    script_name: str = typer.Argument(..., help="Name of the script to execute"),
    extra_args: Annotated[
        Optional[List[str]], typer.Argument(help="Extra arguments")
    ] = None,
    scope: str = typer.Option(
        "both",
        "--scope",
        help="Registry scope: 'workspace', 'user', or 'both' (default both)",
    ),
):
    """
    [Execute] Executes a script from an installed tool package.
    """
    extra_args = extra_args or []
    logger.info("Executing script with parameters: %s", extra_args)

    scope = scope.lower()
    if scope not in ("workspace", "user", "both"):
        logger.error("Invalid scope. Choose from 'workspace', 'user', or 'both'.")
        raise ValueError("Invalid scope specified.")

    pkg, resolved_scope = get_package_from_registries(command, scope)
    if not pkg:
        logger.debug(
            "Tool '%s' not found in the specified scope '%s'.", command, resolved_scope
        )
        raise ValueError(f"Tool '{command}' not found in scope '{resolved_scope}'.")

    scripts = pkg.get("scripts", {})
    if script_name not in scripts and scripts:
        logger.error(
            "Script '%s' not found for tool '%s'. Available scripts: %s",
            script_name,
            command,
            sorted(scripts.keys()),
        )
        raise ValueError(f"Script '{script_name}' not found for tool '{command}'.")

    script = Script.from_dict(scripts.get(script_name))
    base_dir = Path(pkg["location"])
    script.execute(base_dir, extra_args)


@execute_app.command("run")
def run_workspace(
    script_name: str = typer.Argument(..., help="Name of the script to execute"),
    extra_args: Annotated[Optional[List[str]], typer.Argument()] = None,
):
    """
    [Execute] Executes a script from the workspace package using the PackageBuilder.
    """
    extra_args = extra_args or []
    workspace_file = find_file_type("manifest", WORKSPACE_APP_DIR)
    if not workspace_file:
        logger.error(
            "No workspace file found. Run 'devt workspace init' to create a new workspace."
        )
        raise ValueError("No workspace file found in the current directory.")

    pb = PackageBuilder(package_path=workspace_file.parent)
    if script_name not in pb.scripts:
        logger.error("Script '%s' not found in the workspace package.", script_name)
        raise ValueError(f"Script '{script_name}' not found in the workspace package.")

    base_dir = workspace_file.parent.resolve()
    pb.scripts[script_name].execute(base_dir, extra_args=extra_args)


@execute_app.command("install")
def install(
    tool_commands: List[str] = typer.Argument(..., help="Tool commands to install"),
    scope: str = typer.Option(
        "both",
        "--scope",
        help="Registry scope: 'workspace', 'user', or 'both' (default: both)",
    ),
):
    """
    [Execute] Runs the 'install' script for each given tool.
    """
    for tool_command in tool_commands:
        run_script(tool_command, "install", scope=scope, extra_args=[])


@execute_app.command("uninstall")
def uninstall(
    tool_commands: List[str] = typer.Argument(..., help="Tool commands to uninstall"),
    scope: str = typer.Option(
        "both",
        "--scope",
        help="Registry scope: 'workspace', 'user', or 'both' (default: both)",
    ),
):
    """
    [Execute] Runs the 'uninstall' script for each given tool.
    """
    for tool_command in tool_commands:
        run_script(tool_command, "uninstall", scope=scope, extra_args=[])


@execute_app.command("upgrade")
def upgrade(
    tool_commands: List[str] = typer.Argument(..., help="Tool commands to upgrade"),
    scope: str = typer.Option(
        "both",
        "--scope",
        help="Registry scope: 'workspace', 'user', or 'both' (default: both)",
    ),
):
    """
    [Execute] Runs the 'upgrade' script for each given tool.
    """
    for tool_command in tool_commands:
        run_script(tool_command, "upgrade", scope=scope, extra_args=[])
