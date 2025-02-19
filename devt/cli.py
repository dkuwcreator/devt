# devt/cli.py
import json
import shutil
import os
from pathlib import Path
from typing import List, Optional
import zipfile
import requests
import typer
from typing_extensions import Annotated

from devt import __version__

# Import functions and constants from our modules
from devt.config import (
    REGISTRY_FILE_NAME,
    USER_REGISTRY_DIR,
    WORKSPACE_REGISTRY_DIR,
    setup_environment,
)
from devt.logger_manager import configure_formatter, logger, configure_logging
from devt.package_manager import PackageBuilder, PackageManager
from devt.utils import (
    find_file_type,
    find_recursive_manifest_files,
    get_execute_args,
    load_json,
    save_json,
)
from devt.registry_manager import Registry
from devt.executor import ManifestRunner

app = typer.Typer(help="DevT: A tool for managing development tool packages.")

# ---------------------------------------------------------------------------
# Import the RegistryManager class and instantiate it
# ---------------------------------------------------------------------------
user_registry = Registry(USER_REGISTRY_DIR)
workspace_registry = Registry(WORKSPACE_REGISTRY_DIR)

registry_managers = {
    "user": user_registry,
    "workspace": workspace_registry,
}


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
    log_format: str = typer.Option(
        "default",
        help="Log format type (default, detailed).",
        show_default=False,
    ),
):
    """
    Global callback to configure logging before any commands run.
    """
    if scope not in registry_managers:
        raise typer.BadParameter(
            f"Invalid scope: {scope}. Must be 'user' or 'workspace'."
        )

    # Set the global registry manager based on the scope
    ctx.obj = {"registry_manager": registry_managers[scope]}

    # Call the configure_logging function
    configure_logging(log_level)

    # Choose the formatter based on the log format
    configure_formatter(log_format)

    # If you want to prevent "No command provided" confusion, you can handle
    # the case where no subcommand was invoked:
    if not ctx.invoked_subcommand:
        # For example, show help or a message:
        typer.echo("No command provided. Use --help for usage.")
        raise typer.Exit()


## ---------------------------------------------------------------------------
## Managing Local Package functions
## ---------------------------------------------------------------------------


def export_package(package_location: Path, output_path: Path):
    """
    Export a package folder as a zip archive.
    """
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file in package_location.rglob("*"):
            if file.is_file():
                zf.write(file, file.relative_to(package_location))
    return output_path


def move_package(
    pm: PackageManager,
    source_registry: Registry,
    target_registry: Registry,
    package_command: str,
):
    """
    Move a package from one registry (source) to another (target).

    This function copies the package folder from the source registry into the target registry,
    re-reads the package (and its scripts) from the copied folder, adds it to the target registry,
    and then removes it from the source registry.
    """
    package = source_registry.get_package(package_command)
    if not package:
        logger.error("Package '%s' not found in the source registry.", package_command)
        return False

    target_tools_dir = target_registry.registry_path / "tools"
    target_tools_dir.mkdir(parents=True, exist_ok=True)
    current_location = Path(package["location"])
    target_location = target_tools_dir / current_location.name

    try:
        shutil.copytree(current_location, target_location)
    except Exception as e:
        logger.error("Error copying package folder: %s", e)
        return False

    try:
        new_package = PackageBuilder(target_location).build_package()
        target_registry.add_package(
            new_package.command,
            new_package.name,
            new_package.description,
            str(new_package.location),
            new_package.dependencies,
        )
        for script_name, script in new_package.scripts.items():
            try:
                target_registry.add_script(new_package.command, script_name, script)
            except Exception as e:
                logger.error(
                    "Error adding script '%s' to target registry: %s", script_name, e
                )
    except Exception as e:
        logger.error("Error adding package to target registry: %s", e)
        return False

    try:
        pm.remove_package(package_command)
        shutil.rmtree(current_location)
        logger.info("Package '%s' moved successfully.", package_command)
        return True
    except Exception as e:
        logger.error("Error removing package from source registry: %s", e)
        return False


