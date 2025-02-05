# devt/cli.py
import json
import subprocess
import shutil
import os
from pathlib import Path
from typing import List, Optional
import typer
import logging

from . import __version__

# Import functions and constants from our modules
from devt.config import (
    REGISTRY_DIR,
    WORKSPACE_REGISTRY_DIR,
    REGISTRY_FILE,
    WORKSPACE_REGISTRY_FILE,
    WORKSPACE_FILE,
    WORKSPACE_DIR,
)
from devt.utils import load_json, on_exc, save_json, determine_source
from devt.git_ops import clone_or_update_repo
from devt.registry import update_registry, update_registry_with_workspace
from devt.package_ops import add_local, delete_local_package, sync_repositories
from devt.executor import (
    get_tool,
    resolve_script,
    resolve_working_directory,
    build_full_command,
    execute_command,
)


app = typer.Typer(help="DevT: A tool for managing development tool packages.")

# Create sub-apps for repository commands and local package commands.
repo_app = typer.Typer(help="Commands for repository-based tools.")
local_app = typer.Typer(help="Commands for local package-based tools.")

# Attach sub-apps to the main app.
app.add_typer(repo_app, name="repo")
app.add_typer(local_app, name="local")


# ---------------------------------------------------------------------------
# Repository-based commands
# ---------------------------------------------------------------------------
@repo_app.command("add")
def add_repo(
    source: str,
    branch: str = typer.Option(None, help="Specify the branch for repository sources."),
    workspace: bool = typer.Option(False, help="Add to workspace-level registry."),
    dry_run: bool = typer.Option(False, help="Preview actions without making changes."),
    auto_sync: bool = typer.Option(
        True, help="Automatically sync repositories after adding."
    ),
):
    """
    Add tools from a repository to the registry.

    Example:
        devt repo add https://github.com/dkuwcreator/devt-tools.git --branch main --workspace
    """
    app_dir = WORKSPACE_REGISTRY_DIR if workspace else REGISTRY_DIR
    registry_file = app_dir / "registry.json"
    logger = logging.getLogger("devt")
    typer.echo(f"Adding repository tools to registry from {registry_file}...")
    registry = load_json(registry_file)
    try:
        if dry_run:
            typer.echo(f"Dry run: would clone or update repository {source}")
            raise typer.Exit()
        repo_dir = clone_or_update_repo(source, app_dir, branch)
        # Find each manifest.json and use its parent directory as a tool folder.
        tool_dirs = [manifest.parent for manifest in repo_dir.rglob("manifest.json")]
        for tool_dir in tool_dirs:
            registry = update_registry(
                tool_dir,
                registry_file,
                registry,
                source,
                auto_sync=auto_sync,
            )
        save_json(registry_file, registry)
        typer.echo("Repository tools successfully added to the registry.")
    except Exception as e:
        logger.exception("An error occurred while adding repository tools: %s", e)


@repo_app.command("remove")
def remove_repo(
    repo_name: str = typer.Argument(
        ..., help="Name of the repository (group) to remove."
    ),
    workspace: bool = typer.Option(False, help="Remove from workspace-level registry."),
    force: bool = typer.Option(False, help="Force removal without confirmation."),
    dry_run: bool = typer.Option(False, help="Preview actions without changes."),
):
    """
    Remove a repository and all its associated tools from the registry.

    Example:
        devt repo remove devt-tools --workspace
    """
    app_dir = WORKSPACE_REGISTRY_DIR if workspace else REGISTRY_DIR
    registry_file = app_dir / "registry.json"
    registry = load_json(registry_file)
    logger = logging.getLogger("devt")

    # Identify entries that are from a repository and belong to the group.
    repo_entries = {
        tool: data
        for tool, data in registry.items()
        if data is not None
        and isinstance(data, dict)
        and data.get("location", "").startswith("repos")
        and data.get("dir") == repo_name
    }
    if not repo_entries:
        logger.error("Repository '%s' not found in registry.", repo_name)
        raise typer.Exit()

    # Confirm removal if not forced.
    if not force:
        if not typer.confirm(
            f"Are you sure you want to remove repository '{repo_name}' and all its tools?"
        ):
            typer.echo("Operation cancelled.")
            raise typer.Exit()

    if dry_run:
        typer.echo(f"Dry run: would remove repository '{repo_name}' and its tools.")
        raise typer.Exit()

    # Remove each tool from the registry.
    for tool in list(repo_entries.keys()):
        del registry[tool]
    save_json(registry_file, registry)

    # Remove the repository directory.
    repo_dir = app_dir / "repos" / repo_name
    if repo_dir.exists():
        try:
            shutil.rmtree(repo_dir, onexc=on_exc)
            typer.echo(f"Repository '{repo_name}' removed successfully from disk.")
        except Exception as e:
            logger.error("Failed to remove repository '%s': %s", repo_name, e)
            raise
    else:
        logger.warning("Repository directory not found: %s", repo_dir)

    typer.echo(
        f"Repository '{repo_name}' and its associated tools have been removed from the registry."
    )


