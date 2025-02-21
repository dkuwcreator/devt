#!/usr/bin/env python
"""
devt/cli.py

DevT: A CLI tool for managing development tool packages.
This file defines subcommands for repository management, tool management,
script execution, project-level controls, and meta commands.
"""

import json
import logging
import shutil
from pathlib import Path
from typing import List, Optional
import yaml
import typer

# Import support modules and classes
from devt.utils import find_file_type
from devt.logger_manager import configure_formatter, configure_logging
from devt.registry_manager import Registry
from devt.package_manager import PackageBuilder, PackageManager, Script
from devt.repo_manager import RepoManager
from devt.config import (
    USER_APP_DIR,
    WORKSPACE_APP_DIR,
    WORKSPACE_REGISTRY_DIR,
    USER_REGISTRY_DIR,
    setup_environment,
)
from devt.package_manager import PackageManager
from devt import (
    __version__,
)  # Assume __version__ is defined in devt_cli/__init__.py

logger = logging.getLogger(__name__)

# Initialize Typer main app and sub-apps
app = typer.Typer(help="DevT: A CLI tool for managing development tool packages.")
repo_app = typer.Typer(help="Repository management commands")
tool_app = typer.Typer(help="Tool management commands")  # formerly package_app
project_app = typer.Typer(help="Project-level commands")
self_app = typer.Typer(help="DevT self management commands")

repo_manager = RepoManager(USER_REGISTRY_DIR)


# Utility: select registry by scope option (default: user)
def get_registry_dir(scope: str) -> Path:
    return WORKSPACE_REGISTRY_DIR if scope.lower() == "workspace" else USER_REGISTRY_DIR


# Define a callback to set runtime config settings
@app.callback()
def main(
    ctx: typer.Context,
    scope: str = typer.Option(
        "user",
        help="Scope of the command: user (default) or workspace.",
        show_default=False,
    ),
    log_level: str = typer.Option(
        "WARNING",
        help="Global log level (DEBUG, INFO, WARNING, ERROR). "
        "Default is WARNING. Overridable via DEVT_LOG_LEVEL env var.",
    ),
    log_format: str = typer.Option(
        "default",
        help="Log format type (default, detailed).",
        show_default=False,
    ),
):
    """
    Global callback to configure logging before any commands run.
    Loads and persists configuration settings between sessions.
    """

    # Determine the config file location
    config_file = USER_APP_DIR / "config.json"

    # Load saved configs if available and override defaults
    if config_file.exists():
        try:
            saved_config = json.loads(config_file.read_text())
            # Override options if saved values exist
            scope = saved_config.get("scope", scope)
            log_level = saved_config.get("log_level", log_level)
            log_format = saved_config.get("log_format", log_format)
        except Exception as e:
            typer.echo(f"Error loading config file: {e}")

    # Set up the environment and directories
    setup_environment()

    # Set scope-specific registry and tools directory
    registry_dir = get_registry_dir(scope)
    registry_manager = Registry(registry_dir)
    pkg_manager = PackageManager(registry_dir / "tools")

    # Set the global registry and pkg_manager for use in subcommands
    ctx.obj = {
        "scope": scope,
        "registry": registry_manager,
        "pkg_manager": pkg_manager,
    }

    # Configure logging settings
    configure_logging(log_level)
    configure_formatter(log_format)

    # Persist runtime configuration settings for future sessions
    config = {
        "scope": scope,
        "log_level": log_level,
        "log_format": log_format,
    }

    # If no subcommand is provided, show help
    if not ctx.invoked_subcommand:
        typer.echo("No command provided. Use --help for usage.")
        raise typer.Exit()


# Separate command to persist configuration settings for future sessions
@app.command("config")
def set_config(
    scope: Optional[str] = typer.Option(
        None,
        help="Persisted scope for future sessions: user or workspace.",
    ),
    log_level: Optional[str] = typer.Option(
        None,
        help="Persisted log level for future sessions (DEBUG, INFO, WARNING, ERROR).",
    ),
    log_format: Optional[str] = typer.Option(
        None,
        help="Persisted log format for future sessions: default or detailed.",
    ),
):
    """
    Persists configuration settings to be used in future sessions.
    Only the options provided will be updated.
    """
    config_file = USER_APP_DIR / "config.json"
    current_config = {}
    if config_file.exists():
        try:
            current_config = json.loads(config_file.read_text())
        except Exception as e:
            typer.echo(f"Error reading config file: {e}")

    if scope:
        current_config["scope"] = scope
    if log_level:
        current_config["log_level"] = log_level
    if log_format:
        current_config["log_format"] = log_format

    try:
        config_file.write_text(json.dumps(current_config, indent=4))
        typer.echo("Configuration settings have been persisted for future sessions.")
    except Exception as e:
        typer.echo(f"Error writing config file: {e}")