def copy_package_to_workspace(pm, source_registry, target_registry, package_command):
    """
    Copy a package from the user registry to the workspace registry for customization,
    keeping the same command as the original.

    Steps:
      1. Retrieve the package from the source (user) registry.
      2. Copy its folder from the source registry's tools folder into the target registry's tools folder,
         keeping the same folder name.
      3. Re-read the package from the new folder, update its description to indicate customization,
         and add (or update) the package record (and its scripts) into the target registry.
      4. The original package remains intact in the user registry.
    """
    package = source_registry.get_package(package_command)
    if not package:
        logger.error("Package '%s' not found in source registry.", package_command)
        return False

    target_tools_dir = target_registry.registry_path / "tools"
    target_tools_dir.mkdir(parents=True, exist_ok=True)
    current_location = Path(package["location"])
    # Keep the same folder name (and therefore command)
    target_location = target_tools_dir / current_location.name

    # Remove target location if it exists.
    if target_location.exists():
        shutil.rmtree(target_location)
    try:
        shutil.copytree(current_location, target_location)
    except Exception as e:
        logger.error("Error copying package folder: %s", e)
        return False

    try:
        # Re-read the package from the new location.
        new_pkg = PackageBuilder(target_location).build_package()
        # Keep the same command, but update the description to indicate customization.
        new_pkg.description = f"{new_pkg.description} (Customized)"

        # Add or update the package record in the target registry.
        try:
            target_registry.add_package(
                new_pkg.command,
                new_pkg.name,
                new_pkg.description,
                str(new_pkg.location),
                new_pkg.dependencies,
            )
        except Exception as e:
            logger.info(
                "Package record already exists in target registry. Updating it."
            )
            target_registry.update_package(
                new_pkg.command,
                new_pkg.name,
                new_pkg.description,
                str(new_pkg.location),
                new_pkg.dependencies,
            )

        # Add or update each script.
        for script_name, script in new_pkg.scripts.items():
            existing = target_registry.get_script(new_pkg.command, script_name)
            if existing:
                target_registry.update_script(new_pkg.command, script_name, script)
                logger.info("Updated script '%s' for customized package.", script_name)
            else:
                target_registry.add_script(new_pkg.command, script_name, script)
                logger.info("Added script '%s' for customized package.", script_name)
    except Exception as e:
        logger.error("Error adding customized package to target registry: %s", e)
        return False

    logger.info(
        "Package '%s' copied to workspace (customized) successfully.", package_command
    )
    return True


