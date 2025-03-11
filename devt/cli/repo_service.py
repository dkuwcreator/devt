#!/usr/bin/env python3
"""
devt/cli/tool_service.py

Tool Service Commands

Provides commands to import, export, update, and remove tool packages.
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import typer

from devt.cli.sync_service import SyncManager
from devt.cli.tool_service import ToolService
from devt.constants import SCOPE_TO_REGISTRY_DIR
from devt.registry.manager import RegistryManager
from devt.repo_manager import RepoManager
from devt.utils import scopes_to_registry_dirs

logger = logging.getLogger(__name__)


class RepoService:
    """
    Manages repositories and associated tools.
    """

    @classmethod
    def from_context(cls, ctx: typer.Context) -> "RepoService":
        return cls(ctx.obj.get("registry_dir"))

    def __init__(self, registry_dir: Path) -> None:
        self.registry = RegistryManager(registry_dir)
        self.tool_service = ToolService(registry_dir)
        self.repo_manager = RepoManager()
        self.sync_manager = SyncManager(registry_dir)

    # -------------------------------------------
    # Repository Import / Export / Update Operations
    # -------------------------------------------

    def import_repo(
        self, url: str, branch: str, sync: bool, name: str, force: bool
    ) -> None:
        """Imports a repository into the registry."""
        logger.info("Adding repository: %s", url)

        # Clone the repo locally
        repo_dir, effective_branch = self.repo_manager.add_repo(url, branch=branch, force=force)
        display_name = name or repo_dir.name
        logger.info("Repository cloned at %s", repo_dir)

        # Add repository to the registry
        self.registry.register_repository(
            url=url,
            name=display_name,
            branch=effective_branch,
            location=str(repo_dir),
            auto_sync=sync,
            force=force,
        )

        # Import all tools from this repo
        self.tool_service.import_tool(repo_dir, display_name, force)

    def remove_repo(self, repo_name: str) -> None:
        """Removes a repository and all its associated tools."""
        repo = self.registry.repository_registry.get_repo_by_name(name=repo_name)
        if not repo:
            logger.info("Repository '%s' not found.", repo_name)
            return

        location = repo.get("location")
        if location:
            self.repo_manager.remove_repo(str(location))
            logger.info("Removed repository '%s'.", repo_name)

        self.tool_service.remove_group_tools(repo_name)

        self.registry.unregister_repository(repo.get("url"))

    def sync_repos(self, filters: Dict[str, Optional[str]], force: bool) -> None:
        """Synchronizes all repositories by re-importing them from disk."""
        repos = self.list_repos(**filters)
        if not repos:
            logger.info("No repositories found to sync.")
            raise ValueError("No repositories found to sync.")

        for repo in repos:
            self.sync_manager.sync_single_repository(repo, force)

    def list_repos(self, **filters: Dict[str, Optional[str]]) -> List[Dict[str, Any]]:
        """Returns a list of all repositories in the registry."""
        return self.registry.list_repositories(**filters)

    def get_repo_info(self, repo_name: str) -> Optional[dict]:
        """Retrieves repository information by its unique name."""
        repo = self.registry.get_repo_by_name(name=repo_name)
        if not repo:
            logger.warning("Repository '%s' not found in the registry.", repo_name)
            raise ValueError(f"Repository '{repo_name}' not found in the registry.")
        return repo


class RepoServiceWrapper:
    """
    Wrapper class for RepoService to use in Typer commands.
    """

    @classmethod
    def from_context(cls, ctx: typer.Context) -> "RepoServiceWrapper":
        return cls(ctx.obj.get("scope"))

    def __init__(self, scope: Optional[str] = None) -> None:
        logger.info("Initializing RepoServiceWrapper with scope: %s", scope)
        self.scope = scope
        self.repo_services: Dict[str, RepoService] = self.get_scopes_to_query(scope)
        self.found_scope = None

    def get_scopes_to_query(
        self, scope: Optional[str] = None
    ) -> Dict[str, RepoService]:
        """
        Returns a dictionary mapping scope names to ToolService instances.

        :param scope: If 'user' or 'workspace', returns that single scope.
                      If 'both', 'all', or None, returns both scopes.
        :raises ValueError: If an invalid scope is provided.
        """
        registry_dirs = scopes_to_registry_dirs()

        normalized_scope = scope.lower() if scope else None

        if normalized_scope in (None, "both", "all"):
            logger.info("Querying both 'workspace' and 'user' scopes.")
            return {
                s: RepoService(registry_dir)
                for s, registry_dir in registry_dirs.items()
            }

        if normalized_scope in registry_dirs:
            logger.info("Querying single scope: %s", normalized_scope)
            return {
                normalized_scope: RepoService(SCOPE_TO_REGISTRY_DIR[normalized_scope])
            }

        logger.error(
            "Invalid scope provided: %s. Choose 'workspace', 'user', or 'both'.", scope
        )
        raise ValueError(
            "Invalid scope provided. Choose 'workspace', 'user', or 'both'."
        )

    def import_repo(
        self, url: str, branch: str, sync: bool, name: str, force: bool
    ) -> None:
        """Imports a repository into the registry."""
        if not self.scope or self.scope == "both":
            raise ValueError(
                "Cannot import repository without specifying a single scope."
            )
        self.repo_services[self.scope].import_repo(url, branch, sync, name, force)

    def remove_repo(self, repo_name: str) -> None:
        """Removes a repository and all its associated tools."""
        for scope, repo_service in self.repo_services.items():
            self.found_scope = scope
            try:
                repo_service.remove_repo(repo_name)
                return
            except ValueError:
                continue
        raise ValueError(f"Repository '{repo_name}' not found in any scope.")

    def sync_repos(self, filters: Dict[str, Optional[str]], force: bool) -> None:
        """Synchronizes all repositories by re-importing them from disk."""
        for scope, repo_service in self.repo_services.items():
            self.found_scope = scope
            repo_service.sync_repos(filters, force)
            return

    def list_repos(self, **filters: Dict[str, Optional[str]]) -> Dict[str, List[dict]]:
        """Returns a dictionary of repositories matching the filters."""
        results = {}
        for self.found_scope, repo_service in self.repo_services.items():
            results[self.found_scope] = repo_service.list_repos(**filters)
        return results

    def get_repo_info(self, repo_name: str) -> Optional[dict]:
        """Retrieves repository information by its unique name."""
        for scope, repo_service in self.repo_services.items():
            self.found_scope = scope
            try:
                return repo_service.get_repo_info(repo_name)
            except ValueError:
                continue
        raise ValueError(f"Repository '{repo_name}' not found in any scope.")
