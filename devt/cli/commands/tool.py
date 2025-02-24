import json
import shutil
from pathlib import Path
from typing import List, Optional

import typer

from devt.package.manager import PackageManager
from devt.config_manager import USER_REGISTRY_DIR, WORKSPACE_REGISTRY_DIR
from devt.registry.manager import PackageRegistry, ScriptRegistry, create_db_engine

tool_app = typer.Typer(help="Tool management commands")


def delete_tool_scripts(registry: ScriptRegistry, command: str) -> None:
    """Delete all scripts for a given tool command."""
    for script in registry.list_scripts(command):
        registry.delete_script(command, script["script"])


def print_tool_info(tool: dict, header: str = "=" * 50) -> None:
    """Print tool information in a formatted way."""
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


def get_target_registries(to: str):
    """Return target package and script registries based on an input string."""
    to_lower = to.lower()
    if to_lower == "user":
        target_package_registry = PackageRegistry(
            create_db_engine(registry_path=USER_REGISTRY_DIR)
        )
        target_script_registry = ScriptRegistry(
            create_db_engine(registry_path=USER_REGISTRY_DIR)
        )
    elif to_lower == "workspace":
        target_package_registry = PackageRegistry(
            create_db_engine(registry_path=WORKSPACE_REGISTRY_DIR)
        )
        target_script_registry = ScriptRegistry(
            create_db_engine(registry_path=WORKSPACE_REGISTRY_DIR)
        )
    else:
        target_package_registry = target_script_registry = None
    return target_package_registry, target_script_registry


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
    group: str = typer.Option(
        None, "--group", help="Custom group name for the tool package (optional)"
    ),
):
    """
    Imports a tool package (or multiple tool packages) into the registry.
    """
    scope = ctx.obj["scope"]
    package_registry: PackageRegistry = ctx.obj["package_registry"]
    script_registry: ScriptRegistry = ctx.obj["script_registry"]
    pkg_manager: PackageManager = ctx.obj["pkg_manager"]

    if path.suffix.lower() == ".zip":
        destination_dir = path.parent / path.stem
        path = pkg_manager.unpack_package(path, destination_dir)

    packages = pkg_manager.import_package(path, group=group, force=force)
    count = 0
    for pkg in packages:
        existing_pkg = package_registry.get_package(pkg.command)
        if existing_pkg:
            if force:
                package_registry.delete_package(pkg.command)
                delete_tool_scripts(script_registry, pkg.command)
            else:
                typer.echo(
                    f"Package '{pkg.command}' already exists. Use --force to overwrite."
                )
                continue
        package_registry.add_package(
            pkg.command,
            pkg.name,
            pkg.description,
            str(pkg.location),
            pkg.dependencies,
            group=pkg.group,
        )
        for script_name, script in pkg.scripts.items():
            script_registry.add_script(pkg.command, script_name, script.to_dict())
        count += 1
    typer.echo(f"Imported {count} tool package(s) into the {scope} registry.")


