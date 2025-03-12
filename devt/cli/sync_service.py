#!/usr/bin/env python3
"""
devt/cli/sync_service.py

Synchronization Manager

Provides methods to synchronize repositories and tools in the background.
"""
import concurrent.futures
from pathlib import Path
import threading
import time
import typer
import logging
from devt.cli.tool_service import ToolService
from devt.registry.manager import RegistryManager
from devt.repo_manager import RepoManager
from datetime import datetime

logger = logging.getLogger(__name__)


class SyncManager:
    SYNC_INTERVAL = 30  # seconds

    @classmethod
    def from_context(cls, ctx: typer.Context) -> "SyncManager":
        return cls(ctx.obj.get("registry_dir"))

    def __init__(self, registry_dir: Path) -> None:
        self.registry = RegistryManager(registry_dir)
        self.tool_service = ToolService(registry_dir)
        self.repo_manager = RepoManager()
        self.last_sync_time = 0

    def sync_single_repository(self, repo: dict, force: bool = False) -> None:
        """
        Sync a single repository, update tools, and handle any errors.
        """
        repo_name = repo["name"]

        # Check if last_update is recent and skip sync if within SYNC_INTERVAL
        last_update_str = repo.get("last_update")
        if last_update_str:
            last_update_dt = datetime.fromisoformat(last_update_str)
            now = datetime.now(last_update_dt.tzinfo)
            elapsed = (now - last_update_dt).total_seconds()
            logger.debug(
                "Repository sync check details - elapsed: %.2f seconds, sync interval: %d seconds, force sync: %s",
                elapsed,
                self.SYNC_INTERVAL,
                force,
            )
            if elapsed < self.SYNC_INTERVAL and not force:
                logger.info(
                    "Skipping sync for '%s' as last update was %.2f seconds ago (< SYNC_INTERVAL).",
                    repo_name,
                    elapsed,
                )
                return

        logger.info(
            "Starting sync for repository '%s' located at %s",
            repo_name,
            repo["location"],
        )
        updated_dir, current_branch, changes_made = self.repo_manager.sync_repo(
            repo["location"]
        )
        logger.debug(
            "Sync result for '%s': updated_dir=%s, branch=%s, changes_made=%s",
            repo_name,
            updated_dir,
            current_branch,
            changes_made,
        )

        # Update last_update timestamp in registry
        self.registry.repository_registry.update_repository(repo.get("url"))

        if not changes_made and not force:
            logger.info("No changes detected for '%s'; skipping update.", repo_name)
            return

        logger.info("Importing tools from updated directory: %s", updated_dir)
        self.tool_service.overwrite_tool(updated_dir, repo_name, True)

    def sync_all_repositories(self, force: bool = False) -> None:
        """
        Synchronize all repositories with auto-sync enabled in parallel and wait for completion.
        """
        repositories = self.registry.repository_registry.list_repositories(
            auto_sync=True
        )
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
                # Exceptions will bubble up if any occur inside sync_single_repository
                logger.info("Auto-synced repository: %s", repo_name)
                future.result()

    def start_background_sync(self, subcommand: str) -> None:
        """
        Start a thread to perform background auto-sync if enough time has passed.
        """
        now = time.time()
        if now - self.last_sync_time < self.SYNC_INTERVAL:
            logger.debug(
                "Background sync throttled. Time since last sync: %.2f seconds.",
                now - self.last_sync_time,
            )
            return

        self.last_sync_time = now
        logger.info("Starting background sync.")

        def run_sync() -> None:
            logger.info("Background sync started.")
            self.sync_all_repositories()
            logger.info("Background sync completed.")

        thread = threading.Thread(target=run_sync, daemon=False)
        thread.start()
        logger.debug("Background sync started for subcommand: %s", subcommand)
        if subcommand == "run" or subcommand == "tool":
            thread.join()
        logger.info("Background sync completed and joined.")
