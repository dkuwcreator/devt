# devt/utils.py
import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlparse

import yaml

logger = logging.getLogger(__name__)


def load_json(file_path: Path) -> dict:
    try:
        with open(file_path, "r") as file:
            return json.load(file)
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError as e:
        logger.error(f"Error decoding JSON in {file_path}: {e}")
        return {}


def save_json(file_path: Path, data: dict):
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(file_path, "w") as file:
        json.dump(data, file, indent=4)


def find_file_type(file_type: str, current_dir: Path = Path.cwd()) -> Optional[Path]:
    """
    Check if a workspace file (.json, .cjson, .yaml, .yml) exists in the current directory.
    Returns the path to the workspace file if found, otherwise None.
    """
    for ext in ["yaml", "yml", "json", "cjson"]:
        workspace_file = current_dir / f"{file_type}.{ext}"
        if workspace_file.exists():
            return workspace_file
    return None


def load_manifest(manifest_path: Path) -> Dict[str, Any]:
    """Load and parse the manifest file (YAML or JSON)."""
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Manifest file not found: {manifest_path}")

    with manifest_path.open("r", encoding="utf-8") as f:
        if manifest_path.suffix in [".yaml", ".yml"]:
            data = yaml.safe_load(f)
        elif manifest_path.suffix in [".json", ".cjson"]:
            data = json.load(f)
        else:
            raise ValueError(f"Unsupported file extension: {manifest_path.suffix}")

        if not data:
            raise ValueError(f"Manifest file is empty or invalid: {manifest_path}")
    return data


def merge_configs(*configs: Dict[str, Any]) -> Dict[str, Any]:
    """
    Merge multiple dictionaries in order, where later values overwrite earlier ones.
    If both values for a key are dictionaries, merge them shallowly.
    """
    result: Dict[str, Any] = {}
    for config in configs:
        if not config:
            continue
        for key, value in config.items():
            if (
                key in result
                and isinstance(result[key], dict)
                and isinstance(value, dict)
            ):
                merged = result[key].copy()
                merged.update(value)
                result[key] = merged
            else:
                result[key] = value
    return result


def determine_source(source: str) -> str:
    parsed_url = urlparse(source)
    if parsed_url.scheme and parsed_url.netloc:
        return "repo"
    logger.info("Source is not a URL. Checking if it's a local path...")
    source_path = Path(source)
    if source_path.exists():
        return "local"
    raise FileNotFoundError(f"Error: The source path '{source}' does not exist.")


def on_exc(func, path, exc):
    import os

    if isinstance(exc, PermissionError):
        os.chmod(path, 0o777)  # Grant write permissions
        func(path)  # Retry the operation
    else:
        raise exc  # Re-raise any other exception