@tool_app.command("list")
def tool_list(
    ctx: typer.Context,
    command: str = typer.Option(None, help="Filter by tool command"),
    name: str = typer.Option(None, help="Filter by tool name (partial match)"),
    description: str = typer.Option(None, help="Filter by tool description"),
    location: str = typer.Option(None, help="Filter by tool location (partial match)"),
    group: str = typer.Option(None, help="Filter by tool group"),
    active: bool = typer.Option(None, help="Filter by active status"),
):
    """
    Lists all tools in the registry, with filtering options.
    """
    package_registry: PackageRegistry = ctx.obj["package_registry"]
    tools = package_registry.list_packages(
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
    Displays detailed information and available scripts for the specified tool.
    """
    package_registry: PackageRegistry = ctx.obj["package_registry"]
    script_registry: ScriptRegistry = ctx.obj["script_registry"]
    tool = package_registry.get_package(command)
    if not tool:
        typer.echo(f"Tool with command '{command}' not found.")
        raise typer.Exit(code=1)
    print_tool_info(tool)
    scripts = script_registry.list_scripts(command)
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
    package_registry: PackageRegistry = ctx.obj["package_registry"]
    script_registry: ScriptRegistry = ctx.obj["script_registry"]
    pkg_manager: PackageManager = ctx.obj["pkg_manager"]
    pkg_info = package_registry.get_package(command)
    if not pkg_info:
        typer.echo(f"Tool '{command}' not found in {scope} registry.")
        raise typer.Exit(code=1)
    pkg_location = Path(pkg_info["location"])
    if pkg_manager.delete_package(pkg_location):
        package_registry.delete_package(pkg_info["command"])
        delete_tool_scripts(script_registry, pkg_info["command"])
        typer.echo(f"Tool '{command}' removed from {scope} registry.")
    else:
        typer.echo(f"Failed to remove tool '{command}'.")


@tool_app.command("move")
def tool_move(
    ctx: typer.Context,
    tool_command: str = typer.Argument(..., help="Unique tool command to move"),
    to: str = typer.Option(..., "--to", help="Target registry: user or workspace"),
):
    """
    Moves a tool package from one registry to the other (user ⇄ workspace).
    """
    # Get user and workspace registries (or initialize them on the fly)
    user_package_registry = ctx.obj.get("user_package_registry")
    user_script_registry = ctx.obj.get("user_script_registry")
    workspace_package_registry = ctx.obj.get("workspace_package_registry")
    workspace_script_registry = ctx.obj.get("workspace_script_registry")

    if not (user_package_registry and workspace_package_registry):
        user_engine = create_db_engine(registry_path=USER_REGISTRY_DIR)
        user_package_registry = PackageRegistry(user_engine)
        user_script_registry = ScriptRegistry(user_engine)
        workspace_engine = create_db_engine(registry_path=WORKSPACE_REGISTRY_DIR)
        workspace_package_registry = PackageRegistry(workspace_engine)
        workspace_script_registry = ScriptRegistry(workspace_engine)

    # Determine source registry based on where the tool exists.
    pkg_info = user_package_registry.get_package(tool_command)
    if pkg_info:
        src_package_registry = user_package_registry
        src_script_registry = user_script_registry
    else:
        pkg_info = workspace_package_registry.get_package(tool_command)
        if pkg_info:
            src_package_registry = workspace_package_registry
            src_script_registry = workspace_script_registry
        else:
            typer.echo(f"Tool '{tool_command}' not found in any registry.")
            raise typer.Exit(code=1)

    to_lower = to.lower()
    if to_lower not in ("user", "workspace"):
        typer.echo("Invalid target registry specified. Choose 'user' or 'workspace'.")
        raise typer.Exit(code=1)

    target_package_registry = (
        user_package_registry if to_lower == "user" else workspace_package_registry
    )
    target_script_registry = (
        user_script_registry if to_lower == "user" else workspace_script_registry
    )

    if src_package_registry == target_package_registry:
        typer.echo(f"Tool '{tool_command}' is already in the {to_lower} registry.")
        raise typer.Exit(code=1)

    current_location = Path(pkg_info["location"])
    target_tools_dir = target_package_registry.registry_path / "tools"
    target_tools_dir.mkdir(parents=True, exist_ok=True)
    target_location = target_tools_dir / current_location.name

    try:
        shutil.copytree(current_location, target_location)
    except Exception as e:
        typer.echo(f"Error copying tool folder: {e}")
        raise typer.Exit(code=1)

    pkg_manager = PackageManager(target_package_registry.registry_path / "tools")
    try:
        new_pkg = pkg_manager.import_package(target_location)[0]
    except Exception as e:
        typer.echo(f"Error importing moved tool: {e}")
        raise typer.Exit(code=1)

    target_package_registry.add_package(
        new_pkg.command,
        new_pkg.name,
        new_pkg.description,
        str(new_pkg.location),
        new_pkg.dependencies,
    )
    for script_name, script in new_pkg.scripts.items():
        target_script_registry.add_script(
            new_pkg.command, script_name, script.to_dict()
        )

    src_package_registry.delete_package(pkg_info["command"])
    delete_tool_scripts(src_script_registry, pkg_info["command"])
    try:
        shutil.rmtree(current_location)
    except Exception as e:
        typer.echo(f"Error removing source tool folder: {e}")

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
    package_registry: PackageRegistry = ctx.obj["package_registry"]
    pkg_manager: PackageManager = ctx.obj["pkg_manager"]
    pkg_info = package_registry.get_package(tool_command)
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
    new_command: str = typer.Option(
        None, "--rename", help="New command name for the customized tool"
    ),
):
    """
    Copies a tool package from the user registry to the workspace for customization.
    """
    user_engine = create_db_engine(registry_path=USER_REGISTRY_DIR)
    user_package_registry = PackageRegistry(user_engine)
    workspace_engine = create_db_engine(registry_path=WORKSPACE_REGISTRY_DIR)
    workspace_package_registry = PackageRegistry(workspace_engine)
    workspace_script_registry = ScriptRegistry(workspace_engine)

    pkg_manager = PackageManager(WORKSPACE_REGISTRY_DIR / "tools")
    pkg_info = user_package_registry.get_package(tool_command)
    if not pkg_info:
        typer.echo(f"Tool '{tool_command}' not found in user registry.")
        raise typer.Exit(code=1)
    pkg_location = Path(pkg_info["location"])
    new_pkg = pkg_manager.import_package(pkg_location, pkg_info["group"])[0]
    if new_command:
        new_pkg.command = new_command
    workspace_package_registry.add_package(
        new_pkg.command,
        new_pkg.name,
        new_pkg.description,
        str(new_pkg.location),
        new_pkg.dependencies,
        group=new_pkg.group,
    )
    for script_name, script in new_pkg.scripts.items():
        workspace_script_registry.add_script(
            new_pkg.command, script_name, script.to_dict()
        )
    typer.echo(
        f"Tool '{tool_command}' customized to '{new_pkg.command}' in workspace registry."
    )


@tool_app.command("update")
def tool_update(
    ctx: typer.Context,
    tool_command: str = typer.Argument(
        None,
        help="Unique tool command to update. If omitted, update all tools in the indicated scope.",
    ),
    manifest: Path = typer.Option(
        None,
        "--manifest",
        help="Path to updated manifest file (used for a specific tool if provided)",
    ),
):
    """
    Updates tool package(s) using an updated manifest file.
    """
    scope = ctx.obj["scope"]
    package_registry: PackageRegistry = ctx.obj["package_registry"]
    script_registry: ScriptRegistry = ctx.obj["script_registry"]
    pkg_manager: PackageManager = ctx.obj["pkg_manager"]

    def update_single_tool(command: str) -> None:
        pkg_info = package_registry.get_package(command)
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
        package_registry.update_package(
            new_pkg.command,
            new_pkg.name,
            new_pkg.description,
            str(new_pkg.location),
            new_pkg.dependencies,
        )
        for script_name, script in new_pkg.scripts.items():
            script_registry.update_script(
                new_pkg.command, script_name, script.to_dict()
            )
        typer.echo(f"Tool '{command}' updated in {scope} registry.")

    if tool_command:
        update_single_tool(tool_command)
    else:
        all_packages = package_registry.list_packages()
        if not all_packages:
            typer.echo(f"No tools found in {scope} registry to update.")
            raise typer.Exit(code=0)
        for pkg in all_packages:
            update_single_tool(pkg["command"])

@tool_app.command("sync")
def tool_sync(ctx: typer.Context):
    """
    Syncs active tool packages from the registry by re-importing them
    from their location on disk.
    """
    from devt.config_manager import USER_REGISTRY_DIR, WORKSPACE_REGISTRY_DIR

    registries = {}
    for scope, registry_dir in [("user", USER_REGISTRY_DIR), ("workspace", WORKSPACE_REGISTRY_DIR)]:
        engine = create_db_engine(registry_path=registry_dir)
        registries[scope] = {
            "package_registry": PackageRegistry(engine),
            "script_registry": ScriptRegistry(engine),
            "tools_dir": registry_dir / "tools",
        }

    for scope, reg in registries.items():
        count = 0
        # Get only active packages from the registry.
        active_packages = reg["package_registry"].list_packages(active=True)
        for pkg in active_packages:
            pkg_location = Path(pkg["location"])
            pm = PackageManager(reg["tools_dir"])
            try:
                packages = pm.import_package(pkg_location, pkg["group"], force=True)
                new_pkg = packages[0]
            except Exception as e:
                typer.echo(f"Error importing package from {pkg_location}: {e}")
                continue

            # Update the package and its scripts in the registry.
            if reg["package_registry"].get_package(new_pkg.command):
                reg["package_registry"].update_package(
                    new_pkg.command,
                    new_pkg.name,
                    new_pkg.description,
                    str(new_pkg.location),
                    new_pkg.dependencies,
                )
                for script_name, script in new_pkg.scripts.items():
                    reg["script_registry"].update_script(
                        new_pkg.command, script_name, script.to_dict()
                    )
            else:
                reg["package_registry"].add_package(
                    new_pkg.command,
                    new_pkg.name,
                    new_pkg.description,
                    str(new_pkg.location),
                    new_pkg.dependencies,
                    group=getattr(new_pkg, "group", None),
                )
                for script_name, script in new_pkg.scripts.items():
                    reg["script_registry"].add_script(
                        new_pkg.command, script_name, script.to_dict()
                    )
            count += 1
        typer.echo(f"Synced {count} active package(s) in the {scope} registry.")

    typer.echo("Synchronization completed.")
