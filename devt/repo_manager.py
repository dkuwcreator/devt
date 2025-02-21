"""
repo_manager.py

Provides a RepoManager class to add, sync, and remove repositories in a dedicated
'repos' folder. Repositories managed here can later be imported locally by the tool,
similarly to how local directories are handled.
"""

import shutil
import logging
from pathlib import Path
from urllib.parse import urlparse

from git import Repo

from devt.utils import on_exc  # Requires GitPython: pip install GitPython

logger = logging.getLogger(__name__)


class RepoManager:
    """
    Manages repositories stored in a dedicated repos folder.

    This class allows you to add (clone or update), sync, and remove repositories.
    Repositories are stored in a subfolder named 'repos' within the provided base directory.
    """

    def __init__(self, base_dir: Path) -> None:
        """
        Initialize the RepoManager with a base directory.

        Args:
            base_dir (Path): The base directory where the 'repos' folder will be created.
        """
        self.base_dir: Path = base_dir.resolve()
        self.repos_dir: Path = self.base_dir / "repos"
        self.repos_dir.mkdir(parents=True, exist_ok=True)
        logger.info(
            "Initialized RepoManager with repos directory at: %s", self.repos_dir
        )

    def _get_repo_dir(self, repo_url: str) -> Path:
        """
        Derive the repository's local directory based on its URL.

        Args:
            repo_url (str): The URL of the repository.

        Returns:
            Path: The local repository directory under the repos folder.
        """
        repo_name = Path(urlparse(repo_url).path).stem
        return self.repos_dir / repo_name

    def sync_repo(self, repo_identifier: str, branch: str = None) -> tuple[Path, str]:
        """
        Update an existing repository.

        The repo_identifier can be either a repository name (or relative directory under repos)
        or an absolute/local directory path. If a URL is provided instead, it will be
        converted to a local repo directory using _get_repo_dir.

        Args:
            repo_identifier (str): The repository name, local path, or URL.
            branch (str, optional): Branch to update. If provided, attempts to check out
                                    and pull that branch. Defaults to None.

        Returns:
            tuple[Path, str]: The local path to the repository and its effective branch.

        Raises:
            Exception: If the repository directory doesn't exist or update fails.
        """
        # Determine the repository directory.
        if repo_identifier.startswith(("http://", "https://", "git@")):
            repo_dir = self._get_repo_dir(repo_identifier)
        else:
            potential_path = Path(repo_identifier)
            if potential_path.is_absolute():
                repo_dir = potential_path.resolve()
            else:
                repo_dir = (self.repos_dir / repo_identifier).resolve()

        if not repo_dir.exists():
            raise Exception(f"Repository directory does not exist: {repo_dir}")

        try:
            repo = Repo(repo_dir)
            if repo.is_dirty():
                logger.warning(
                    "Repository %s is dirty. Resetting to a clean state...",
                    repo_dir.name,
                )
                repo.git.reset("--hard")
            if branch is not None:
                if branch in [b.name for b in repo.branches]:
                    repo.git.checkout(branch)
                else:
                    logger.warning(
                        "Branch '%s' does not exist in repository '%s'. Updating the current branch instead.",
                        branch, repo_dir.name
                    )
            logger.info("Updating repository %s...", repo_dir.name)
            # Pull the specified branch if it exists; otherwise, pull the current branch.
            current_branch = repo.active_branch.name
            repo.remotes.origin.pull(branch if branch in [b.name for b in repo.branches] else current_branch)
            effective_branch = repo.active_branch.name
        except Exception as e:
            logger.error("Failed to update repository at %s: %s", repo_dir, e)
            raise e
        return repo_dir, effective_branch

    def add_repo(self, repo_url: str, branch: str = None) -> tuple[Path, str]:
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
        repo_dir = self._get_repo_dir(repo_url)
        if repo_dir.exists():
            # If repository already exists, update it.
            logger.info("Repository %s already exists. Updating...", repo_dir.name)
            return self.sync_repo(repo_url, branch=branch)
        try:
            logger.info("Cloning repository %s...", repo_url)
            repo = Repo.clone_from(repo_url, repo_dir, branch=branch)
            effective_branch = repo.active_branch.name
        except Exception as e:
            logger.error("Failed to clone repository %s: %s", repo_url, e)
            raise e
        return repo_dir, effective_branch

    def remove_repo(self, repo_url: str) -> bool:
        """
        Remove a repository from the repos folder.

        Args:
            repo_url (str): The URL of the repository to remove.

        Returns:
            bool: True if the repository was removed successfully, False otherwise.
        """
        repo_dir = self._get_repo_dir(repo_url)
        if repo_dir.exists():
            try:
                shutil.rmtree(repo_dir, onexc=on_exc)
                logger.info("Repository '%s' removed successfully.", repo_dir)
                return True
            except Exception as e:
                logger.error("Failed to remove repository '%s': %s", repo_dir, e)
                return False
        else:
            logger.warning("Repository '%s' does not exist.", repo_dir)
            return False
