#!/usr/bin/env python
"""
devt/cli.py

DevT: A CLI tool for managing development tool packages.
This file defines subcommands for repository management, tool management,
script execution, project-level controls, and meta commands.
"""

import json
import subprocess
import shutil
import logging
from pathlib import Path
from typing import List, Optional

import typer

# Import support modules and classes
from registry_manager import Registry
from package_manager import PackageManager, Script
from repo_manager import RepoManager
from devt_cli import __version__  # Assume __version__ is defined in devt_cli/__init__.py

# Initialize Typer main app and sub-apps
app = typer.Typer(help="DevT: A CLI tool for managing development tool packages.")
repo_app = typer.Typer(help="Repository management commands")
tool_app = typer.Typer(help="Tool management commands")  # formerly package_app
project_app = typer.Typer(help="Project-level commands")
self_app = typer.Typer(help="DevT self management commands")

# Setup global directories
USER_REGISTRY_DIR = Path.home() / ".devt" / "user_registry"
WORKSPACE_REGISTRY_DIR = Path.home() / ".devt" / "workspace_registry"
TOOLS_DIR = USER_REGISTRY_DIR / "tools"
REPO_BASE_DIR = Path.home() / ".devt" / "repos"
WORKSPACE_DIR = Path.cwd() / ".devt_workspace"

# Instantiate support objects
user_registry = Registry(USER_REGISTRY_DIR)
workspace_registry = Registry(WORKSPACE_REGISTRY_DIR)
pkg_manager = PackageManager(TOOLS_DIR)
repo_manager = RepoManager(REPO_BASE_DIR)

# Utility: select registry by scope option (default: user)
def get_registry(scope: str) -> Registry:
    return workspace_registry if scope.lower() == "workspace" else user_registry


# =====================================================
# Repository Management Commands
# =====================================================
@repo_app.command("add")
def repo_add(
    source: str = typer.Argument(..., help="URL of the repository to add"),
    branch: str = typer.Option("main", "--branch", help="Git branch (default: main)"),
    sync: bool = typer.Option(True, "--sync/--no-sync", help="Enable auto-sync (default: sync)"),
    name: Optional[str] = typer.Option(None, "--name", help="Custom repository name")
):
    """
    Adds a repository containing tool packages to the registry.
    
    After cloning/syncing, all tools found in the repository are imported into the registry
    under a group named after the repository (or a custom name if provided).
    """
    repo_url = source
    repo_dir = repo_manager.add_repo(repo_url, branch=branch)
    if sync:
        repo_dir = repo_manager.sync_repo(repo_url, branch=branch)
    
    # Determine group name: use custom name if provided, otherwise the repository folder name.
    group_name = name if name else repo_dir.name
    typer.echo(f"Repository added at: {repo_dir} (group: {group_name})")
    
    # Import all tool packages from this repository and add them to the registry
    try:
        packages = pkg_manager.import_package(repo_dir, group=group_name)
        for pkg in packages:
            user_registry.add_package(
                pkg.command,
                pkg.name,
                pkg.description,
                str(pkg.location),
                pkg.dependencies,
                group=group_name,
            )
            for script_name, script in pkg.scripts.items():
                user_registry.add_script(pkg.command, script_name, script.to_dict())
        typer.echo(f"Imported {len(packages)} tool package(s) from repository '{group_name}'.")
    except Exception as e:
        typer.echo(f"Error importing packages from repository: {e}")


