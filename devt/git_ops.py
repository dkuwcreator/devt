# devt/git_ops.py
import logging
from pathlib import Path
import shutil
from typing import Dict, Any, List, Optional, Tuple
from urllib.parse import urlparse
from git import Repo
import typer

from devt.package_ops import BaseToolCollection
from devt.registry import RegistryManager
from devt.utils import on_exc

logger = logging.getLogger(__name__)


class ToolRepo(BaseToolCollection):
    """
    A Git-based repository of tools, typically located at: app_dir / 'repos' / <repo_name>.
    """

    def __init__(
        self,
        name: str,
        base_path: Path,
        registry_manager: RegistryManager,
        remote_url: str,
        branch: Optional[str] = None,
        auto_sync: bool = True,
    ):
        super().__init__(name, base_path, registry_manager)
        self.remote_url = remote_url
        self.branch = branch
        self.auto_sync = auto_sync

    def setup_collection(self) -> bool:
        """
        Clone the Git repo if it doesn't exist. If it does exist, do nothing.
        """
        if not self.base_path.exists():
            logger.info(
                "Cloning repository '%s' from %s into %s",
                self.name,
                self.remote_url,
                self.base_path,
            )
            try:
                if self.branch is None:
                    repo = Repo.clone_from(self.remote_url, self.base_path)
                    self.branch = repo.active_branch.name
                else:
                    Repo.clone_from(self.remote_url, self.base_path, branch=self.branch)

                return True
            except Exception as e:
                logger.error("Failed to clone repository '%s': %s", self.remote_url, e)
                raise
        else:
            logger.debug(
                    "Repo '%s' already exists at %s. No clone needed.",
                    self.name,
                    self.base_path,
                )
            typer.echo(f"Repo '{self.name}' already exists at {self.base_path}.")
            typer.echo(f"Use 'devt sync {self.name}' to pull the latest changes.")
            # if self.branch is None:
            #     typer.echo(f"Use 'devt sync {self.name}' to pull the latest changes.")
            # else:
            #     typer.echo(
            #         f"Use 'devt sync {self.name} --branch {self.branch}' to pull the latest changes."
            #     )
            return False
                
    def sync_collection(self) -> bool:
        """
        Pull the latest changes if auto_sync is True.
        """
        try:
            repo = Repo(self.base_path)
            if repo.is_dirty():
                logger.warning(
                    "Repo %s is dirty; resetting local changes...", self.base_path
                )
                repo.git.reset("--hard")

            if self.branch:
                logger.info(
                    "Checking out branch '%s' for repo '%s'...", self.branch, self.name
                )
                repo.git.checkout(self.branch)

            logger.info("Pulling latest changes for repo '%s'...", self.name)
            repo.remotes.origin.pull()
            return True
        except Exception as e:
            logger.error("Failed to pull changes in '%s': %s", self.base_path, e)
            raise

    def remove_collection(self, force: bool = False) -> bool:
        if not force:
            logger.info("Confirm removal of repo '%s' at %s", self.name, self.base_path)
            # CLI prompt or other logic could go here.

        if not self.base_path.exists():
            logger.warning("Repo directory %s not found.", self.base_path)
            return False

        logger.info("Removing repo '%s' at %s...", self.name, self.base_path)
        try:
            shutil.rmtree(self.base_path, onexc=on_exc)
            logger.info("Successfully removed repo '%s'.", self.name)
        except Exception as e:
            logger.error("Failed to remove repo '%s': %s", self.name, e)
            raise
        return True

    def add_repo(self) -> None:
        """
        Clone the repository and add it to the registry.
        """
        is_setup = self.setup_collection()
        if is_setup:
            is_added = self.add_tools_to_registry(
                source=self.remote_url,
                branch=self.branch,
                auto_sync=self.auto_sync
            )
            if is_added:
                self.registry_manager.save_registry()

    def update_repo(self) -> None:
        """
        Pull the latest changes from the repository.
        """
        is_synced = self.sync_collection()
        if is_synced:
            is_added = self.add_tools_to_registry(
                source=self.remote_url,
                branch=self.branch,
                auto_sync=self.auto_sync
            )
            if is_added:
                self.registry_manager.save_registry()

    def remove_repo(self, force: bool = False) -> None:
        """
        Remove the repository and associated tools from the registry.
        """
        is_removed = self.remove_collection(force=force)
        if is_removed:
            self._remove_associated_tools()
            self.registry_manager.save_registry()


def update_repo(repo_dir: Path, branch: str = None) -> Path:
    """
    Update a git repository.
    """
    repo = Repo(repo_dir)
    if repo.is_dirty():
        logger.warning(
            "Repository %s is dirty. Resetting to a clean state...", repo_dir
        )
        repo.git.reset("--hard")
    logger.info("Updating repository %s...", repo_dir)
    if branch:
        repo.git.checkout(branch)
    repo.remotes.origin.pull()
    return repo_dir


def clone_or_update_repo(
    repo_url: str, base_dir: Path, branch: str = None
) -> Tuple[Path, str]:
    """
    Clone or update a git repository.
    """
    repo_name = Path(urlparse(repo_url).path).stem
    repo_dir = base_dir / "repos" / repo_name

    try:
        if repo_dir.exists():
            update_repo(repo_dir, branch=branch)
        else:
            logger.info("Cloning repository %s...", repo_url)
            if branch is None:
                repo = Repo.clone_from(repo_url, repo_dir)
                branch = repo.active_branch.name
            else:
                Repo.clone_from(repo_url, repo_dir, branch=branch)
    except Exception as e:
        logger.error("Failed to clone or update repository %s: %s", repo_url, e)
        raise

    return repo_dir, branch
