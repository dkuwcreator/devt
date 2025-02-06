# devt/git_ops.py
import logging
from pathlib import Path
from urllib.parse import urlparse
from git import Repo

logger = logging.getLogger("devt")


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
    repo.remotes.origin.pull()
    return repo_dir


def clone_or_update_repo(repo_url: str, base_dir: Path, branch: str = None) -> Path:
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
            Repo.clone_from(repo_url, repo_dir, branch=branch or "main")
    except Exception as e:
        logger.error("Failed to clone or update repository %s: %s", repo_url, e)
        raise

    return repo_dir