# ---------------------------------------------------------------------------
# Managing Local Package commands
# ---------------------------------------------------------------------------
@app.command("import")
def import_package(
    ctx: typer.Context,
    local_path: Path = typer.Argument(..., help="Path to the local package or folder."),
    group: Optional[str] = typer.Option(
        None, help="Group name for the imported package(s)."
    ),
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
    logger.info("Importing local package(s) from '%s' into the registry.", local_path)
    registry_manager = ctx.obj.get("registry_manager")
    pm = PackageManager(registry_manager)

    def try_import(path, collection):
        try:
            pm.import_package(path, collection=collection)
        except Exception as e:
            logger.error("Error importing package from '%s': %s", path, e)
            raise typer.Exit(code=1)

    if local_path.is_file():
        try_import(local_path, group)
    else:
        collection = group or local_path.name
        for mf in find_recursive_manifest_files(local_path):
            try_import(mf, collection)


@app.command("delete")
def delete_tool(
    ctx: typer.Context,
    command: str = typer.Argument(..., help="Command of the tool to delete."),
    force: bool = typer.Option(False, help="Force deletion without confirmation."),
):
    """
    Delete a tool from the registry.

    Example:
        devt delete <tool command> --scope <user/workspace>
    """
    registry_manager = ctx.obj.get("registry_manager")
    pm = PackageManager(registry_manager)

    if not force and not typer.confirm(
        f"Are you sure you want to delete tool '{command}'?"
    ):
        typer.echo("Operation cancelled.")
        raise typer.Exit()

    try:
        pm.remove_package(command)
        typer.echo(f"Tool '{command}' deleted.")
    except Exception as e:
        logger.error(f"Error deleting tool '{command}': {e}")
        raise typer.Exit(code=1)


@app.command("delete-group")
def delete_group(
    ctx: typer.Context,
    group: str = typer.Argument(..., help="Group name to delete."),
    force: bool = typer.Option(False, help="Force deletion without confirmation."),
):
    """
    Delete a group of tools from the registry.

    Example:
        devt delete-group <group name> --scope <user/workspace>
    """
    registry_manager: Registry = ctx.obj.get("registry_manager")
    pm = PackageManager(registry_manager)

    if not force and not typer.confirm(
        f"Are you sure you want to delete group '{group}'?"
    ):
        typer.echo("Operation cancelled.")
        raise typer.Exit()

    try:
        collection = registry_manager.list_packages(collection=group)
        for pkg in collection:
            pm.remove_package(pkg["command"])
        typer.echo(f"Group '{group}' deleted.")

    except Exception as e:
        logger.error(f"Error deleting group '{group}': {e}")
        raise typer.Exit(code=1)


@app.command("export")
def export_tool(
    ctx: typer.Context,
    command: str = typer.Argument(..., help="Command of the tool to export."),
    output: Path = typer.Argument(..., help="Output path for the exported package."),
):
    """
    Export a tool from the registry as a zip archive.

    Example:
        devt export <tool command> <output path> --scope <user/workspace>
    """
    registry_manager: Registry = ctx.obj.get("registry_manager")

    try:
        package = registry_manager.get_package(command)
        if not package:
            logger.error("Tool '%s' not found in the registry.", command)
            raise typer.Exit(code=1)

        package_location = Path(package["location"])
        if not package_location.exists():
            logger.error("Tool folder '%s' not found.", package_location)
            raise typer.Exit(code=1)

        export_package(package_location, output)
        typer.echo(f"Tool '{command}' exported to '{output}'.")
    except Exception as e:
        logger.error("Error exporting tool '%s': %s", command, e)
        raise typer.Exit(code=1)

@app.command("export-group")
def export_group(
    ctx: typer.Context,
    group: str = typer.Argument(..., help="Group name to export."),
    output: Path = typer.Argument(..., help="Output path for the exported package."),
):
    """
    Export a group of tools from the registry as a zip archive.

    Example:
        devt export-group <group name> <output path> --scope <user/workspace>
    """
    registry_manager: Registry = ctx.obj.get("registry_manager")

    try:
        collection = registry_manager.list_packages(collection=group)
        if not collection:
            logger.error("No tools found in group '%s'.", group)
            raise typer.Exit(code=1)

        group_dir = registry_manager.registry_path / "tools" / group
        if not group_dir.exists():
            logger.error("Group folder '%s' not found.", group_dir)
            raise typer.Exit(code=1)

        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zf:
            for pkg in collection:
                pkg_location = Path(pkg["location"])
                for file in pkg_location.rglob("*"):
                    if file.is_file():
                        zf.write(file, file.relative_to(pkg_location))

        typer.echo(f"Group '{group}' exported to '{output}'.")
    except Exception as e:
        logger.error("Error exporting group '%s': %s", group, e)
        raise typer.Exit(code=1)

@app.command("rename-group")
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


@app.command("move")
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


# # ---------------------------------------------------------------------------
# # Visualization Commands (List, Info)
# # ---------------------------------------------------------------------------
# # TODO: BEGIN - Move these to a separate module and extend with more features
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
    command: Optional[str] = typer.Option(None, help="Filter tools by command."),
    name: Optional[str] = typer.Option(None, help="Filter tools by name."),
    description: Optional[str] = typer.Option(
        None, help="Filter tools by description."
    ),
    location: Optional[str] = typer.Option(None, help="Filter tools by location."),
    collection: Optional[str] = typer.Option(None, help="Filter tools by collection."),
    active: Optional[bool] = typer.Option(None, help="Filter tools by active status."),
):
    """
    List tools from the user and/or workspace registry in a concise table.
    """
    # If neither flag is set, search both registries.
    if not user_level and not workspace_level:
        user_level = True
        workspace_level = True

    found_any = False
    for scope, registry_manager in registry_managers.items():
        if (scope == "user" and not user_level) or (
            scope == "workspace" and not workspace_level
        ):
            continue

        # Determine active filter:
        # If user explicitly passes --active, use that.
        # Otherwise, if --all is not set, only show active tools.
        active_filter = active if active is not None else (None if all_tools else True)

        packages = registry_manager.list_packages(
            command=command,
            name=name,
            description=description,
            location=location,
            collection=collection,
            active=active_filter,
        )

        if not packages:
            typer.echo(f"No tools found in the {scope} registry.")
            continue

        found_any = True
        header = f"{'Tool Command':<20} {'Name':<20} {'Active':<7} {'Collection':<20}"
        typer.echo(f"\n[{scope.upper()} REGISTRY]")
        typer.echo(header)
        typer.echo("-" * len(header))
        for pkg in packages:
            typer.echo(
                f"{pkg['command']:<20} {pkg['name']:<20} "
                f"{('Yes' if pkg['active'] else 'No'):<7} {pkg['collection']:<20}"
            )

    if not found_any:
        typer.echo("No tools found.")