# =====================================================
# Repository Management Commands
# =====================================================
@repo_app.command("add")
def repo_add(
    ctx: typer.Context,
    source: str = typer.Argument(..., help="URL of the repository to add"),
    branch: Optional[str] = typer.Option(
        None,
        "--branch",
        help="Git branch to use (default is the repository's default branch)",
    ),
    sync: bool = typer.Option(
        True, "--sync/--no-sync", help="Enable auto-sync (default: sync)"
    ),
    name: Optional[str] = typer.Option(
        None, "--name", help="Custom repository name (for display purposes)"
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Force overwrite if repository, its packages, and registry entries already exist",
    ),
):
    """
    Adds a repository containing tool packages to the registry.

    After cloning/syncing, all tools found in the repository are imported into the registry.
    Note: The registry uses the repository URL as the primary key.
    """
    registry_manager: Registry = ctx.obj["registry"]
    pkg_manager: PackageManager = ctx.obj["pkg_manager"]
    repo_url = source
    logger.info("Starting to add repository with URL: %s", repo_url)

    # If force is enabled, attempt to remove any existing repository folder and registry entries.
    if force:
        # Remove repository folder if it exists.
        repo_candidate = repo_manager.repos_dir / Path(repo_url).stem
        if repo_candidate.exists():
            try:
                # Use force option in remove_repo if supported.
                repo_manager.remove_repo(str(repo_candidate))
                typer.echo(
                    f"Existing repository at '{repo_candidate}' removed due to force option."
                )
            except Exception as e:
                typer.echo(f"Error removing existing repository folder: {e}")

        # Remove previously registered repository entries and associated packages.
        try:
            # Delete registry entry for the repository if it exists.
            registry_manager.delete_repository(repo_url)
        except Exception:
            pass
        # Remove package entries associated with this repository.
        packages_existing = registry_manager.list_packages(group=repo_url)
        for pkg in packages_existing:
            registry_manager.delete_package(pkg["command"])
            for scr in registry_manager.list_scripts(pkg["command"]):
                registry_manager.delete_script(pkg["command"], scr["script"])

    # add_repo now returns a tuple (repo_dir, effective_branch)
    repo_dir, effective_branch = repo_manager.add_repo(repo_url, branch=branch)
    display_name = name if name else repo_dir.name
    typer.echo(
        f"Repository added at: {repo_dir} (name: {display_name}, url: {repo_url})"
    )
    logger.debug("Repository cloned at %s with branch %s", repo_dir, effective_branch)

    # Add the repository to the registry using the URL as the unique key.
    try:
        registry_manager.add_repository(
            url=repo_url,
            name=display_name,
            branch=effective_branch,
            location=str(repo_dir),
            auto_sync=sync,
        )
        logger.info("Repository '%s' added to the registry.", repo_url)
        typer.echo(f"Repository '{repo_url}' added to the registry.")
    except Exception as e:
        logger.exception("Error adding repository to registry:")
        typer.echo(f"Error adding repository to registry: {e}")
        raise typer.Exit(code=1)

    # Import all tool packages from this repository and add them to the registry,
    # associating them with the repository URL.
    try:
        logger.info("Importing tool packages from repository '%s'...", display_name)
        packages = pkg_manager.import_package(
            repo_dir, group=repo_dir.name, overwrite=force
        )
        for pkg in packages:
            # If force is enabled, remove existing package entries before adding.
            if force:
                if registry_manager.get_package(pkg.command):
                    registry_manager.delete_package(pkg.command)
                    for script in registry_manager.list_scripts(pkg.command):
                        registry_manager.delete_script(pkg.command, script["script"])
            registry_manager.add_package(
                pkg.command,
                pkg.name,
                pkg.description,
                str(pkg.location),
                pkg.dependencies,
                group=repo_dir.name,
            )
            for script_name, script in pkg.scripts.items():
                registry_manager.add_script(pkg.command, script_name, script.to_dict())
        logger.info(
            "Imported %d tool package(s) from repository '%s'.",
            len(packages),
            display_name,
        )
        typer.echo(
            f"Imported {len(packages)} tool package(s) from repository '{display_name}'."
        )
    except Exception as e:
        logger.exception("Error importing packages from repository:")
        typer.echo(f"Error importing packages from repository: {e}")