@repo_app.command("remove")
def repo_remove(
    repo_name: str = typer.Argument(..., help="Repository name to remove"),
    force: bool = typer.Option(False, "--force", help="Force removal")
):
    """
    Removes a repository and all its associated tools.
    
    This command deletes the repository folder from disk and removes all package entries
    in the registry that belong to the group named after the repository.
    """
    repo_dir = repo_manager.repos_dir / repo_name
    if not repo_dir.exists():
        typer.echo(f"Repository '{repo_name}' not found.")
        raise typer.Exit(code=1)
    
    if force:
        typer.echo(f"Force removing repository '{repo_name}'...")
    
    success = repo_manager.remove_repo(str(repo_dir))
    if success:
        typer.echo(f"Repository '{repo_name}' removed from disk.")
        # Remove registry entries in the group matching repo_name
        packages = user_registry.list_packages(group=repo_name)
        if packages:
            for pkg in packages:
                user_registry.delete_package(pkg["command"])
                for script in user_registry.list_scripts(pkg["command"]):
                    user_registry.delete_script(pkg["command"], script["script"])
            typer.echo(f"Removed {len(packages)} tool package(s) from registry under group '{repo_name}'.")
        else:
            typer.echo(f"No registry entries found for group '{repo_name}'.")
    else:
        typer.echo(f"Failed to remove repository '{repo_name}'.")


@repo_app.command("sync")
def repo_sync(
    repo_name: str = typer.Argument(..., help="Repository name to sync"),
    branch: str = typer.Option("main", "--branch", help="Git branch (default: main)")
):
    """
    Syncs a specific repository (pulls latest changes).
    """
    repo_dir = repo_manager.repos_dir / repo_name
    if not repo_dir.exists():
        typer.echo(f"Repository '{repo_name}' not found.")
        raise typer.Exit(code=1)
    updated_dir = repo_manager.sync_repo(str(repo_dir), branch=branch)
    typer.echo(f"Repository '{repo_name}' synced. Local path: {updated_dir}")


@repo_app.command("sync-all")
def repo_sync_all():
    """
    Synchronizes all repositories at once.
    """
    repos = list(repo_manager.repos_dir.iterdir())
    if not repos:
        typer.echo("No repositories found.")
        return
    for repo in repos:
        try:
            repo_manager.sync_repo(str(repo), branch="main")
            typer.echo(f"Synced repository: {repo.name}")
        except Exception as e:
            typer.echo(f"Failed to sync {repo.name}: {e}")


@repo_app.command("list")
def repo_list():
    """
    Displays all registered repositories and their status.
    """
    repos = list(repo_manager.repos_dir.iterdir())
    if repos:
        for repo in repos:
            typer.echo(repo.name)
    else:
        typer.echo("No repositories found.")


# =====================================================
# Tool Management Commands
# =====================================================
@tool_app.command("import")
def tool_import(
    path: Path = typer.Argument(..., help="Path to a manifest file or tool package directory"),
    scope: str = typer.Option("user", "--scope", help="Registry scope: user or workspace")
):
    """
    Imports a tool package (or multiple tool packages) into the registry from:
      - A manifest file (YAML/JSON)
      - A directory with one manifest (a single tool package)
      - A directory with multiple subdirectories (multiple tool packages)
    """
    registry = get_registry(scope)
    packages = pkg_manager.import_package(path)
    count = 0
    for pkg in packages:
        registry.add_package(pkg.command, pkg.name, pkg.description, str(pkg.location), pkg.dependencies, group=pkg.group)
        for script_name, script in pkg.scripts.items():
            registry.add_script(pkg.command, script_name, script.to_dict())
        count += 1
    typer.echo(f"Imported {count} tool package(s) into the {scope} registry.")


@tool_app.command("list")
def tool_list():
    """
    Lists all imported tool packages in the user registry.
    """
    packages = user_registry.list_packages()
    if packages:
        for pkg in packages:
            typer.echo(f"{pkg['command']} - {pkg['name']}")
    else:
        typer.echo("No tool packages found.")


