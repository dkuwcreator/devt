import concurrent.futures
import threading
import time
import typer
import logging
from devt.cli.helpers import get_managers
from devt.cli.tool_service import ToolService
from devt.package.manager import PackageManager
from devt.registry.manager import RegistryManager
from devt.repo_manager import RepoManager

logger = logging.getLogger(__name__)

class SyncManager:
    SYNC_INTERVAL = 60

    @classmethod
    def from_context(cls, ctx: typer.Context) -> "SyncManager":
        registry, pkg_manager, repo_manager, _, _ = get_managers(ctx)
        tool_service = ToolService.from_context(ctx)
        return cls(registry, repo_manager, pkg_manager, tool_service)

    def __init__(self, registry, repo_manager, pkg_manager, tool_service):
        self.registry: RegistryManager = registry
        self.repo_manager: RepoManager = repo_manager
        self.pkg_manager: PackageManager = pkg_manager
        self.tool_service: ToolService = tool_service
        self.last_sync_time = 0

    def sync_single_repository(self, repo: dict, force: bool = False) -> None:
        """
        Sync a single repository, update tools, and handle any errors.
        """
        repo_name = repo["name"]
        logger.info("Starting sync for repository '%s' located at %s", repo_name, repo["location"])
        updated_dir, current_branch, changes_made = self.repo_manager.sync_repo(repo["location"])
        logger.debug("Sync result for '%s': updated_dir=%s, branch=%s, changes_made=%s",
                     repo_name, updated_dir, current_branch, changes_made)

        if not changes_made and not force:
            logger.info("No changes detected for '%s'; skipping update.", repo_name)
            return

        try:
            logger.info("Importing tools from updated directory: %s", updated_dir)
            self.tool_service.overwrite_tool(updated_dir, repo_name, True)
        except Exception as e:
            logger.error("Error syncing repository '%s': %s", repo_name, e)

    def sync_all_repositories(self, force: bool = False) -> None:
        """
        Synchronize all repositories with auto-sync enabled in parallel and wait for completion.
        """
        repositories = self.registry.repository_registry.list_repositories(auto_sync=True)
        logger.info("Found %d repositories with auto-sync enabled.", len(repositories))
        if not repositories:
            logger.info("No repositories found with auto-sync enabled.")
            return

        with concurrent.futures.ThreadPoolExecutor() as executor:
            future_to_repo = {
                executor.submit(self.sync_single_repository, repo, force): repo["name"]
                for repo in repositories
            }
            # Wait for all futures to complete before continuing
            concurrent.futures.wait(future_to_repo.keys())

            for future in future_to_repo.keys():
                repo_name = future_to_repo[future]
                try:
                    future.result()
                    logger.info("Auto-synced repository: %s", repo_name)
                except Exception as e:
                    logger.error("Failed to auto-sync repository '%s': %s", repo_name, e)

    def start_background_sync(self, ctx: typer.Context) -> None:
        """
        Start a thread to perform background auto-sync if enough time has passed.
        """
        now = time.time()
        if now - self.last_sync_time < self.SYNC_INTERVAL:
            logger.debug("Background sync throttled. Time since last sync: %.2f seconds.", now - self.last_sync_time)
            return

        self.last_sync_time = now
        logger.info("Starting background sync.")

        def run_sync() -> None:
            logger.info("Background sync started.")
            self.sync_all_repositories()
            logger.info("Background sync completed.")

        thread = threading.Thread(target=run_sync, daemon=False)  # daemon=False ensures it runs to completion
        thread.start()
        thread.join()  # Waits for completion before returning
        logger.info("Background sync completed and joined.")