@repo_app.command("remove")
def repo_remove(
    ctx: typer.Context,
    repo_name: str = typer.Argument(..., help="Repository name to remove"),
    force: bool = typer.Option(False, "--force", help="Force removal"),
):
    """
    Removes a repository and all its associated tools.

    This command deletes the repository folder from disk and removes all package entries
    in the registry that belong to the group named after the repository. It also removes
    the packages using the package manager and deletes the repository entry from the registry.
    """
    registry_manager: Registry = ctx.obj["registry"]
    pkg_manager: PackageManager = ctx.obj["pkg_manager"]
    repo_dir = repo_manager.repos_dir / repo_name
    if not repo_dir.exists():
        typer.echo(f"Repository '{repo_name}' not found.")
        raise typer.Exit(code=1)

    if force:
        typer.echo(f"Force removing repository '{repo_name}'...")

    try:
        # Pass force flag to the removal method if supported by the repo manager.
        success = repo_manager.remove_repo(str(repo_dir))
    except Exception as e:
        typer.echo(f"Error removing repository '{repo_name}': {e}")
        raise typer.Exit(code=1)

    if success:
        typer.echo(f"Repository '{repo_name}' removed from disk.")

        # Remove registry entries and tool packages belonging to the repository group
        packages = registry_manager.list_packages(group=repo_name)
        if packages:
            removed_count = 0
            for pkg in packages:
                pkg_path = Path(pkg["location"])
                try:
                    if pkg_manager.delete_package(pkg_path):
                        removed_count += 1
                except Exception as e:
                    typer.echo(f"Error removing package at '{pkg_path}': {e}")
                registry_manager.delete_package(pkg["command"])
                for script in registry_manager.list_scripts(pkg["command"]):
                    registry_manager.delete_script(pkg["command"], script["script"])
            typer.echo(
                f"Removed {removed_count} tool package(s) from disk and {len(packages)} registry entry(ies) for group '{repo_name}'."
            )
        else:
            typer.echo(f"No registry entries found for group '{repo_name}'.")

        # Finally, remove the repository entry from the registry
        try:
            # Get the repository entry by name and remove it by URL
            repo_entry = registry_manager.get_repositories_by_name(name=repo_name)
            registry_manager.delete_repository(repo_entry["url"])
            typer.echo(f"Repository '{repo_name}' removed from the registry.")
        except Exception as e:
            typer.echo(f"Failed to remove repository '{repo_name}' from registry: {e}")
    else:
        typer.echo(f"Failed to remove repository '{repo_name}'.")


@repo_app.command("sync")
def repo_sync(
    ctx: typer.Context,
    repo_name: str = typer.Argument(..., help="Repository name to sync"),
    branch: Optional[str] = typer.Option(
        None,
        "--branch",
        help="Git branch to sync (if provided, checkout that branch and pull updates)",
    ),
):
    """
    Syncs a specific repository.
    If branch is provided, verifies the branch exists, checks it out, and pulls the latest changes.
    Otherwise, syncs using the currently checked-out branch.
    Also updates the tool packages and registry entries.
    """
    repo_dir = repo_manager.repos_dir / repo_name
    if not repo_dir.exists():
        typer.echo(f"Repository '{repo_name}' not found.")
        raise typer.Exit(code=1)

    updated_dir = repo_manager.sync_repo(str(repo_dir), branch=branch)
    typer.echo(f"Repository '{repo_name}' synced. Local path: {updated_dir}")

    # Update packages and registry entries below:
    registry_manager: Registry = ctx.obj["registry"]
    pkg_manager: PackageManager = ctx.obj["pkg_manager"]

    try:
        packages = pkg_manager.import_package(updated_dir, group=repo_name)
        for pkg in packages:
            registry_manager.update_package(
                pkg.command,
                pkg.name,
                pkg.description,
                str(pkg.location),
                pkg.dependencies,
                group=repo_name,
            )
            for script_name, script in pkg.scripts.items():
                registry_manager.update_script(
                    pkg.command, script_name, script.to_dict()
                )
        typer.echo(
            f"Updated {len(packages)} tool package(s) from repository '{repo_name}' in the registry."
        )
    except Exception as e:
        typer.echo(
            f"Error updating packages and registry for repository '{repo_name}': {e}"
        )


