# devt/package_ops.py
from datetime import datetime, timezone
import json
import shutil
import logging
from pathlib import Path

# import json
from abc import ABC, abstractmethod

from devt.registry import RegistryManager
from typing import List, Optional

# from dataclasses import dataclass, asdict, field

# from devt.registry import RegistryManager

from .utils import on_exc, save_json

logger = logging.getLogger(__name__)

# @dataclass
# class ToolManifest:
#     """
#     Represents the structure of a tool package's manifest.json file.

#     Fields:
#         name (str): Short name/title of the tool.
#         description (str): A human-readable summary of the tool's purpose.
#         command (str): A unique identifier (CLI command) used in the registry.
#         base_dir (Optional[str]): A custom base directory for resolving paths.
#         dependencies (Dict[str, str]): Version constraints for required tools/libraries.
#         scripts (Dict[str, Any]): Keyed by script name ("install", "update", etc.) and
#             may include platform-specific subkeys (e.g., "windows", "posix").
#     """

#     name: str
#     description: str
#     command: str
#     base_dir: Optional[str] = None

#     # Dependencies: e.g. {"python": "^3.9.0", "pip": "^21.0.0"}
#     dependencies: Dict[str, Any] = field(default_factory=dict)

#     # Scripts can be deeply nested, so we keep it flexible:
#     # e.g.,
#     #   {
#     #       "windows": {"install": "...", "update": "..."},
#     #       "posix": {"update": "..."},
#     #       "install": "...",
#     #       ...
#     #   }
#     scripts: Dict[str, Any] = field(default_factory=dict)


class BaseToolCollection(ABC):
    """
    Base or abstract class that defines common behaviors for a 'collection' of tools on disk.
    Subclasses can be a local group (ToolGroup) or a Git-based repo (ToolRepo).
    """

    def __init__(self, name: str, base_path: Path, registry_manager: RegistryManager):
        """
        :param name: Short identifier (group name or repo name).
        :param base_path: Directory under which the collection is stored.
        :param registry_manager: Manages the registry (load/save, update, remove, etc.).
        """
        self.name = name
        self.base_path = base_path
        self.registry_manager = registry_manager

    @abstractmethod
    def setup_collection(self) -> None:
        """
        Create or clone the collection on disk.
        """
        pass

    @abstractmethod
    def sync_collection(self) -> None:
        """
        Update the local files to the latest state.
        """
        pass

    @abstractmethod
    def remove_collection(self, force: bool = False) -> None:
        """
        Physically remove the directory and remove associated registry entries.
        """
        pass

    def find_tool_dirs(self) -> List[Path]:
        """
        Look for subdirectories containing 'manifest.json' within this collection.
        """
        if not self.base_path.exists():
            return []
        manifest_files = list(self.base_path.rglob("manifest.json"))
        return [m.parent for m in manifest_files]

    def add_tools_to_registry(
        self, source: str, branch: Optional[str] = None, auto_sync: bool = False
    ) -> bool:
        """
        Scan for tool directories and update the registry with each discovered tool.
        """
        tool_dirs = self.find_tool_dirs()
        if not tool_dirs:
            logger.warning(
                "No tool directories found for %s '%s'.",
                self.__class__.__name__,
                self.name,
            )
            logger.warning("Removing collection '%s'...", self.name)
            self.remove_collection(force=True)
            return False

        logger.info(
            "Found %d tool directories for %s '%s'.",
            len(tool_dirs),
            self.__class__.__name__,
            self.name,
        )
        try:
            for tool_dir in tool_dirs:
                self._register_tool_dir(tool_dir, source, branch, auto_sync)
            return True
        except Exception as e:
            logger.error("Error adding tools to registry: %s", e)
            return False

    def _register_tool_dir(
        self, tool_dir: Path, source: str, branch: Optional[str], auto_sync: bool
    ) -> None:
        manifest_path = tool_dir / "manifest.json"
        if not manifest_path.exists():
            return
        try:
            with manifest_path.open("r", encoding="utf-8") as f:
                manifest_data = json.load(f)
        except Exception as e:
            logger.error("Could not read manifest at %s: %s", manifest_path, e)
            return

        command = manifest_data.get("command")
        if not command:
            logger.warning("Skipping tool in %s; no 'command' field found.", tool_dir)
            return

        entry = {
            "manifest": manifest_data,
            "location": self._relative_location(manifest_path),
            "added": datetime.now(timezone.utc).isoformat(),
            "source": source,
            "dir": self.name,
            "active": True,
            "branch": branch,
            "auto_sync": auto_sync,
        }
        logger.info(
            "Updating registry for tool '%s' in collection '%s'.", command, self.name
        )
        self.registry_manager.update_tool_in_registry(command, entry)

    def _relative_location(self, manifest_path: Path) -> str:
        """
        Attempt to store a path relative to the registry file's parent directory.
        """
        try:
            return str(
                manifest_path.relative_to(self.registry_manager.registry_file.parent)
            )
        except ValueError:
            return str(manifest_path)

    def _remove_associated_tools(self) -> None:
        """
        Remove all registry entries whose 'dir' field matches self.name.
        """
        reg = self.registry_manager.registry
        to_delete = [tool for tool, data in reg.items() if data.get("dir") == self.name]
        for tool_name in to_delete:
            self.registry_manager.remove_tool_from_registry(tool_name)
        if to_delete:
            logger.info(
                "Removed %d tools from registry for %s '%s'.",
                len(to_delete),
                self.__class__.__name__,
                self.name,
            )


