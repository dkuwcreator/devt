import argparse
from dataclasses import dataclass
import json
import logging
import os
import re
import shlex
import shutil
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import subprocess
from typing import Any, Dict, List, Optional, Tuple, Union

from git import Repo
import requests
import typer
from jsonschema import validate, ValidationError
import yaml

from config import (
    REGISTRY_FILE_NAME,
    SUBPROCESS_ALLOWED_KEYS,
    USER_REGISTRY_DIR,
    WORKSPACE_APP_DIR,
    WORKSPACE_FILE_NAME,
    WORKSPACE_REGISTRY_DIR,
)
from utils import get_execute_args, load_json, merge_configs, on_exc, save_json

logger = logging.getLogger(__name__)

IS_WINDOWS = os.name == "nt"
IS_POSIX = not IS_WINDOWS
CURRENT_OS = "posix" if IS_POSIX else "windows"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


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
    global_dict = {
        k: v for k, v in manifest_data.items() if k in SUBPROCESS_ALLOWED_KEYS
    }
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


def default_shell_prefix(command) -> List[str]:
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

    def __init__(
        self,
        args: str,
        shell: str = None,
        cwd: Path = ".",
        env: dict[str, str] = None,
        **kwargs,
    ):
        self.args = args
        self.shell = shell
        self.cwd = cwd
        self.env = env or {}
        self.kwargs = {k: v for k, v in kwargs.items() if k in SUBPROCESS_ALLOWED_KEYS}

    def _apply_cwd(self, base_dir: Path) -> str:
        """Resolve and apply the 'cwd' key if present."""
        final_cwd = resolve_rel_path(base_dir, self.cwd)

        print(final_cwd)

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
        if isinstance(self.shell, str):
            # Keep the main command as a single token
            wrapper_tokens = to_tokens(self.shell, posix=IS_POSIX, split=True)
            main_token = self.args if isinstance(self.args, str) else " ".join(self.args)
            final_tokens = wrapper_tokens + [main_token]
        else:
            # Split the main command
            main_tokens = to_tokens(self.args, posix=IS_POSIX, split=True)
            final_tokens = main_tokens

        # Reassemble tokens into a shell-ready command string
        return self._join_args(final_tokens)

    def _prepare_args_with_default_shell(
        self,
    ) -> str:
        """
        Build the final args string, applying shell wrapper if needed,
        and construct a properly formatted shell command string.
        """
        final_tokens = default_shell_prefix(self.args)

        # Reassemble tokens into a shell-ready command string
        return self._join_args(final_tokens)

    def _join_args(self, final_tokens: List[str]) -> str:
        """Join the arguments into a single string."""
        return (
            subprocess.list2cmdline(final_tokens)
            if IS_WINDOWS
            else shlex.join(final_tokens)
        )

    def to_subprocess_args(self, base_dir: Path, extra_args: List[str] = None, **kwargs) -> Dict[str, Any]:
        """
        Prepare the arguments for subprocess.run(), merging in the environment
        and working directory if present.
        """
        final_cwd = self._apply_cwd(base_dir)
        final_env = self._apply_env()
        final_args = self._get_args_base()

        if needs_shell_fallback(final_args):
            final_args = self._prepare_args_with_default_shell()

        if extra_args:
            extra_tokens = to_tokens(extra_args, posix=IS_POSIX, split=True)
            final_args += " " + self._join_args(extra_tokens)

        return {
            "args": final_args,
            "shell": True,
            "cwd": final_cwd,
            "env": final_env,
            **self.kwargs,
            **kwargs,
        }

    def to_dict(self) -> dict:
        return {
            "args": self.args,
            "shell": self.shell,
            "cwd": str(self.cwd),
            "env": self.env,
            **self.kwargs,
        }

    def __str__(self):
        return json.dumps(self.to_dict(), indent=4)


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
        print(command)
        print(script_name)
        print(script)
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO scripts VALUES (?, ?, ?, ?, ?, ?, ?)
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
            return Script(
                row[2], row[5], Path(row[3]), json.loads(row[4]), **json.loads(row[6])
            )
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

    def update_script(self, command, script_name, script: Script):
        with self.conn:
            self.conn.execute(
                """
                UPDATE scripts
                SET args = ?,
                    cwd = ?,
                    env = ?,
                    shell = ?,
                    kwargs = ?
                WHERE command = ? AND script_name = ?
            """,
                (
                    script.args,
                    str(script.cwd),
                    json.dumps(script.env),
                    script.shell,
                    json.dumps(script.kwargs),
                    command,
                    script_name,
                ),
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

    def update_package(self, command, name, description, location, dependencies):
        with self.conn:
            self.conn.execute(
                """
                UPDATE packages
                SET name = ?,
                    description = ?,
                    location = ?,
                    dependencies = ?,
                    last_update = ?
                WHERE command = ?
            """,
                (name, description, location, dependencies, now(), command),
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

    def __str__(self):
        scripts_str = "\n".join(
            f"    {name}: {script}" for name, script in self.scripts.items()
        )
        dependencies_str = json.dumps(self.dependencies, indent=4)
        return (
            f"ToolPackage(\n"
            f"  name={self.name},\n"
            f"  description={self.description},\n"
            f"  command={self.command},\n"
            f"  scripts={{\n{scripts_str}\n  }},\n"
            f"  location={self.location},\n"
            f"  dependencies={dependencies_str},\n"
            f"  install_date={self.install_date},\n"
            f"  last_update={self.last_update}\n"
            f")"
        )


class PackageBuilder:
    def __init__(self, package_path: Path):
        self.manifest_path = self.find_manifest(package_path)
        self.location = package_path
        self.manifest = self._get_manifest(self.manifest_path)
        self.scripts = self._get_all_scripts(self.manifest)

    def find_manifest(self, package_path: Path) -> Path:
        manifest_path = find_file_type("manifest", package_path)
        if not manifest_path:
            raise FileNotFoundError("Manifest file not found.")
        return manifest_path

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
            return Script(**merge_configs(base_config, {"args": script_entry}))

        # If OS-specific command or dict is present, merge accordingly
        if script_entry and CURRENT_OS in script_entry:
            os_specific = script_entry[CURRENT_OS]
            if isinstance(os_specific, (str, list)):
                return Script(
                    **merge_configs(base_config, script_entry, {"args": os_specific})
                )
            if isinstance(os_specific, dict):
                return Script(**merge_configs(base_config, script_entry, os_specific))

        raise ValueError(f"Script '{script_key}' not found in the manifest.")

    def _get_all_scripts(self, manifest: dict) -> Dict[str, Script]:
        scripts = get_execute_args(manifest)
        script_names = set(scripts.keys()) | set(scripts.get(CURRENT_OS, {}).keys())
        return {
            script_key: self._get_script_entry(scripts, script_key)
            for script_key in script_names
            if script_key not in ("posix", "windows", *SUBPROCESS_ALLOWED_KEYS)
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


class PackageManager:
    def __init__(self, registry: Registry):
        self.registry = registry

    def import_package(self, manifest_path: Path):
        package_dir = self.move_package_to_registry(manifest_path.parent)
        package = PackageBuilder(package_dir).build_package()
        try:
            self.registry.add_package(
                package.command,
                package.name,
                package.description,
                str(package.location),
                json.dumps(package.dependencies),
            )
        except sqlite3.IntegrityError:
            logger.error("Package already exists in the registry.")
            return
        for script_name, script in package.scripts.items():
            self.registry.add_script(package.command, script_name, script)

    def move_package_to_registry(self, package_dir: Path) -> Path:
        registry_package_dir = self.registry.registry_dir / "tools" / package_dir.name
        if registry_package_dir.exists():
            shutil.rmtree(registry_package_dir)
        shutil.copytree(package_dir, registry_package_dir)
        return registry_package_dir

    def list_packages(self):
        return self.registry.list_packages()

    def remove_package(self, command: str):
        self.registry.remove_package(command)
        scripts = self.registry.list_scripts(command)
        for script in scripts:
            self.registry.remove_script(command, script)

    def show_package(self, command: str):
        package = self.registry.get_package(command)
        if not package:
            logger.error("Package not found in the registry.")
            return
        scripts = self.registry.list_scripts(command)
        script_objects = {
            script: self.registry.get_script(command, script) for script in scripts
        }
        return ToolPackage(
            package[1],
            package[2],
            package[0],
            script_objects,
            Path(package[3]),
            json.loads(package[4]),
            package[5],
            package[6],
        )

    def get_base_dir(self, command: str):
        return self.registry.registry_dir / "tools" / command

    def run_script(self, command: str, script_name: str, **kwargs):
        script = self.registry.get_script(command, script_name)
        if not script:
            logger.error("Script not found in the registry.")
            return
        args = script.to_subprocess_args(self.get_base_dir(command), **kwargs)
        logger.info("Running script: %s %s", args, kwargs)
        try:
            subprocess.run(args)
        except subprocess.CalledProcessError as e:
            logger.error("Error running script: %s", e)

    def update_package(self, manifest_path: Path):
        package_dir = self.move_package_to_registry(manifest_path.parent)
        package = PackageBuilder(package_dir).build_package()
        self.registry.update_package(
            package.command,
            package.name,
            package.description,
            str(package.location),
            json.dumps(package.dependencies),
        )
        for script_name, script in package.scripts.items():
            self.registry.update_script(package.command, script_name, script)


def main():
    registry = Registry()
    manager = PackageManager(registry)

    parser = argparse.ArgumentParser(description="Package Manager Tool")
    parser.add_argument(
        "command", choices=["import", "export", "list", "remove", "show", "run", "update"]
    )
    parser.add_argument("--source", help="Path to the package manifest file")
    parser.add_argument("--name", help="Name of the package")
    parser.add_argument("--script", help="Name of the script to run")

    args = parser.parse_args()

    if args.command == "import":
        manager.import_package(Path(args.source))
    elif args.command == "list":
        print(manager.registry.list_packages())
    elif args.command == "remove":
        manager.remove_package(args.name)
    elif args.command == "show":
        print(manager.show_package(args.name))
    elif args.command == "run":
        manager.run_script(args.name, args.script)
    elif args.command == "update":
        manager.update_package(Path(args.source))


if __name__ == "__main__":
    main()