@repo_app.command("sync-all")
def repo_sync_all(ctx: typer.Context):
    """
    Synchronizes all repositories at once by calling the repo_sync command for each repository.
    """
    repos = list(repo_manager.repos_dir.iterdir())
    if not repos:
        typer.echo("No repositories found.")
        return
    for repo in repos:
        try:
            # Reuse the repo_sync command to update each repository and its registry entries
            repo_sync(ctx, repo.name)
            typer.echo(f"Synced repository: {repo.name}")
        except Exception as e:
            typer.echo(f"Failed to sync {repo.name}: {e}")


@repo_app.command("list")
def repo_list(
    ctx: typer.Context,
    url: Optional[str] = typer.Option(None, help="Filter by repository URL"),
    name: Optional[str] = typer.Option(
        None, help="Filter by repository name (partial match)"
    ),
    branch: Optional[str] = typer.Option(None, help="Filter by branch (partial match)"),
    location: Optional[str] = typer.Option(
        None, help="Filter by location (partial match)"
    ),
    auto_sync: Optional[bool] = typer.Option(
        None, help="Filter by auto sync status (True/False)"
    ),
):
    """
    Displays all registered repositories and their status using the registry,
    with filtering options.
    """
    registry_manager: Registry = ctx.obj["registry"]
    repos = registry_manager.list_repositories(
        url=url, name=name, branch=branch, location=location, auto_sync=auto_sync
    )
    if repos:
        # Define headers
        headers = ["Name", "URL", "Branch", "Location", "Auto Sync"]
        # Prepare rows from repos data
        rows = []
        for repo in repos:
            rows.append(
                [
                    str(repo.get("name", "")),
                    str(repo.get("url", "")),
                    str(repo.get("branch", "")),
                    str(repo.get("location", "")),
                    str(repo.get("auto_sync", "")),
                ]
            )
        # Calculate maximum width for each column
        col_widths = [
            max(len(headers[i]), max((len(row[i]) for row in rows), default=0))
            for i in range(len(headers))
        ]
        # Build the separator and header line
        separator = "+" + "+".join("-" * (w + 2) for w in col_widths) + "+"
        header_line = (
            "|"
            + "|".join(
                f" {headers[i].ljust(col_widths[i])} " for i in range(len(headers))
            )
            + "|"
        )

        typer.echo(separator)
        typer.echo(header_line)
        typer.echo(separator)
        # Print each row in the table
        for row in rows:
            row_line = (
                "|"
                + "|".join(f" {row[i].ljust(col_widths[i])} " for i in range(len(row)))
                + "|"
            )
            typer.echo(row_line)
        typer.echo(separator)
    else:
        typer.echo("No repositories found.")


# =====================================================
# Tool Management Commands
# =====================================================
@tool_app.command("import")
def tool_import(
    ctx: typer.Context,
    path: Path = typer.Argument(
        ...,
        help="Path to a manifest file, tool package directory, or package zip archive",
    ),
    force: bool = typer.Option(
        False, "--force", help="Force overwrite if the package already exists"
    ),
    group: Optional[str] = typer.Option(
        None, "--group", help="Custom group name for the tool package (optional)"
    ),
):
    """
    Imports a tool package (or multiple tool packages) into the registry from:
      - A manifest file (YAML/JSON)
      - A directory with one manifest (a single tool package)
      - A directory with multiple subdirectories (multiple tool packages)
      - A zip archive (will be unpacked first)
    If force is enabled, any existing package with the same command is overwritten.
    If group is not provided, the import_package function will try to determine the group.
    """
    scope = ctx.obj["scope"]
    registry_manager: Registry = ctx.obj["registry"]
    pkg_manager: PackageManager = ctx.obj["pkg_manager"]

    # If the provided path is a zip archive, unpack it first
    if path.suffix.lower() == ".zip":
        destination_dir = path.parent / path.stem
        path = pkg_manager.unpack_package(path, destination_dir)

    packages = pkg_manager.import_package(path, group=group, force=force)
    count = 0
    for pkg in packages:
        existing_pkg = registry_manager.get_package(pkg.command)
        if existing_pkg:
            if force:
                registry_manager.delete_package(pkg.command)
                for script in registry_manager.list_scripts(pkg.command):
                    registry_manager.delete_script(pkg.command, script["script"])
            else:
                typer.echo(
                    f"Package '{pkg.command}' already exists. Use --force to overwrite."
                )
                continue

        registry_manager.add_package(
            pkg.command,
            pkg.name,
            pkg.description,
            str(pkg.location),
            pkg.dependencies,
            group=pkg.group,
        )
        for script_name, script in pkg.scripts.items():
            registry_manager.add_script(pkg.command, script_name, script.to_dict())
        count += 1
    typer.echo(f"Imported {count} tool package(s) into the {scope} registry.")


