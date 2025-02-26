from pathlib import Path
from typing import Optional

import typer
import logging

from devt.cli.helpers import get_managers
from devt.config_manager import APP_NAME
from devt.utils import print_table

from devt.cli.tool_service import ToolService

logger = logging.getLogger(__name__)
tool_app = typer.Typer(help="Tool management commands")


def handle_errors(func):
    import functools

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.exception("An error occurred in %s:", func.__name__)
            typer.echo(f"An error occurred: {e}")
            raise typer.Exit(code=1)

    return wrapper


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


@tool_app.command("import")
@handle_errors
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
    Imports a tool package (or multiple tool packages) into the registry.
    """
    logger.info("Starting tool import: path=%s, force=%s, group=%s", path, force, group)
    service = ToolService.from_context(ctx)
    service.import_tool(path, group or "default", force)
    logger.info("Tool import completed successfully for path: %s", path)


@tool_app.command("list")
@handle_errors
def tool_list(
    ctx: typer.Context,
    command: Optional[str] = typer.Option(None, help="Filter by tool command"),
    name: Optional[str] = typer.Option(None, help="Filter by tool name (partial match)"),
    description: Optional[str] = typer.Option(None, help="Filter by tool description"),
    location: Optional[str] = typer.Option(None, help="Filter by tool location (partial match)"),
    group: Optional[str] = typer.Option(None, help="Filter by tool group"),
    active: Optional[bool] = typer.Option(None, help="Filter by active status"),
):
    """
    Lists all tools in the effective registry with detailed information.
    """
    logger.info("Listing tools with filters: command=%s, name=%s, description=%s, location=%s, group=%s, active=%s",
                command, name, description, location, group, active)
    registry, _, _, _, _ = get_managers(ctx)
    tools = registry.package_registry.list_packages(
        command=command,
        name=name,
        description=description,
        location=location,
        group=group,
        active=active,
    )
    if tools:
        headers = ["Command", "Name", "Description", "Location", "Group", "Active"]
        rows = [
            [
                str(tool.get("command", "")),
                str(tool.get("name", "")),
                str(tool.get("description", "")),
                str(tool.get("location", "")),
                str(tool.get("group", "")),
                str(tool.get("active", "")),
            ]
            for tool in tools
        ]
        print_table(headers, rows)
    else:
        typer.echo("No tools found.")
        logger.info("No tools found with provided filters.")


@tool_app.command("info")
@handle_errors
def tool_info(
    ctx: typer.Context,
    command: str = typer.Argument(..., help="Unique tool command identifier"),
):
    """
    Displays detailed information and available scripts for the specified tool.
    """
    logger.info("Fetching info for tool: %s", command)
    registry, _, _, _, _ = get_managers(ctx)
    pkg = registry.retrieve_package(command)
    if pkg:
        print_tool_details(pkg)
        typer.echo("\nAvailable Scripts:")
        for script_name, script in pkg.get("scripts", {}).items():
            print_script_info(command, script_name, script)
        typer.secho("-" * 60, fg="green")
        logger.info("Displayed info for tool '%s'.", command)
    else:
        typer.secho(f"Tool '{command}' not found in the effective registry.", fg="red")
        logger.warning("Tool '%s' not found.", command)


@tool_app.command("remove")
@handle_errors
def tool_remove(
    ctx: typer.Context,
    command: str = typer.Argument(..., help="Unique tool command to remove"),
):
    """
    Removes a tool package from the effective registry.
    """
    logger.info("Attempting to remove tool with command: %s", command)
    service = ToolService.from_context(ctx)
    service.remove_tool(command)
    typer.echo(f"Tool '{command}' removed successfully.")


@tool_app.command("remove-group")
@handle_errors
def tool_remove_group(
    ctx: typer.Context,
    group: str = typer.Argument(..., help="Group name to remove"),
):
    """
    Removes all tool packages in the specified group from the effective registry.
    """
    logger.info("Attempting to remove all tools in group: %s", group)
    service = ToolService.from_context(ctx)
    service.remove_group_tools(group)
    typer.echo(f"All tools in group '{group}' removed successfully.")


@tool_app.command("move")
@handle_errors
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
    Moves a tool package from one registry to the other.
    """
    logger.info("Initiating move of tool '%s' to target registry: %s", command, to)
    if to.lower() not in ("user", "workspace"):
        typer.echo("Invalid target registry specified. Choose 'user' or 'workspace'.")
        logger.error("Invalid target registry specified for move: %s", to)
        raise typer.Exit(code=1)
    service = ToolService.from_context(ctx)
    service.move_tool(command, to, force)
    typer.echo(f"Tool '{command}' moved to {to} registry.")


@tool_app.command("export")
@handle_errors
def tool_export(
    ctx: typer.Context,
    tool_command: str = typer.Argument(..., help="Unique tool command to export"),
    output: Path = typer.Argument(..., help="Output zip archive path"),
):
    """
    Exports a tool package as a ZIP archive.
    """
    logger.info("Exporting tool '%s' to output path: %s", tool_command, output)
    service = ToolService.from_context(ctx)
    service.export_tool(tool_command, output)
    typer.echo(f"Tool '{tool_command}' exported successfully.")


@tool_app.command("customize")
@handle_errors
def tool_customize(
    ctx: typer.Context,
    tool_command: str = typer.Argument(..., help="Unique tool command to customize"),
    force: bool = typer.Option(
        False, "--force", help="Force overwrite if the package already exists"
    ),
):
    """
    Copies a tool package from the user registry to the workspace for customization.
    """
    logger.info("Customizing tool '%s'.", tool_command)
    service = ToolService.from_context(ctx)
    service.customize_tool(tool_command, force)
    typer.echo(f"Tool '{tool_command}' copied to workspace for customization.")


@tool_app.command("sync")
@handle_errors
def tool_sync(ctx: typer.Context):
    """
    Syncs active tool packages from the registry by re-importing them from disk.
    """
    logger.info("Starting tool synchronization.")
    service = ToolService.from_context(ctx)
    counts = service.sync_tools()
    for sc, count in counts.items():
        typer.echo(f"Synced {count} active tool packages in {sc} registry.")