class ToolGroup(BaseToolCollection):
    """
    A purely local group of tools. Typically located at: app_dir / 'tools' / <group_name>.
    """

    def setup_collection(self) -> bool:
        if not self.base_path.exists():
            logger.info(
                "Creating local tool group '%s' at %s", self.name, self.base_path
            )
            self.base_path.mkdir(parents=True, exist_ok=True)
            return True
        else:
            logger.debug(
                "Tool group '%s' already exists at %s.", self.name, self.base_path
            )
            return False

    def sync_collection(self) -> None:
        """
        For local groups, there's no real sync with a remote. So do nothing or implement custom logic.
        """
        logger.debug("No sync operation for local group '%s'.", self.name)

    def remove_collection(self, force: bool = False) -> bool:
        if not force:
            logger.info(
                "Confirm removal of local group '%s' at %s", self.name, self.base_path
            )
            # CLI prompt or other logic could go here.

        if not self.base_path.exists():
            logger.warning("Group directory %s not found.", self.base_path)
            return False

        logger.info(
            "Removing local tool group '%s' at %s...", self.name, self.base_path
        )
        try:
            shutil.rmtree(self.base_path)
            logger.info("Successfully removed group '%s'.", self.name)
            return True
        except Exception as e:
            logger.error("Failed to remove group '%s': %s", self.name, e)
            raise

    def add_group(self) -> None:
        """
        Create the local group and add it to the registry.
        """
        is_setup = self.setup_collection()
        if is_setup:
            is_added = self.add_tools_to_registry(source=self.base_path)
            if is_added:
                self.registry_manager.save_registry()

    def remove_group(self, force: bool = False) -> None:
        """
        Remove the local group and associated tools from the registry.
        """
        is_removed = self.remove_collection(force=force)
        if is_removed:
            self._remove_associated_tools()
            self.registry_manager.save_registry()


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
        logger.error(
            "Failed to copy local path %s to %s: %s", source_path, destination, e
        )
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


def delete_local_package(
    tool_key: str, base_dir: Path, registry: dict, registry_file: Path
):
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
        logger.error(
            "Registry entry for tool '%s' does not appear to be a local package.",
            tool_key,
        )
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


def remove_repository(
    repo_name: str, base_dir: Path, registry: dict, registry_file: Path
):
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
            new_registry = {
                key: value
                for key, value in registry.items()
                if value.get("dir") != repo_name
            }
            save_json(registry_file, new_registry)
        except Exception as e:
            logger.error("Failed to remove repository '%s': %s", repo_name, e)
            raise
    else:
        logger.warning("Repository directory not found: %s", repo_dir)
