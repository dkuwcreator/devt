import inspect
import os
import shlex
import shutil
import subprocess
import logging
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional, Union
from dataclasses import dataclass, field
import zipfile

from devt.executor import IS_WINDOWS, default_shell_prefix, needs_shell_fallback, to_tokens
from devt.utils import find_file_type, load_manifest, validate_manifest

logger = logging.getLogger(__name__)


def now() -> str:
    """Return the current timestamp as an ISO-formatted string."""
    return datetime.now().isoformat()

# ---------------------------
# Helper: Allowed keys for Script initialization
# ---------------------------
# Dynamically extract allowed arguments for subprocess.run() and subprocess.Popen()
RUN_KEYS = set(inspect.signature(subprocess.run).parameters.keys())
POPEN_KEYS = set(inspect.signature(subprocess.Popen).parameters.keys())
# Combine both to get a full set of allowed arguments
ALLOWED_KEYS = RUN_KEYS | POPEN_KEYS

# ---------------------------
# Script Class
# ---------------------------
@dataclass
class Script:
    """
    Represents a command (or script) defined in a package manifest.
    
    Provides functionality to build and assemble the command tokens
    for execution via subprocess.
    """
    def __init__(
        self,
        args: Union[str, List[str]],
        shell: Optional[str] = None,
        extended_shell: Optional[str] = None,
        cwd: Path = Path("."),
        env: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        self.args = args
        self.shell = shell
        self.extended_shell = extended_shell
        self.cwd = cwd
        self.env = env if env is not None else {}
        self.kwargs = {k: v for k, v in kwargs.items() if k in self.ALLOWED_KEYS}

    def build_command_tokens(self) -> List[str]:
        """
        Build the list of command tokens for the script.
        
        If 'shell' or 'extended_shell' is provided, they are prepended accordingly.
        """
        tokens = to_tokens(self.args) if isinstance(self.args, str) else self.args
        if self.shell:
            tokens = to_tokens(self.shell) + tokens
        if self.extended_shell:
            tokens = to_tokens(self.extended_shell) + tokens
        return tokens

    def assemble_command(self) -> str:
        """
        Assemble the final command string from tokens, applying shell fallback if needed.
        """
        tokens = self.build_command_tokens()
        if needs_shell_fallback(tokens):
            command_str = shlex.join(tokens) if not IS_WINDOWS else subprocess.list2cmdline(tokens)
            tokens = default_shell_prefix(command_str)
        return shlex.join(tokens) if not IS_WINDOWS else subprocess.list2cmdline(tokens)

    def resolve_cwd(self, base_dir: Path, auto_create: bool = False) -> Path:
        """
        Resolve the working directory (cwd) relative to a given base directory.
        
        If 'cwd' is not absolute, it is resolved against 'base_dir'. Optionally,
        if 'auto_create' is True, the directory will be created if it doesn't exist.
        
        Raises:
            FileNotFoundError: if the directory does not exist and auto_create is False.
            NotADirectoryError: if the resolved path exists but is not a directory.
        """
        resolved = self.cwd if self.cwd.is_absolute() else base_dir / self.cwd
        if not resolved.exists():
            if auto_create:
                logger.info("Auto-creating missing working directory '%s'", resolved)
                resolved.mkdir(parents=True, exist_ok=True)
            else:
                raise FileNotFoundError(f"Working directory '{resolved}' does not exist.")
        if not resolved.is_dir():
            raise NotADirectoryError(f"Resolved path '{resolved}' is not a directory.")
        return resolved

    def prepare_subprocess_args(
        self, base_dir: Path, extra_args: Optional[List[str]] = None, auto_create_cwd: bool = False
    ) -> Dict[str, Any]:
        """
        Prepare the dictionary of subprocess arguments, merging any extra arguments.
        
        Args:
            base_dir: The base directory (typically the package location).
            extra_args: Additional command-line arguments to append.
            auto_create_cwd: Whether to auto-create the working directory if missing.
            
        Returns:
            A dictionary suitable for use with subprocess.run().
        """
        command = self.assemble_command()
        if extra_args:
            extra_str = shlex.join(extra_args) if not IS_WINDOWS else subprocess.list2cmdline(extra_args)
            command += " " + extra_str
        env = {**os.environ, **self.env} if self.env else None
        cwd_path = self.resolve_cwd(base_dir, auto_create=auto_create_cwd)
        return {
            "args": command,
            "shell": True,
            "cwd": str(cwd_path),
            "env": env,
            **self.kwargs,
        }

    def to_dict(self) -> Dict[str, Any]:
        """
        Serialize the Script instance to a dictionary.
        """
        return {
            "args": self.args,
            "shell": self.shell,
            "extended_shell": self.extended_shell,
            "cwd": str(self.cwd),
            "env": self.env,
            "kwargs": self.kwargs,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Script":
        """
        Create a Script instance from a dictionary.
        """
        return cls(
            args=data["args"],
            shell=data.get("shell"),
            extended_shell=data.get("extended_shell"),
            cwd=Path(data["cwd"]),
            env=data.get("env", {}),
            kwargs=data.get("kwargs", {}),
        )


# ---------------------------
# ToolPackage Dataclass
# ---------------------------
@dataclass
class ToolPackage:
    """
    Represents a package built from a manifest file, containing package-level
    metadata and a collection of scripts.
    """
    name: str
    description: str
    command: str
    scripts: Dict[str, Script]
    location: Path
    dependencies: Dict[str, Any]
    group: str = "default"
    install_date: str = ""
    last_update: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """
        Serialize the ToolPackage instance to a dictionary.
        """
        return {
            "command": self.command,
            "name": self.name,
            "description": self.description,
            "location": str(self.location),
            "dependencies": self.dependencies,
            "group": self.group,
            "install_date": self.install_date,
            "last_update": self.last_update,
        }

def apply_os_overrides(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Apply OS-specific overrides to a given configuration dictionary.
    
    For Windows, if a "windows" key is present, its values will override
    the base configuration. Similarly, for non-Windows systems, the "posix"
    key will override base values.
    
    Args:
        config: The script configuration dictionary.
        
    Returns:
        The updated configuration dictionary.
    """
    if IS_WINDOWS and "windows" in config:
        os_config = config.pop("windows")
        config.update(os_config)
    elif not IS_WINDOWS and "posix" in config:
        os_config = config.pop("posix")
        config.update(os_config)
    return config


class PackageBuilder:
    """
    Processes a package directory by locating its manifest, validating it,
    and building a ToolPackage instance containing package metadata and its scripts.
    """
    def __init__(self, package_path: Path, group: str = "default") -> None:
        """
        Initialize the PackageBuilder.
        
        Args:
            package_path: The directory containing the package.
            group: The group name for this package.
        """
        self.package_path: Path = package_path.resolve()
        logger.debug("Resolved package path: %s", self.package_path)
        self.manifest_path: Path = self.find_manifest(self.package_path)
        self.manifest: Dict[str, Any] = self._load_manifest(self.manifest_path)
        self.top_level_cwd: str = self.manifest.get("cwd", ".")
        self.group: str = group
        self.scripts = self._build_scripts(self.manifest)
        self._resolve_scripts()

    def find_manifest(self, package_path: Path) -> Path:
        """
        Locate the manifest file within the package directory.
        
        Args:
            package_path: The directory to search.
        
        Returns:
            The path to the manifest file.
        
        Raises:
            FileNotFoundError: If no manifest file is found.
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
        
        Args:
            manifest_path: The path to the manifest file.
        
        Returns:
            The manifest as a dictionary.
        
        Raises:
            ValueError: If the manifest is invalid.
        """
        manifest = load_manifest(manifest_path)
        if not validate_manifest(manifest):
            error_msg = f"Invalid manifest file at {manifest_path}"
            logger.error(error_msg)
            raise ValueError(error_msg)
        logger.info("Manifest loaded and validated successfully.")
        return manifest

    def _build_scripts(self, manifest: Dict[str, Any]) -> Dict[str, Script]:
        """
        Build Script objects from the manifest configuration.
        
        Args:
            manifest: The manifest dictionary.
        
        Returns:
            A dictionary mapping script names to Script instances.
        
        Raises:
            ValueError: If no scripts are defined or if a script configuration is invalid.
        """
        scripts: Dict[str, Script] = {}
        scripts_data = manifest.get("scripts", {})
        if not scripts_data:
            error_msg = "No scripts defined in the manifest."
            logger.error(error_msg)
            raise ValueError(error_msg)
        for name, config in scripts_data.items():
            try:
                if isinstance(config, (str, list)):
                    # Use top-level cwd if not specified.
                    script_instance = Script(args=config, cwd=Path(self.top_level_cwd))
                elif isinstance(config, dict):
                    # Set cwd to top-level if not provided.
                    if "cwd" not in config:
                        config["cwd"] = self.top_level_cwd
                    # Apply OS-specific overrides.
                    config = apply_os_overrides(config)
                    # Ensure that cwd is a Path object.
                    config["cwd"] = Path(config["cwd"])
                    script_instance = Script(**config)
                else:
                    error_msg = f"Invalid configuration type for script '{name}'."
                    logger.error(error_msg)
                    raise ValueError(error_msg)
                scripts[name] = script_instance
                logger.debug("Built script '%s' with configuration: %s", name, script_instance)
            except Exception as e:
                logger.exception("Error building script '%s': %s", name, e)
                raise
        return scripts

    def _resolve_script_cwd(self, script: Script) -> Path:
        """
        Resolve a script's working directory relative to the package directory.
        
        Args:
            script: The Script instance whose cwd is to be resolved.
        
        Returns:
            The resolved absolute Path for the script's cwd.
        
        Raises:
            ValueError: If the resolved cwd lies outside the package directory.
        """
        if script.cwd.is_absolute():
            resolved = script.cwd.resolve()
        else:
            resolved = (self.package_path / script.cwd).resolve()
        try:
            resolved.relative_to(self.package_path)
        except ValueError:
            error_msg = (
                f"Script cwd '{script.cwd}' resolves to '{resolved}', which is outside "
                f"the package directory '{self.package_path}'."
            )
            logger.error(error_msg)
            raise ValueError(error_msg)
        return resolved

    def _resolve_scripts(self) -> None:
        """
        Update each script's cwd to its resolved absolute path.
        """
        for name, script in self.scripts.items():
            try:
                resolved_cwd = self._resolve_script_cwd(script)
                script.cwd = resolved_cwd
                logger.debug("Resolved cwd for script '%s': %s", name, resolved_cwd)
            except Exception as e:
                logger.exception("Error resolving cwd for script '%s': %s", name, e)
                raise

    def build_package(self) -> ToolPackage:
        """
        Build and return a ToolPackage instance using the manifest and scripts.
        
        Returns:
            A ToolPackage instance containing package metadata and scripts.
        """
        package = ToolPackage(
            name=self.manifest.get("name", ""),
            description=self.manifest.get("description", ""),
            command=self.manifest.get("command", ""),
            scripts=self.scripts,
            location=self.package_path,
            dependencies=self.manifest.get("dependencies", {}),
            group=self.group,
            install_date=now(),
            last_update=now(),
        )
        logger.info("Built package: %s", package)
        return package
    
class PackageManager:
    """
    Handles file system operations for packages, including importing, moving,
    copying, deleting, and exporting package directories.
    """
    def __init__(self, tools_dir: Path) -> None:
        """
        Initialize the PackageManager with a directory where packages will be stored.

        Args:
            tools_dir: The root directory for storing package folders.
        """
        self.tools_dir: Path = tools_dir
        self.tools_dir.mkdir(parents=True, exist_ok=True)
        logger.info("Tools directory is set to: %s", self.tools_dir)

    def _copy_dir(self, source: Path, destination: Path) -> Optional[Path]:
        """
        Copy the entire package directory from source to destination.

        Args:
            source: The source directory to copy.
            destination: The target directory.

        Returns:
            The destination path if successful, or None if an error occurred.
        """
        logger.info("Copying package directory '%s' to '%s'", source, destination)
        try:
            shutil.copytree(source, destination)
            logger.info("Package directory copied successfully.")
            return destination
        except Exception as e:
            logger.error("Error copying package directory from '%s' to '%s': %s", source, destination, e)
            return None

    def _delete_dir(self, dir_path: Path) -> None:
        """
        Delete the specified directory and its contents.

        Args:
            dir_path: The directory path to delete.
        """
        logger.info("Deleting package directory: %s", dir_path)
        try:
            shutil.rmtree(dir_path)
            logger.info("Package directory deleted successfully.")
        except Exception as e:
            logger.error("Error deleting package directory '%s': %s", dir_path, e)

    def move_package_to_tools_dir(
        self, package_dir: Path, group: str = "default", overwrite: bool = False
    ) -> Optional[Path]:
        """
        Move a package directory into the tools directory under a specified group.
        If the target directory exists, it will be overwritten if the flag is set.

        Args:
            package_dir: The source package directory.
            group: The group under which the package is stored.
            overwrite: Whether to overwrite an existing directory.

        Returns:
            The target directory path if successful, else None.
        """
        target_dir = self.tools_dir / group / package_dir.name
        if target_dir.exists():
            if overwrite:
                logger.info("Overwriting existing package directory: %s", target_dir)
                self._delete_dir(target_dir)
            else:
                logger.error("Package directory already exists: %s", target_dir)
                return None
        return self._copy_dir(package_dir, target_dir)

    def import_package(self, source: Path, group: Optional[str] = None, overwrite: bool = False) -> List[ToolPackage]:
        """
        Imports package(s) from the specified source and returns a list of ToolPackage objects.
        The source may be a manifest file or a directory containing one or more manifests.
        If an error occurs while processing one manifest, it logs the error and continues with the others.

        Args:
            source: A path to a manifest file or a directory containing packages.
            group: An optional group name to assign to imported packages.
            overwrite: Unused in this context; could be used for future incremental updates.

        Returns:
            A list of successfully built ToolPackage objects.
        """
        packages: List[ToolPackage] = []
        effective_group = group or (source.stem if source.is_file() else source.name)
        errors: List[str] = []

        if source.is_file() and source.suffix in [".json", ".yaml", ".yml"]:
            try:
                pkg = PackageBuilder(source.parent, effective_group).build_package()
                packages.append(pkg)
            except Exception as e:
                error_msg = f"Error building package from '{source}': {e}"
                logger.error(error_msg)
                errors.append(error_msg)
        elif source.is_dir():
            # First try the root directory.
            manifest = find_file_type("manifest", source)
            if manifest:
                try:
                    pkg = PackageBuilder(source, effective_group).build_package()
                    packages.append(pkg)
                except Exception as e:
                    error_msg = f"Error building package from '{source}': {e}"
                    logger.error(error_msg)
                    errors.append(error_msg)
            else:
                # Search recursively for manifest files.
                for mf in source.rglob("manifest.*"):
                    try:
                        pkg = PackageBuilder(mf.parent, effective_group).build_package()
                        packages.append(pkg)
                    except Exception as e:
                        error_msg = f"Error building package from '{mf}': {e}"
                        logger.error(error_msg)
                        errors.append(error_msg)
        else:
            error_msg = f"Unsupported source type: {source}"
            logger.error(error_msg)
            errors.append(error_msg)

        if errors:
            logger.warning("Encountered errors during package import: %s", errors)
        else:
            logger.info("Successfully imported %d package(s) from %s", len(packages), source)
        return packages

    def delete_package(self, package_dir: Path) -> bool:
        """
        Public method to delete a package directory.

        Args:
            package_dir: The package directory to delete.

        Returns:
            True if the deletion was successful, False otherwise.
        """
        if package_dir.exists():
            try:
                self._delete_dir(package_dir)
                logger.info("Package directory '%s' deleted successfully.", package_dir)
                return True
            except Exception as e:
                logger.error("Error deleting package directory '%s': %s", package_dir, e)
                return False
        else:
            logger.warning("Package directory '%s' does not exist.", package_dir)
            return False

    def export_package(self, package_location: Path, output_path: Path) -> Path:
        """
        Export a package folder as a zip archive.

        Args:
            package_location: The package folder to export.
            output_path: The output path for the zip archive.

        Returns:
            The output path if the export was successful.
        """
        logger.info("Exporting package from '%s' to zip file '%s'.", package_location, output_path)
        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for file in package_location.rglob("*"):
                if file.is_file():
                    zf.write(file, file.relative_to(package_location))
        logger.info("Package exported successfully to '%s'.", output_path)
        return output_path