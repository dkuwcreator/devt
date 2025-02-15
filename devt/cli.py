# devt/cli.py
import json
import re
import shutil
import os
from pathlib import Path
from typing import List, Optional
import requests
import typer
from typing_extensions import Annotated

from devt import __version__

# Import functions and constants from our modules
from devt.config import (
    WORKSPACE_DIR,
    configure_logging,
    logger,
    REGISTRY_DIR,
    WORKSPACE_REGISTRY_DIR,
    REGISTRY_FILE,
    WORKSPACE_REGISTRY_FILE,
)
from devt.utils import find_file_type, load_json, save_json
from devt.git_manager import ToolRepo
from devt.registry import RegistryManager, get_tool, update_tool_in_registry

from devt.package_manager import ToolGroup
from devt.executor import Executor, ManifestRunner

app = typer.Typer(help="DevT: A tool for managing development tool packages.")


# Define a callback to set global log level or other config
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
):
    """
    Global callback to configure logging before any commands run.
    """

    # Call the configure_logging function
    configure_logging(log_level)

    # If you want to prevent "No command provided" confusion, you can handle
    # the case where no subcommand was invoked:
    if not ctx.invoked_subcommand:
        # For example, show help or a message:
        typer.echo("No command provided. Use --help for usage.")
        raise typer.Exit()


# ---------------------------------------------------------------------------
# Managing Repository commands
# ---------------------------------------------------------------------------
def update_registry_with_tools(
    tool_dirs, registry_file, registry, source, branch, auto_sync
):
    registry = load_json(registry_file)
    for tool_dir in tool_dirs:
        registry = update_tool_in_registry(
            tool_dir,
            registry_file,
            registry,
            source,
            branch,
            auto_sync=auto_sync,
        )
    save_json(registry_file, registry)


def guess_repo_name_from_url(url: str) -> str:
    """
    Attempt to guess a repository name from the remote URL.
    Example: https://github.com/user/devt-tools.git -> devt-tools
    """
    last_part = url.strip().split("/")[-1]
    # remove .git if present
    name = re.sub(r"\.git$", "", last_part)
    if not name:
        name = "default_repo"
    return name


@app.command("add")
def add_repo(
    source: str,
    branch: str = typer.Option(None, help="Specify the branch for repository sources."),
    workspace: bool = typer.Option(False, help="Add to workspace-level registry."),
    dry_run: bool = typer.Option(False, help="Preview actions without making changes."),
    auto_sync: bool = typer.Option(
        True, help="Automatically sync repositories after adding."
    ),
    name_override: Optional[str] = typer.Option(
        None, "--name", help="Override the inferred repository name."
    ),
):
    """
    Add tools from a repository to the registry.

    Example:
        devt repo add https://github.com/dkuwcreator/devt-tools.git --branch main --workspace
    """
    app_dir = WORKSPACE_REGISTRY_DIR if workspace else REGISTRY_DIR

    registry_file = app_dir / "registry.json"
    typer.echo(f"Adding repository tools to registry from {registry_file}...")
    registry_manager = RegistryManager(registry_file)
    # Derive a name for the repo if not explicitly provided
    repo_name = name_override or guess_repo_name_from_url(source)
    repo_dir = app_dir / "repos" / repo_name

    typer.echo(f"[devt] Using registry file: {registry_file}")

    if dry_run:
        typer.echo(f"[dry-run] Would clone or update repo '{source}' into '{repo_dir}'")
        raise typer.Exit()

    # Create a ToolRepo object for this repository
    tool_repo = ToolRepo(
        name=repo_name,
        base_path=repo_dir,
        registry_manager=registry_manager,
        remote_url=source,
        branch=branch,
        auto_sync=auto_sync,
    )

    try:
        tool_repo.add_repo()
    except Exception as e:
        logger.exception("An error occurred while adding repository tools: %s", e)
        raise typer.Exit(code=1)


