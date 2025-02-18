import os
import json
import shlex
import subprocess
import shutil
import logging
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional, Union
from dataclasses import dataclass, field

from executor import IS_WINDOWS, default_shell_prefix, needs_shell_fallback, to_tokens
from utils import find_file_type, load_manifest, validate_manifest

def now() -> str:
    return datetime.now().isoformat()

# ---------------------------
# Script Class
# ---------------------------
@dataclass
class Script:
    """
    A class representing a command (or script) defined in a package manifest.
    """
    args: Union[str, List[str]]
    shell: Optional[str] = None
    cwd: Path = Path(".")
    env: Dict[str, Any] = field(default_factory=dict)
    kwargs: Dict[str, Any] = field(default_factory=dict)

    def build_command_tokens(self) -> List[str]:
        if self.shell:
            wrapper_tokens = to_tokens(self.shell)
            # If the main command is provided as a list, join it into one token;
            # otherwise, use it as-is.
            main_command = self.args if isinstance(self.args, str) else " ".join(self.args)
            tokens = wrapper_tokens + [main_command]
        else:
            tokens = to_tokens(self.args)
        return tokens

    def assemble_command(self) -> str:
        tokens = self.build_command_tokens()
        if needs_shell_fallback(tokens):
            # When fallback is needed, join the tokens into a command string
            # and then wrap them with the default shell prefix.
            command_str = shlex.join(tokens) if not IS_WINDOWS else subprocess.list2cmdline(tokens)
            tokens = default_shell_prefix(command_str)
        return shlex.join(tokens) if not IS_WINDOWS else subprocess.list2cmdline(tokens)

    def resolve_cwd(self, base_dir: Path) -> Path:
        resolved = self.cwd if self.cwd.is_absolute() else base_dir / self.cwd
        if not resolved.is_dir():
            raise FileNotFoundError(f"Working directory '{resolved}' does not exist.")
        return resolved

    def prepare_subprocess_args(self, base_dir: Path, extra_args: Optional[List[str]] = None) -> Dict[str, Any]:
        command = self.assemble_command()
        if extra_args:
            extra_tokens = to_tokens(extra_args)
            extra_str = shlex.join(extra_tokens) if not IS_WINDOWS else subprocess.list2cmdline(extra_tokens)
            command += " " + extra_str
        env = {**os.environ, **self.env} if self.env else None
        return {
            "args": command,
            "shell": True,
            "cwd": str(self.resolve_cwd(base_dir)),
            "env": env,
            **self.kwargs,
        }

# ---------------------------
# ToolPackage Dataclass
# ---------------------------
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

# ---------------------------
# PackageBuilder Class
# ---------------------------
class PackageBuilder:
    """
    Processes a package directory by locating its manifest,
    validating it, and building ToolPackage and Script objects.
    """
    def __init__(self, package_path: Path):
        self.package_path = package_path
        self.manifest_path = self.find_manifest(package_path)
        self.manifest = self._load_manifest(self.manifest_path)
        self.scripts = self._build_scripts(self.manifest)

    def find_manifest(self, package_path: Path) -> Path:
        # Log all files in the package directory for debugging.
        for f in package_path.iterdir():
            logging.getLogger(__name__).info("Found file in package: %s", f.name)
            
        manifest_path = find_file_type("manifest", package_path)
        if not manifest_path:
            raise FileNotFoundError("Manifest file not found in the package directory.")
        return manifest_path

    def _load_manifest(self, manifest_path: Path) -> Dict[str, Any]:
        manifest = load_manifest(manifest_path)
        if not validate_manifest(manifest):
            raise ValueError("Invalid manifest file.")
        return manifest

    def _build_scripts(self, manifest: dict) -> Dict[str, Script]:
        scripts = {}
        scripts_data = manifest.get("scripts", {})
        if not scripts_data:
            raise ValueError("No scripts defined in the manifest.")
        for name, config in scripts_data.items():
            if isinstance(config, (str, list)):
                scripts[name] = Script(args=config)
            elif isinstance(config, dict):
                scripts[name] = Script(**config)
            else:
                raise ValueError(f"Invalid configuration for script '{name}'.")
        return scripts

    def build_package(self) -> ToolPackage:
        return ToolPackage(
            name=self.manifest.get("name", ""),
            description=self.manifest.get("description", ""),
            command=self.manifest.get("command", ""),
            scripts=self.scripts,
            location=self.package_path,
            dependencies=self.manifest.get("dependencies", {}),
            install_date=now(),
            last_update=now(),
        )