@tool_app.command("list")
def tool_list(
    ctx: typer.Context,
    command: Optional[str] = typer.Option(None, help="Filter by tool command"),
    name: Optional[str] = typer.Option(
        None, help="Filter by tool name (partial match)"
    ),
    description: Optional[str] = typer.Option(None, help="Filter by tool description"),
    location: Optional[str] = typer.Option(
        None, help="Filter by tool location (partial match)"
    ),
    group: Optional[str] = typer.Option(None, help="Filter by tool group"),
    active: Optional[bool] = typer.Option(None, help="Filter by active status"),
):
    """
    Lists all tools in the registry, with filtering options.
    """
    registry_manager: Registry = ctx.obj["registry"]
    tools = registry_manager.list_packages(
        command=command,
        name=name,
        description=description,
        location=location,
        group=group,
        active=active,
    )
    if tools:
        for tool in tools:
            typer.echo(
                f"Command:     {tool.get('command')}\n"
                f"Name:        {tool.get('name')}\n"
                f"Description: {tool.get('description')}\n"
                f"Location:    {tool.get('location')}\n"
                f"Group:       {tool.get('group')}\n"
                f"Active:      {tool.get('active')}\n"
                "------------------------------------"
            )
    else:
        typer.echo("No tools found.")


@tool_app.command("info")
def tool_info(
    ctx: typer.Context,
    command: str = typer.Argument(..., help="Unique tool command identifier"),
):
    """
    Displays detailed information and the available scripts for the specified tool.
    """
    registry_manager: Registry = ctx.obj["registry"]
    tool = registry_manager.get_package(command)
    if not tool:
        typer.echo(f"Tool with command '{command}' not found.")
        raise typer.Exit(code=1)

    # Display tool information in a formatted manner.
    header = "=" * 50
    typer.echo(header)
    typer.echo(f"{'TOOL INFORMATION':^50}")
    typer.echo(header)
    typer.echo(f"{'Command:':12s} {tool.get('command', 'N/A')}")
    typer.echo(f"{'Name:':12s} {tool.get('name', 'N/A')}")
    typer.echo(f"{'Description:':12s} {tool.get('description', 'N/A')}")
    typer.echo(f"{'Location:':12s} {tool.get('location', 'N/A')}")
    typer.echo(f"{'Group:':12s} {tool.get('group', 'N/A')}")
    typer.echo(f"{'Active:':12s} {tool.get('active', 'N/A')}")
    typer.echo(header)

    # Display available scripts.
    scripts = registry_manager.list_scripts(command)
    if scripts:
        typer.echo("\nAvailable Scripts:")
        for script in scripts:
            typer.echo("-" * 50)
            for key, value in script.items():
                typer.echo(f"{key.capitalize():12s}: {value}")
        typer.echo("-" * 50)
    else:
        typer.echo("No scripts found for this tool.")


@tool_app.command("remove")
def tool_remove(
    ctx: typer.Context,
    command: str = typer.Argument(..., help="Unique tool command to remove"),
):
    """
    Removes a tool package from the specified scope.
    """
    scope = ctx.obj["scope"]
    registry_manager: Registry = ctx.obj["registry"]
    pkg_manager: PackageManager = ctx.obj["pkg_manager"]
    pkg_info = registry_manager.get_package(command)
    if not pkg_info:
        typer.echo(f"Tool '{command}' not found in {scope} registry.")
        raise typer.Exit(code=1)
    pkg_location = Path(pkg_info["location"])
    if pkg_manager.delete_package(pkg_location):
        registry_manager.delete_package(pkg_info["command"])
        for s in registry_manager.list_scripts(pkg_info["command"]):
            registry_manager.delete_script(pkg_info["command"], s["script"])
        typer.echo(f"Tool '{registry_manager}' removed from {scope} registry.")
    else:
        typer.echo(f"Failed to remove tool '{command}'.")


