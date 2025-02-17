from dataclasses import dataclass
import json
import logging
import os
import re
import shutil
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from typing import Any, Dict, List, Optional, Tuple, Union

from git import Repo
import requests
import typer
from jsonschema import validate, ValidationError

from devt.config import (
    REGISTRY_FILE_NAME,
    SUBPROCESS_ALLOWED_KEYS,
    USER_REGISTRY_DIR,
    WORKSPACE_APP_DIR,
    WORKSPACE_FILE_NAME,
    WORKSPACE_REGISTRY_DIR,
)
from devt.executor import CURRENT_OS
from devt.utils import get_execute_args, load_json, merge_configs, on_exc, save_json

logger = logging.getLogger(__name__)


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


MANIFEST_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "command": {"type": "string"},
        "scripts": {
            "type": "object",
            "properties": {
                "install": {"type": "string"},
                "windows": {"type": "object"},
                "posix": {"type": "object"},
            },
            "additionalProperties": False,
        },
    },
    "required": ["name", "command", "scripts"],
    "additionalProperties": False,
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


def load_yaml(file_path: Path) -> dict:
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            return yaml.safe_load(file)
    except FileNotFoundError:
        logger.error(f"File not found: {file_path}")
        return {}
    except yaml.YAMLError as e:
        logger.error(f"Error decoding YAML in {file_path}: {e}")
        return {}


def save_yaml(file_path: Path, data: dict) -> None:
    file_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(file_path, "w", encoding="utf-8") as file:
            yaml.dump(data, file)
    except IOError as e:
        logger.error(f"Error writing YAML to {file_path}: {e}")


def find_file_type(file_type: str, current_dir: Path = Path.cwd()) -> Optional[Path]:
    """
    Check if a workspace file (.json, .cjson, .yaml, .yml) exists in the current directory.
    Returns the path to the workspace file if found, otherwise None.
    """
    logger.info("Looking for %s file in %s...", file_type, current_dir)
    for ext in ["yaml", "yml", "json", "cjson"]:
        workspace_file = current_dir / f"{file_type}.{ext}"
        if workspace_file.exists():
            return workspace_file
    logger.warning("No %s file found in %s.", file_type, current_dir)
    return None


def load_manifest(manifest_path: Path) -> Dict[str, Any]:
    """Load and parse the manifest file (YAML or JSON)."""
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Manifest file not found: {manifest_path}")

    if manifest_path.suffix in [".yaml", ".yml"]:
        return load_yaml(manifest_path)
    if manifest_path.suffix in [".json", ".cjson"]:
        return load_json(manifest_path)

    raise ValueError(f"Unsupported file extension: {manifest_path.suffix}")


def export_manifest(manifest: dict, dest_path: Path, file_type: str = "yaml") -> None:
    """Export a manifest to a file."""
    if file_type == "yaml":
        save_yaml(dest_path, manifest)
    elif file_type == "json":
        save_json(dest_path, manifest)
    else:
        raise ValueError(f"Unsupported file type: {file_type}")

    logger.info("Manifest exported to %s", dest_path)


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


def get_execute_args(manifest_data: dict) -> dict:
    """Get the arguments for executing a script."""
    global_dict = {k: v for k, v in manifest_data.items() if k != "scripts"}
    scripts_dict = manifest_data.get("scripts", {})
    if not scripts_dict:
        raise ValueError("No scripts found in the manifest file.")
    return merge_configs(global_dict, scripts_dict)


def needs_shell_fallback(args: Union[str, List[str]]) -> bool:
    if isinstance(args, list):
        maybe_first_arg = args[0]
    else:
        maybe_first_arg = shlex.split(args, posix=IS_POSIX)[0]

    return shutil.which(maybe_first_arg) is None


def default_shell_prefix(command) -> str:
    """Return the default shell prefix for the current OS."""

    if os.name == "nt":
        if shutil.which("pwsh"):
            return ["pwsh", "-Command", f"& {command}"]
        else:
            return ["powershell", "-Command", f"& {command}"]
    else:
        return ["bash", "-c", command]


def to_tokens(
    val: Union[str, List[str]], *, posix: bool, split: bool = True
) -> List[str]:
    """
    Normalize a value into a list of tokens.

    If split is True and the value is a string, it will be split with shlex.
    If split is False, the string will be returned as a single-item list.
    """
    if val is None:
        return []
    if isinstance(val, list):
        return val
    return shlex.split(val, posix=posix) if split else [val]


