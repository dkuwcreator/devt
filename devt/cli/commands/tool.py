import json
import shutil
from pathlib import Path
from typing import Dict, List, Optional

import typer

from devt.cli.helpers import import_and_register_packages, remove_and_unregister_group_packages, remove_and_unregister_single_package
from devt.package.manager import PackageManager
from devt.config_manager import APP_NAME, USER_REGISTRY_DIR, WORKSPACE_REGISTRY_DIR
from devt.registry.manager import RegistryManager

tool_app = typer.Typer(help="Tool management commands")


def print_tool_summary(tool: dict) -> None:
    typer.echo(
        f"Command:     {tool.get('command')}\n"
        f"Name:        {tool.get('name')}\n"
        f"Description: {tool.get('description')}\n"
        f"Location:    {tool.get('location')}\n"
        f"Group:       {tool.get('group')}\n"
        f"Active:      {tool.get('active')}\n"
        "------------------------------------"
    )


def print_tool_details(tool: dict) -> None:
    border = "=" * 60
    typer.secho(border, fg="bright_blue")
    typer.secho(" TOOL INFORMATION ".center(60, " "), fg="bright_blue", bold=True)
    typer.secho(border, fg="bright_blue")
    typer.echo(f"{'Command:':15s} {tool.get('command', 'N/A')}")
    typer.echo(f"{'Name:':15s} {tool.get('name', 'N/A')}")
    typer.echo(f"{'Description:':15s} {tool.get('description', 'N/A')}")
    typer.echo(f"{'Location:':15s} {tool.get('location', 'N/A')}")
    typer.echo(f"{'Group:':15s} {tool.get('group', 'N/A')}")
    typer.echo(f"{'Active:':15s} {tool.get('active', 'N/A')}")
    typer.secho(border, fg="bright_blue")


def print_script_info(tool_command: str, script_name: str, script: dict) -> None:
    script_border = "-" * 60
    typer.secho(script_border, fg="green")
    typer.secho(f'Script: "{script_name}" ', fg="green", bold=True)
    typer.secho(script_border, fg="green")
    for key, value in script.items():
        if key not in ("command", "script"):
            typer.echo(f"{key.capitalize():15s}: {value}")
    typer.secho(script_border, fg="green")
    typer.secho(f" > {APP_NAME} do {tool_command} {script_name}", fg="green", bold=True)


def get_scopes_to_query(scope: str = None) -> Dict[str, RegistryManager]:
    """
    Returns a dictionary mapping scope names to their corresponding
    PackageRegistry instances based on the provided scope filter.
    If scope is None, returns both user and workspace registries.
    """
    if scope:
        scope_lower = scope.lower()
        if scope_lower not in ("user", "workspace"):
            typer.echo("Invalid scope provided. Choose 'user' or 'workspace'.")
            raise typer.Exit(code=1)
        if scope_lower == "user":
            return {"user": RegistryManager(USER_REGISTRY_DIR)}
        else:
            return {"workspace": RegistryManager(WORKSPACE_REGISTRY_DIR)}
    else:
        return {
            "user": RegistryManager(USER_REGISTRY_DIR),
            "workspace": RegistryManager(WORKSPACE_REGISTRY_DIR),
        }


def get_package_from_registries(
    command: str, scope: str
) -> tuple[Optional[dict], Optional[str]]:
    """
    Retrieves a tool package from the user and workspace registries.
    Returns the package and the scope where it was found.
    """
    for scope, registry in get_scopes_to_query(scope).items():
        pkg = registry.retrieve_package(command)
        if pkg:
            return pkg, scope
    return None, None

def get_repo_from_registries(
    name: str, scope: str
) -> tuple[Optional[dict], Optional[str]]:
    """
    Retrieves a repository from the user and workspace registries.
    Returns the repository and the scope where it was found.
    """
    for scope, registry in get_scopes_to_query(scope).items():
        repo = registry.repository_registry.get_repo_by_name(name)
        if repo:
            return repo, scope
    return None, None


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
    registry_dir = USER_REGISTRY_DIR if scope == "user" else WORKSPACE_REGISTRY_DIR
    pkg_manager = PackageManager(registry_dir)
    registry = RegistryManager(registry_dir)
    import_and_register_packages(pkg_manager, registry, path, group, force)


@tool_app.command("list")
def tool_list(
    ctx: typer.Context,
    command: str = typer.Option(None, help="Filter by tool command"),
    name: str = typer.Option(None, help="Filter by tool name (partial match)"),
    description: str = typer.Option(None, help="Filter by tool description"),
    location: str = typer.Option(None, help="Filter by tool location (partial match)"),
    group: str = typer.Option(None, help="Filter by tool group"),
    active: bool = typer.Option(None, help="Filter by active status"),
    scope: str = typer.Option(
        None,
        "--scope",
        help="Scope to filter: 'user' or 'workspace'. If omitted, both are shown.",
    ),
):
    """
    Lists all tools in the registry, with filtering options.
    By default, both user and workspace scopes are displayed.
    """
    scopes_to_query: Dict[str, RegistryManager] = get_scopes_to_query(scope)
    found_any = False
    for sc, registry in scopes_to_query.items():
        tools = registry.package_registry.list_packages(
            command=command,
            name=name,
            description=description,
            location=location,
            group=group,
            active=active,
        )
        typer.echo(f"\nScope: {sc.capitalize()}")
        typer.echo("------------------------------------")
        if tools:
            found_any = True
            for tool in tools:
                print_tool_summary(tool)
        else:
            typer.echo("No tools found in this scope.")
    if not found_any:
        typer.echo("No tools found.")