@app.command("show")
def show_tool_info(
    command: str = typer.Argument(..., help="Command of the tool to show."),
    scope: Optional[List[str]] = typer.Option(
        None, "--scope", help="Specify registry scope(s): user and/or workspace"
    ),
):
    """
    Show detailed information about a tool from the registry.

    If --scope is provided, searches in the specified scope(s). Otherwise, uses the default registry.
    """
    found = False
    for scope, registry_manager in registry_managers.items():
        package = registry_manager.get_package(command)
        if package:
            found = True
            typer.echo(f"[{scope.upper()} REGISTRY]")
            typer.echo(f"Tool: {package['name']} ({command})")
            typer.echo(f"Description: {package['description']}")
            typer.echo(f"Location: {package['location']}")
            typer.echo(f"Group: {package['group']}")
            typer.echo(f"Active: {'Yes' if package['active'] else 'No'}")
            typer.echo("Scripts:")
            scripts = registry_manager.list_scripts(command)
            if not scripts:
                typer.echo("  No scripts found.")
            else:
                for script in scripts:
                    typer.echo(f"  Script: {script['script']}")
                    typer.echo(f"    Args: {script['args']}")
                    typer.echo(f"    Shell: {script['shell']}")
                    typer.echo(f"    CWD: {script['cwd']}")
                    typer.echo(f"    Env: {script['env']}")
                    typer.echo(f"    Kwargs: {script['kwargs']}")
            typer.echo("")  # Separate output between scopes

    if not found:
        typer.echo(f"Tool '{command}' not found in the specified registry scope(s).")
        raise typer.Exit(code=1)


# TODO: END

# # # ---------------------------------------------------------------------------
# # # Managing Repository commands
# # # ---------------------------------------------------------------------------
# # @app.command("add")
# # def add_repo(
# #     ctx: typer.Context,
# #     source: str,
# #     branch: str = typer.Option(None, help="Specify the branch for repository sources."),
# #     auto_sync: bool = typer.Option(
# #         True, help="Automatically sync repositories after adding."
# #     ),
# #     name_override: Optional[str] = typer.Option(
# #         None, "--name", help="Override the inferred repository name."
# #     ),
# # ):
# #     """
# #     Add tools from a repository to the registry.

# #     Example:
# #         devt repo add <source> --branch <branch> --name <repo name> --scope <user/workspace>
# #     """
# #     registry_manager = ctx.obj.get("registry_manager")
# #     typer.echo(f"Using registry directory: {registry_manager.location()}")

# #     # Derive a name for the repo if not explicitly provided
# #     repo_name = name_override or guess_repo_name_from_url(source)
# #     repo_dir = registry_manager.location() / "repos" / repo_name

# #     # Create a ToolRepo object for this repository
# #     tool_repo = ToolRepo(
# #         name=repo_name,
# #         base_path=repo_dir,
# #         registry_manager=registry_manager,
# #         remote_url=source,
# #         branch=branch,
# #         auto_sync=auto_sync,
# #     )

# #     try:
# #         tool_repo.add_repo()
# #     except Exception as e:
# #         logger.exception("An error occurred while adding repository tools: %s", e)
# #         raise typer.Exit(code=1)


# # @app.command("remove")
# # def remove_repo(
# #     ctx: typer.Context,
# #     repo_name: str = typer.Argument(
# #         ..., help="Name of the repository (group) to remove."
# #     ),
# #     force: bool = typer.Option(False, help="Force removal without confirmation."),
# # ):
# #     """
# #     Remove a repository and all its associated tools from the registry.