@tool_app.command("move")
def tool_move(
    tool_command: str = typer.Argument(..., help="Unique tool command to move"),
    to: str = typer.Option(..., "--to", help="Target registry: user or workspace"),
):
    """
    Moves a tool package from one registry to the other (user ⇄ workspace).
    Determines the tool's current registry, checks that the target differs from it,
    copies the tool package to the target, adds it to the target registry, and removes
    the package from the source registry and disk.
    """
    # Instantiate both registries
    user_registry = Registry(USER_REGISTRY_DIR)
    workspace_registry = Registry(WORKSPACE_REGISTRY_DIR)

    # Determine source registry
    src_registry = None
    pkg_info = user_registry.get_package(tool_command)
    if pkg_info:
        src_registry = user_registry
    else:
        pkg_info = workspace_registry.get_package(tool_command)
        if pkg_info:
            src_registry = workspace_registry
    if not src_registry or not pkg_info:
        typer.echo(f"Tool '{tool_command}' not found in any registry.")
        raise typer.Exit(code=1)

    # Determine target registry based on the 'to' option
    to_lower = to.lower()
    if to_lower not in ("user", "workspace"):
        typer.echo("Invalid target registry specified. Choose 'user' or 'workspace'.")
        raise typer.Exit(code=1)
    target_registry = user_registry if to_lower == "user" else workspace_registry

    # Ensure source and target are not the same
    if src_registry == target_registry:
        typer.echo(f"Tool '{tool_command}' is already in the {to_lower} registry.")
        raise typer.Exit(code=1)

    # Prepare source and target paths
    current_location = Path(pkg_info["location"])
    target_tools_dir = target_registry.registry_path / "tools"
    target_tools_dir.mkdir(parents=True, exist_ok=True)
    target_location = target_tools_dir / current_location.name

    # Copy the package to the target
    try:
        shutil.copytree(current_location, target_location)
    except Exception as e:
        typer.echo(f"Error copying tool folder: {e}")
        raise typer.Exit(code=1)

    # Import the package from the new location and add it to the target registry
    pkg_manager = PackageManager(target_registry.registry_path / "tools")
    try:
        new_pkg = pkg_manager.import_package(target_location)[0]
    except Exception as e:
        typer.echo(f"Error importing moved tool: {e}")
        raise typer.Exit(code=1)

    target_registry.add_package(
        new_pkg.command,
        new_pkg.name,
        new_pkg.description,
        str(new_pkg.location),
        new_pkg.dependencies,
    )
    for script_name, script in new_pkg.scripts.items():
        target_registry.add_script(new_pkg.command, script_name, script.to_dict())

    # Remove the tool from the source registry and delete its folder
    src_registry.delete_package(pkg_info["command"])
    for s in src_registry.list_scripts(pkg_info["command"]):
        src_registry.delete_script(pkg_info["command"], s["script"])
    try:
        shutil.rmtree(current_location)
    except Exception as e:
        typer.echo(f"Error removing source tool folder: {e}")
        # Not an immediate exit - warn and continue

    typer.echo(f"Tool '{tool_command}' successfully moved to the {to_lower} registry.")


@tool_app.command("export")
def tool_export(
    ctx: typer.Context,
    tool_command: str = typer.Argument(..., help="Unique tool command to export"),
    output: Path = typer.Argument(..., help="Output zip archive path"),
):
    """
    Exports a tool package as a ZIP archive.
    """
    scope = ctx.obj["scope"]
    registry_manager: Registry = ctx.obj["registry"]
    pkg_manager: PackageManager = ctx.obj["pkg_manager"]
    pkg_info = registry_manager.get_package(tool_command)
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
    new_command: Optional[str] = typer.Option(
        None, "--rename", help="New command name for the customized tool"
    ),
):
    """
    Copies a tool package from the user registry to the workspace for customization.
    Optionally renames the tool command.
    """
    user_registry = Registry(USER_REGISTRY_DIR)
    workspace_registry = Registry(WORKSPACE_REGISTRY_DIR)
    pkg_manager = PackageManager(WORKSPACE_REGISTRY_DIR / "tools")
    pkg_info = user_registry.get_package(tool_command)
    if not pkg_info:
        typer.echo(f"Tool '{tool_command}' not found in user registry.")
        raise typer.Exit(code=1)
    pkg_location = Path(pkg_info["location"])
    new_pkg = pkg_manager.import_package(pkg_location)[0]
    if new_command:
        new_pkg.command = new_command
    workspace_registry.add_package(
        new_pkg.command,
        new_pkg.name,
        new_pkg.description,
        str(new_pkg.location),
        new_pkg.dependencies,
    )
    for script_name, script in new_pkg.scripts.items():
        workspace_registry.add_script(new_pkg.command, script_name, script.to_dict())
    typer.echo(
        f"Tool '{tool_command}' customized to '{new_pkg.command}' in workspace registry."
    )