@repo_app.command("sync")
def sync_repos(
    workspace: bool = typer.Option(
        False, help="Sync repositories from workspace registry."
    )
):
    """
    Sync all repositories by pulling the latest changes.

    Example:
        devt repo sync --workspace
    """
    app_dir = WORKSPACE_REGISTRY_DIR if workspace else REGISTRY_DIR
    sync_repositories(app_dir)
    typer.echo("All repositories have been synced successfully.")


# ---------------------------------------------------------------------------
# Local package commands
# ---------------------------------------------------------------------------
@local_app.command("import")
def import_package(
    local_path: str,
    group: Optional[str] = typer.Option(
        None, help="Group name for the imported package(s)."
    ),
    workspace: bool = typer.Option(False, help="Import into workspace-level registry."),
    dry_run: bool = typer.Option(False, help="Preview actions without changes."),
):
    """
    Import a local package or collection of packages into the registry.

    If the provided path is a single package (a path to a manifest file or a folder
    with one manifest file in its root), the tool will be added to the default group
    (unless a group name is provided).

    If the provided path is a folder containing multiple subdirectories each with a
    manifest file, then the group will be named after that folder (unless a group name
    is provided).

    Examples:
        devt local import ./single-package
        devt local import ./collection-of-packages --group custom-group
    """
    app_dir = WORKSPACE_REGISTRY_DIR if workspace else REGISTRY_DIR
    registry_file = app_dir / "registry.json"
    registry = load_json(registry_file)
    logger = logging.getLogger("devt")

    local_path_obj = Path(local_path).resolve()
    if not local_path_obj.exists():
        logger.error("Path '%s' does not exist.", local_path)
        raise typer.Exit()

    # Base destination for local packages.
    dest_base = app_dir / "tools"

    if local_path_obj.is_file():
        # Assume it's a manifest file: use its parent as the package.
        pkg_folder = local_path_obj.parent
        group_name = group if group else "default"
        dest = dest_base / group_name / pkg_folder.name
        if dry_run:
            logger.info(
                "Dry run: would import package from file '%s' to '%s'", local_path, dest
            )
            raise typer.Exit()
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(pkg_folder, dest, dirs_exist_ok=True)
        if (dest / "manifest.json").exists():
            tool_dirs = [dest]
        else:
            tool_dirs = [
                d
                for d in dest.iterdir()
                if d.is_dir() and (d / "manifest.json").exists()
            ]
    elif local_path_obj.is_dir():
        # Check if multiple subdirectories with manifest.json exist.
        subpackages = [
            d
            for d in local_path_obj.iterdir()
            if d.is_dir() and (d / "manifest.json").exists()
        ]
        if len(subpackages) > 1:
            group_name = group if group else local_path_obj.name
            tool_dirs = []
            for subpkg in subpackages:
                dest = dest_base / group_name / subpkg.name
                if dry_run:
                    logger.info(
                        "Dry run: would import package '%s' to '%s'", subpkg, dest
                    )
                    continue
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(subpkg, dest, dirs_exist_ok=True)
                tool_dirs.append(dest)
        else:
            if (local_path_obj / "manifest.json").exists():
                group_name = group if group else "default"
                dest = dest_base / group_name / local_path_obj.name
            else:
                subdirs = [
                    d
                    for d in local_path_obj.iterdir()
                    if d.is_dir() and (d / "manifest.json").exists()
                ]
                if subdirs:
                    group_name = group if group else "default"
                    dest = dest_base / group_name / subdirs[0].name
                else:
                    logger.error(
                        "No valid package (manifest.json) found in '%s'", local_path
                    )
                    raise typer.Exit()
            if dry_run:
                logger.info(
                    "Dry run: would import package from directory '%s' to '%s'",
                    local_path,
                    dest,
                )
                raise typer.Exit()
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(local_path_obj, dest, dirs_exist_ok=True)
            tool_dirs = [dest]
    else:
        logger.error("Path '%s' is neither a file nor a directory.", local_path)
        raise typer.Exit()

    # Update the registry for each detected tool package.
    for tool_dir in tool_dirs:
        registry = update_registry(
            tool_dir,
            registry_file,
            registry,
            str(local_path_obj),
            auto_sync=False,  # Local packages are not auto-synced.
        )

    save_json(registry_file, registry)
    logger.info(
        "Local package(s) successfully imported into the registry under group '%s'.",
        group_name,
    )
    typer.echo(f"Imported local package(s) into group '{group_name}'.")


