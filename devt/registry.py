# devt/registry.py
import json
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
import logging
# from devt.package_ops import ToolManifest
from devt.utils import load_json, save_json

from .manifest import validate_manifest

logger = logging.getLogger(__name__)

# @dataclass
# class ToolRegistryEntry:
#     """
#     Represents one entry in the registry for a single tool.
#     """
#     manifest: ToolManifest
#     location: str
#     added: str
#     source: str
#     dir: str
#     active: bool
#     branch: Optional[str] = None
#     auto_sync: bool = False


class RegistryManager:
    """
    Minimal example of a registry manager that loads/saves a JSON dictionary.
    Each entry in the registry is keyed by the tool's 'command' or unique name.
    """

    def __init__(self, registry_file: Path):
        self.registry_file = registry_file
        self.registry: Dict[str, Dict[str, Any]] = {}
        self.load_registry()

    def load_registry(self) -> None:
        if not self.registry_file.exists():
            logger.info(
                "Registry file not found: %s. Starting empty.", self.registry_file
            )
            self.registry = {}
            return
        try:
            with self.registry_file.open("r", encoding="utf-8") as f:
                self.registry = json.load(f)
        except Exception as e:
            logger.error("Failed to load registry %s: %s", self.registry_file, e)
            self.registry = {}

    def save_registry(self) -> None:
        try:
            with self.registry_file.open("w", encoding="utf-8") as f:
                json.dump(self.registry, f, indent=2)
            logger.debug("Saved registry with %d entries.", len(self.registry))
        except Exception as e:
            logger.error("Failed to save registry %s: %s", self.registry_file, e)

    def update_tool_in_registry(self, tool_name: str, data: any) -> None:
        """
        Add or overwrite the registry entry for a given tool_name.
        """
        self.registry[tool_name] = data

    def remove_tool_from_registry(self, tool_name: str) -> None:
        """
        Remove a tool entry by name.
        """
        if tool_name in self.registry:
            del self.registry[tool_name]


def update_tool_in_registry(
    tool_dir: Path,
    registry_file: Path,
    registry: dict,
    source: str,
    branch: str = None,
    auto_sync: bool = True,
) -> dict:
    """
    Update the tool registry with information from a manifest file.
    """
    manifest_path = tool_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Missing manifest.json in {tool_dir}.")

    validate_manifest(manifest_path)

    manifest = load_json(manifest_path)

    try:
        location = str(manifest_path.relative_to(registry_file.parent))
    except ValueError:
        location = str(manifest_path)

    location_parts = Path(location).parts
    second_position = (
        location_parts[1] if len(location_parts) > 1 else location_parts[0]
    )

    registry_entry = {
        "manifest": manifest,
        "location": location,
        "added": datetime.now(timezone.utc).isoformat(),
        "source": str(source),
        "dir": second_position,
        "active": True,
        "branch": branch,
        "auto_sync": auto_sync,
    }
    command = manifest.get("command")
    if not command:
        raise KeyError(f"'command' key is missing in manifest: {manifest_path}")
    registry[command] = registry_entry
    return registry


def update_registry_with_workspace(
    registry_file: Path,
    registry: dict,
    workspace_file: Path,
    workspace_dir: Path,
    auto_sync: bool = True,
) -> dict:
    """
    Update the workspace registry with information from the workspace.json file.
    """
    if not workspace_file.exists():
        logger.info("No workspace.json found in %s.", workspace_dir)
        return registry

    manifest = load_json(workspace_file)

    try:
        location = str(workspace_file.relative_to(registry_file.parent))
    except ValueError:
        location = str(workspace_file)

    location_parts = Path(location).parts
    second_position = (
        location_parts[1] if len(location_parts) > 1 else location_parts[0]
    )

    registry_entry = {
        "manifest": manifest,
        "location": location,
        "added": datetime.now(timezone.utc).isoformat(),
        "source": str(workspace_dir),
        "dir": second_position,
        "active": True,
        "branch": None,
        "auto_sync": auto_sync,
    }
    command = "workspace"
    registry[command] = registry_entry
    return registry