@tool_app.command("update")
def tool_update(
    ctx: typer.Context,
    tool_command: Optional[str] = typer.Argument(
        None,
        help="Unique tool command to update. If omitted, update all tools in the indicated scope.",
    ),
    manifest: Optional[Path] = typer.Option(
        None,
        "--manifest",
        help="Path to updated manifest file (used for a specific tool if provided)",
    ),
):
    """
    Updates tool package(s) using an updated manifest file.
    If a tool_command is provided, only that tool is updated (using the supplied manifest if provided,
    or its current manifest location otherwise). If no tool_command is provided, all packages in the
    indicated scope will be updated from their existing locations.
    """
    scope = ctx.obj["scope"]
    registry: Registry = ctx.obj["registry"]
    pkg_manager: PackageManager = ctx.obj["pkg_manager"]

    def update_single_tool(command: str) -> None:
        pkg_info = registry.get_package(command)
        if not pkg_info:
            typer.echo(f"Tool '{command}' not found in {scope} registry.")
            return
        pkg_location = Path(pkg_info["location"])
        update_path = manifest if manifest else pkg_location
        try:
            new_pkg = pkg_manager.import_package(update_path)[0]
        except Exception as e:
            typer.echo(f"Error updating tool '{command}': {e}")
            return
        registry.update_package(
            new_pkg.command,
            new_pkg.name,
            new_pkg.description,
            str(new_pkg.location),
            new_pkg.dependencies,
        )
        for script_name, script in new_pkg.scripts.items():
            registry.update_script(new_pkg.command, script_name, script.to_dict())
        typer.echo(f"Tool '{command}' updated in {scope} registry.")

    if tool_command:
        update_single_tool(tool_command)
    else:
        all_packages = registry.list_packages()
        if not all_packages:
            typer.echo(f"No tools found in {scope} registry to update.")
            raise typer.Exit(code=0)
        for pkg in all_packages:
            update_single_tool(pkg["command"])


# =====================================================
# Script Execution & Utility Commands
# =====================================================
@app.command("do")
def run_script(
    tool_command: str = typer.Argument(..., help="Unique tool command"),
    script_name: str = typer.Argument(..., help="Name of the script to execute"),
    scope: str = typer.Option(
        "both",
        "--scope",
        help="Registry scope to search for the script: 'workspace', 'user', or 'both' (default both)",
    ),
    extra_args: List[str] = typer.Argument(None, help="Extra arguments for the script"),
):
    """
    Executes a script from an installed tool package.
    Tries the specified registry scope (workspace, user, or both).
    If the script is not found but the package exists, shows available scripts.
    """
    scope = scope.lower()
    # Validate scope option and determine which registries to search.
    if scope not in ("workspace", "user", "both"):
        typer.echo("Invalid scope. Choose from 'workspace', 'user', or 'both'.")
        raise typer.Exit(code=1)

    workspace_registry = Registry(WORKSPACE_REGISTRY_DIR)
    user_registry = Registry(USER_REGISTRY_DIR)

    registries = []
    if scope == "workspace":
        registries = [workspace_registry]
    elif scope == "user":
        registries = [user_registry]
    else:  # both
        registries = [workspace_registry, user_registry]

    # Try to get the script info from the selected registries.
    script_info = None
    pkg_info = None
    for reg in registries:
        script_info = reg.get_script(tool_command, script_name)
        if script_info:
            pkg_info = reg.get_package(tool_command)
            break

    if script_info and pkg_info:
        try:
            # Build the Script instance from the stored dictionary.
            script = Script.from_dict(script_info)
            base_dir = Path(pkg_info["location"])
            # Execute the script using its built-in execute functionality.
            result = script.execute(base_dir, extra_args)
            typer.echo(f"Command executed with return code {result.returncode}")
        except Exception as err:
            typer.echo(f"Error executing script: {err}")
            raise typer.Exit(code=1)
    else:
        # If script not found, list all available scripts for the tool in the selected scope(s).
        available_scripts = set()
        tool_found = False
        for reg in registries:
            pkg = reg.get_package(tool_command)
            if pkg:
                tool_found = True
                for scr in reg.list_scripts(tool_command):
                    available_scripts.add(scr.get("script"))
        if tool_found:
            typer.echo(
                f"Script '{script_name}' not found for tool '{tool_command}'. "
                f"Available scripts: {sorted(available_scripts)}"
            )
        else:
            typer.echo(
                f"Tool '{tool_command}' not found in the specified scope '{scope}'."
            )
        raise typer.Exit(code=1)


