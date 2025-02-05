# devt/package_ops.py
import shutil
import logging
from pathlib import Path
import json

from .utils import on_exc, save_json
from .git_ops import clone_or_update_repo

logger = logging.getLogger("devt")


def add_local(local_path: str, base_dir: Path) -> Path:
    """
    Add a local tool to the specified base directory.
    (A simple copy operation; grouping is handled by the CLI.)
    """
    source_path = Path(local_path).resolve()
    if not source_path.exists():
        raise FileNotFoundError(f"Path '{local_path}' does not exist.")
    
    # Default destination: simply copy the source folder into base_dir/tools using its name.
    destination = base_dir / "tools" / source_path.name
    try:
        shutil.copytree(source_path, destination, dirs_exist_ok=True)
    except Exception as e:
        logger.error("Failed to copy local path %s to %s: %s", source_path, destination, e)
        raise

    return destination


def import_local_package(local_path: str, base_dir: Path) -> Path:
    """
    Import a local tool package into the registry.
    (This function simply copies the package from local_path to the
     destination under base_dir/tools. Grouping is handled by the CLI.)
    """
    source_path = Path(local_path).resolve()
    if not source_path.exists():
        raise FileNotFoundError(f"Path '{local_path}' does not exist.")
    
    destination = base_dir / "tools" / source_path.name
    try:
        shutil.copytree(source_path, destination, dirs_exist_ok=True)
        logger.info("Local package imported successfully: %s", source_path.name)
    except Exception as e:
        logger.error("Failed to copy local package %s: %s", source_path, e)
        raise

    return destination


def export_local_package(package_name: str, destination_path: str, base_dir: Path):
    """
    Export a local tool package from the registry.
    This function assumes that the package is stored under base_dir/tools.
    """
    tool_dir = base_dir / "tools" / package_name
    destination = Path(destination_path).resolve()

    if not tool_dir.exists():
        raise FileNotFoundError(f"Tool package '{package_name}' does not exist.")

    try:
        shutil.copytree(tool_dir, destination, dirs_exist_ok=True)
        logger.info("Local package exported successfully to %s", destination)
    except Exception as e:
        logger.error("Failed to export local package %s: %s", package_name, e)
        raise


def delete_local_package(tool_key: str, base_dir: Path, registry: dict, registry_file: Path):
    """
    Delete a local tool package from the registry.
    
    Instead of assuming the package folder is simply base_dir / "tools" / tool_key,
    we use the registry entry's "location" field. For example, if the registry entry's
    "location" is "tools\\test_tools\\test\\manifest.json", we delete its parent folder.
    """
    entry = registry.get(tool_key)
    if not entry:
        logger.error("No registry entry found for tool '%s'.", tool_key)
        return

    location = entry.get("location", "")
    if not location.startswith("tools"):
        logger.error("Registry entry for tool '%s' does not appear to be a local package.", tool_key)
        return

    # Construct the absolute path to the manifest file; if location is relative, use base_dir.
    tool_manifest_path = Path(location)
    if not tool_manifest_path.is_absolute():
        tool_manifest_path = base_dir / tool_manifest_path
    # The package folder is assumed to be the parent directory of manifest.json.
    tool_dir = tool_manifest_path.parent

    if tool_dir.exists():
        try:
            shutil.rmtree(tool_dir)
            logger.info("Tool package '%s' removed successfully.", tool_key)
            # Remove the entry from the registry and update the JSON file.
            registry.pop(tool_key, None)
            save_json(registry_file, registry)
        except Exception as e:
            logger.error("Failed to remove tool package '%s': %s", tool_key, e)
            raise
    else:
        logger.warning("Tool package directory not found: %s", tool_dir)


def remove_repository(repo_name: str, base_dir: Path, registry: dict, registry_file: Path):
    """
    Remove a repository from the registry.
    
    This function deletes the local repository directory and then filters
    the registry to remove any tools whose "dir" field matches repo_name.
    """
    repo_dir = base_dir / "repos" / repo_name
    if repo_dir.exists():
        try:
            shutil.rmtree(repo_dir, onexc=on_exc)
            logger.info("Repository '%s' removed successfully.", repo_name)
            # Filter registry entries not belonging to the repository.
            new_registry = {key: value for key, value in registry.items() if value.get("dir") != repo_name}
            save_json(registry_file, new_registry)
        except Exception as e:
            logger.error("Failed to remove repository '%s': %s", repo_name, e)
            raise
    else:
        logger.warning("Repository directory not found: %s", repo_dir)


def sync_repositories(base_dir: Path):
    """
    Sync all repositories in the registry by pulling the latest changes.
    """
    repos_dir = base_dir / "repos"
    if not repos_dir.exists():
        logger.warning("No repositories found to sync.")
        return

    logger.info("Syncing repositories in %s...", repos_dir)
    for repo_path in repos_dir.iterdir():
        if repo_path.is_dir():
            try:
                # Call clone_or_update_repo with the directory path as a string.
                clone_or_update_repo(str(repo_path), base_dir, branch=None)
            except Exception as e:
                logger.error("Failed to sync repository '%s': %s", repo_path.name, e)