# #     Example:
# #         devt repo remove <repo name> --scope <user/workspace>
# #     """
# #     registry_manager = ctx.obj.get("registry_manager")
# #     typer.echo(f"Using registry directory: {registry_manager.location()}")
# #     repo_dir = registry_manager.location() / "repos" / repo_name

# #     if not repo_dir.exists():
# #         logger.error("[devt] Repository directory '%s' not found.", repo_dir)
# #         raise typer.Exit(code=1)

# #     # Confirm removal if not forced.
# #     if not force:
# #         if not typer.confirm(
# #             f"Are you sure you want to remove repository '{repo_name}' and all its tools?"
# #         ):
# #             typer.echo("Operation cancelled.")
# #             raise typer.Exit()

# #     # Create a ToolRepo just so we can call remove_collection()
# #     tool_repo = ToolRepo(
# #         name=repo_name,
# #         base_path=repo_dir,
# #         registry_manager=registry_manager,
# #         remote_url="",
# #     )

# #     try:
# #         tool_repo.remove_repo(force=force)
# #         typer.echo(f"[devt] Repository '{repo_name}' and its associated tools removed.")
# #     except Exception as e:
# #         logger.error("[devt] Failed to remove repository '%s': %s", repo_name, e)
# #         raise typer.Exit(code=1)


# # def _sync_one_repo(
# #     registry_manager: RegistryManager,
# #     repo_name: str,
# #     raise_on_missing: bool = True,
# # ) -> None:
# #     """
# #     Perform the actual sync logic for a single repo.
# #     If `raise_on_missing` is True, raise typer.Exit if the repo directory is missing.
# #     If False, just log a warning and return.
# #     """
# #     single_repo_dir = registry_manager.location() / "repos" / repo_name

# #     if not single_repo_dir.exists():
# #         msg = f"Requested repo '{repo_name}' not found at {single_repo_dir}"
# #         if raise_on_missing:
# #             logger.error(msg)
# #             raise typer.Exit(code=1)
# #         else:
# #             logger.warning(msg)
# #             return

# #     logger.info(f"Syncing repository: {repo_name}")

# #     # Look up registry data
# #     matching_entry = None
# #     for tool_key, data in registry_manager.registry.items():
# #         if data.get("dir") == repo_name:
# #             matching_entry = data
# #             break

# #     remote_url = matching_entry["source"] if matching_entry else ""
# #     branch = matching_entry.get("branch") if matching_entry else None
# #     auto_sync = matching_entry.get("auto_sync") if matching_entry else True

# #     # Sync the single repo
# #     tool_repo = ToolRepo(
# #         name=repo_name,
# #         base_path=single_repo_dir,
# #         registry_manager=registry_manager,
# #         remote_url=remote_url,
# #         branch=branch,
# #         auto_sync=auto_sync,
# #     )
# #     try:
# #         tool_repo.update_repo()
# #         typer.echo(f"Repository '{repo_name}' sync completed.")
# #     except Exception as e:
# #         logger.error(f"[devt] Failed to sync repository {repo_name}: {e}")


# # @app.command("sync")
# # def sync_repo(
# #     ctx: typer.Context,
# #     repo_name: str = typer.Argument(..., help="Name of the repository to sync."),
# # ):
# #     """
# #     Sync a single repository by pulling the latest changes.

# #     Example:
# #         devt sync <repo name> --scope <user/workspace>
# #     """
# #     registry_manager = ctx.obj.get("registry_manager")

# #     _sync_one_repo(registry_manager, repo_name, raise_on_missing=True)


# # @app.command("sync-all")
# # def sync_all(
# #     ctx: typer.Context,
# # ):
# #     """
# #     Sync ALL repositories by pulling the latest changes.

# #     Example:
# #         devt sync-all --scope <user/workspace>
# #     """
# #     registry_manager = ctx.obj.get("registry_manager")

# #     repos_dir = registry_manager.location() / "repos"
# #     if not repos_dir.exists():
# #         logger.warning(f"Repositories directory not found: {repos_dir}")
# #         return

# #     logger.info("Starting repository sync of ALL repos...")

