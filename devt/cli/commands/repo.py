import functools
import logging
from typing import Callable, Dict, TypeVar, Any, Optional
from typing_extensions import Annotated

import typer

from devt.cli.helpers import check_git_and_exit, is_git_installed
from devt.utils import print_table
from devt.registry.manager import RegistryManager
from devt.repo_manager import RepoManager
from devt.cli.sync_service import SyncManager
from devt.cli.tool_service import ToolService

repo_app = typer.Typer(help="Repository management commands")
logger = logging.getLogger(__name__)

T = TypeVar("T", bound=Callable[..., Any])


def handle_errors(func: T) -> T:
    """Decorator for catching and handling exceptions in Typer commands."""

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.exception("An error occurred in %s:", func.__name__)
            raise typer.Exit(code=1)

    return wrapper  # type: ignore


@repo_app.callback()
def main(ctx: typer.Context) -> None:
    """
    Manage repositories containing tool packages.
    """
    check_git_and_exit()
    ctx.obj = ctx.obj or {}
    ctx.obj["repo_manager"] = RepoManager()
    ctx.obj["tool_manager"] = ToolService.from_context(ctx)
    ctx.obj["sync_manager"] = SyncManager.from_context(ctx)


@repo_app.command("add")
@handle_errors
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
    scope = ctx.obj.get("scope")
    registry = RegistryManager(scope)
    repo_manager = RepoManager()
    repo_url = source
    logger.info("Adding repository: %s", repo_url)

    if force:
        repo_manager.remove_repo(repo_url)
        registry.repository_registry.delete_repository(repo_url)

    repo_dir, effective_branch = repo_manager.add_repo(repo_url, branch=branch)
    display_name = name or repo_dir.name
    logger.info("Repository cloned at %s", repo_dir)

    try:
        registry.repository_registry.add_repository(
            url=repo_url,
            name=display_name,
            branch=effective_branch,
            location=str(repo_dir),
            auto_sync=sync,
        )
        tool_manager = ToolService.from_context(ctx)
        tool_manager.import_tool(repo_dir, display_name, force)
    except Exception:
        repo_manager.remove_repo(repo_url)
        registry.repository_registry.delete_repository(repo_url)
        logger.exception("Error importing repository, rolling back changes.")
        raise typer.Exit(code=1)


@repo_app.command("remove")
@handle_errors
def repo_remove(
    ctx: typer.Context,
    repo_name: str = typer.Argument(..., help="Name of the repository to remove."),
) -> None:
    """
    Removes a repository and all its associated tools.
    """
    scope = ctx.obj.get("scope")
    registry = RegistryManager(scope)
    repo_manager = RepoManager()
    repo = registry.repository_registry.get_repo_by_name(name=repo_name)

    if not repo:
        logger.info("Repository '%s' not found.", repo_name)
        return

    location = repo.get("location")
    if location:
        repo_manager.remove_repo(str(location))

    tool_manager = ToolService.from_context(ctx)
    tool_manager.remove_group_tools(repo_name)

    try:
        registry.repository_registry.delete_repository(repo.get("url"))
    except Exception:
        logger.exception("Failed to remove repository '%s' from registry.", repo_name)


@repo_app.command("sync")
@handle_errors
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
    scope = ctx.obj.get("scope")
    registry = RegistryManager(scope)
    sync_manager = SyncManager.from_context(ctx)
    repos = registry.repository_registry.list_repositories(name=repo_name)

    if not repos:
        logger.info("No repositories found to sync.")
        return

    for repo in repos:
        sync_manager.sync_single_repository(repo, force)


@repo_app.command("list")
@handle_errors
def repo_list(
    ctx: typer.Context,
    url: Optional[str] = None,
    name: Optional[str] = None,
    branch: Optional[str] = None,
    location: Optional[str] = None,
    auto_sync: Optional[bool] = None,
) -> None:
    """
    Displays all registered repositories and their status.
    """
    scope = ctx.obj.get("scope")
    registry = RegistryManager(scope)
    if registry is None:
        raise typer.Exit(code=1)

    repos = registry.repository_registry.list_repositories(
        url=url, name=name, branch=branch, location=location, auto_sync=auto_sync
    )
    if repos:
        headers = ["Name", "URL", "Branch", "Location", "Auto Sync", "Last Update"]
        rows = [
            [
                repo.get("name", ""),
                repo.get("url", ""),
                repo.get("branch", ""),
                repo.get("location", ""),
                str(repo.get("auto_sync", "")),
                repo.get("last_update", ""),
            ]
            for repo in repos
        ]
        print_table(headers, rows)
    else:
        logger.info("No repositories found.")
