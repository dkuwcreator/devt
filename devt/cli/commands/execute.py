import logging
from pathlib import Path
from typing import List, Optional
from typing_extensions import Annotated
import typer

from devt.cli.helpers import get_package_from_registries
from devt.config_manager import WORKSPACE_APP_DIR
from devt.package.manager import PackageBuilder
from devt.package.script import Script
from devt.utils import find_file_type

execute_app = typer.Typer(help="Script execution and utility commands")
logger = logging.getLogger(__name__)


@execute_app.command("do")
def run_script(
    command: str = typer.Argument(..., help="Unique tool command"),
    script_name: str = typer.Argument(..., help="Name of the script to execute"),
    extra_args: Annotated[Optional[List[str]], typer.Argument(help="Extra arguments")] = None,
    scope: str = typer.Option(
        "both",
        "--scope",
        help="Registry scope: 'workspace', 'user', or 'both' (default both)",
    ),
):
    """
    Executes a script from an installed tool package.
    """
    extra_args = extra_args or []
    logger.info(f"Executing script with parameters: {extra_args}")

    scope = scope.lower()
    if scope not in ("workspace", "user", "both"):
        typer.echo("Invalid scope. Choose from 'workspace', 'user', or 'both'.")
        raise typer.Exit(code=1)

    # Instantiate separate registry instances for scripts and packages
    pkg, scope = get_package_from_registries(command, scope)

    if not pkg:
        logger.error(f"Tool '{command}' not found in the specified scope '{scope}'.")
        raise typer.Exit(code=1)

    scripts = pkg.get("scripts", {})

    if script_name not in scripts and scripts:
        typer.echo(
            f"Script '{script_name}' not found for tool '{command}'. "
            f"Available scripts: {sorted(scripts.keys())}"
        )
        raise typer.Exit(code=1)

    try:
        script = Script.from_dict(scripts.get(script_name))
        base_dir = Path(pkg["location"])
        result = script.execute(base_dir, extra_args)
        logger.info(f"Command executed with return code {result.returncode}")
    except Exception as err:
        logger.error(f"Error executing script: {err}")
        raise typer.Exit(code=1)


@execute_app.command("run")
def run_workspace(
    script_name: str = typer.Argument(..., help="Name of the script to execute"),
    extra_args: Annotated[Optional[List[str]], typer.Argument()] = None,
):
    """
    Executes a script from the workspace package using the PackageBuilder.
    """
    if extra_args is None:
        extra_args = []
    workspace_file = find_file_type("manifest", WORKSPACE_APP_DIR)
    if not workspace_file.exists():
        typer.echo("No workspace file found in the current directory.")
        typer.echo("Run 'devt workspace init' to create a new workspace.")
        raise typer.Exit(code=1)

    try:
        pb = PackageBuilder(package_path=workspace_file.parent)
        if script_name not in pb.scripts:
            logger.error(f"Script '{script_name}' not found in the workspace package.")
            raise typer.Exit(code=1)
        script = pb.scripts[script_name]
    except Exception as e:
        logger.error(f"Error building workspace package: {e}")
        raise typer.Exit(code=1)

    base_dir = workspace_file.parent.resolve()
    try:
        result = script.execute(base_dir, extra_args=extra_args)
        logger.info(f"Command executed with return code {result.returncode}")
    except Exception as e:
        logger.error(f"Error executing script: {e}")
        raise typer.Exit(code=1)


# Standardized tool script commands
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
    Runs the 'install' script for each given tool.
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
    Runs the 'uninstall' script for each given tool.
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
    Runs the 'upgrade' script for each given tool.
    """
    for tool_command in tool_commands:
        run_script(tool_command, "upgrade", scope=scope, extra_args=[])


@execute_app.command("version")
def version(
    tool_commands: List[str] = typer.Argument(
        ..., help="Tool commands to display version"
    ),
    scope: str = typer.Option(
        "both",
        "--scope",
        help="Registry scope: 'workspace', 'user', or 'both' (default: both)",
    ),
):
    """
    Runs the 'version' script for each given tool.
    """
    for tool_command in tool_commands:
        run_script(tool_command, "version", scope=scope, extra_args=[])


@execute_app.command("test")
def test(
    tool_commands: List[str] = typer.Argument(..., help="Tool commands to test"),
    scope: str = typer.Option(
        "both",
        "--scope",
        help="Registry scope: 'workspace', 'user', or 'both' (default: both)",
    ),
):
    """
    Runs tool-specific tests for each given tool.
    """
    for tool_command in tool_commands:
        run_script(tool_command, "test", scope=scope, extra_args=[])