# #     repo_paths = [p for p in repos_dir.iterdir() if p.is_dir()]

# #     if not repo_paths:
# #         logger.warning(f"No repositories found in directory: {repos_dir}")
# #         return

# #     for repo_path in repo_paths:
# #         if not repo_path.is_dir() or repo_path.name.startswith(".git"):
# #             continue

# #         current_repo_name = repo_path.name

# #         # Reuse the same sync logic. But here we use `raise_on_missing=False`
# #         # so that if one repo is missing or fails, we don't exit the entire loop.
# #         _sync_one_repo(
# #             registry_manager=registry_manager,
# #             repo_name=current_repo_name,
# #             raise_on_missing=False,
# #         )

# #     logger.info("Repository sync completed.")


# # ---------------------------------------------------------------------------
# # Project Commands (Init)
# # ---------------------------------------------------------------------------
# # TODO: BEGIN - (needs refactoring) The functions below should be extended. Add templates feature.


# @app.command("init")
# def init_project():
#     """
#     Initialize the current project by creating a workspace.json configuration file.

#     This file will be added to the workspace registry under the key "workspace".
#     """
#     project_file = Path.cwd() / "workspace.json"
#     if project_file.exists():
#         typer.echo("workspace.json already exists in the current directory.")
#         raise typer.Exit()
#     default_config = {
#         "tools": {},
#         "scripts": {
#             "test": "echo 'Run project tests'",
#             "deploy": "echo 'Deploy project'",
#             "destroy": "echo 'Destroy project resources'",
#         },
#     }
#     with project_file.open("w") as f:
#         json.dump(default_config, f, indent=4)
#     typer.echo("Initialized project with workspace.json.")


# # TODO: END


# # ---------------------------------------------------------------------------
# # Execute Commands (Do, Run, Install, Uninstall, Upgrade, Version, Test)
# # ---------------------------------------------------------------------------
# # def auto_sync_tool(
# #     tool_name: str, registry_dir: Path, registry_manager: RegistryManager
# # ):
# #     """
# #     If auto_sync is enabled for the tool, update the repository.
# #     """
# #     tool = find_tool_in_registry(tool_name, registry_dir / "registry.json")
# #     if tool and tool.get("auto_sync", False):
# #         _sync_one_repo(
# #             tool.get("dir", ""),
# #             workspace=(registry_dir == WORKSPACE_REGISTRY_DIR),
# #             registry_manager=registry_manager,
# #             raise_on_missing=False,
# #         )


# @app.command("do")
# def do(
#     tool_name: str = typer.Argument(..., help="The tool to run the script for."),
#     script_name: str = typer.Argument(..., help="The name of the script to run."),
#     additional_args: Annotated[Optional[List[str]], typer.Argument()] = None,
# ):
#     """
#     Run a specified script for the given tool.

#     The tool is looked up first in the workspace registry, then in the user registry.
#     """
#     # TODO: BEGIN - (needs refactoring) This block should find the tool in the registry, sync if needed, and produce the base_dir and scripts_dict.
#     # Lookup the tool from the registries.
#     try:
#         tool, registry_dir = get_tool(tool_name)
#     except ValueError as ve:
#         raise typer.Exit(str(ve))

#     # If auto_sync is enabled, update the repository.
#     if tool.get("auto_sync", False):
#         _sync_one_repo(
#             registry_manager=RegistryManager(registry_dir),
#             repo_name=tool.get("dir", ""),
#             raise_on_missing=False,
#         )
#         try:
#             tool, registry_dir = get_tool(tool_name)
#         except ValueError as ve:
#             raise typer.Exit(str(ve))

#     manifest_path = registry_dir / tool.get("location")

#     base_dir, scripts_dict = get_execute_args(manifest_path)
#     # TODO: END

#     executor = ManifestRunner(base_dir, scripts_dict)

#     # Execute a script synchronously.
#     try:
#         executor.run_shell_fallback(script_name, additional_args)
#     except Exception as e:
#         print(f"Execution error: {e}")