@app.command("remove")
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
    registry_manager = RegistryManager(registry_file)

    repo_dir = app_dir / "repos" / repo_name

    if not repo_dir.exists():
        logger.error("[devt] Repository directory '%s' not found.", repo_dir)
        raise typer.Exit(code=1)

    # Confirm removal if not forced.
    if not force:
        if not typer.confirm(
            f"Are you sure you want to remove repository '{repo_name}' and all its tools?"
        ):
            typer.echo("Operation cancelled.")
            raise typer.Exit()

    if dry_run:
        typer.echo(f"[dry-run] Would remove repository '{repo_name}' at '{repo_dir}'")
        raise typer.Exit()

    # Create a ToolRepo just so we can call remove_collection()
    tool_repo = ToolRepo(
        name=repo_name,
        base_path=repo_dir,
        registry_manager=registry_manager,
        remote_url="",
    )

    try:
        tool_repo.remove_repo(force=force)
        typer.echo(f"[devt] Repository '{repo_name}' and its associated tools removed.")
    except Exception as e:
        logger.error("[devt] Failed to remove repository '%s': %s", repo_name, e)
        raise typer.Exit(code=1)


def _sync_one_repo(
    repo_name: str,
    workspace: bool,
    registry_manager: RegistryManager,
    raise_on_missing: bool = True,
) -> None:
    """
    Perform the actual sync logic for a single repo.
    If `raise_on_missing` is True, raise typer.Exit if the repo directory is missing.
    If False, just log a warning and return.
    """
    app_dir = WORKSPACE_REGISTRY_DIR if workspace else REGISTRY_DIR
    repos_dir = app_dir / "repos"
    single_repo_dir = repos_dir / repo_name

    if not single_repo_dir.exists():
        msg = f"[devt] Requested repo '{repo_name}' not found at {single_repo_dir}"
        if raise_on_missing:
            logger.error(msg)
            raise typer.Exit(code=1)
        else:
            logger.warning(msg)
            return

    logger.info(f"[devt] Syncing repository: {repo_name}")

    # Look up registry data
    matching_entry = None
    for tool_key, data in registry_manager.registry.items():
        if data.get("dir") == repo_name:
            matching_entry = data
            break

    remote_url = matching_entry["source"] if matching_entry else ""
    branch = matching_entry.get("branch") if matching_entry else None
    auto_sync = matching_entry.get("auto_sync") if matching_entry else True

    # Sync the single repo
    tool_repo = ToolRepo(
        name=repo_name,
        base_path=single_repo_dir,
        registry_manager=registry_manager,
        remote_url=remote_url,
        branch=branch,
        auto_sync=auto_sync,
    )
    try:
        tool_repo.update_repo()
        typer.echo(f"Repository '{repo_name}' sync completed.")
    except Exception as e:
        logger.error(f"[devt] Failed to sync repository {repo_name}: {e}")


@app.command("sync")
def sync_repo(
    repo_name: str = typer.Argument(..., help="Name of the repository to sync."),
    workspace: bool = typer.Option(
        False,
        help="Sync a repository from the workspace registry instead of user-level.",
    ),
):
    """
    Sync a single repository by pulling the latest changes.

    Example:
        devt sync devt-tools
        devt sync devt-tools --workspace
    """
    app_dir = WORKSPACE_REGISTRY_DIR if workspace else REGISTRY_DIR
    registry_file = app_dir / "registry.json"
    registry_manager = RegistryManager(registry_file)

    _sync_one_repo(repo_name, workspace, registry_manager, raise_on_missing=True)


@app.command("sync-all")
def sync_all(
    workspace: bool = typer.Option(
        False, help="Sync all repositories from workspace registry."
    ),
):
    """
    Sync ALL repositories by pulling the latest changes.

    Example:
        devt sync-all
        devt sync-all --workspace
    """
    app_dir = WORKSPACE_REGISTRY_DIR if workspace else REGISTRY_DIR
    registry_file = app_dir / "registry.json"
    registry_manager = RegistryManager(registry_file)

    repos_dir = app_dir / "repos"
    if not repos_dir.exists():
        logger.warning(f"[devt] Repositories directory not found: {repos_dir}")
        return

    logger.info("[devt] Starting repository sync of ALL repos...")

    repo_paths = [p for p in repos_dir.iterdir() if p.is_dir()]

    if not repo_paths:
        logger.warning(f"[devt] No repositories found in directory: {repos_dir}")
        return

    for repo_path in repo_paths:
        if not repo_path.is_dir() or repo_path.name.startswith(".git"):
            continue

        current_repo_name = repo_path.name

        # Reuse the same sync logic. But here we use `raise_on_missing=False`
        # so that if one repo is missing or fails, we don't exit the entire loop.
        _sync_one_repo(
            repo_name=current_repo_name,
            workspace=workspace,
            registry_manager=registry_manager,
            raise_on_missing=False,
        )

    logger.info("[devt] Repository sync completed.")