@tool_app.command("remove")
def tool_remove(
    tool_command: str = typer.Argument(..., help="Unique tool command to remove"),
    scope: str = typer.Option("user", "--scope", help="Registry scope: user or workspace")
):
    """
    Removes a tool package from the specified scope.
    """
    registry = get_registry(scope)
    pkg_info = registry.get_package(tool_command)
    if not pkg_info:
        typer.echo(f"Tool '{tool_command}' not found in {scope} registry.")
        raise typer.Exit(code=1)
    pkg_location = Path(pkg_info["location"])
    if pkg_manager.delete_package(pkg_location):
        registry.delete_package(pkg_info["command"])
        for s in registry.list_scripts(pkg_info["command"]):
            registry.delete_script(pkg_info["command"], s["script"])
        typer.echo(f"Tool '{tool_command}' removed from {scope} registry.")
    else:
        typer.echo(f"Failed to remove tool '{tool_command}'.")


@tool_app.command("move")
def tool_move(
    tool_command: str = typer.Argument(..., help="Unique tool command to move"),
    to: str = typer.Option(..., "--to", help="Target registry: user or workspace")
):
    """
    Moves a tool package from one registry to the other (user ⇄ workspace).
    """
    src_registry = user_registry if user_registry.get_package(tool_command) else workspace_registry
    target_registry = get_registry(to)
    pkg_info = src_registry.get_package(tool_command)
    if not pkg_info:
        typer.echo(f"Tool '{tool_command}' not found in source registry.")
        raise typer.Exit(code=1)
    current_location = Path(pkg_info["location"])
    target_tools_dir = target_registry.registry_path / "tools"
    target_tools_dir.mkdir(parents=True, exist_ok=True)
    target_location = target_tools_dir / current_location.name
    try:
        shutil.copytree(current_location, target_location)
    except Exception as e:
        typer.echo(f"Error copying tool folder: {e}")
        raise typer.Exit(code=1)
    new_pkg = pkg_manager.import_package(target_location)[0]
    target_registry.add_package(new_pkg.command, new_pkg.name, new_pkg.description, str(new_pkg.location), new_pkg.dependencies)
    for script_name, script in new_pkg.scripts.items():
        target_registry.add_script(new_pkg.command, script_name, script.to_dict())
    src_registry.delete_package(pkg_info["command"])
    for s in src_registry.list_scripts(pkg_info["command"]):
        src_registry.delete_script(pkg_info["command"], s["script"])
    try:
        shutil.rmtree(current_location)
    except Exception as e:
        typer.echo(f"Error removing source tool folder: {e}")
    typer.echo(f"Tool '{tool_command}' moved to {to} registry.")


@tool_app.command("export")
def tool_export(
    tool_command: str = typer.Argument(..., help="Unique tool command to export"),
    output: Path = typer.Argument(..., help="Output zip archive path"),
    scope: str = typer.Option("user", "--scope", help="Registry scope: user or workspace")
):
    """
    Exports a tool package as a ZIP archive.
    """
    registry = get_registry(scope)
    pkg_info = registry.get_package(tool_command)
    if not pkg_info:
        typer.echo(f"Tool '{tool_command}' not found in {scope} registry.")
        raise typer.Exit(code=1)
    pkg_location = Path(pkg_info["location"])
    output = (Path.cwd() / output).resolve()
    pkg_manager.export_package(pkg_location, output)
    typer.echo(f"Tool '{tool_command}' exported to {output}.")


@tool_app.command("customize")
def tool_customize(
    tool_command: str = typer.Argument(..., help="Unique tool command to customize"),
    new_command: Optional[str] = typer.Option(None, "--new_command", help="New command name for the customized tool")
):
    """
    Copies a tool package from the user registry to the workspace for customization.
    Optionally renames the tool command.
    """
    pkg_info = user_registry.get_package(tool_command)
    if not pkg_info:
        typer.echo(f"Tool '{tool_command}' not found in user registry.")
        raise typer.Exit(code=1)
    pkg_location = Path(pkg_info["location"])
    new_pkg = pkg_manager.import_package(pkg_location)[0]
    if new_command:
        new_pkg.command = new_command
    workspace_registry.add_package(new_pkg.command, new_pkg.name, new_pkg.description, str(new_pkg.location), new_pkg.dependencies)
    for script_name, script in new_pkg.scripts.items():
        workspace_registry.add_script(new_pkg.command, script_name, script.to_dict())
    typer.echo(f"Tool '{tool_command}' customized to '{new_pkg.command}' in workspace registry.")