@local_app.command("delete")
def delete_tool_or_group(
    name: str = typer.Argument(
        ..., help="Identifier of the local tool to delete or group name to delete."
    ),
    group: bool = typer.Option(False, "--group", help="Treat 'name' as a group name."),
    workspace: bool = typer.Option(False, help="Operate on workspace-level registry."),
    force: bool = typer.Option(False, help="Force deletion without confirmation."),
    dry_run: bool = typer.Option(False, help="Preview actions without changes."),
):
    """
    Delete a local tool or an entire group of local tools from the registry.

    If --group is provided, 'name' is treated as a group name and all tools in that group are deleted.
    Otherwise, 'name' is treated as a tool identifier.
    """
    app_dir = WORKSPACE_REGISTRY_DIR if workspace else REGISTRY_DIR
    registry_file = app_dir / "registry.json"
    registry = load_json(registry_file)
    logger = logging.getLogger("devt")

    if group:
        tools_in_group = {
            tool: data
            for tool, data in registry.items()
            if data.get("location", "").startswith("tools") and data.get("dir") == name
        }
        if not tools_in_group:
            logger.error("No local tools found in group '%s'.", name)
            raise typer.Exit()
        if not force and not typer.confirm(
            f"Are you sure you want to delete all tools in group '{name}'?"
        ):
            typer.echo("Operation cancelled.")
            raise typer.Exit()
        if dry_run:
            typer.echo(f"Dry run: would delete tools: {list(tools_in_group.keys())}")
            raise typer.Exit()
        for tool in list(tools_in_group.keys()):
            delete_local_package(tool, app_dir, registry, registry_file)
            logger.info("Deleted tool '%s' from registry.", tool)
        group_dir = app_dir / "tools" / name
        if group_dir.exists() and not any(group_dir.iterdir()):
            shutil.rmtree(group_dir)
            logger.info("Removed empty group directory '%s'.", group_dir)
        save_json(registry_file, registry)
        typer.echo(f"Deleted all local tools in group '{name}'.")
    else:
        if name not in registry:
            logger.error("Local tool '%s' not found in registry.", name)
            raise typer.Exit()
        entry = registry[name]
        if not entry.get("location", "").startswith("tools"):
            logger.error("Tool '%s' is not a local package.", name)
            raise typer.Exit()
        if not force and not typer.confirm(
            f"Are you sure you want to delete tool '{name}'?"
        ):
            typer.echo("Operation cancelled.")
            raise typer.Exit()
        if dry_run:
            typer.echo(f"Dry run: would delete local tool '{name}'.")
            raise typer.Exit()
        delete_local_package(name, app_dir, registry, registry_file)
        group_dir = app_dir / "tools" / entry.get("dir", "")
        if group_dir.exists() and not any(group_dir.iterdir()):
            shutil.rmtree(group_dir)
            logger.info("Removed empty group directory '%s'.", group_dir)
        save_json(registry_file, registry)
        typer.echo(f"Deleted local tool '{name}'.")