# ---------------------------
# PackageManager Class
# ---------------------------
class PackageManager:
    """
    Manages packages using the Registry.
    It can import, list, remove, update packages,
    and run their scripts.
    """
    def __init__(self, registry):
        """
        :param registry: An instance of the ORM-based Registry.
        """
        self.registry = registry
        self.logger = logging.getLogger(__name__)

    def move_package_to_registry(self, package_dir: Path) -> Path:
        """
        Copies the package folder to the registry's tools folder.
        """
        registry_tools_dir = self.registry.db_path / "tools"
        registry_tools_dir.mkdir(parents=True, exist_ok=True)
        registry_package_dir = registry_tools_dir / package_dir.name
        if registry_package_dir.exists():
            shutil.rmtree(registry_package_dir)
        shutil.copytree(package_dir, registry_package_dir)
        return registry_package_dir

    def import_package(self, manifest_path: Path):
        package_dir = manifest_path.parent
        registry_package_dir = self.move_package_to_registry(package_dir)
        package = PackageBuilder(registry_package_dir).build_package()
        try:
            # Attempt to add package. If it fails due to IntegrityError, update it.
            self.registry.add_package(
                package.command,
                package.name,
                package.description,
                str(package.location),
                package.dependencies,
            )
            self.logger.info("Package added successfully.")
        except Exception as e:
            self.logger.error("Error adding package to registry: %s", e)
            # For example, if you detect an IntegrityError, you can update:
            self.logger.info("Updating existing package '%s'.", package.command)
            self.registry.update_package(
                package.command,
                package.name,
                package.description,
                str(package.location),
                package.dependencies,
            )

        for script_name, script in package.scripts.items():
            try:
                self.registry.add_script(package.command, script_name, script)
            except Exception as e:
                self.logger.error("Error adding script '%s': %s", script_name, e)
                
    def list_packages(self) -> List[str]:
        return self.registry.list_packages()

    def remove_package(self, command: str):
        """
        Removes a package and its associated scripts from the registry.
        """
        self.registry.remove_package(command)
        script_names = self.registry.list_scripts(command)
        for script_name in script_names:
            self.registry.remove_script(command, script_name)

    def show_package(self, command: str) -> Optional[ToolPackage]:
        pkg_dict = self.registry.get_package(command)
        if not pkg_dict:
            self.logger.error("Package not found: %s", command)
            return None

        script_names = self.registry.list_scripts(command)
        scripts = {}
        for script_name in script_names:
            script = self.registry.get_script(command, script_name)
            if script:
                scripts[script_name] = script

        return ToolPackage(
            name=pkg_dict["name"],
            description=pkg_dict["description"],
            command=pkg_dict["command"],
            scripts=scripts,
            location=Path(pkg_dict["location"]),
            dependencies=pkg_dict["dependencies"],
            install_date=pkg_dict["install_date"],
            last_update=pkg_dict["last_update"],
        )

    def run_script(self, command: str, script_name: str, base_dir: Path, extra_args: List[str] = None):
        script = self.registry.get_script(command, script_name)
        if not script:
            self.logger.error("Script '%s' not found in package '%s'.", script_name, command)
            return
        try:
            args = script.prepare_subprocess_args(base_dir, extra_args=extra_args)
        except Exception as e:
            self.logger.error("Error preparing subprocess arguments: %s", e)
            return

        self.logger.info("Running script with command: %s", args["args"])
        try:
            subprocess.run(**args)
        except subprocess.CalledProcessError as e:
            self.logger.error("Error running script: %s", e)

    def update_package(self, manifest_path: Path):
        """
        Update the package record in the registry by re-reading the manifest from the package folder.
        This version assumes that the package folder is already in the registry and does not move or copy it.
        It also updates each script: if a script record exists, it updates it; otherwise, it adds it.
        """
        package_dir = manifest_path.parent
        # Re-read the package from the existing folder.
        package = PackageBuilder(package_dir).build_package()
        try:
            self.registry.update_package(
                package.command,
                package.name,
                package.description,
                str(package.location),
                package.dependencies,
            )
        except Exception as e:
            self.logger.error("Error updating package: %s", e)
            return

        for script_name, script in package.scripts.items():
            try:
                # Check if the script exists first.
                existing = self.registry.get_script(package.command, script_name)
                if existing:
                    self.registry.update_script(package.command, script_name, script)
                    self.logger.info("Updated script '%s'.", script_name)
                else:
                    self.registry.add_script(package.command, script_name, script)
                    self.logger.info("Added script '%s'.", script_name)
            except Exception as e:
                self.logger.error("Error updating script '%s': %s", script_name, e)
