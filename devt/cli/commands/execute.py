import logging
from pathlib import Path
from typing import List, Optional
from typing_extensions import Annotated
import typer

from devt.config_manager import USER_REGISTRY_DIR, WORKSPACE_REGISTRY_DIR, WORKSPACE_APP_DIR
from devt.registry.manager import ScriptRegistry, PackageRegistry, create_db_engine
from devt.package.manager import PackageBuilder
from devt.package.script import Script
from devt.utils import find_file_type

execute_app = typer.Typer(help="Script execution and utility commands")
logger = logging.getLogger(__name__)

@execute_app.command("do")
def run_script(
    tool_command: str = typer.Argument(..., help="Unique tool command"),
    script_name: str = typer.Argument(..., help="Name of the script to execute"),
    scope: str = typer.Option("both", "--scope", help="Registry scope: 'workspace', 'user', or 'both' (default both)"),
    extra_args: Annotated[Optional[List[str]], typer.Argument()] = None,
):
    """
    Executes a script from an installed tool package.
    """
    if extra_args is None:
        extra_args = []
    typer.echo(f"Executing script with parameters: {extra_args}")

    scope = scope.lower()
    if scope not in ("workspace", "user", "both"):
        typer.echo("Invalid scope. Choose from 'workspace', 'user', or 'both'.")
        raise typer.Exit(code=1)

    # Instantiate separate registry instances for scripts and packages
    workspace_engine = create_db_engine(registry_path=WORKSPACE_REGISTRY_DIR)
    workspace_script_registry = ScriptRegistry(workspace_engine)
    workspace_package_registry = PackageRegistry(workspace_engine)
    user_engine = create_db_engine(registry_path=USER_REGISTRY_DIR)
    user_script_registry = ScriptRegistry(user_engine)
    user_package_registry = PackageRegistry(user_engine)

    # Build a list of (package_registry, script_registry) pairs based on the chosen scope
    registries: List[tuple[PackageRegistry, ScriptRegistry]] = []
    if scope == "workspace":
        registries.append((workspace_package_registry, workspace_script_registry))
    elif scope == "user":
        registries.append((user_package_registry, user_script_registry))
    else:  # both
        registries.append((workspace_package_registry, workspace_script_registry))
        registries.append((user_package_registry, user_script_registry))

    script_info = None
    pkg_info = None
    for pkg_reg, script_reg in registries:
        script_info = script_reg.get_script(tool_command, script_name)
        if script_info:
            pkg_info = pkg_reg.get_package(tool_command)
            break

    if script_info and pkg_info:
        try:
            script = Script.from_dict(script_info)
            base_dir = Path(pkg_info["location"])
            result = script.execute(base_dir, extra_args)
            typer.echo(f"Command executed with return code {result.returncode}")
        except Exception as err:
            typer.echo(f"Error executing script: {err}")
            raise typer.Exit(code=1)
    else:
        available_scripts = set()
        tool_found = False
        for pkg_reg, script_reg in registries:
            pkg = pkg_reg.get_package(tool_command)
            if pkg:
                tool_found = True
                for scr in script_reg.list_scripts(tool_command):
                    available_scripts.add(scr.get("script"))
        if tool_found:
            typer.echo(
                f"Script '{script_name}' not found for tool '{tool_command}'. "
                f"Available scripts: {sorted(available_scripts)}"
            )
        else:
            typer.echo(f"Tool '{tool_command}' not found in the specified scope '{scope}'.")
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
        typer.echo("Run 'devt project init' to create a new workspace.")
        raise typer.Exit(code=1)

    try:
        pb = PackageBuilder(package_path=workspace_file.parent)
        if script_name not in pb.scripts:
            typer.echo(f"Script '{script_name}' not found in the workspace package.")
            raise typer.Exit(code=1)
        script = pb.scripts[script_name]
    except Exception as e:
        typer.echo(f"Error building workspace package: {e}")
        raise typer.Exit(code=1)

    base_dir = workspace_file.parent.resolve()
    try:
        result = script.execute(base_dir, extra_args=extra_args)
        typer.echo(f"Command executed with return code {result.returncode}")
    except Exception as e:
        typer.echo(f"Error executing script: {e}")
        raise typer.Exit(code=1)

# Standardized tool script commands
@execute_app.command("install")
def install(
    tool_commands: List[str] = typer.Argument(..., help="Tool commands to install"),
    scope: str = typer.Option("both", "--scope", help="Registry scope: 'workspace', 'user', or 'both' (default: both)"),
):
    """
    Runs the 'install' script for each given tool.
    """
    for tool_command in tool_commands:
        run_script(tool_command, "install", scope=scope, extra_args=[])

@execute_app.command("uninstall")
def uninstall(
    tool_commands: List[str] = typer.Argument(..., help="Tool commands to uninstall"),
    scope: str = typer.Option("both", "--scope", help="Registry scope: 'workspace', 'user', or 'both' (default: both)"),
):
    """
    Runs the 'uninstall' script for each given tool.
    """
    for tool_command in tool_commands:
        run_script(tool_command, "uninstall", scope=scope, extra_args=[])

@execute_app.command("upgrade")
def upgrade(
    tool_commands: List[str] = typer.Argument(..., help="Tool commands to upgrade"),
    scope: str = typer.Option("both", "--scope", help="Registry scope: 'workspace', 'user', or 'both' (default: both)"),
):
    """
    Runs the 'upgrade' script for each given tool.
    """
    for tool_command in tool_commands:
        run_script(tool_command, "upgrade", scope=scope, extra_args=[])

@execute_app.command("version")
def version(
    tool_commands: List[str] = typer.Argument(..., help="Tool commands to display version"),
    scope: str = typer.Option("both", "--scope", help="Registry scope: 'workspace', 'user', or 'both' (default: both)"),
):
    """
    Runs the 'version' script for each given tool.
    """
    for tool_command in tool_commands:
        run_script(tool_command, "version", scope=scope, extra_args=[])

@execute_app.command("test")
def test(
    tool_commands: List[str] = typer.Argument(..., help="Tool commands to test"),
    scope: str = typer.Option("both", "--scope", help="Registry scope: 'workspace', 'user', or 'both' (default: both)"),
):
    """
    Runs tool-specific tests for each given tool.
    """
    for tool_command in tool_commands:
        run_script(tool_command, "test", scope=scope, extra_args=[])