@dataclass
class Script:
    args: str
    shell: str = None
    cwd: Path = "."
    env: dict[str, str] = None
    kwargs: dict[str, Any] = None

    def __post_init__(self):
        if self.kwargs is None:
            self.kwargs = {}
        # Filter kwargs to only include allowed keys
        self.kwargs = {
            k: v for k, v in self.kwargs.items() if k in SUBPROCESS_ALLOWED_KEYS
        }

    def _apply_cwd(self, base_dir: Path) -> str:
        """Resolve and apply the 'cwd' key if present."""
        final_cwd = resolve_rel_path(base_dir, self.cwd)

        if not final_cwd.is_dir():
            raise FileNotFoundError(f"Working directory '{final_cwd}' does not exist.")

        return str(final_cwd)

    def _apply_env(self) -> dict[str, str]:
        """Merge environment variables if 'env' key is present."""
        if self.env:
            return {**os.environ, **self.env}
        return None

    def _get_args_base(
        self,
    ) -> str:
        """
        Build the final args string, applying shell wrapper if needed,
        and construct a properly formatted shell command string.
        """
        if self.shell:
            # Keep the main command as a single token
            wrapper_tokens = to_tokens(self.shell, posix=IS_POSIX, split=True)
            main_token = self.args if isinstance(self.args, str) else " ".join(self.args)
            final_tokens = wrapper_tokens + [main_token]
        else:
            # Split the main command
            main_tokens = to_tokens(self.args, posix=IS_POSIX, split=True)
            final_tokens = main_tokens

        # Reassemble tokens into a shell-ready command string
        return (
            subprocess.list2cmdline(final_tokens)
            if IS_WINDOWS
            else shlex.join(final_tokens)
        )

    def _prepare_args_with_default_shell(
        self,
    ) -> str:
        """
        Build the final args string, applying shell wrapper if needed,
        and construct a properly formatted shell command string.
        """
        final_tokens = default_shell_prefix(self.args)

        # Reassemble tokens into a shell-ready command string
        return (
            subprocess.list2cmdline(final_tokens)
            if IS_WINDOWS
            else shlex.join(final_tokens)
        )

    def to_dict(self, base_dir: Path) -> dict:
        """
        Convert the script configuration to a dictionary suitable for subprocess.run().
        """
        # Normalize extra arguments (always split them)
        if not self.shell and needs_shell_fallback(self.args):
            args = self._prepare_args_with_default_shell()
        else:
            args = self._get_args_base()
        return {
            "args": args,
            "cwd": self._apply_cwd(base_dir),
            "env": self._apply_env(),
            "shell": True,
            **self.kwargs,
        }

    def run(self, base_dir: Path) -> int:
        """
        Run the script with the given configuration.
        """
        script_dict = self.to_dict(base_dir)
        try:
            return subprocess.run(**script_dict).returncode
        except subprocess.CalledProcessError as e:
            raise CommandExecutionError(
                f"Error running command: {script_dict['args']}",
                e.returncode,
                e.stdout,
                e.stderr,
            )


@dataclass
class ToolPackage:
    name: str
    description: str
    command: str
    scripts: Dict[str, Script]
    location: Path
    dependencies: Dict[str, Any]
    install_date: str
    last_update: str


class PackageBuilder:
    def __init__(self, manifest_path: Path):
        self.manifest_path = manifest_path
        self.location = manifest_path.parent
        self.manifest = self._get_manifest(manifest_path)
        self.scripts = self._get_all_scripts(self.manifest)

    def _get_manifest(self, manifest_path: Path) -> Dict[str, Any]:
        manifest = load_manifest(manifest_path)
        if not validate_manifest(manifest):
            raise ValueError(f"Invalid manifest file: {manifest_path}")
        return manifest

    def _get_script_entry(self, scripts: Dict[str, Any], script_key: str) -> Script:
        """
        Retrieve the script configuration for the specified script key,
        merging in OS-specific configurations when available.
        """
        base_config = dict(scripts)

        # If OS-specific settings exist for the script_key, merge them
        if CURRENT_OS in base_config and script_key in base_config[CURRENT_OS]:
            base_config = merge_configs(base_config, base_config[CURRENT_OS])

        script_entry = base_config.get(script_key)

        # If script_entry is a direct command (string or list), just merge
        if isinstance(script_entry, (str, list)):
            return merge_configs(base_config, {"args": script_entry})

        # If OS-specific command or dict is present, merge accordingly
        if script_entry and CURRENT_OS in script_entry:
            os_specific = script_entry[CURRENT_OS]
            if isinstance(os_specific, (str, list)):
                return merge_configs(base_config, script_entry, {"args": os_specific})
            if isinstance(os_specific, dict):
                return merge_configs(base_config, script_entry, os_specific)

        raise ValueError(f"Script '{script_key}' not found in the manifest.")

    def _get_all_scripts(self, manifest: dict) -> Dict[str, Script]:
        scripts = get_execute_args(manifest)
        script_names = set(scripts.keys()) | set(scripts.get(CURRENT_OS, {}).keys())
        return {
            script_key: self._get_script_entry(scripts, script_key)
            for script_key in script_names
            if script_key not in ("posix", "windows")
        }

    def build_package(self) -> ToolPackage:
        return ToolPackage(
            self.manifest["name"],
            self.manifest["description"],
            self.manifest["command"],
            self.scripts,
            self.location,
            self.manifest.get("dependencies", {}),
            now(),
            now(),
        )


