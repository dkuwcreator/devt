import functools
import logging
import shutil
import threading  # <-- NEW IMPORT for background thread
from pathlib import Path
import concurrent.futures
from typing import Callable, Dict, TypeVar, Any, List, Optional
import time

import typer

from devt.cli.commands.tool import get_repo_from_registries
from devt.cli.helpers import (
    import_and_register_packages,
    remove_and_unregister_group_packages,
    update_and_register_group_packages,
)
from devt.config_manager import USER_REGISTRY_DIR, WORKSPACE_REGISTRY_DIR
from devt.utils import print_table
from devt.registry.manager import (
    PackageRegistry,
    RegistryManager,
    ScriptRegistry,
    RepositoryRegistry,
)
from devt.package.manager import PackageManager
from devt.repo_manager import RepoManager

repo_app = typer.Typer(help="Repository management commands")
logger = logging.getLogger(__name__)

T = TypeVar("T", bound=Callable[..., Any])


LAST_SYNC_TIME = 0
SYNC_INTERVAL = 60

# ---------- Utility Functions & Decorators ----------


def handle_errors(func: T) -> T:
    """Decorator for catching and handling exceptions in Typer commands."""

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.exception("An error occurred in %s:", func.__name__)
            typer.echo(f"An error occurred: {e}")
            raise typer.Exit(code=1)

    return wrapper  # type: ignore


def is_git_installed() -> bool:
    """Check if Git is installed on the system."""
    return shutil.which("git") is not None


def check_git_and_exit() -> None:
    """Exit if Git is not found."""
    if not is_git_installed():
        typer.echo(
            "Git is required for repository management. Please install Git and try again."
        )
        raise typer.Exit(code=1)


# ---------- Helpers for Package & Repository Cleanup ----------


def remove_existing_repo(
    repo_manager: RepoManager,
    registry: RegistryManager,
    pkg_manager: PackageManager,
    repository_identifier: str,
    group_name: Optional[str] = None,
) -> None:
    """
    Completely remove a repository from the filesystem and registry,
    along with any packages/scripts belonging to it.
    """
    group = group_name or Path(repository_identifier).stem
    repo_candidate = repo_manager.repos_dir / group

    # Remove the repo folder if it exists
    if repo_candidate.exists():
        try:
            repo_manager.remove_repo(str(repo_candidate))
            typer.echo(
                f"Existing repository '{repo_candidate}' removed due to force option."
            )
        except Exception as e:
            typer.echo(f"Error removing repository '{repo_candidate}': {e}")

    # Remove the repository record from the registry
    try:
        registry.repository_registry.delete_repository(repository_identifier)
    except Exception as e:
        logger.debug(f"Repository '{repository_identifier}' not in registry: {e}")

    remove_and_unregister_group_packages(
        registry=registry, pkg_manager=pkg_manager, group=group
    )


# ---------- Centralized Sync Logic ----------


def sync_single_repository(
    repo: Dict[str, Any],
    repo_manager: RepoManager,
    pkg_manager: PackageManager,
    registry: RegistryManager,
    force: bool = False,
) -> None:
    """
    Sync a single repository (optionally checking out a specific branch),
    import packages, and update the registries.

    :param repo_name: Name of the repository folder (also used as 'group').
    :param repo_manager: The RepoManager instance.
    :param pkg_manager: The PackageManager instance.
    :param repository_registry: The RepositoryRegistry instance.
    :param package_registry: The PackageRegistry instance.
    :param script_registry: The ScriptRegistry instance.
    :param branch: Branch to check out for syncing.
    """
    repo_name = repo["name"]
    # Sync from remote
    updated_dir, current_branch, changes_made = repo_manager.sync_repo(repo["location"])

    # If no changes, we can exit early (not necessarily an error)
    if not changes_made and not force:
        typer.echo(f"Repository '{repo_name}' is already up-to-date.")
        return

    # Attempt to import packages from the updated directory
    try:
        # Update packages/scripts in the registry
        update_and_register_group_packages(pkg_manager, registry, repo_name)
    except Exception as e:
        logger.error("Error syncing repository '%s': %s", repo_name, e)


# ---------- Background Auto Sync ----------


