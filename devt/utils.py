#!/usr/bin/env python3
"""
devt/utils.py

Utility functions for the application.

Provides functions for loading and saving JSON files, setting user environment variables,
resolving relative paths, and determining the source type of a path.
"""

import json
import logging
import os
from pathlib import Path
import platform
from typing import Any, Dict, List, Optional, Tuple, Union
from urllib.parse import urlparse

from jsonschema import ValidationError, validate
import typer
import yaml

from devt.constants import USER_APP_DIR, WORKSPACE_APP_DIR

# from InquirerPy import inquirer

logger = logging.getLogger(__name__)


def scopes_to_registry_dirs() -> dict:
    """
    Returns the appropriate registry directory based on the specified scope.
    If WORKSPACE_APP_DIR does not exist, the workspace entry is omitted.
    """
    registry_dirs = {"user": USER_APP_DIR}
    if WORKSPACE_APP_DIR.exists():
        registry_dirs["workspace"] = WORKSPACE_APP_DIR
    return registry_dirs


def set_user_environment_var(name: str, value: str) -> None:
    """
    Persists a user environment variable across sessions in a cross-platform way.
    """
    system = platform.system()

    try:
        if system == "Windows":
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_SET_VALUE
            ) as key:
                winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
            logger.debug("Set user environment variable on Windows: %s=%s", name, value)

        elif system in ["Linux", "Darwin"]:  # Darwin is macOS
            bashrc_path = os.path.expanduser("~/.bashrc")
            zshrc_path = os.path.expanduser("~/.zshrc")
            export_command = f'export {name}="{value}"\n'

            # Export variable in the shell profile, but only if not already present
            for rc_path in [bashrc_path, zshrc_path]:
                if os.path.exists(rc_path):
                    with open(rc_path, "r") as f:
                        content = f.read()
                    if export_command.strip() not in content:
                        with open(rc_path, "a") as f:
                            f.write(export_command)

            # Also set it for the current session
            os.environ[name] = value

            logger.debug(
                "Set user environment variable on Linux/macOS: %s=%s", name, value
            )
        else:
            logger.warning(
                "Unsupported OS: %s. Cannot persist environment variable.", system
            )

    except Exception as e:
        logger.error("Failed to set user environment variable %s: %s", name, e)


def resolve_rel_path(base_dir: Path, rel_path: str) -> Path:
    """Resolve the relative path against the base directory."""
    resolved = (base_dir / Path(rel_path)).resolve()
    logger.debug("Resolved '%s' against '%s' to '%s'.", rel_path, base_dir, resolved)
    return resolved


def load_json(file_path: Path) -> dict:
    logger.debug("Loading JSON file: %s", file_path)
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            data = json.load(file)
            logger.debug("Successfully loaded JSON from: %s", file_path)
            return data
    except FileNotFoundError:
        logger.error("JSON file not found: %s", file_path)
        return {}
    except json.JSONDecodeError as e:
        logger.error("Error decoding JSON in %s: %s", file_path, e)
        return {}