@tool_app.command("update")
def tool_update(
    tool_command: str = typer.Argument(..., help="Unique tool command to update"),
    manifest: Optional[Path] = typer.Option(None, "--manifest", help="Path to updated manifest file"),
    scope: str = typer.Option("user", "--scope", help="Registry scope: user or workspace")
):
    """
    Updates an existing tool package using an updated manifest file.
    """
    registry = get_registry(scope)
    pkg_info = registry.get_package(tool_command)
    if not pkg_info:
        typer.echo(f"Tool '{tool_command}' not found in {scope} registry.")
        raise typer.Exit(code=1)
    pkg_location = Path(pkg_info["location"])
    update_path = manifest if manifest else pkg_location
    new_pkg = pkg_manager.import_package(update_path)[0]
    registry.update_package(new_pkg.command, new_pkg.name, new_pkg.description, str(new_pkg.location), new_pkg.dependencies)
    for script_name, script in new_pkg.scripts.items():
        registry.update_script(new_pkg.command, script_name, script.to_dict())
    typer.echo(f"Tool '{tool_command}' updated in {scope} registry.")


# =====================================================
# Script Execution & Utility Commands
# =====================================================
@app.command("run")
def run_script(
    tool_command: str = typer.Argument(..., help="Unique tool command"),
    script_name: str = typer.Argument(..., help="Name of the script to execute"),
    extra_args: List[str] = typer.Argument(None, help="Extra arguments for the script"),
    scope: str = typer.Option("user", "--scope", help="Registry scope: user or workspace")
):
    """
    Executes a script from an installed tool package.
    """
    registry = get_registry(scope)
    pkg_info = registry.get_package(tool_command)
    if not pkg_info:
        typer.echo(f"Tool '{tool_command}' not found in {scope} registry.")
        raise typer.Exit(code=1)
    script_info = registry.get_script(tool_command, script_name)
    if not script_info:
        typer.echo(f"Script '{script_name}' not found in tool '{tool_command}'.")
        raise typer.Exit(code=1)
    script = Script.from_dict(script_info)
    base_dir = Path(pkg_info["location"])
    proc_args = script.prepare_subprocess_args(base_dir, extra_args)
    typer.echo(f"Executing command: {proc_args['args']}")
    subprocess.run(**proc_args)


@app.command("exec")
def exec_cmd(
    tool_command: str = typer.Argument(..., help="Unique tool command"),
    script_name: str = typer.Argument(..., help="Name of the script to execute"),
    extra_args: List[str] = typer.Argument(None, help="Extra arguments for the script")
):
    """
    Alias for 'devt run' that does not auto-sync the tool.
    """
    run_script(tool_command, script_name, extra_args)


# Standardized Tool Scripts (shorthand commands)
@app.command("install")
def install(tool_command: str = typer.Argument(..., help="Tool command to install")):
    """
    Runs the 'install' script for the given tool.
    """
    run_script(tool_command, "install", extra_args=[])


@app.command("uninstall")
def uninstall(tool_command: str = typer.Argument(..., help="Tool command to uninstall")):
    """
    Runs the 'uninstall' script for the given tool.
    """
    run_script(tool_command, "uninstall", extra_args=[])


@app.command("upgrade")
def upgrade(tool_command: str = typer.Argument(..., help="Tool command to upgrade")):
    """
    Runs the 'upgrade' script for a tool.
    """
    run_script(tool_command, "upgrade", extra_args=[])


@app.command("version")
def tool_version(tool_command: str = typer.Argument(..., help="Tool command to display version")):
    """
    Displays the version of a tool.
    """
    run_script(tool_command, "version", extra_args=[])