# ---------------------------------------------------------------------------
# Managing Local Package commands
# ---------------------------------------------------------------------------
@app.command("import")
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
    registry_manager = RegistryManager(registry_file)

    local_path_obj = Path(local_path).resolve()
    if not local_path_obj.exists():
        logger.error("Path '%s' does not exist.", local_path)
        raise typer.Exit()

    # Base destination for local packages.
    dest_base = app_dir / "tools"

    if local_path_obj.is_file() or (local_path_obj / "manifest.json").is_file():
        # Assume it's a manifest file: use its parent as the package.
        pkg_folder = (
            local_path_obj.parent if local_path_obj.is_file() else local_path_obj
        )
        print(pkg_folder)
        group_name = group if group else "default"
        dest = dest_base / group_name / pkg_folder.name
        if dry_run:
            logger.info(
                "Dry run: would import package from file '%s' to '%s'", local_path, dest
            )
            raise typer.Exit()
        tool_group = ToolGroup(
            name=group_name,
            base_path=dest,
            registry_manager=registry_manager,
            source=pkg_folder,
        )
        try:
            tool_group.add_group()
        except Exception as e:
            logger.error("Failed to import package from file '%s': %s", local_path, e)
            raise typer.Exit(code=1)
    elif local_path_obj.is_dir():
        # Assume it's a folder with multiple packages.
        group_name = group if group else local_path_obj.name
        dest = dest_base / group_name
        if dry_run:
            logger.info(
                "Dry run: would import package from folder '%s' to '%s'",
                local_path,
                dest,
            )
            raise typer.Exit()
        tool_group = ToolGroup(
            name=group_name,
            base_path=dest,
            registry_manager=registry_manager,
            source=local_path_obj,
        )
        try:
            tool_group.add_group()
        except Exception as e:
            logger.error("Failed to import package from folder '%s': %s", local_path, e)
            raise typer.Exit(code=1)
    else:
        logger.error("Path '%s' is neither a file nor a directory.", local_path)
        raise typer.Exit()

    logger.info(
        "Local package(s) successfully imported into the registry under group '%s'.",
        group_name,
    )
    typer.echo(f"Imported local package(s) into group '{group_name}'.")


@app.command("delete")
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

    registry_manager = RegistryManager(registry_file)

    if group:
        tool_group = ToolGroup(
            name=name,
            base_path=app_dir / "tools" / name,
            registry_manager=registry_manager,
            source="",
        )
        try:
            tool_group.remove_group(force=force)
        except Exception as e:
            logger.error("Failed to remove local group '%s': %s", name, e)
            raise typer.Exit(code=1)
    else:
        tool, registry_dir = get_tool(name)
        tool_group = ToolGroup(
            name=name,
            base_path=app_dir / "tools" / tool.get("dir"),
            registry_manager=registry_manager,
            source="",
        )
        try:
            tool_group.remove_package(name)
        except Exception as e:
            logger.error("Failed to remove local tool '%s': %s", name, e)
            raise typer.Exit(code=1)


# @app.command("export")
# def export_tool_or_group(
#     name: str = typer.Argument(
#         ..., help="Identifier of the local tool to export or group name."
#     ),
#     destination: str = typer.Argument(..., help="Destination directory for export."),
#     group: bool = typer.Option(
#         False,
#         "--group",
#         help="Treat 'name' as a group name to export all tools in that group.",
#     ),
#     workspace: bool = typer.Option(False, help="Operate on workspace-level registry."),
#     dry_run: bool = typer.Option(False, help="Preview actions without changes."),
# ):
#     """
#     Export a local tool or a group of local tools to a specified destination.

#     If --group is provided, 'name' is treated as a group name and all tools in that group are exported.
#     Otherwise, 'name' is treated as a tool identifier.
#     """
#     app_dir = WORKSPACE_REGISTRY_DIR if workspace else REGISTRY_DIR
#     registry_file = app_dir / "registry.json"
#     registry = load_json(registry_file)
#     dest = Path(destination).resolve()