@local_app.command("export")
def export_tool_or_group(
    name: str = typer.Argument(
        ..., help="Identifier of the local tool to export or group name."
    ),
    destination: str = typer.Argument(..., help="Destination directory for export."),
    group: bool = typer.Option(
        False,
        "--group",
        help="Treat 'name' as a group name to export all tools in that group.",
    ),
    workspace: bool = typer.Option(False, help="Operate on workspace-level registry."),
    dry_run: bool = typer.Option(False, help="Preview actions without changes."),
):
    """
    Export a local tool or a group of local tools to a specified destination.

    If --group is provided, 'name' is treated as a group name and all tools in that group are exported.
    Otherwise, 'name' is treated as a tool identifier.
    """
    app_dir = WORKSPACE_REGISTRY_DIR if workspace else REGISTRY_DIR
    registry_file = app_dir / "registry.json"
    registry = load_json(registry_file)
    logger = logging.getLogger("devt")
    dest = Path(destination).resolve()

    if group:
        tools_in_group = {
            tool: data
            for tool, data in registry.items()
            if data.get("location", "").startswith("tools") and data.get("dir") == name
        }
        if not tools_in_group:
            logger.error("No local tools found in group '%s'.", name)
            raise typer.Exit()
        if dry_run:
            typer.echo(
                f"Dry run: would export tools in group '{name}': {list(tools_in_group.keys())} to {dest}"
            )
            raise typer.Exit()
        dest_group = dest / name
        dest_group.mkdir(parents=True, exist_ok=True)
        for tool, data in tools_in_group.items():
            tool_manifest = Path(data.get("location"))
            if not tool_manifest.is_absolute():
                tool_manifest = app_dir / tool_manifest
            tool_folder = tool_manifest.parent
            tool_dest = dest_group / tool_folder.name
            shutil.copytree(tool_folder, tool_dest, dirs_exist_ok=True)
            typer.echo(f"Exported tool '{tool}' to {tool_dest}")
        typer.echo(f"Exported group '{name}' to {dest_group}")
    else:
        if name not in registry:
            logger.error("Local tool '%s' not found in registry.", name)
            raise typer.Exit()
        data = registry[name]
        if not data.get("location", "").startswith("tools"):
            logger.error("Tool '%s' is not a local package.", name)
            raise typer.Exit()
        tool_manifest = Path(data.get("location"))
        if not tool_manifest.is_absolute():
            tool_manifest = app_dir / tool_manifest
        tool_folder = tool_manifest.parent
        tool_dest = dest / tool_folder.name
        if dry_run:
            typer.echo(f"Dry run: would export tool '{name}' to {tool_dest}")
            raise typer.Exit()
        shutil.copytree(tool_folder, tool_dest, dirs_exist_ok=True)
        typer.echo(f"Exported tool '{name}' to {tool_dest}")


@local_app.command("rename-group")
def rename_group(
    old_name: str = typer.Argument(..., help="Current group name."),
    new_name: str = typer.Argument(..., help="New group name."),
    workspace: bool = typer.Option(False, help="Operate on workspace-level registry."),
    force: bool = typer.Option(False, help="Force rename without confirmation."),
    dry_run: bool = typer.Option(False, help="Preview actions without changes."),
):
    """
    Rename a group of local tools.

    Updates both the registry entries and physically renames the group folder under base_dir/tools.
    """
    app_dir = WORKSPACE_REGISTRY_DIR if workspace else REGISTRY_DIR
    registry_file = app_dir / "registry.json"
    registry = load_json(registry_file)
    logger = logging.getLogger("devt")

    tools_in_group = {
        tool: data
        for tool, data in registry.items()
        if data.get("location", "").startswith("tools") and data.get("dir") == old_name
    }
    if not tools_in_group:
        logger.error("No local tools found in group '%s'.", old_name)
        raise typer.Exit()

    if not force and not typer.confirm(
        f"Are you sure you want to rename group '{old_name}' to '{new_name}'?"
    ):
        typer.echo("Operation cancelled.")
        raise typer.Exit()

    if dry_run:
        typer.echo(
            f"Dry run: would rename group '{old_name}' to '{new_name}' for tools: {list(tools_in_group.keys())}"
        )
        raise typer.Exit()

    old_group_dir = app_dir / "tools" / old_name
    new_group_dir = app_dir / "tools" / new_name
    if old_group_dir.exists():
        try:
            old_group_dir.rename(new_group_dir)
            typer.echo(f"Renamed folder '{old_group_dir}' to '{new_group_dir}'")
        except Exception as e:
            logger.error(
                "Failed to rename group folder '%s' to '%s': %s",
                old_group_dir,
                new_group_dir,
                e,
            )
            raise
    else:
        logger.error("Group directory '%s' not found.", old_group_dir)
        raise typer.Exit()

    for tool, data in tools_in_group.items():
        data["dir"] = new_name
        old_location_prefix = f"tools/{old_name}"
        new_location_prefix = f"tools/{new_name}"
        if data.get("location", "").startswith(old_location_prefix):
            data["location"] = data["location"].replace(
                old_location_prefix, new_location_prefix, 1
            )
    save_json(registry_file, registry)
    typer.echo(f"Group renamed from '{old_name}' to '{new_name}' in registry.")


