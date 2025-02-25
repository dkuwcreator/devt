# devt/utils.py
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
from urllib.parse import urlparse

from jsonschema import ValidationError, validate
import typer
import yaml

logger = logging.getLogger(__name__)


def resolve_rel_path(base_dir: Path, rel_path: str) -> Path:
    """Resolve the relative path against the base directory."""
    return (base_dir / Path(rel_path)).resolve()


def load_json(file_path: Path) -> dict:
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            return json.load(file)
    except FileNotFoundError:
        logger.error(f"File not found: {file_path}")
        return {}
    except json.JSONDecodeError as e:
        logger.error(f"Error decoding JSON in {file_path}: {e}")
        return {}


def save_json(file_path: Path, data: dict, indent: Union[int, None] = 2) -> None:
    file_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(file_path, "w", encoding="utf-8") as file:
            json.dump(data, file, indent=indent)
    except IOError as e:
        logger.error(f"Error writing JSON to {file_path}: {e}")


def find_file_type(prefix: str, current_dir: Path = Path.cwd()) -> Optional[Path]:
    """
    Search for a file with the specified prefix and common file extensions (.json, .cjson, .yaml, .yml)
    in the provided directory.
    Returns the path to the file if found, otherwise None.
    """
    logger.info("Starting search in %s for file with prefix '%s'.", current_dir, prefix)
    for ext in ["yaml", "yml", "json", "cjson"]:
        candidate_file = current_dir / f"{prefix}.{ext}"
        logger.debug("Checking candidate file: %s", candidate_file)
        if candidate_file.exists():
            logger.info("File found: %s", candidate_file)
            return candidate_file
        else:
            logger.debug("File does not exist: %s", candidate_file)
    logger.warning(
        "No file found for prefix '%s' in directory %s.", prefix, current_dir
    )
    return None


def load_manifest(manifest_path: Path) -> Dict[str, Any]:
    """Load and parse the manifest file (YAML or JSON)."""
    if not manifest_path.is_file():
        manifest_path = find_file_type("manifest", manifest_path)
        if not manifest_path:
            raise FileNotFoundError("Manifest file not found.")

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


def save_manifest(manifest_dir: Path, data: Dict[str, Any], type: str = "yaml") -> None:
    """Save the manifest data to a file (YAML or JSON)."""
    if type not in ["yaml", "json"]:
        raise ValueError(f"Unsupported file type: {type}")
    manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest_file = manifest_dir / f"manifest.{type}"
    with manifest_file.open("w", encoding="utf-8") as f:
        if type == "yaml":
            yaml.dump(data, f, default_flow_style=False)
        elif type == "json":
            json.dump(data, f, indent=2)
        else:
            raise ValueError(f"Unsupported file type: {type}")


def find_recursive_manifest_files(
    current_dir: Path = Path.cwd(), max_depth: int = 3
) -> List[Path]:
    """
    Recursively search for manifest files in the current directory and its subdirectories up to a specified depth.
    Returns a list of paths to the manifest files found.
    """
    manifest_files = []
    for path in current_dir.rglob("*"):
        if path.is_file() and path.name in [
            "manifest.yaml",
            "manifest.yml",
            "manifest.json",
        ]:
            if len(path.relative_to(current_dir).parts) <= max_depth:
                manifest_files.append(path)
    return manifest_files


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


def get_execute_args(manifest_path: Path) -> Tuple[Path, Dict[str, Any]]:
    """Get the arguments for executing a script."""
    base_dir = manifest_path.parent
    manifest_data = load_manifest(manifest_path)
    global_dict = {k: v for k, v in manifest_data.items() if k != "scripts"}
    scripts_dict = manifest_data.get("scripts", {})
    if not scripts_dict:
        raise ValueError("No scripts found in the manifest file.")
    return base_dir, merge_configs(global_dict, scripts_dict)


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
    """
    Validate a manifest against the schema.
    """
    logger.info("Validating manifest: %s", manifest)
    try:
        validate(instance=manifest, schema=MANIFEST_SCHEMA)
        scripts = manifest.get("scripts", {})

        # Check for the presence of an install script (generic or shell-specific)
        install_present = (
            "install" in scripts
            or ("windows" in scripts and "install" in scripts["windows"])
            or ("posix" in scripts and "install" in scripts["posix"])
        )
        if not install_present:
            logger.error(f"Manifest scripts: {json.dumps(scripts, indent=4)}")
            return False

        return True

    except ValidationError as e:
        logger.error("Manifest validation error: %s", e)
        return False


def print_table(headers: List[str], rows: List[List[str]]) -> None:
    """Prints a formatted table given headers and row data."""
    col_widths = [
        max(len(headers[i]), max((len(row[i]) for row in rows), default=0))
        for i in range(len(headers))
    ]
    separator = "+" + "+".join("-" * (w + 2) for w in col_widths) + "+"
    header_line = (
        "|"
        + "|".join(f" {headers[i].ljust(col_widths[i])} " for i in range(len(headers)))
        + "|"
    )
    typer.echo(separator)
    typer.echo(header_line)
    typer.echo(separator)
    for row in rows:
        row_line = (
            "|"
            + "|".join(f" {row[i].ljust(col_widths[i])} " for i in range(len(row)))
            + "|"
        )
        typer.echo(row_line)
    typer.echo(separator)