#     if group:
#         tools_in_group = {
#             tool: data
#             for tool, data in registry.items()
#             if data.get("location", "").startswith("tools") and data.get("dir") == name
#         }
#         if not tools_in_group:
#             logger.error("No local tools found in group '%s'.", name)
#             raise typer.Exit()
#         if dry_run:
#             typer.echo(
#                 f"Dry run: would export tools in group '{name}': {list(tools_in_group.keys())} to {dest}"
#             )
#             raise typer.Exit()
#         dest_group = dest / name
#         dest_group.mkdir(parents=True, exist_ok=True)
#         for tool, data in tools_in_group.items():
#             tool_manifest = Path(data.get("location"))
#             if not tool_manifest.is_absolute():
#                 tool_manifest = app_dir / tool_manifest
#             tool_folder = tool_manifest.parent
#             tool_dest = dest_group / tool_folder.name
#             shutil.copytree(tool_folder, tool_dest, dirs_exist_ok=True)
#             typer.echo(f"Exported tool '{tool}' to {tool_dest}")
#         typer.echo(f"Exported group '{name}' to {dest_group}")
#     else:
#         if name not in registry:
#             logger.error("Local tool '%s' not found in registry.", name)
#             raise typer.Exit()
#         data = registry[name]
#         if not data.get("location", "").startswith("tools"):
#             logger.error("Tool '%s' is not a local package.", name)
#             raise typer.Exit()
#         tool_manifest = Path(data.get("location"))
#         if not tool_manifest.is_absolute():
#             tool_manifest = app_dir / tool_manifest
#         tool_folder = tool_manifest.parent
#         tool_dest = dest / tool_folder.name
#         if dry_run:
#             typer.echo(f"Dry run: would export tool '{name}' to {tool_dest}")
#             raise typer.Exit()
#         shutil.copytree(tool_folder, tool_dest, dirs_exist_ok=True)
#         typer.echo(f"Exported tool '{name}' to {tool_dest}")


# @app.command("rename-group")
# def rename_group(
#     old_name: str = typer.Argument(..., help="Current group name."),
#     new_name: str = typer.Argument(..., help="New group name."),
#     workspace: bool = typer.Option(False, help="Operate on workspace-level registry."),
#     force: bool = typer.Option(False, help="Force rename without confirmation."),
#     dry_run: bool = typer.Option(False, help="Preview actions without changes."),
# ):
#     """
#     Rename a group of local tools.

#     Updates both the registry entries and physically renames the group folder under base_dir/tools.
#     """
#     app_dir = WORKSPACE_REGISTRY_DIR if workspace else REGISTRY_DIR
#     registry_file = app_dir / "registry.json"
#     registry = load_json(registry_file)

#     tools_in_group = {
#         tool: data
#         for tool, data in registry.items()
#         if data.get("location", "").startswith("tools") and data.get("dir") == old_name
#     }
#     if not tools_in_group:
#         logger.error("No local tools found in group '%s'.", old_name)
#         raise typer.Exit()

#     if not force and not typer.confirm(
#         f"Are you sure you want to rename group '{old_name}' to '{new_name}'?"
#     ):
#         typer.echo("Operation cancelled.")
#         raise typer.Exit()

#     if dry_run:
#         typer.echo(
#             f"Dry run: would rename group '{old_name}' to '{new_name}' for tools: {list(tools_in_group.keys())}"
#         )
#         raise typer.Exit()

#     old_group_dir = app_dir / "tools" / old_name
#     new_group_dir = app_dir / "tools" / new_name
#     if old_group_dir.exists():
#         try:
#             old_group_dir.rename(new_group_dir)
#             typer.echo(f"Renamed folder '{old_group_dir}' to '{new_group_dir}'")
#         except Exception as e:
#             logger.error(
#                 "Failed to rename group folder '%s' to '%s': %s",
#                 old_group_dir,
#                 new_group_dir,
#                 e,
#             )
#             raise
#     else:
#         logger.error("Group directory '%s' not found.", old_group_dir)
#         raise typer.Exit()

#     for tool, data in tools_in_group.items():
#         data["dir"] = new_name
#         old_location_prefix = f"tools/{old_name}"
#         new_location_prefix = f"tools/{new_name}"
#         if data.get("location", "").startswith(old_location_prefix):
#             data["location"] = data["location"].replace(
#                 old_location_prefix, new_location_prefix, 1
#             )
#     save_json(registry_file, registry)
#     typer.echo(f"Group renamed from '{old_name}' to '{new_name}' in registry.")