def repo_sync_auto() -> None:
    """
    Synchronize all repositories with auto_sync=True in parallel.
    """
    registry = RegistryManager(USER_REGISTRY_DIR)
    repo_manager = RepoManager(USER_REGISTRY_DIR)
    pkg_manager = PackageManager(USER_REGISTRY_DIR)

    repositories = registry.repository_registry.list_repositories(auto_sync=True)
    if not repositories:
        typer.echo("No repositories found with auto-sync enabled.")
        return

    with concurrent.futures.ThreadPoolExecutor() as executor:
        futures = {
            executor.submit(
                sync_single_repository,
                repo_name=repo["name"],
                repo_manager=repo_manager,
                pkg_manager=pkg_manager,
                registry=registry,
                branch=None,
                error_on_missing=False,
            ): repo["name"]
            for repo in repositories
        }

        for future in concurrent.futures.as_completed(futures):
            repo_name = futures[future]
            try:
                future.result()
                typer.echo(f"Auto-synced repository: {repo_name}")
            except Exception as e:
                typer.echo(f"Failed to auto-sync {repo_name}: {e}")


def start_background_auto_sync(ctx: typer.Context) -> None:
    """
    Spawns a daemon thread to run the repo_sync_auto command logic in the background.
    This ensures we don't block the user's main command.

    The background thread will terminate automatically if the main process exits.
    """
    global LAST_SYNC_TIME
    now = time.time()

    if now - LAST_SYNC_TIME < SYNC_INTERVAL:
        return  # Skip if it hasn't been 1 minute

    # Update LAST_SYNC_TIME immediately to avoid multiple threads
    LAST_SYNC_TIME = now

    # We call the existing `repo_sync_auto` function directly.
    # Because it's a Typer command, we can invoke it the same way (passing the context).
    def run_sync_in_background() -> None:
        # You might choose to catch exceptions or add a time-based throttling here.
        repo_sync_auto(ctx)

    thread = threading.Thread(target=run_sync_in_background, daemon=True)
    thread.start()


# ---------- Repository App Callback ----------


@repo_app.callback()
def main(ctx: typer.Context) -> None:
    """
    Manage repositories containing tool packages.
    """
    check_git_and_exit()
    ctx.obj = ctx.obj or {}

    # Initialize the RepoManager (and any other objects you need).
    ctx.obj["repo_manager"] = RepoManager(USER_REGISTRY_DIR)


# ---------- Commands ----------


@repo_app.command("add")
@handle_errors
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
        False, "--force", help="Force overwrite if repository exists"
    ),
) -> None:
    """
    Adds a repository containing tool packages to the registry.
    """
    scope = ctx.obj["scope"]
    registry_dir = USER_REGISTRY_DIR if scope == "user" else WORKSPACE_REGISTRY_DIR
    registry = RegistryManager(registry_dir)
    repo_manager = RepoManager(USER_REGISTRY_DIR)

    repo_url = source
    logger.info("Starting to add repository with URL: %s", repo_url)

    # Remove existing repo if --force
    if force:
        remove_existing_repo(
            repo_manager,
            registry,
            repo_url,
        )

    # Clone/checkout the repo
    repo_dir, effective_branch = repo_manager.add_repo(repo_url, branch=branch)
    display_name = name if name else repo_dir.name
    typer.echo(
        f"Repository added at: {repo_dir} (name: {display_name}, url: {repo_url})"
    )
    logger.debug("Repository cloned at %s with branch %s", repo_dir, effective_branch)

    # Register repository + import packages
    try:
        registry.repository_registry.add_repository(
            url=repo_url,
            name=display_name,
            branch=effective_branch,
            location=str(repo_dir),
            auto_sync=sync,
        )
        logger.info("Repository '%s' added to the registry.", repo_url)
        typer.echo(f"Repository '{repo_url}' added to the registry.")

        import_and_register_packages(
            scope=scope, path=repo_dir, group=display_name, force=force
        )

    except Exception as e:
        logger.exception("Error during repository addition, removing repository:")
        remove_existing_repo(
            repo_manager,
            registry,
            repo_url,
        )
        typer.echo(
            f"Error importing packages from repository: {e}. Repository removed."
        )
        raise typer.Exit(code=1)