class Registry:
    def __init__(self, db_path=USER_REGISTRY_DIR):
        self.registry_dir = db_path
        self.conn = sqlite3.connect(db_path / "registry.db")
        self._create_tables()

    def _create_tables(self):
        with self.conn:
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS scripts (
                    command TEXT,
                    script_name TEXT,
                    args TEXT,
                    cwd TEXT,
                    env TEXT,
                    shell BOOLEAN,
                    kwargs TEXT,
                    PRIMARY KEY (command, script_name)
                )
                """
            )
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS packages (
                    command TEXT PRIMARY KEY,
                    name TEXT,
                    description TEXT,
                    location TEXT,
                    dependencies TEXT,
                    install_date TEXT,
                    last_update TEXT
                )
                """
            )

    def add_script(self, command, script_name, script: Script):
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO scripts VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    command,
                    script_name,
                    script.args,
                    script.cwd,
                    json.dumps(script.env),
                    script.shell,
                    json.dumps(script.kwargs),
                ),
            )

    def get_script(self, command, script_name):
        cursor = self.conn.execute(
            "SELECT * FROM scripts WHERE command = ? AND script_name = ?",
            (command, script_name),
        )
        row = cursor.fetchone()
        if row:
            return Script(*row[2:])
        return None

    def list_scripts(self, command):
        cursor = self.conn.execute(
            "SELECT script_name FROM scripts WHERE command = ?", (command,)
        )
        return [row[0] for row in cursor.fetchall()]

    def remove_script(self, command, script_name):
        with self.conn:
            self.conn.execute(
                "DELETE FROM scripts WHERE command = ? AND script_name = ?",
                (command, script_name),
            )

    def add_package(self, command, name, description, location, dependencies):
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO packages VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (command, name, description, location, dependencies, now(), now()),
            )

    def get_package(self, command):
        cursor = self.conn.execute(
            "SELECT * FROM packages WHERE command = ?", (command,)
        )
        return cursor.fetchone()

    def list_packages(self):
        cursor = self.conn.execute("SELECT command FROM packages")
        return [row[0] for row in cursor.fetchall()]

    def remove_package(self, command):
        with self.conn:
            self.conn.execute("DELETE FROM packages WHERE command = ?", (command,))


class PackageManager:
    def __init__(self, registry: Registry):
        self.registry = registry

    def build_package(self, manifest_path: Path) -> ToolPackage:
        manifest = load_manifest(manifest_path)
        manifest = validate_manifest(manifest)
        # Get the base directory of the manifest
        base_dir = manifest_path.parent
        # Resolve the location of the tool package

    def add_package(self, package: ToolPackage):
        self.registry.add_package(
            package.command,
            package.name,
            package.description,
            str(package.location),
            json.dumps(package.dependencies),
        )

    def get_package(self, command):
        package = self.registry.get_package(command)
        if package:
            return ToolPackage(
                package[1],
                package[2],
                command,
                self._load_scripts(command),
                Path(package[3]),
                json.loads(package[4]),
                package[5],
                package[6],
            )
        return None

    def list_packages(self):
        return self.registry.list_packages()

    def remove_package(self, command):
        self.registry.remove_package(command)

    def _load_scripts(self, command):
        scripts = self.registry.list_scripts(command)
        return {script: self.registry.get_script(command, script) for script in scripts}