# @app.command()
# def run(
#     script_name: str = typer.Argument(..., help="The name of the script to run."),
#     additional_args: Annotated[Optional[List[str]], typer.Argument()] = None,
# ):
#     """
#     Run a specified script for the given tool.
#     """
#     # Check if "workspace" .json | .cjson | .yaml | .yml exists in the current directory.
#     workspace_file = find_file_type("workspace")
#     if not workspace_file:
#         typer.echo("No workspace file found in the current directory.")
#         typer.echo("Please run 'devt init' to create a workspace file.")
#         raise typer.Exit(code=1)

#     base_dir, scripts_dict = get_execute_args(workspace_file)

#     executor = ManifestRunner(base_dir, scripts_dict)

#     # Execute a script synchronously.
#     try:
#         executor.run_shell_fallback(script_name, additional_args)
#     except Exception as e:
#         print(f"Execution error: {e}")


# @app.command()
# def install(
#     tools: List[str] = typer.Argument(..., help="List of tool names to install"),
# ):
#     """
#     Install the specified tools.
#     """
#     for tool in tools:
#         do(tool, "install")


# @app.command()
# def uninstall(
#     tools: List[str] = typer.Argument(..., help="List of tool names to uninstall"),
# ):
#     """
#     Uninstall the specified tools.
#     """
#     for tool in tools:
#         do(tool, "uninstall")


# @app.command()
# def upgrade(
#     tools: List[str] = typer.Argument(..., help="List of tool names to upgrade"),
# ):
#     """
#     Upgrade the specified tools.
#     """
#     for tool in tools:
#         do(tool, "upgrade")


# @app.command()
# def version(
#     tools: List[str] = typer.Argument(
#         ..., help="List of tool names to display the version for"
#     ),
# ):
#     """
#     Display the version of the specified tools.
#     """
#     for tool in tools:
#         do(tool, "version")


# @app.command()
# def test(
#     tools: List[str] = typer.Argument(
#         ..., help="List of tool names to run the test for"
#     ),
# ):
#     """
#     Run the test script for the specified tools.
#     """
#     for tool in tools:
#         do(tool, "test")


# # ---------------------------------------------------------------------------
# # App Meta Commands (Version, Upgrade)
# # ---------------------------------------------------------------------------
# # TODO: BEGIN - The functionality of this block should be moved to a separate file (e.g. meta.py) and imported here.
# def check_for_update(current_version):
#     try:
#         response = requests.get(
#             "https://api.github.com/repos/dkuwcreator/devt/releases/latest"
#         )
#         response.raise_for_status()
#         latest_version = response.json()["tag_name"]
#         logger.info(f"Latest version: {latest_version}")
#         return latest_version if latest_version != current_version else None
#     except requests.RequestException as e:
#         logger.error(f"Failed to check for updates: {e}")
#         return None


# def download_latest_version(url, download_path):
#     try:
#         response = requests.get(url, stream=True)
#         response.raise_for_status()
#         with open(download_path, "wb") as file:
#             shutil.copyfileobj(response.raw, file)
#         logger.info(f"Downloaded latest version to {download_path}")
#     except requests.RequestException as e:
#         logger.error(f"Failed to download the latest version: {e}")
#         raise


# @app.command()
# def my_upgrade():
#     import sys

#     current_version = __version__
#     typer.echo(f"Current version: {current_version}")
#     typer.echo("Checking for updates...")
#     latest_version = check_for_update(current_version)

#     if latest_version:
#         typer.echo(f"New version available: {latest_version}. Downloading...")
#         download_url = f"https://github.com/dkuwcreator/devt/releases/download/{latest_version}/devt.exe"
#         temp_folder = Path(os.getenv("TEMP", "/tmp"))
#         download_path = temp_folder / f"devt_{latest_version}.exe"
#         download_latest_version(download_url, download_path)

#         # Replace the current version with the new one
#         current_executable = sys.executable
#         try:
#             logger.info("Replacing the current executable with the new version...")
#             os.replace(download_path, current_executable)
#             typer.echo("Upgrade complete!")
#         except Exception as e:
#             logger.error("Failed to replace the current executable: %s", e)
#             typer.echo("Upgrade failed. Please try again.")
#     else:
#         typer.echo("You are already using the latest version.")


# @app.command()
# def my_version():
#     typer.echo(f"Version: {__version__}")


# # TODO: END


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
    setup_environment()
    entry()
