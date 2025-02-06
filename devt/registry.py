# devt/registry.py
import json
from pathlib import Path
from datetime import datetime, timezone
import logging
from devt.utils import load_json, save_json

from .manifest import validate_manifest

logger = logging.getLogger("devt")

def update_tool_in_registry(tool_dir: Path, registry_file: Path, registry: dict, source: str, branch: str = None, auto_sync: bool = True) -> dict:
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
    second_position = location_parts[1] if len(location_parts) > 1 else location_parts[0]

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

def update_registry_with_workspace(registry_file: Path, registry: dict, workspace_file: Path, workspace_dir: Path, auto_sync: bool = True) -> dict:
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
    second_position = location_parts[1] if len(location_parts) > 1 else location_parts[0]

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