@local_app.command("move-tool")
def move_tool(
    tool_name: str = typer.Argument(..., help="Identifier of the local tool to move."),
    new_group: str = typer.Argument(
        ..., help="New group name where the tool will be moved."
    ),
    workspace: bool = typer.Option(False, help="Operate on workspace-level registry."),
    force: bool = typer.Option(False, help="Force move without confirmation."),
    dry_run: bool = typer.Option(False, help="Preview actions without changes."),
):
    """
    Move a local tool from its current group to a new group.

    Updates the registry entry's group ("dir" field) and physically moves the tool folder.
    """
    app_dir = WORKSPACE_REGISTRY_DIR if workspace else REGISTRY_DIR
    registry_file = app_dir / "registry.json"
    registry = load_json(registry_file)
    logger = logging.getLogger("devt")

    if tool_name not in registry:
        logger.error("Local tool '%s' not found in registry.", tool_name)
        raise typer.Exit()

    data = registry[tool_name]
    if not data.get("location", "").startswith("tools"):
        logger.error("Tool '%s' is not a local package.", tool_name)
        raise typer.Exit()

    current_group = data.get("dir")
    if current_group == new_group:
        typer.echo(f"Tool '{tool_name}' is already in group '{new_group}'.")
        raise typer.Exit()

    tool_manifest = Path(data.get("location"))
    if not tool_manifest.is_absolute():
        tool_manifest = app_dir / tool_manifest
    tool_folder = tool_manifest.parent
    new_tool_folder = app_dir / "tools" / new_group / tool_folder.name

    if not force and not typer.confirm(
        f"Move tool '{tool_name}' from group '{current_group}' to '{new_group}'?"
    ):
        typer.echo("Operation cancelled.")
        raise typer.Exit()

    if dry_run:
        typer.echo(
            f"Dry run: would move tool '{tool_name}' from '{tool_folder}' to '{new_tool_folder}'"
        )
        raise typer.Exit()

    new_group_dir = app_dir / "tools" / new_group
    new_group_dir.mkdir(parents=True, exist_ok=True)

    try:
        shutil.move(str(tool_folder), str(new_tool_folder))
        data["dir"] = new_group
        old_location_prefix = f"tools/{current_group}"
        new_location_prefix = f"tools/{new_group}"
        if data.get("location", "").startswith(old_location_prefix):
            data["location"] = data["location"].replace(
                old_location_prefix, new_location_prefix, 1
            )
        save_json(registry_file, registry)
        typer.echo(f"Tool '{tool_name}' moved to group '{new_group}'.")
    except Exception as e:
        logger.error("Failed to move tool '%s': %s", tool_name, e)
        raise


# ---------------------------------------------------------------------------
# Other Commands (List, Do, Run, Install, Uninstall, Upgrade, Version, Test)
# These commands remain in the main app.
# ---------------------------------------------------------------------------
@app.command("list")
def list_tools(
    workspace: bool = typer.Option(False, help="List tools from workspace registry.")
):
    """
    List all tools in the registry.
    """
    logger = logging.getLogger("devt")
    if not workspace:
        logger.info("Listing tools from registry %s...", REGISTRY_FILE)
        registry = load_json(REGISTRY_FILE)
        for name, value in registry.items():
            if value.get("active", True):
                logger.info("%s: %s", name, value.get("source"))
    else:
        logger.info(
            "Listing tools from workspace registry %s...", WORKSPACE_REGISTRY_FILE
        )
        registry = load_json(WORKSPACE_REGISTRY_FILE)
        for name, value in registry.items():
            logger.info("%s: %s", name, value.get("source"))


