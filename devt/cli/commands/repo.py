#!/usr/bin/env python3
"""
devt/cli/commands/repo.py

Repository Management Commands

Provides commands to add, remove, sync, and list repositories containing tool packages.
"""

import logging
from typing import Optional
from typing_extensions import Annotated

import typer

from devt.cli.helpers import check_git_and_exit
# Removed: from devt.error_wrapper import handle_errors
from devt.cli.repo_service import RepoServiceWrapper
from devt.utils import print_table
from devt.repo_manager import RepoManager
from devt.cli.sync_service import SyncManager
from devt.cli.tool_service import ToolServiceWrapper
from datetime import datetime

repo_app = typer.Typer(help="Repository management commands")
logger = logging.getLogger(__name__)


@repo_app.callback()
def main(ctx: typer.Context) -> None:
    """
    Manage repositories containing tool packages.
    """
    check_git_and_exit()
    # ctx.obj = ctx.obj or {}
    # ctx.obj["repo_manager"] = RepoManager()
    # ctx.obj["tool_manager"] = ToolServiceWrapper.from_context(ctx)
    # ctx.obj["sync_manager"] = SyncManager.from_context(ctx)


@repo_app.command("add")
def repo_add(
    ctx: typer.Context,
    source: str = typer.Argument(..., help="URL of the repository to add."),
    branch: Optional[str] = typer.Option(
        None, help="Branch to clone. Default is the default branch."
    ),
    sync: bool = typer.Option(
        True, "--sync", help="Enable auto-sync for the repository."
    ),
    name: Optional[str] = typer.Option(
        None, "--name", help="Display name for the repository."
    ),
    force: bool = typer.Option(
        False, "--force", help="Force overwrite if repository already exists."
    ),
) -> None:
    """
    Adds a repository containing tool packages to the registry.
    """
    service = RepoServiceWrapper.from_context(ctx)
    service.import_repo(source, branch, sync, name, force)
    typer.echo("Repository added successfully.")
    


@repo_app.command("remove")
def repo_remove(
    ctx: typer.Context,
    repo_name: str = typer.Argument(..., help="Name of the repository to remove."),
    scope: str = typer.Option(
        "both", help="Registry scope: 'workspace', 'user', or 'both' (default: both)"
    ),
) -> None:
    """
    Removes a repository and all its associated tools.
    """
    logger.debug("Removing repository: %s", repo_name)
    if scope == "both":
        logger.warning(
            "It is recommended to specify the scope, as removing from both scopes may lead to unclear removal behavior."
        )
    logger.debug("Removing repository: %s", repo_name)
    service = RepoServiceWrapper(scope)
    service.remove_repo(repo_name)
    typer.echo(f"Repository removed successfully from the {service.found_scope} registry.")
    

@repo_app.command("sync")
def repo_sync(
    ctx: typer.Context,
    repo_name: Annotated[
        Optional[str], typer.Argument(help="Name of the repository to sync")
    ] = None,
    force: bool = typer.Option(
        False, "--force", help="Force overwrite if repository already exists."
    ),
):
    """
    Synchronize repositories (either all or filtered by name).
    """
    service = RepoServiceWrapper.from_context(ctx)
    service.sync_repos(filters={"name": repo_name}, force=force)
    typer.echo("Repositories synchronized successfully.")
    
def format_dt_str(dt_str: str) -> str:
    if not dt_str:
        return ""
    try:
        dt = datetime.fromisoformat(dt_str)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        logger.error(f"ValueError: {dt_str} is not a valid datetime format")
        return dt_str
    except AttributeError:
        logger.error(f"AttributeError: {dt_str} is not a string")
        return dt_str
    
@repo_app.command("list")
def repo_list(
    ctx: typer.Context,
    url: Optional[str] = typer.Option(None, help="Filter by repository URL"),
    name: Optional[str] = typer.Option(None, help="Filter by repository name"),
    branch: Optional[str] = typer.Option(None, help="Filter by repository branch"),
    location: Optional[str] = typer.Option(None, help="Filter by repository location"),
    auto_sync: Optional[bool] = typer.Option(None, help="Filter by auto-sync status"),
    scope: Optional[str] = typer.Option(
        "both", help="Registry scope: 'workspace', 'user', or 'both' (default: both)"
    )
) -> None:
    """
    Displays all registered repositories and their status.
    """
    logger.debug(
        "Listing repositories with filters: url=%s, name=%s, branch=%s, "
        "location=%s, auto_sync=%s",
        url,
        name,
        branch,
        location,
        auto_sync,
    )
    service = RepoServiceWrapper(scope)
    results = service.list_repos(
        url=url, name=name, branch=branch, location=location, auto_sync=auto_sync
    )

    for current_scope, repos in results.items():
        typer.echo(f"\n{current_scope.capitalize()} Registry:")
        if repos:
            headers = ["Name", "URL", "Branch", "Location", "Auto Sync", "Last Update"]
            rows = [
                [
                    repo.get("name", ""),
                    repo.get("url", ""),
                    repo.get("branch", ""),
                    repo.get("location", ""),
                    str(repo.get("auto_sync", "")),
                    format_dt_str(repo.get("last_update", "")),
                ]
                for repo in repos
            ]
            print_table(headers, rows)
        else:
            logger.debug("No repositories found.")
            typer.echo("No repositories found.")
    typer.echo("\n")