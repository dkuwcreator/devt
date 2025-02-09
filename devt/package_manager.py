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
            "source": str(source),
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

    def __init__(
            self,
            name: str,
            base_path: Path,
            registry_manager: RegistryManager,
            source: str
    ):
        super().__init__(name, base_path, registry_manager)
        self.source = source

    def setup_collection(self) -> bool:
            logger.info(
                "Creating local tool group '%s' at %s", self.name, self.base_path
            )
            self.base_path.mkdir(parents=True, exist_ok=True)
            try:
                # copy the source directory to the base_path
                # dest_path = self.base_path / source_path.name
                shutil.copytree(self.source, self.base_path, dirs_exist_ok=True)
                return True
            except Exception as e:
                logger.error("Failed to create local group '%s': %s", self.name, e)
                raise

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
        try:
            shutil.rmtree(self.base_path)
            logger.info("Local group '%s' removed successfully.", self.name)
            return True
        except Exception as e:
            logger.error("Failed to remove local group '%s': %s", self.name, e)
            return False
        

    def add_group(self) -> None:
        """
        Create the local group and add it to the registry.
        """
        is_setup = self.setup_collection()
        if is_setup:
            is_added = self.add_tools_to_registry(source=self.base_path)
            if is_added:
                self.registry_manager.save_registry()

    def update_group(self) -> None:
        """
        For local groups, there's no real update operation. So do nothing or implement custom logic.
        """
        logger.info("No update operation for local group '%s'.", self.name)

    def remove_group(self, force: bool = False) -> None:
        """
        Remove the local group and associated tools from the registry.
        """
        is_removed = self.remove_collection(force=force)
        if is_removed:
            self._remove_associated_tools()
            self.registry_manager.save_registry()

    def remove_package(self, package: str) -> None:
        """
        Remove a specific package from the local group and registry.
        """
        tool_dir = self.base_path / package
        if not tool_dir.exists():
            logger.warning("Tool directory %s not found.", tool_dir)
            return

        logger.info("Removing tool '%s' from local group '%s'...", package, self.name)
        try:
            shutil.rmtree(tool_dir)
            self.registry_manager.remove_tool_from_registry(package)
            self.registry_manager.save_registry()
            logger.info("Successfully removed tool '%s'.", package)
        except Exception as e:
            logger.error("Failed to remove tool '%s': %s", package, e)
            raise