def save_json(file_path: Path, data: dict, indent: Union[int, None] = 2) -> None:
    logger.debug("Saving JSON to file: %s", file_path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(file_path, "w", encoding="utf-8") as file:
            json.dump(data, file, indent=indent)
            logger.debug("JSON successfully saved to: %s", file_path)
    except IOError as e:
        logger.error("Error writing JSON to %s: %s", file_path, e)


def find_file_type(prefix: str, current_dir: Path = Path.cwd()) -> Optional[Path]:
    """
    Search for a file with the specified prefix and common file extensions (.json, .cjson, .yaml, .yml)
    in the provided directory.
    Returns the path to the file if found, otherwise None.
    """
    logger.debug("Searching for file with prefix '%s' in: %s", prefix, current_dir)
    for ext in ["yaml", "yml", "json", "cjson"]:
        candidate_file = current_dir / f"{prefix}.{ext}"
        logger.debug("Checking candidate: %s", candidate_file)
        if candidate_file.exists():
            logger.debug("Found candidate: %s", candidate_file)
            return candidate_file
    logger.warning("No file found for prefix '%s' in: %s", prefix, current_dir)
    return None


def load_manifest(manifest_path: Path) -> Dict[str, Any]:
    """Load and parse the manifest file (YAML or JSON)."""
    if not manifest_path.is_file():
        logger.debug(
            "Manifest path '%s' is not a file; searching for manifest.", manifest_path
        )
        manifest_path = find_file_type("manifest", manifest_path)
        if not manifest_path:
            logger.error("Manifest file not found in directory: %s", manifest_path)
            raise FileNotFoundError("Manifest file not found.")

    logger.debug("Loading manifest file: %s", manifest_path)
    with manifest_path.open("r", encoding="utf-8") as f:
        if manifest_path.suffix in [".yaml", ".yml"]:
            data = yaml.safe_load(f)
        elif manifest_path.suffix in [".json", ".cjson"]:
            data = json.load(f)
        else:
            logger.error("Unsupported file extension: %s", manifest_path.suffix)
            raise ValueError(f"Unsupported file extension: {manifest_path.suffix}")

        if not data:
            logger.error("Manifest file is empty or invalid: %s", manifest_path)
            raise ValueError(f"Manifest file is empty or invalid: {manifest_path}")
    logger.debug("Manifest loaded from: %s", manifest_path)
    return data


def save_manifest(manifest_dir: Path, data: Dict[str, Any], type: str = "yaml") -> None:
    """Save the manifest data to a file (YAML or JSON)."""
    if type not in ["yaml", "json"]:
        logger.error("Unsupported file type specified for manifest saving: %s", type)
        raise ValueError(f"Unsupported file type: {type}")
    manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest_file = manifest_dir / f"manifest.{type}"
    logger.debug("Saving manifest to: %s", manifest_file)
    with manifest_file.open("w", encoding="utf-8") as f:
        if type == "yaml":
            yaml.dump(data, f, default_flow_style=False)
        elif type == "json":
            json.dump(data, f, indent=2)
    logger.debug("Manifest saved to: %s", manifest_file)


def find_recursive_manifest_files(
    current_dir: Path = Path.cwd(), max_depth: int = 3
) -> List[Path]:
    """
    Recursively search for manifest files in the current directory and its subdirectories up to a specified depth.
    Returns a list of paths to the manifest files found.
    """
    logger.debug(
        "Recursively searching for manifest files in %s (max depth %d)",
        current_dir,
        max_depth,
    )
    manifest_files = []
    for path in current_dir.rglob("*"):
        if path.is_file() and path.name in [
            "manifest.yaml",
            "manifest.yml",
            "manifest.json",
        ]:
            if len(path.relative_to(current_dir).parts) <= max_depth:
                logger.debug("Found manifest file: %s", path)
                manifest_files.append(path)
    logger.info("Total manifest files found: %d", len(manifest_files))
    return manifest_files


def merge_configs(*configs: Dict[str, Any]) -> Dict[str, Any]:
    """
    Merge multiple dictionaries in order, where later values overwrite earlier ones.
    If both values for a key are dictionaries, merge them shallowly.
    """
    logger.debug("Merging %d configuration sources.", len(configs))
    result: Dict[str, Any] = {}
    for config in configs:
        if not config:
            logger.debug("Skipping empty configuration source.")
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
                logger.debug("Merged dictionaries for key '%s'.", key)
            else:
                result[key] = value
                logger.debug("Set config key '%s' to '%s'.", key, value)
    return result


def get_execute_args(manifest_path: Path) -> Tuple[Path, Dict[str, Any]]:
    """Get the arguments for executing a script."""
    logger.debug("Extracting execution arguments from manifest: %s", manifest_path)
    base_dir = manifest_path.parent
    manifest_data = load_manifest(manifest_path)
    global_dict = {k: v for k, v in manifest_data.items() if k != "scripts"}
    scripts_dict = manifest_data.get("scripts") or {}
    if not scripts_dict:
        logger.error("No scripts found in the manifest: %s", manifest_path)
        raise ValueError("No scripts found in the manifest file.")
    merged = merge_configs(global_dict, scripts_dict)
    logger.debug("Execution arguments: %s", merged)
    return base_dir, merged


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


def determine_source(source: str) -> str:
    logger.debug("Determining source type for: %s", source)
    parsed_url = urlparse(source)
    if parsed_url.scheme and parsed_url.netloc:
        logger.debug("Source determined to be URL: %s", source)
        return "repo"
    source_path = Path(source)
    if source_path.exists():
        logger.debug("Local source exists: %s", source)
        return "local"
    logger.error("Source path does not exist: %s", source)
    raise FileNotFoundError(f"Error: The source path '{source}' does not exist.")


def on_exc(func, path, exc):
    import os

    logger.debug("Handling exception for path: %s; Exception: %s", path, exc)
    if isinstance(exc, PermissionError):
        os.chmod(path, 0o777)
        logger.debug("Permission error handled; changed permissions for: %s", path)
        func(path)
    else:
        logger.exception("Unhandled exception for path: %s", path)
        raise exc


MANIFEST_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "command": {"type": "string"},
        "scripts": {"type": "object"},
    },
    "required": ["name", "command", "scripts"],
}