@tool_app.command("info")
def tool_info(
    ctx: typer.Context,
    command: str = typer.Argument(..., help="Unique tool command identifier"),
    scope: str = typer.Option(
        None,
        "--scope",
        help="Scope to query: 'user' or 'workspace'. If omitted, both are queried.",
    ),
):
    """
    Displays detailed information and available scripts for the specified tool.
    """
    pkg, scope = get_package_from_registries(command, scope)
    if pkg:
        print_tool_details(pkg)
        typer.echo("\nAvailable Scripts:")
        scripts = pkg.get("scripts", {})
        for script_name, script in scripts.items():
            print_script_info(command, script_name, script)
        typer.secho("-" * 60, fg="green")
    else:
        typer.secho(f"Tool '{command}' not found in the specified scope.", fg="red")


@tool_app.command("remove")
def tool_remove(
    ctx: typer.Context,
    command: str = typer.Argument(..., help="Unique tool command to remove"),
):
    """
    Removes a tool package from the specified scope.
    """
    scope = ctx.obj["scope"]
    registry_dir = USER_REGISTRY_DIR if scope == "user" else WORKSPACE_REGISTRY_DIR
    pkg_manager = PackageManager(registry_dir)
    registry = RegistryManager(registry_dir)
    remove_and_unregister_single_package(pkg_manager, registry, command)

@tool_app.command("remove-group")
def tool_remove_group(
    ctx: typer.Context,
    group: str = typer.Argument(..., help="Group name to remove"),
):
    """
    Removes all tool packages in the specified group from the registry.
    """
    scope = ctx.obj["scope"]
    registry_dir = USER_REGISTRY_DIR if scope == "user" else WORKSPACE_REGISTRY_DIR
    pkg_manager = PackageManager(registry_dir)
    registry = RegistryManager(registry_dir)
    remove_and_unregister_group_packages(pkg_manager, registry, group)


@tool_app.command("move")
def tool_move(
    ctx: typer.Context,
    command: str = typer.Argument(..., help="Unique tool command to move"),
    to: str = typer.Argument(
        ..., help="Target registry to move the tool to (user or workspace)"
    ),
    force: bool = typer.Option(
        False, "--force", help="Force overwrite if the package already exists"
    ),
):
    """
    Moves a tool package from one registry to the other (user ⇄ workspace).
    """
    if to.lower() not in ("user", "workspace"):
        typer.echo("Invalid target registry specified. Choose 'user' or 'workspace'.")
        raise typer.Exit(code=1)
    not_to = "workspace" if to == "user" else "user"
    source_dir = USER_REGISTRY_DIR if to == "workspace" else WORKSPACE_REGISTRY_DIR
    source_registry = RegistryManager(source_dir)
    source_pkg_manager = PackageManager(source_dir)

    pkg_info = source_registry.package_registry.get_package(command)
    if not pkg_info:
        typer.echo(f"Tool '{command}' not found in {not_to} registry.")
        raise typer.Exit(code=1)

    target_dir = USER_REGISTRY_DIR if to == "user" else WORKSPACE_REGISTRY_DIR
    target_registry = RegistryManager(target_dir)
    target_pkg_manager = PackageManager(target_dir)

    # Import the package into the target registry
    import_and_register_packages(
        target_pkg_manager,
        target_registry,
        Path(pkg_info["location"]),
        pkg_info["group"],
        force,
    )
    # Delete the package from the source registry
    remove_and_unregister_single_package(source_pkg_manager, source_registry, command)
    typer.echo(f"Tool '{command}' moved to {to} registry.")


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
    package_registry = RegistryManager(ctx.obj["registry_dir"])
    pkg_manager = PackageManager(ctx.obj["registry_dir"])
    pkg_info = package_registry.package_registry.get_package(tool_command)
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
    force: bool = typer.Option(
        False, "--force", help="Force overwrite if the package already exists"
    ),
):
    """
    Copies a tool package from the user registry to the workspace for customization.
    """
    user_registry = RegistryManager(USER_REGISTRY_DIR)
    workspace_registry = RegistryManager(WORKSPACE_REGISTRY_DIR)
    workspace_pkg_manager = PackageManager(WORKSPACE_REGISTRY_DIR)

    pkg_info = user_registry.package_registry.get_package(tool_command)
    if not pkg_info:
        typer.echo(f"Tool '{tool_command}' not found in user registry.")
        raise typer.Exit(code=1)
    pkg_location = Path(pkg_info["location"])
    new_pkg = workspace_pkg_manager.import_package(
        pkg_location, group=pkg_info["group"], force=force
    )[0]
    workspace_registry.register_package(new_pkg.to_dict())


@tool_app.command("sync")
def tool_sync(ctx: typer.Context):
    """
    Syncs active tool packages from the registry by re-importing them
    from their location on disk.
    """
    registries = get_scopes_to_query(ctx.obj["scope"])
    for scope, reg_dir in registries.items():
        registry = RegistryManager(reg_dir)
        pkg_manager = PackageManager(reg_dir)
        count = 0
        # Get only active packages from the registry.
        active_packages = registry.package_registry.list_packages(active=True)
        for pkg in active_packages:
            pkg_location = Path(pkg["location"])
            try:
                new_pkg = pkg_manager.update_package(pkg_location, pkg["group"])
            except Exception as e:
                typer.echo(f"Error importing package from {pkg_location}: {e}")
                continue

            registry.register_package(new_pkg.to_dict(), force=True)
            count += 1
        typer.echo(f"Synced {count} active tool packages in {scope} registry.")
