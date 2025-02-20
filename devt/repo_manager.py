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

from git import Repo  # Requires GitPython: pip install GitPython

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
        logger.info("Initialized RepoManager with repos directory at: %s", self.repos_dir)

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

    def sync_repo(self, repo_url: str, branch: str = "main") -> Path:
        """
        Clone or update a repository.
        
        If the repository already exists, it is updated (and reset if dirty). Otherwise,
        it is cloned from the provided URL.
        
        Args:
            repo_url (str): The URL of the repository.
            branch (str): The branch to clone or update. Default is "main".
        
        Returns:
            Path: The local path to the repository directory.
        
        Raises:
            Exception: If cloning or updating fails.
        """
        repo_dir = self._get_repo_dir(repo_url)
        try:
            if repo_dir.exists():
                repo = Repo(repo_dir)
                if repo.is_dirty():
                    logger.warning(
                        "Repository %s is dirty. Resetting to a clean state...", repo_dir.name
                    )
                    repo.git.reset("--hard")
                logger.info("Updating repository %s...", repo_dir.name)
                repo.remotes.origin.pull()
            else:
                logger.info("Cloning repository %s...", repo_url)
                Repo.clone_from(repo_url, repo_dir, branch=branch)
        except Exception as e:
            logger.error("Failed to clone or update repository %s: %s", repo_url, e)
            raise e
        return repo_dir

    def add_repo(self, repo_url: str, branch: str = "main") -> Path:
        """
        Add a repository by cloning or updating it.
        
        This is essentially a wrapper for sync_repo to express the intent of adding a repo.
        
        Args:
            repo_url (str): The URL of the repository.
            branch (str): The branch to use. Default is "main".
        
        Returns:
            Path: The local path to the repository.
        """
        return self.sync_repo(repo_url, branch=branch)

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
                shutil.rmtree(repo_dir)
                logger.info("Repository '%s' removed successfully.", repo_dir)
                return True
            except Exception as e:
                logger.error("Failed to remove repository '%s': %s", repo_dir, e)
                return False
        else:
            logger.warning("Repository '%s' does not exist.", repo_dir)
            return False