def validate_manifest(manifest: dict) -> bool:
    logger.debug("Validating manifest: %s", manifest)
    try:
        validate(instance=manifest, schema=MANIFEST_SCHEMA)
        logger.debug("Manifest validated successfully.")
        return True
    except ValidationError as e:
        logger.error("Manifest validation error: %s", e)
        return False


def print_table(
    headers: List[str], rows: List[List[str]], max_field_length: int = 30
) -> List[str]:
    logger.info("Printing table with headers: %s", headers)

    def truncate_field(text: str, width: int) -> str:
        if len(text) > width:
            return text[: max(width - 3, 0)] + "..." if width > 3 else text[:width]
        return text

    # Calculate column widths but limit them to max_field_length
    col_widths = [
        min(
            max(len(headers[i]), max((len(row[i]) for row in rows), default=0)),
            max_field_length,
        )
        for i in range(len(headers))
    ]

    # Build the formatted header line with truncation if needed
    separator = "+" + "+".join("-" * (w + 2) for w in col_widths) + "+"
    header_line = (
        "|"
        + "|".join(
            f" {truncate_field(headers[i], col_widths[i]).ljust(col_widths[i])} "
            for i in range(len(headers))
        )
        + "|"
    )

    typer.echo(separator)
    typer.echo(header_line)
    typer.echo(separator)

    for row in rows:
        row_line = (
            "|"
            + "|".join(
                f" {truncate_field(row[i], col_widths[i]).ljust(col_widths[i])} "
                for i in range(len(row))
            )
            + "|"
        )
        typer.echo(row_line)

    typer.echo(separator)
    logger.info("Table printed successfully.")

    # Use select_row to let the user choose a row after printing the table
    # selected = select_row(headers, rows)
    # logger.info("Row selected from print_table: %s", selected)
    # return selected


# def select_row(headers: List[str], rows: List[List[str]]) -> List[str]:
#     """
#     Presents a searchable list of rows using InquirerPy.
#     Each row is displayed as a string combining its columns.
#     When a row is selected, the original row list is returned.
#     """
#     # Build choices: Each choice shows a row as a joined string, and its value is the row list.
#     choices = [{"name": " | ".join(row), "value": row} for row in rows]

#     # Use fuzzy search to allow searching for specific rows.
#     selected_row = inquirer.fuzzy(
#         message="Search and select a row:",
#         choices=choices,
#     ).execute()

#     logger.info("Selected row: %s", selected_row)
#     return selected_row