@repo_app.command("remove")
def repo_remove(
    ctx: typer.Context,
    repo_name: str = typer.Argument(..., help="Repository name to remove"),
):
    """
    Removes a repository and all its associated tools.
    """
    scope = ctx.obj["scope"]
    registry_dir = USER_REGISTRY_DIR if scope == "user" else WORKSPACE_REGISTRY_DIR
    registry = RegistryManager(registry_dir)
    repo_manager = RepoManager(USER_REGISTRY_DIR)

    repo_dir = registry_dir / "repos" / repo_name
    if not repo_dir.exists():
        typer.echo(f"Repository '{repo_name}' not found.")
        raise typer.Exit(code=1)

    try:
        repo_manager.remove_repo(str(repo_dir))
    except Exception as e:
        typer.echo(f"Error removing repository '{repo_name}': {e}")
        raise typer.Exit(code=1)

    typer.echo(f"Repository '{repo_name}' removed from disk.")

    remove_and_unregister_group_packages(
        scope=ctx.obj["scope"],
        group=repo_name,
    )

    try:
        repo = registry.repository_registry.get_repo_by_name(name=repo_name)
        registry.repository_registry.delete_repository(repo["url"])
        typer.echo(f"Repository '{repo_name}' removed from the registry.")
    except Exception as e:
        typer.echo(f"Failed to remove repository '{repo_name}' from registry: {e}")


@repo_app.command("sync")
@handle_errors
def repo_sync(
    ctx: typer.Context,
    repo_name: str = typer.Argument(..., help="Repository name to sync"),
    branch: Optional[str] = typer.Option(
        None,
        "--branch",
        help="Git branch to sync (checkout and pull updates if provided)",
    ),
    force: bool = typer.Option(
        False, "--force", help="Force overwrite of existing packages"
    ),
) -> None:
    """
    Sync a specific repository (pull changes, re-import packages, update registry).
    """
    scope = ctx.obj["scope"]
    registry_dir = USER_REGISTRY_DIR if scope == "user" else WORKSPACE_REGISTRY_DIR
    registry = RegistryManager(registry_dir)
    repo_manager = RepoManager(USER_REGISTRY_DIR)
    pkg_manager = PackageManager(registry_dir)

    sync_single_repository(
        repo_name=repo_name,
        repo_manager=repo_manager,
        pkg_manager=pkg_manager,
        registry=registry,
        branch=branch,
        error_on_missing=True,
        force=force,
    )


@repo_app.command("sync-all")
@handle_errors
def repo_sync_all(
    ctx: typer.Context,
    force: bool = typer.Option(
        False, "--force", help="Force overwrite of existing packages"
    ),
) -> None:
    """
    Synchronize all repositories found in the repos directory (serially).
    """
    registry = RegistryManager(USER_REGISTRY_DIR)
    repo_manager = RepoManager(USER_REGISTRY_DIR)
    pkg_manager = PackageManager(USER_REGISTRY_DIR)

    repos = registry.repository_registry.list_repositories()

    for repo in repos:
        print(f"Syncing repository: {repo}")
        try:
            sync_single_repository(
                repo=repo,
                repo_manager=repo_manager,
                pkg_manager=pkg_manager,
                registry=registry,
                force=force,
            )
            typer.echo(f"Synced repository: {repo['name']}")
        except Exception as e:
            typer.echo(f"Failed to sync {repo['name']}: {e}")


@repo_app.command("list")
@handle_errors
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
) -> None:
    """
    Displays all registered repositories and their status.
    """
    registry = RegistryManager(USER_REGISTRY_DIR)
    repos = registry.repository_registry.list_repositories(
        url=url, name=name, branch=branch, location=location, auto_sync=auto_sync
    )
    if repos:
        headers = ["Name", "URL", "Branch", "Location", "Auto Sync"]
        rows = [
            [
                str(repo.get("name", "")),
                str(repo.get("url", "")),
                str(repo.get("branch", "")),
                str(repo.get("location", "")),
                str(repo.get("auto_sync", "")),
            ]
            for repo in repos
        ]
        print_table(headers, rows)
    else:
        typer.echo("No repositories found.")