@app.command("run")
def run_workspace(
    script_name: str = typer.Argument(..., help="Name of the script to execute"),
    extra_args: List[str] = typer.Argument(None, help="Extra arguments for the script"),
):
    """
    Executes a script from the workspace package using the PackageBuilder.
    """
    workspace_file = find_file_type("manifest", WORKSPACE_APP_DIR)
    if not workspace_file.exists():
        typer.echo("No workspace file found in the current directory.")
        typer.echo("Run 'devt project init' to create a new workspace.")
        raise typer.Exit(code=1)

    try:
        # Build the package from the workspace directory using PackageBuilder.
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


# Standardized Tool Scripts (shorthand commands)
@app.command("install")
def install(
    tool_commands: List[str] = typer.Argument(..., help="Tool commands to install"),
    scope: str = typer.Option(
        "both",
        "--scope",
        help="Registry scope to search for the script: 'workspace', 'user', or 'both' (default: both)",
    ),
):
    """
    Runs the 'install' script for each given tool.
    """
    for tool_command in tool_commands:
        run_script(tool_command, "install", scope=scope, extra_args=[])


@app.command("uninstall")
def uninstall(
    tool_commands: List[str] = typer.Argument(..., help="Tool commands to uninstall"),
    scope: str = typer.Option(
        "both",
        "--scope",
        help="Registry scope to search for the script: 'workspace', 'user', or 'both' (default: both)",
    ),
):
    """
    Runs the 'uninstall' script for each given tool.
    """
    for tool_command in tool_commands:
        run_script(tool_command, "uninstall", scope=scope, extra_args=[])


@app.command("upgrade")
def upgrade(
    tool_commands: List[str] = typer.Argument(..., help="Tool commands to upgrade"),
    scope: str = typer.Option(
        "both",
        "--scope",
        help="Registry scope to search for the script: 'workspace', 'user', or 'both' (default: both)",
    ),
):
    """
    Runs the 'upgrade' script for each given tool.
    """
    for tool_command in tool_commands:
        run_script(tool_command, "upgrade", scope=scope, extra_args=[])


@app.command("version")
def version(
    tool_commands: List[str] = typer.Argument(
        ..., help="Tool commands to display version"
    ),
    scope: str = typer.Option(
        "both",
        "--scope",
        help="Registry scope to search for the script: 'workspace', 'user', or 'both' (default: both)",
    ),
):
    """
    Runs the 'version' script for each given tool.
    """
    for tool_command in tool_commands:
        run_script(tool_command, "version", scope=scope, extra_args=[])


@app.command("test")
def test(
    tool_commands: List[str] = typer.Argument(..., help="Tool commands to test"),
    scope: str = typer.Option(
        "both",
        "--scope",
        help="Registry scope to search for the script: 'workspace', 'user', or 'both' (default: both)",
    ),
):
    """
    Runs tool-specific tests for each given tool.
    """
    for tool_command in tool_commands:
        run_script(tool_command, "test", scope=scope, extra_args=[])


# =====================================================
# Template for workspace initialization
# =====================================================
WORKSPACE_TEMPLATE = {
    "name": "My Workspace",
    "description": "A basic workspace.",
    "dependencies": {},
    "scripts": {"test": "echo workspace test"},
}


# =====================================================
# Project-Level Commands
# =====================================================
@project_app.command("init")
def project_init(
    file_format: str = typer.Option(
        "yaml",
        "--format",
        help="File format to initialize the workspace. Options: 'yaml' (default) or 'json'.",
    )
):
    """
    Initializes a new development environment in the current project.
    Creates a workspace file (YAML by default, but JSON if specified) with a basic template.
    """
    # Check if a workspace file already exists using find_file_type.
    workspace_file = find_file_type("workspace", WORKSPACE_APP_DIR)
    if workspace_file.exists():
        typer.echo("Project already initialized.")
        raise typer.Exit(code=0)

    file_format_lower = file_format.lower()
    if file_format_lower == "json":
        workspace_file = WORKSPACE_APP_DIR / "workspace.json"
        workspace_content = json.dumps(WORKSPACE_TEMPLATE, indent=4)
    else:
        workspace_file = WORKSPACE_APP_DIR / "workspace.yaml"
        workspace_content = yaml.dump(WORKSPACE_TEMPLATE, sort_keys=False)
    workspace_file.write_text(workspace_content)
    typer.echo(
        f"Project initialized successfully with {file_format_lower.upper()} format."
    )


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
    workspace_file = find_file_type("workspace", WORKSPACE_APP_DIR)
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