@app.command("init")
def init_project():
    """
    Initialize the current project by creating a workspace.json configuration file.
    
    This file will be added to the workspace registry under the key "workspace".
    """
    project_file = Path.cwd() / "workspace.json"
    if project_file.exists():
        typer.echo("workspace.json already exists in the current directory.")
        raise typer.Exit()
    default_config = {
         "tools": {},
         "scripts": {
              "test": "echo 'Run project tests'",
              "deploy": "echo 'Deploy project'",
              "destroy": "echo 'Destroy project resources'"
         }
    }
    with project_file.open("w") as f:
         json.dump(default_config, f, indent=4)
    typer.echo("Initialized project with workspace.json.")


@app.command("do")
def do(
    tool_name: str = typer.Argument(..., help="The tool to run the script for."),
    script_name: str = typer.Argument(..., help="The name of the script to run."),
    additional_args: List[str] = typer.Argument(None, help="Additional arguments to pass to the script."),
):
    """
    Run a specified script for the given tool.
    
    The tool is looked up first in the workspace registry, then in the user registry.
    """
    logger = logging.getLogger("devt")
    shell = "posix" if os.name != "nt" else "windows"

    # Lookup the tool from the registries.
    try:
        tool, registry_dir = get_tool(tool_name)
    except ValueError as ve:
        raise typer.Exit(str(ve))

    # Resolve the script command.
    cmd = resolve_script(tool, script_name, shell)
    typer.echo(f"Script: {cmd}")

    # If auto_sync is enabled, update the repository.
    if tool.get("auto_sync", False):
        from devt.git_ops import clone_or_update_repo
        repo_name = tool.get("dir")
        repo_dir = Path(registry_dir) / repo_name
        logger.info("Auto-syncing repository for tool '%s'...", tool_name)
        clone_or_update_repo(tool["source"], repo_dir, branch=None)
        # Re-read the tool entry in case the manifest has changed.
        try:
            tool, registry_dir = get_tool(tool_name)
        except ValueError as ve:
            raise typer.Exit(str(ve))
        cmd = resolve_script(tool, script_name, shell)
        typer.echo(f"Updated Script: {cmd}")

    full_command = build_full_command(cmd, additional_args)
    logger.info("Full command string: %s", full_command)
    
    new_cwd = resolve_working_directory(tool, registry_dir)
    logger.info("Resolved working directory: %s", new_cwd)
    if not new_cwd.exists():
        raise ValueError(f"Error: Working directory '{new_cwd}' does not exist.")
    
    execute_command(full_command, new_cwd)


@app.command()
def run(
    script_name: str = typer.Argument(..., help="The name of the script to run."),
    additional_args: Optional[List[str]] = typer.Argument(
        None, help="Additional arguments to pass to the script."
    ),
):
    """
    Run a specified script for the given tool.
    """
    do("workspace", script_name, additional_args)


@app.command()
def install(
    tools: List[str] = typer.Argument(..., help="List of tool names to install"),
):
    """
    Install the specified tools.
    """
    for tool in tools:
        do(tool, "install")


@app.command()
def uninstall(
    tools: List[str] = typer.Argument(..., help="List of tool names to uninstall"),
):
    """
    Uninstall the specified tools.
    """
    for tool in tools:
        do(tool, "uninstall")


@app.command()
def upgrade(
    tools: List[str] = typer.Argument(..., help="List of tool names to upgrade"),
):
    """
    Upgrade the specified tools.
    """
    for tool in tools:
        do(tool, "upgrade")


@app.command()
def version(
    tools: List[str] = typer.Argument(
        ..., help="List of tool names to display the version for"
    ),
):
    """
    Display the version of the specified tools.
    """
    for tool in tools:
        do(tool, "version")


@app.command()
def test(
    tools: List[str] = typer.Argument(
        ..., help="List of tool names to run the test for"
    ),
):
    """
    Run the test script for the specified tools.
    """
    for tool in tools:
        do(tool, "test")

@app.command()
def version():
    typer.echo(f"Version: {__version__}")

if __name__ == "__main__":
    app()
