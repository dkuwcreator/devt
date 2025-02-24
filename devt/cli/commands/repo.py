import functools
import logging
import shutil
import threading  # <-- NEW IMPORT for background thread
from pathlib import Path
import concurrent.futures
from typing import Callable, TypeVar, Any, List, Optional
import time

import typer

from devt.config_manager import USER_REGISTRY_DIR
from devt.utils import print_table
from devt.registry.manager import PackageRegistry, ScriptRegistry, RepositoryRegistry
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


def remove_package_and_scripts(
    command: str,
    package_registry: PackageRegistry,
    script_registry: ScriptRegistry,
) -> None:
    """
    Remove a package (and any associated scripts) from the registries.
    """
    try:
        package_registry.delete_package(command)
        for scr in script_registry.list_scripts(command):
            script_registry.delete_script(command, scr["script"])
    except Exception as e:
        typer.echo(f"Error removing package or scripts for '{command}': {e}")


def remove_existing_repo(
    repo_manager: RepoManager,
    repository_registry: RepositoryRegistry,
    package_registry: PackageRegistry,
    script_registry: ScriptRegistry,
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
        repository_registry.delete_repository(repository_identifier)
    except Exception as e:
        logger.debug(f"Repository '{repository_identifier}' not in registry: {e}")

    # Remove any packages (and scripts) that were associated with this group
    for pkg in package_registry.list_packages(group=group):
        remove_package_and_scripts(pkg["command"], package_registry, script_registry)


# ---------- Helpers for Repository & Package Registration ----------


def import_and_register_packages(
    pkg_manager: PackageManager,
    repo_dir: Path,
    group: str,
    force: bool,
    package_registry: PackageRegistry,
    script_registry: ScriptRegistry,
) -> List[Any]:
    """
    Import packages from a repository directory into the local environment
    and register them.
    """
    packages = pkg_manager.import_package(repo_dir, group=group, force=force)
    for pkg in packages:
        if force and package_registry.get_package(pkg.command):
            remove_package_and_scripts(pkg.command, package_registry, script_registry)

        package_registry.add_package(
            pkg.command,
            pkg.name,
            pkg.description,
            str(pkg.location),
            pkg.dependencies,
            group=group,
        )
        for script_name, script in pkg.scripts.items():
            script_registry.add_script(pkg.command, script_name, script.to_dict())

    return packages


# ---------- Centralized Sync Logic ----------


def sync_single_repository(
    repo_name: str,
    repo_manager: RepoManager,
    pkg_manager: PackageManager,
    repository_registry: RepositoryRegistry,
    package_registry: PackageRegistry,
    script_registry: ScriptRegistry,
    branch: Optional[str] = None,
    error_on_missing: bool = True,
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
    :param error_on_missing: Whether to raise an error if repo is missing.
    """
    repo_dir: Path = repo_manager.repos_dir / repo_name

    # Skip or raise error if repo doesn't exist
    if not repo_dir.exists():
        msg = f"Repository '{repo_name}' not found."
        if error_on_missing:
            typer.echo(msg)
            raise typer.Exit(code=1)
        else:
            logger.warning(msg)
            return

    # Sync from remote
    updated_dir, current_branch, changes_made = repo_manager.sync_repo(
        str(repo_dir), branch=branch
    )

    # If no changes, we can exit early (not necessarily an error)
    if not changes_made:
        typer.echo(f"Repository '{repo_name}' is already up-to-date.")
        return

    # Attempt to import packages from the updated directory
    try:
        packages = pkg_manager.import_package(updated_dir, group=repo_name)
        repository = repository_registry.get_repository(repo_name)

        # Update repository info in the registry
        repository_registry.update_repository(
            repository["url"],
            repository["name"],
            current_branch,
            str(updated_dir),
            repository["auto_sync"],
        )

        # Update packages/scripts in the registry
        for pkg in packages:
            package_registry.update_package(
                pkg.command,
                pkg.name,
                pkg.description,
                str(pkg.location),
                pkg.dependencies,
            )
            for script_name, script in pkg.scripts.items():
                script_registry.update_script(
                    pkg.command, script_name, script.to_dict()
                )

        typer.echo(
            f"Updated {len(packages)} tool package(s) from repository '{repo_name}' in the registry."
        )
    except Exception as e:
        typer.echo(
            f"Error updating packages and registry for repository '{repo_name}': {e}"
        )
        logger.error("Error syncing repository '%s': %s", repo_name, e)


# ---------- Background Auto Sync ----------


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
    package_registry: PackageRegistry = ctx.obj["package_registry"]
    script_registry: ScriptRegistry = ctx.obj["script_registry"]
    repository_registry: RepositoryRegistry = ctx.obj["repository_registry"]
    pkg_manager: PackageManager = ctx.obj["pkg_manager"]
    repo_manager: RepoManager = ctx.obj["repo_manager"]

    repo_url = source
    logger.info("Starting to add repository with URL: %s", repo_url)

    # Remove existing repo if --force
    if force:
        remove_existing_repo(
            repo_manager,
            repository_registry,
            package_registry,
            script_registry,
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
        repository_registry.add_repository(
            url=repo_url,
            name=display_name,
            branch=effective_branch,
            location=str(repo_dir),
            auto_sync=sync,
        )
        logger.info("Repository '%s' added to the registry.", repo_url)
        typer.echo(f"Repository '{repo_url}' added to the registry.")

        logger.info("Importing tool packages from repository '%s'...", display_name)
        packages = import_and_register_packages(
            pkg_manager,
            repo_dir,
            repo_dir.name,
            force,
            package_registry,
            script_registry,
        )
        logger.info(
            "Imported %d tool package(s) from repository '%s'.",
            len(packages),
            display_name,
        )
        typer.echo(
            f"Imported {len(packages)} tool package(s) from repository '{display_name}'."
        )

    except Exception as e:
        logger.exception("Error during repository addition, removing repository:")
        remove_existing_repo(
            repo_manager,
            repository_registry,
            package_registry,
            script_registry,
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
    force: bool = typer.Option(False, "--force", help="Force removal"),
):
    """
    Removes a repository and all its associated tools.
    """
    package_registry: PackageRegistry = ctx.obj["package_registry"]
    script_registry: ScriptRegistry = ctx.obj["script_registry"]
    repository_registry: RepositoryRegistry = ctx.obj["repository_registry"]
    pkg_manager: PackageManager = ctx.obj["pkg_manager"]
    repo_manager: RepoManager = ctx.obj["repo_manager"]

    repo_dir = repo_manager.repos_dir / repo_name
    if not repo_dir.exists():
        typer.echo(f"Repository '{repo_name}' not found.")
        raise typer.Exit(code=1)

    if force:
        typer.echo(f"Force removing repository '{repo_name}'...")

    try:
        success = repo_manager.remove_repo(str(repo_dir))
    except Exception as e:
        typer.echo(f"Error removing repository '{repo_name}': {e}")
        raise typer.Exit(code=1)

    if not success:
        typer.echo(f"Failed to remove repository '{repo_name}'.")
        return

    typer.echo(f"Repository '{repo_name}' removed from disk.")

    def remove_packages_and_scripts() -> None:
        packages = package_registry.list_packages(group=repo_name)
        if packages:
            removed_count = 0
            for pkg in packages:
                pkg_path = Path(pkg["location"])
                try:
                    if pkg_manager.delete_package(pkg_path):
                        removed_count += 1
                except Exception as e:
                    typer.echo(f"Error removing package at '{pkg_path}': {e}")
                package_registry.delete_package(pkg["command"])
                for script in script_registry.list_scripts(pkg["command"]):
                    script_registry.delete_script(pkg["command"], script["script"])
            typer.echo(
                f"Removed {removed_count} tool package(s) from disk and {len(packages)} "
                f"registry entry(ies) for group '{repo_name}'."
            )
        else:
            typer.echo(f"No registry entries found for group '{repo_name}'.")

    remove_packages_and_scripts()

    try:
        repo_url = repository_registry.get_repositories_by_name(name=repo_name)
        repository_registry.delete_repository(repo_url)
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
) -> None:
    """
    Sync a specific repository (pull changes, re-import packages, update registry).
    """
    repo_manager: RepoManager = ctx.obj["repo_manager"]
    repository_registry: RepositoryRegistry = ctx.obj["repository_registry"]
    package_registry: PackageRegistry = ctx.obj["package_registry"]
    script_registry: ScriptRegistry = ctx.obj["script_registry"]
    pkg_manager: PackageManager = ctx.obj["pkg_manager"]

    sync_single_repository(
        repo_name=repo_name,
        repo_manager=repo_manager,
        pkg_manager=pkg_manager,
        repository_registry=repository_registry,
        package_registry=package_registry,
        script_registry=script_registry,
        branch=branch,
        error_on_missing=True,  # raise error if repo not found
    )


@repo_app.command("sync-auto")
@handle_errors
def repo_sync_auto(ctx: typer.Context) -> None:
    """
    Synchronize all repositories with auto_sync=True in parallel.
    """
    repository_registry: RepositoryRegistry = ctx.obj["repository_registry"]
    pkg_manager: PackageManager = ctx.obj["pkg_manager"]
    repo_manager: RepoManager = ctx.obj["repo_manager"]
    package_registry: PackageRegistry = ctx.obj["package_registry"]
    script_registry: ScriptRegistry = ctx.obj["script_registry"]

    repos = repository_registry.list_repositories(auto_sync=True)
    if not repos:
        typer.echo("No repositories with auto_sync enabled.")
        return

    typer.echo(f"Starting parallel sync for {len(repos)} repositories...")

    def sync_task(repo_info: dict) -> str:
        """Task function for parallel execution."""
        repo_name = repo_info["name"]
        sync_single_repository(
            repo_name=repo_name,
            repo_manager=repo_manager,
            pkg_manager=pkg_manager,
            repository_registry=repository_registry,
            package_registry=package_registry,
            script_registry=script_registry,
            branch=None,
            error_on_missing=False,  # skip if not found
        )
        return repo_name

    with concurrent.futures.ThreadPoolExecutor() as executor:
        futures = {executor.submit(sync_task, repo): repo["name"] for repo in repos}
        for future in concurrent.futures.as_completed(futures):
            repo_name = futures[future]
            try:
                future.result()
                typer.echo(f"Successfully synced '{repo_name}'")
            except Exception as e:
                typer.echo(f"Failed to sync '{repo_name}': {e}")

    typer.echo("Auto-sync process completed.")


@repo_app.command("sync-all")
@handle_errors
def repo_sync_all(ctx: typer.Context) -> None:
    """
    Synchronize all repositories found in the repos directory (serially).
    """
    repo_manager: RepoManager = ctx.obj["repo_manager"]
    repository_registry: RepositoryRegistry = ctx.obj["repository_registry"]
    package_registry: PackageRegistry = ctx.obj["package_registry"]
    script_registry: ScriptRegistry = ctx.obj["script_registry"]
    pkg_manager: PackageManager = ctx.obj["pkg_manager"]

    repos: List[Path] = list(repo_manager.repos_dir.iterdir())
    if not repos:
        typer.echo("No repositories found.")
        return

    for repo in repos:
        try:
            sync_single_repository(
                repo_name=repo.name,
                repo_manager=repo_manager,
                pkg_manager=pkg_manager,
                repository_registry=repository_registry,
                package_registry=package_registry,
                script_registry=script_registry,
                branch=None,
                error_on_missing=False,
            )
            typer.echo(f"Synced repository: {repo.name}")
        except Exception as e:
            typer.echo(f"Failed to sync {repo.name}: {e}")


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
    repository_registry: RepositoryRegistry = ctx.obj["repository_registry"]
    repos = repository_registry.list_repositories(
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
