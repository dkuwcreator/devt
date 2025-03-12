#!/usr/bin/env python3
"""
devt/cli/commands/tool.py

DevT Tool Commands

Provides commands to import, list, show, remove, move, export, and sync tool packages.
"""

from pathlib import Path
from typing import Optional

import typer
import logging

from devt.constants import APP_NAME
from devt.utils import print_table
from devt.cli.tool_service import ToolServiceWrapper

logger = logging.getLogger(__name__)
tool_app = typer.Typer(help="[Tool] Tool management commands")


def print_tool_summary(tool: dict) -> None:
    """
    Display a brief summary for a single tool (used in read-only contexts).
    """
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
    """
    Display detailed information for a single tool (used in read-only contexts).
    """
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
    """
    Display information about a specific script within a tool (used in read-only contexts).
    Only print a value if it exists.
    """
    script_border = "=" * 60
    section_border = "-" * 60
    typer.secho(script_border, fg="cyan")
    typer.secho(f'Script: "{script_name}" ', fg="cyan", bold=True)
    typer.secho(section_border, fg="cyan")
    for key, value in script.items():
        if key not in ("command", "script") and value:
            typer.secho(f"{key.capitalize():15s}: {value}", fg="yellow")
    typer.secho(section_border, fg="cyan")
    typer.secho(f" > {APP_NAME} do {tool_command} {script_name}", fg="cyan", bold=True)
    typer.secho(script_border, fg="cyan")
    typer.echo("\n")  # Add a newline for spacing between scripts


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
    [Tool] Imports a tool package (or multiple tool packages) into the registry.
    """
    logger.info("Starting tool import: path=%s, force=%s, group=%s", path, force, group)
    service = ToolServiceWrapper.from_context(ctx)
    service.import_tool(path, group or "default", force)
    logger.info("Tool import completed successfully for path: %s", path)
    typer.echo("Tool import completed successfully.")


@tool_app.command("list")
def tool_list(
    ctx: typer.Context,
    command: Optional[str] = typer.Option(None, help="Filter by tool command"),
    name: Optional[str] = typer.Option(None, help="Filter by tool name (partial match)"),
    description: Optional[str] = typer.Option(None, help="Filter by tool description"),
    location: Optional[str] = typer.Option(None, help="Filter by tool location (partial match)"),
    group: Optional[str] = typer.Option(None, help="Filter by tool group"),
    active: Optional[bool] = typer.Option(None, help="Filter by active status"),
    scope: Optional[str] = typer.Option(
        "both", help="Registry scope: 'workspace', 'user', or 'both' (default: both)"
    )
):
    """
    [Tool] Lists all tools in the effective registry with detailed information (read-only).
    """
    logger.debug(
        "Listing tools with filters: command=%s, name=%s, description=%s, "
        "location=%s, group=%s, active=%s",
        command,
        name,
        description,
        location,
        group,
        active,
    )
    service = ToolServiceWrapper(scope)
    results = service.list_tools(
        command=command,
        name=name,
        description=description,
        location=location,
        group=group,
        active=active,
    )
    for current_scope, tools in results.items():
        typer.echo(f"\n{current_scope.capitalize()} Registry:")
        if tools:
            headers = ["Command", "Group", "Name", "Description", "Location", "Active"]
            rows = [
                [
                    str(tool.get("command", "")),
                    str(tool.get("group", "")),
                    str(tool.get("name", "")),
                    str(tool.get("description", "")),
                    str(tool.get("location", "")),
                    str(tool.get("active", "")),
                ]
                for tool in tools
            ]
            print_table(headers, rows)
        else:
            typer.echo("No tools found.")
            logger.debug("No tools found with provided filters.")


@tool_app.command("show")
def tool_show(
    ctx: typer.Context,
    command: str = typer.Argument(..., help="Unique tool command identifier"),
    scope: Optional[str] = typer.Option(
        "both", help="Registry scope: 'workspace', 'user', or 'both' (default: both)"
    )
):
    """
    [Tool] Displays detailed information and available scripts for the specified tool (read-only).
    Searches across all available registries.
    """
    logger.info("Fetching info for tool: %s", command)
    service = ToolServiceWrapper(scope)
    pkg = service.get_tool_info(command)
    # Loop over all scopes (registries) to find the tool
    typer.echo(f"\n{service.found_scope} Registry:")
    print_tool_details(pkg)
    typer.echo("\nAvailable Scripts:")
    for script_name, script in pkg.get("scripts", {}).items():
        print_script_info(command, script_name, script)


@tool_app.command("remove")
def tool_remove(
    ctx: typer.Context,
    command: str = typer.Argument(..., help="Unique tool command to remove"),
):
    """
    [Tool] Removes a tool package from the effective registry.
    """
    logger.info("Attempting to remove tool with command: %s", command)
    service = ToolServiceWrapper.from_context(ctx)
    service.remove_tool(command)
    logger.info("Tool '%s' removed successfully.", command)
    typer.echo("Tool removed successfully.")


@tool_app.command("remove-group")
def tool_remove_group(
    ctx: typer.Context,
    group: str = typer.Argument(..., help="Group name to remove"),
):
    """
    [Tool] Removes all tool packages in the specified group from the effective registry.
    """
    logger.info("Attempting to remove all tools in group: %s", group)
    service = ToolServiceWrapper.from_context(ctx)
    service.remove_group_tools(group)
    logger.info("All tools in group '%s' removed successfully.", group)
    typer.echo("All tools in group removed successfully.")


@tool_app.command("move")
def tool_move(
    ctx: typer.Context,
    command: str = typer.Argument(..., help="Unique tool command to move"),
    to: str = typer.Argument(
        ..., help="Target registry to move the tool to (user or workspace)"
    ),
    force: bool = typer.Option(False, "--force", help="Force overwrite if the package already exists"),
):
    """
    [Tool] Moves a tool package from one registry to the other.
    """
    logger.info("Initiating move of tool '%s' to target registry: %s", command, to)
    if to.lower() not in ("user", "workspace"):
        logger.error("Invalid target registry specified for move: %s", to)
        raise ValueError("Invalid target registry specified. Choose 'user' or 'workspace'.")
    service = ToolServiceWrapper.from_context(ctx)
    service.move_tool(command, to, force)
    logger.info("Tool '%s' moved to '%s' registry.", command, to)
    typer.echo(f"Tool '{command}' moved to '{to}' registry.")


@tool_app.command("export")
def tool_export(
    ctx: typer.Context,
    tool_command: str = typer.Argument(..., help="Unique tool command to export"),
    output: Path = typer.Argument(..., help="Output path"),
    as_zip: bool = typer.Option(False, "--zip", help="Export as a ZIP archive (default: False)"),
    force: bool = typer.Option(False, "--force", help="Force overwrite if the package already exists"),
):
    """
    [Tool] Exports a tool package to the specified output path.
    """
    logger.info("Exporting tool '%s' to output path: %s", tool_command, output)
    service = ToolServiceWrapper.from_context(ctx)
    service.export_tool(tool_command, output, as_zip, force)
    logger.info("Tool '%s' exported successfully to %s.", tool_command, output)
    typer.echo(f"Tool '{tool_command}' exported successfully to {output}.")


@tool_app.command("sync")
def tool_sync(ctx: typer.Context):
    """
    [Tool] Syncs active tool packages from the registry by re-importing them from disk.
    """
    logger.info("Starting tool synchronization.")
    service = ToolServiceWrapper.from_context(ctx)
    service.sync_tools()
    logger.info("Tool synchronization completed successfully.")
    typer.echo("Tool synchronization completed successfully.")

@tool_app.command("open")
def tool_open(
    ctx: typer.Context,
    command: str = typer.Argument(..., help="Unique tool command identifier"),
    scope: Optional[str] = typer.Option(
        "both", help="Registry scope: 'workspace', 'user', or 'both' (default: both)"
    )
):
    """
    [Tool] Opens the tool package directory in the file explorer.
    """
    logger.info("Opening tool directory for command: %s", command)
    service = ToolServiceWrapper(scope)
    pkg = service.get_tool_info(command)
    typer.echo(pkg.get("location"))
