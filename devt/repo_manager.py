#!/usr/bin/env python3
"""
devt/repo_manager.py

Repository Manager

Provides a RepoManager class to add, sync, and remove repositories in a dedicated
'repos' folder. Repositories managed here can later be imported locally by the tool,
similarly to how local directories are handled.
"""

import logging
from pathlib import Path
import shutil
from urllib.parse import urlparse

from git import Repo
from devt.constants import USER_REGISTRY_DIR
from devt.utils import force_remove, on_exc

logger = logging.getLogger(__name__)


class RepoManager:
    """
    Manages repositories stored in a dedicated repos folder.

    This class allows you to add (clone or update), sync, and remove repositories.
    Repositories are stored in a subfolder named 'repos' within the provided base directory.
    """

    def __init__(self) -> None:
        """
        Initialize the RepoManager with a base directory.

        Args:
            base_dir (Path): The base directory where the 'repos' folder will be created.
        """
        self.base_dir: Path = USER_REGISTRY_DIR
        self.repos_dir: Path = self.base_dir / "repos"
        self.repos_dir.mkdir(exist_ok=True)
        logger.debug(
            "Initialized RepoManager with repos directory at: %s", self.repos_dir
        )

    def _get_repo_name(self, repo_url: str) -> str:
        """Extracts a repository name from its URL."""
        return Path(urlparse(repo_url).path).stem

    def _resolve_repo_dir(self, repo_identifier: str) -> Path:
        """Resolves the repository directory based on the identifier (URL, name, or path)."""
        if str(repo_identifier).startswith(("http://", "https://", "git@")):
            return self.repos_dir / self._get_repo_name(repo_identifier)
        potential_path = Path(repo_identifier)
        return (
            potential_path.resolve()
            if potential_path.is_absolute()
            else (self.repos_dir / repo_identifier).resolve()
        )

    def sync_repo(self, repo_identifier: str, branch: str = None) -> tuple[Path, str, bool]:
        """
        Update an existing repository and indicate if any changes were applied.

        The repo_identifier can be either a repository name (or relative directory under repos)
        or an absolute/local directory path. If a URL is provided instead, it will be
        converted to a local repo directory using _get_repo_dir.

        Args:
            repo_identifier (str): The repository name, local path, or URL.
            branch (str, optional): Branch to update. If provided, attempts to check out
                                    and pull that branch. Defaults to None.

        Returns:
            tuple[Path, str, bool]:
                - The local path to the repository.
                - The effective branch.
                - A boolean indicating whether changes were made.

        Raises:
            Exception: If the repository directory doesn't exist or update fails.
        """
        repo_dir = self._resolve_repo_dir(repo_identifier)
        if not repo_dir.exists():
            raise FileNotFoundError(f"Repository directory does not exist: {repo_dir}")

        try:
            repo = Repo(repo_dir)
            if repo.is_dirty():
                logger.warning(
                    "Repository %s is dirty. Resetting to a clean state...",
                    repo_dir.name,
                )
                repo.git.reset("--hard")

            available_branches = {b.name for b in repo.branches}
            if branch and branch in available_branches:
                repo.git.checkout(branch)
            elif branch:
                logger.warning(
                    "Branch '%s' does not exist. Updating the current branch instead.",
                    branch,
                )

            current_branch = repo.active_branch.name
            commit_before = repo.head.commit.hexsha

            logger.info("Updating repository %s...", repo_dir.name)
            repo.remotes.origin.pull()
            commit_after = repo.head.commit.hexsha
            changes_made = commit_before != commit_after

            if changes_made:
                logger.info("Repository %s updated. New commit: %s", repo_dir.name, commit_after)
            else:
                logger.info("Repository %s is already up-to-date.", repo_dir.name)

            return repo_dir, current_branch, changes_made
        except Exception as e:
            logger.error("Failed to update repository at %s: %s", repo_dir, e)
            raise ValueError(f"Failed to update repository at {repo_dir}: {e}")

    def add_repo(self, repo_url: str, branch: str = None, force: bool = False) -> tuple[Path, str]:
        """
        Add a repository by cloning it if not already added or updating it if it exists.

        Args:
            repo_url (str): The URL of the repository.
            branch (str, optional): The branch to clone or update. Defaults to None.

        Returns:
            tuple[Path, str]: The local path to the repository and the effective branch.

        Raises:
            Exception: If cloning or updating fails.
        """
        repo_dir = self._resolve_repo_dir(repo_url)
        if force:
            logger.info("Force-removing existing repository %s...", repo_dir.name)
            try:
                shutil.rmtree(repo_dir, onexc=on_exc)
            except Exception as e:
                logger.error("Failed to remove repository %s: %s", repo_dir, e)
                raise ValueError(f"Failed to remove repository {repo_dir}: {e}")
        elif repo_dir.exists():
            logger.info("Repository %s already exists. Updating...", repo_dir.name)
            updated_dir, current_branch, changes_made = self.sync_repo(repo_dir, branch)
            return updated_dir, current_branch

        logger.info("Cloning repository %s...", repo_url)
        repo = Repo.clone_from(repo_url, repo_dir, branch=branch)
        return repo_dir, repo.active_branch.name

    def remove_repo(self, repo_url: str) -> bool:
        """
        Remove a repository from the repos folder.

        Args:
            repo_url (str): The URL of the repository to remove.

        Returns:
            bool: True if the repository was removed successfully, False otherwise.
        """
        repo_dir = self._resolve_repo_dir(repo_url)
        shutil.rmtree(repo_dir, onexc=on_exc)
        logger.info("Repository '%s' removed successfully.", repo_dir)

    def checkout_branch(self, repo_dir: str, branch: str) -> bool:
        """
        Checkout a branch in a repository.
        
        Args:
            repo_dir (str): The path to the repository directory.
            branch (str): The branch to checkout.

        Returns:
            bool: True if the branch was checked out successfully, False otherwise.
        """

        try:
            repo = Repo(repo_dir)
            if repo.is_dirty():
                logger.info("Repository %s is dirty. Resetting to a clean state...", repo_dir.name)
                repo.git.reset("--hard")
            if branch in {b.name for b in repo.branches}:
                repo.git.checkout(branch)
                logger.info("Checked out branch '%s' in repository %s", branch, repo_dir.name)
                return True
            logger.error("Branch '%s' does not exist in repository %s", branch, repo_dir.name)
            return False
        except Exception as e:
            logger.error("Failed to check out branch '%s' in repository %s: %s", branch, repo_dir, e)
            return False