# @app.command("move")
# def move_tool(
#     tool_name: str = typer.Argument(..., help="Identifier of the local tool to move."),
#     new_group: str = typer.Argument(
#         ..., help="New group name where the tool will be moved."
#     ),
#     workspace: bool = typer.Option(False, help="Operate on workspace-level registry."),
#     force: bool = typer.Option(False, help="Force move without confirmation."),
#     dry_run: bool = typer.Option(False, help="Preview actions without changes."),
# ):
#     """
#     Move a local tool from its current group to a new group.

#     Updates the registry entry's group ("dir" field) and physically moves the tool folder.
#     """
#     app_dir = WORKSPACE_REGISTRY_DIR if workspace else REGISTRY_DIR
#     registry_file = app_dir / "registry.json"
#     registry = load_json(registry_file)

#     if tool_name not in registry:
#         logger.error("Local tool '%s' not found in registry.", tool_name)
#         raise typer.Exit()

#     data = registry[tool_name]
#     if not data.get("location", "").startswith("tools"):
#         logger.error("Tool '%s' is not a local package.", tool_name)
#         raise typer.Exit()

#     current_group = data.get("dir")
#     if current_group == new_group:
#         typer.echo(f"Tool '{tool_name}' is already in group '{new_group}'.")
#         raise typer.Exit()

#     tool_manifest = Path(data.get("location"))
#     if not tool_manifest.is_absolute():
#         tool_manifest = app_dir / tool_manifest
#     tool_folder = tool_manifest.parent
#     new_tool_folder = app_dir / "tools" / new_group / tool_folder.name

#     if not force and not typer.confirm(
#         f"Move tool '{tool_name}' from group '{current_group}' to '{new_group}'?"
#     ):
#         typer.echo("Operation cancelled.")
#         raise typer.Exit()

#     if dry_run:
#         typer.echo(
#             f"Dry run: would move tool '{tool_name}' from '{tool_folder}' to '{new_tool_folder}'"
#         )
#         raise typer.Exit()

#     new_group_dir = app_dir / "tools" / new_group
#     new_group_dir.mkdir(parents=True, exist_ok=True)

#     try:
#         shutil.move(str(tool_folder), str(new_tool_folder))
#         data["dir"] = new_group
#         old_location_prefix = f"tools/{current_group}"
#         new_location_prefix = f"tools/{new_group}"
#         if data.get("location", "").startswith(old_location_prefix):
#             data["location"] = data["location"].replace(
#                 old_location_prefix, new_location_prefix, 1
#             )
#         save_json(registry_file, registry)
#         typer.echo(f"Tool '{tool_name}' moved to group '{new_group}'.")
#     except Exception as e:
#         logger.error("Failed to move tool '%s': %s", tool_name, e)
#         raise


# ---------------------------------------------------------------------------
# Visualization Commands (List, Info)
# ---------------------------------------------------------------------------
@app.command("list")
def list_tools(
    user_level: bool = typer.Option(
        False, "--user", help="List only user-level tools."
    ),
    workspace_level: bool = typer.Option(
        False, "--workspace", help="List only workspace-level tools."
    ),
    all_tools: bool = typer.Option(
        False, "--all", help="Include inactive tools as well."
    ),
):
    """
    List tools from the user and/or workspace registry in a concise table.
    """
    if not user_level and not workspace_level:
        user_level = True
        workspace_level = True

    def load_registry(file_path: Path, scope: str) -> List[dict]:
        data = load_json(file_path) or {}
        tools = []
        for registry_key, info in data.items():
            manifest = info.get("manifest", {})
            tools.append(
                {
                    "registry_key": registry_key,
                    "name": manifest.get("name", registry_key),
                    "description": manifest.get("description", ""),
                    "command": manifest.get("command", ""),
                    "dir": info.get("dir", ""),
                    "active": info.get("active", True),
                    "source": info.get("source", ""),
                    "added": info.get("added", ""),
                    "scope": scope,
                }
            )
        return tools

    found_tools = []
    if user_level:
        found_tools.extend(load_registry(REGISTRY_FILE, "user"))
    if workspace_level:
        found_tools.extend(load_registry(WORKSPACE_REGISTRY_FILE, "workspace"))

    if not all_tools:
        found_tools = [t for t in found_tools if t["active"]]

    if not found_tools:
        typer.echo("No tools found.")
        return

    header = f"{'Name':<20} {'Command':<15} {'Active':<7} {'Dir':<20} {'Source':<40} {'Added'}"
    typer.echo(header)
    typer.echo("-" * len(header))

    for tool in found_tools:
        typer.echo(
            f"{tool['name'][:19]:<20} "
            f"{tool['command'][:14]:<15} "
            f"{'Yes' if tool['active'] else 'No':<7} "
            f"{tool['dir'][:19]:<20} "
            f"{tool['source'][:39]:<40} "
            f"{tool['added'].split('.')[0]}"
        )