@app.command("test")
def test_tool(tool_command: str = typer.Argument(..., help="Tool command to test")):
    """
    Runs tool-specific tests.
    """
    run_script(tool_command, "test", extra_args=[])


# =====================================================
# Project-Level Commands
# =====================================================
@project_app.command("init")
def project_init():
    """
    Initializes a new development environment in the current project.
    Creates a workspace.json file and sets up directory structure.
    """
    workspace_file = Path("workspace.json")
    if workspace_file.exists():
        typer.echo("Project already initialized.")
    else:
        workspace_file.write_text(json.dumps({"tools": [], "scripts": {}}, indent=4))
        typer.echo("Project initialized successfully.")


@project_app.command("list")
def project_list():
    """
    Displays all tools registered in the project's workspace.json.
    """
    workspace_file = Path("workspace.json")
    if workspace_file.exists():
        typer.echo(workspace_file.read_text())
    else:
        typer.echo("No workspace.json found. Run 'devt project init' first.")


@project_app.command("info")
def project_info():
    """
    Displays project configuration settings.
    """
    workspace_file = Path("workspace.json")
    if workspace_file.exists():
        typer.echo(workspace_file.read_text())
    else:
        typer.echo("No workspace.json found.")


@project_app.command("install")
def project_install():
    """
    Installs all tools listed in workspace.json.
    """
    workspace_file = Path("workspace.json")
    if not workspace_file.exists():
        typer.echo("No workspace.json found. Run 'devt project init' first.")
        raise typer.Exit(code=1)
    try:
        workspace = json.loads(workspace_file.read_text())
        tools = workspace.get("tools", [])
        for tool in tools:
            run_script(tool, "install", extra_args=[])
        typer.echo("All project tools installed successfully.")
    except Exception as e:
        typer.echo(f"Failed to install project tools: {e}")


@project_app.command("run")
def project_run(script: str = typer.Argument(..., help="Script name to run globally")):
    """
    Executes a global script defined in workspace.json.
    """
    workspace_file = Path("workspace.json")
    if not workspace_file.exists():
        typer.echo("No workspace.json found. Run 'devt project init' first.")
        raise typer.Exit(code=1)
    try:
        workspace = json.loads(workspace_file.read_text())
        scripts = workspace.get("scripts", {})
        if script not in scripts:
            typer.echo(f"Script '{script}' not found in workspace.json.")
            raise typer.Exit(code=1)
        typer.echo(f"Executing project script: {scripts[script]}")
        # Optionally, you can use ManifestRunner to execute the script.
    except Exception as e:
        typer.echo(f"Failed to run project script: {e}")


@project_app.command("reset")
def project_reset(force: bool = typer.Option(False, "--force", help="Force removal")):
    """
    Removes all project-level tools.
    """
    workspace_file = Path("workspace.json")
    if workspace_file.exists():
        workspace_file.unlink()
        typer.echo("Project reset successfully.")
    else:
        typer.echo("No workspace.json found.")


# =====================================================
# Meta Commands
# =====================================================
@self_app.command("version")
def self_version():
    """
    Displays the current version of DevT.
    """
    typer.echo(f"DevT version: {__version__}")


@self_app.command("upgrade")
def self_upgrade():
    """
    Checks for updates and installs the latest version of DevT.
    """
    # This is a placeholder for actual upgrade logic.
    typer.echo("DevT upgraded successfully.")


@app.command("help")
def help_command(command: Optional[str] = None):
    """
    Displays documentation for DevT commands.
    """
    if command:
        typer.echo(f"Help for command: {command}")
    else:
        typer.echo(app.get_help())


# Add sub-apps to the main app
app.add_typer(repo_app, name="repo")
app.add_typer(tool_app, name="tool")
app.add_typer(project_app, name="project")
app.add_typer(self_app, name="self")

if __name__ == "__main__":
    app()
