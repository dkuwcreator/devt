# package_builder.py
import os
import inspect
import logging
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, Optional

from devt.config_manager import SUBPROCESS_ALLOWED_KEYS
from devt.utils import merge_configs, find_file_type  # Assumes these utilities are available
from .utils import load_and_validate_manifest, merge_global_and_script_configs
from .script import Script

logger = logging.getLogger(__name__)

class ToolPackage:
    """
    Represents a package built from a manifest file.
    """
    def __init__(
        self,
        name: str,
        description: str,
        command: str,
        scripts: Dict[str, Script],
        location: Path,
        dependencies: Dict[str, Any],
        group: str = "default",
        install_date: str = "",
        last_update: str = "",
    ):
        self.name = name
        self.description = description
        self.command = command
        self.scripts = scripts
        self.location = location
        self.dependencies = dependencies
        self.group = group
        self.install_date = install_date
        self.last_update = last_update

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "command": self.command,
            "location": str(self.location),
            "dependencies": self.dependencies,
            "group": self.group,
            "install_date": self.install_date,
            "last_update": self.last_update,
        }

class PackageBuilder:
    """
    Processes a package directory by locating its manifest,
    validating it, merging configurations, and building a ToolPackage.
    """
    def __init__(self, package_path: Path, group: str = "default") -> None:
        self.package_path: Path = package_path.resolve()
        logger.debug("Resolved package path: %s", self.package_path)
        self.manifest_path: Path = self.find_manifest(self.package_path)
        self.manifest: Dict[str, Any] = self._load_manifest(self.manifest_path)
        self.top_level_cwd: str = self.manifest.get("cwd", ".")
        self.group: str = group
        self.scripts = self._build_scripts()

    def find_manifest(self, package_path: Path) -> Path:
        """
        Locate the manifest file within the package directory.
        """
        manifest_path = find_file_type("manifest", package_path)
        if not manifest_path:
            error_msg = f"Manifest file not found in the package directory: {package_path}"
            logger.error(error_msg)
            raise FileNotFoundError(error_msg)
        logger.info("Found manifest at: %s", manifest_path)
        return manifest_path

    def _load_manifest(self, manifest_path: Path) -> Dict[str, Any]:
        """
        Load and validate the manifest file.
        """
        manifest = load_and_validate_manifest(manifest_path)
        logger.info("Manifest loaded and validated successfully.")
        return manifest

    def _get_execute_args(self) -> Dict[str, Any]:
        """
        Merge global and script-specific configurations.
        """
        return merge_global_and_script_configs(self.manifest, SUBPROCESS_ALLOWED_KEYS)

    def _get_script_entry(self, scripts: Dict[str, Any], script_key: str) -> Dict[str, Any]:
        """
        Retrieve the script configuration for a specified key.
        """
        logger.debug("Retrieving script entry for key: %s", script_key)
        base_config = dict(scripts)
        CURRENT_OS = "windows" if os.name == "nt" else "posix"
        if CURRENT_OS in base_config and script_key in base_config[CURRENT_OS]:
            logger.debug("Merging OS-specific settings for script key: %s", script_key)
            base_config = merge_configs(base_config, base_config[CURRENT_OS])
        script_entry = base_config.get(script_key)
        if isinstance(script_entry, (str, list)):
            logger.debug("Script entry is a direct command for key: %s", script_key)
            return merge_configs(base_config, {"args": script_entry})
        if script_entry and CURRENT_OS in script_entry:
            os_specific = script_entry[CURRENT_OS]
            if isinstance(os_specific, (str, list)):
                logger.debug("Merging OS-specific command for script key: %s", script_key)
                return merge_configs(base_config, script_entry, {"args": os_specific})
            if isinstance(os_specific, dict):
                logger.debug("Merging OS-specific dictionary for script key: %s", script_key)
                return merge_configs(base_config, script_entry, os_specific)
        error_msg = f"Script '{script_key}' not found in the manifest."
        logger.error(error_msg)
        raise ValueError(error_msg)

    def _get_all_scripts(self) -> Dict[str, Any]:
        """
        Retrieve all script configurations from the manifest.
        """
        logger.debug("Getting all scripts from the manifest.")
        scripts = self._get_execute_args()
        CURRENT_OS = "windows" if os.name == "nt" else "posix"
        script_names = set(scripts.keys()) | set(scripts.get(CURRENT_OS, {}).keys())
        excluded_keys = {"posix", "windows"} | SUBPROCESS_ALLOWED_KEYS
        return {
            script_key: self._get_script_entry(scripts, script_key)
            for script_key in script_names
            if script_key not in excluded_keys
        }

    def _build_scripts(self) -> Dict[str, Script]:
        """
        Build Script objects from the manifest.
        """
        logger.debug("Building Script objects from the manifest.")
        scripts = self._get_all_scripts()
        return {script_key: Script(**script_entry) for script_key, script_entry in scripts.items()}

    def build_package(self) -> ToolPackage:
        """
        Build and return a ToolPackage instance using the manifest and scripts.
        """
        package = ToolPackage(
            name=self.manifest.get("name", ""),
            description=self.manifest.get("description", ""),
            command=self.manifest.get("command", ""),
            scripts=self.scripts,
            location=self.package_path,
            dependencies=self.manifest.get("dependencies", {}),
            group=self.group,
            install_date=datetime.now().isoformat(),
            last_update=datetime.now().isoformat(),
        )
        logger.info("Built package: %s", package.to_dict())
        return package

def run_package_script(
    manifest_path: Path,
    script_name: str,
    extra_args: Optional[list] = None,
    auto_create_cwd: bool = False,
) -> Any:
    """
    Convenience function to run a specific script from a manifest.
    """
    builder = PackageBuilder(manifest_path.parent)
    package = builder.build_package()
    script = package.scripts.get(script_name)
    if not script:
        raise ValueError(f"Script '{script_name}' not found in the manifest.")
    return script.execute(builder.package_path, extra_args, auto_create_cwd)