def find_tool_in_registry(tool_name: str, registry_file: Path) -> Optional[dict]:
    """
    Looks for `tool_name` in the given registry_file.
    Returns the tool info dict if found, otherwise None.
    """
    registry_data = load_json(registry_file)
    return registry_data.get(tool_name)


@app.command("info")
def show_tool_info(
    tool_name: str = typer.Argument(..., help="Name (key) of the tool to show info."),
    all_tools: bool = typer.Option(False, "--all", help="Show inactive tool info too."),
):
    """
    Show detailed information about a single tool, checking workspace first, then user-level.
    """
    workspace_tool = find_tool_in_registry(tool_name, WORKSPACE_REGISTRY_FILE)
    if workspace_tool:
        found_tool = workspace_tool
        scope = "workspace"
    else:
        user_tool = find_tool_in_registry(tool_name, REGISTRY_FILE)
        if user_tool:
            found_tool = user_tool
            scope = "user"
        else:
            typer.echo(f"No tool named '{tool_name}' found.")
            raise typer.Exit(code=0)

    is_active = found_tool.get("active", True)
    if not all_tools and not is_active:
        typer.echo(f"Tool '{tool_name}' is inactive. Use --all to see inactive tools.")
        raise typer.Exit(code=0)

    manifest = found_tool.get("manifest", {})
    typer.echo("─" * 60)
    typer.echo(f"Tool Name:      {manifest.get('name', tool_name)}")
    typer.echo(f"Registry Key:   {tool_name}")
    typer.echo(f"Scope:          {scope}")
    typer.echo(f"Active:         {is_active}")
    typer.echo(f"Source:         {found_tool.get('source', '')}")
    typer.echo(f"Location:       {found_tool.get('location', '')}")
    typer.echo(f"Added:          {found_tool.get('added', '')}")
    typer.echo(f"Auto Sync:      {found_tool.get('auto_sync', False)}")
    typer.echo(f"Description:    {manifest.get('description', '')}")
    typer.echo(f"Command:        {manifest.get('command', '')}")
    typer.echo("─" * 60)

    dependencies = manifest.get("dependencies", {})
    if dependencies:
        typer.echo("Dependencies:")
        for dep_name, dep_version in dependencies.items():
            typer.echo(f"  • {dep_name}: {dep_version}")
        typer.echo("")

    scripts = manifest.get("scripts", {})
    if not scripts:
        typer.echo("No scripts defined.")
        return

    typer.echo("Scripts:")
    for key, value in scripts.items():
        if isinstance(value, dict):
            for sub_name, sub_cmd in value.items():
                typer.echo(f"  • {key}/{sub_name}: {sub_cmd}")
        else:
            typer.echo(f"  • {key}: {value}")
    typer.echo("─" * 60)


# ---------------------------------------------------------------------------
# Project Commands (Init)
# ---------------------------------------------------------------------------


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
            "destroy": "echo 'Destroy project resources'",
        },
    }
    with project_file.open("w") as f:
        json.dump(default_config, f, indent=4)
    typer.echo("Initialized project with workspace.json.")


# ---------------------------------------------------------------------------
# Execute Commands (Do, Run, Install, Uninstall, Upgrade, Version, Test)
# ---------------------------------------------------------------------------

# import psutil

# def is_activated_by_powershell():
#     parent_process = psutil.Process().parent()
#     print(psutil)
#     print(psutil.Process())
#     print(psutil.Process().parent())
#     print(psutil.Process().parent().parent())
#     print(psutil.Process().parent().parent().parent())
#     print(parent_process)
#     print(parent_process.name())
#     return 'powershell' in parent_process.name().lower()




@app.command("do")
def do(
    tool_name: str = typer.Argument(..., help="The tool to run the script for."),
    script_name: str = typer.Argument(..., help="The name of the script to run."),
    additional_args: Annotated[Optional[List[str]], typer.Argument()] = None,
):
    """
    Run a specified script for the given tool.

    The tool is looked up first in the workspace registry, then in the user registry.
    """

    # if is_activated_by_powershell():
    #     print("This script was activated by PowerShell.")
    # else:
    #     print("This script was not activated by PowerShell.")

    # Lookup the tool from the registries.
    try:
        tool, registry_dir = get_tool(tool_name)
    except ValueError as ve:
        raise typer.Exit(str(ve))

    # If auto_sync is enabled, update the repository.
    if tool.get("auto_sync", False):
        registry_manager = RegistryManager(registry_dir / "registry.json")
        _sync_one_repo(
            tool.get("dir", ""),
            workspace=(registry_dir == WORKSPACE_REGISTRY_DIR),
            registry_manager=registry_manager,
            raise_on_missing=False,
        )
        try:
            tool, registry_dir = get_tool(tool_name)
        except ValueError as ve:
            raise typer.Exit(str(ve))

    manifest_path = registry_dir / tool.get("location")

    executor = ManifestRunner(manifest_path)

    # Execute a script synchronously.
    try:
        executor.run_script(script_name, additional_args)
    except Exception as e:
        print(f"Execution error: {e}")


@app.command()
def run(
    script_name: str = typer.Argument(..., help="The name of the script to run."),
    additional_args: Annotated[Optional[List[str]], typer.Argument()] = None,
):
    """
    Run a specified script for the given tool.
    """
    # Check if "workspace" .json | .cjson | .yaml | .yml exists in the current directory.
    workspace_file = find_file_type("workspace")
    if not workspace_file:
        typer.echo("No workspace file found in the current directory.")
        raise typer.Exit(code=1)

    executor = ManifestRunner(workspace_file)

    # Execute a script synchronously.
    try:
        executor.run_script(script_name, additional_args)
    except Exception as e:
        print(f"Execution error: {e}")


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
def my_version():
    typer.echo(f"Version: {__version__}")


def check_for_update(current_version):
    try:
        response = requests.get(
            "https://api.github.com/repos/dkuwcreator/devt/releases/latest"
        )
        response.raise_for_status()
        latest_version = response.json()["tag_name"]
        logger.info(f"Latest version: {latest_version}")
        return latest_version if latest_version != current_version else None
    except requests.RequestException as e:
        logger.error(f"Failed to check for updates: {e}")
        return None


def download_latest_version(url, download_path):
    try:
        response = requests.get(url, stream=True)
        response.raise_for_status()
        with open(download_path, "wb") as file:
            shutil.copyfileobj(response.raw, file)
        logger.info(f"Downloaded latest version to {download_path}")
    except requests.RequestException as e:
        logger.error(f"Failed to download the latest version: {e}")
        raise


@app.command()
def my_upgrade():
    import sys

    current_version = __version__
    typer.echo(f"Current version: {current_version}")
    typer.echo("Checking for updates...")
    latest_version = check_for_update(current_version)

    if latest_version:
        typer.echo(f"New version available: {latest_version}. Downloading...")
        download_url = f"https://github.com/dkuwcreator/devt/releases/download/{latest_version}/devt.exe"
        temp_folder = Path(os.getenv("TEMP", "/tmp"))
        download_path = temp_folder / f"devt_{latest_version}.exe"
        download_latest_version(download_url, download_path)

        # Replace the current version with the new one
        current_executable = sys.executable
        try:
            logger.info("Replacing the current executable with the new version...")
            os.replace(download_path, current_executable)
            typer.echo("Upgrade complete!")
        except Exception as e:
            logger.error("Failed to replace the current executable: %s", e)
            typer.echo("Upgrade failed. Please try again.")
    else:
        typer.echo("You are already using the latest version.")


# ------------------------------------------------------------------------------
# Final entry point using a entry() function
# ------------------------------------------------------------------------------
def entry():
    """
    Entry point when calling python cli.py directly.

    If you install this as a package (e.g. via setup.py/pyproject.toml),
    you could have a console_script entry point that calls main().
    """
    app()


if __name__ == "__main__":
    entry()
