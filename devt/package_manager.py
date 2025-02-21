"""
A flexible script runner that loads a YAML manifest with global and per-script configuration,
merges in OS-specific overrides, and produces a dictionary for subprocess.run().
It defines a PackageBuilder to process a manifest, a ToolPackage to hold package-level metadata,
and a Script class that encapsulates command execution details.
"""

import inspect
import logging
import os
import shlex
import shutil
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Union
from dataclasses import dataclass, field
import zipfile

# External utility functions assumed available from your project.
from utils import (
    merge_configs,
    resolve_rel_path,
    find_file_type,
    load_manifest,
    validate_manifest,
)

# Configure logger
logger = logging.getLogger(__name__)

# OS flags and allowed subprocess keys
IS_WINDOWS = os.name == "nt"
IS_POSIX = not IS_WINDOWS
CURRENT_OS = "posix" if IS_POSIX else "windows"
# Dynamically extract allowed arguments for subprocess.run() and subprocess.Popen()
RUN_KEYS = set(inspect.signature(subprocess.run).parameters.keys())
POPEN_KEYS = set(inspect.signature(subprocess.Popen).parameters.keys())
# Combine both to get a full set of allowed arguments
SUBPROCESS_ALLOWED_KEYS = RUN_KEYS | POPEN_KEYS


# -----------------------------------------------------------------------------
# Helper Functions and Exception
# -----------------------------------------------------------------------------


class CommandExecutionError(Exception):
    """Custom exception for wrapping command execution errors."""

    def __init__(
        self,
        message: str,
        returncode: int,
        stdout: Optional[str] = None,
        stderr: Optional[str] = None,
    ) -> None:
        super().__init__(message)
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def needs_shell_fallback(args: Union[str, List[str]]) -> bool:
    """Determine whether the given command requires a shell fallback."""
    if isinstance(args, list):
        maybe_first_arg = args[0]
    else:
        maybe_first_arg = shlex.split(args, posix=IS_POSIX)[0]
    print(maybe_first_arg)
    print(shutil.which(maybe_first_arg))
    return shutil.which(maybe_first_arg) is None


def default_shell_prefix(command: str) -> List[str]:
    """Return the default shell prefix for the current OS."""
    if IS_WINDOWS:
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
    If `split` is True and the value is a string, it is split with shlex.
    Otherwise, the value is returned as a list (or single-item list if string).
    """
    if val is None:
        return []
    if isinstance(val, list):
        return val
    return shlex.split(val, posix=posix) if split else [val]


def prepare_args_base(
    config: Dict[str, Any], extra_args: Optional[Union[str, List[str]]] = None
) -> str:
    """
    Build the final args string using legacy logic:
      - If a shell wrapper is provided, it is prepended.
      - Extra command-line arguments (if any) are appended.
    Returns a single string formatted for subprocess.run().
    """
    args = config["args"]
    shell_wrapper = config.get("shell")
    extra_tokens = (
        to_tokens(extra_args, posix=IS_POSIX, split=True) if extra_args else []
    )

    if shell_wrapper:
        # Treat the main command as a single token.
        main_token = args if isinstance(args, str) else " ".join(args)
        final_tokens = (
            to_tokens(shell_wrapper, posix=IS_POSIX, split=True)
            + [main_token]
            + extra_tokens
        )
    else:
        main_tokens = to_tokens(args, posix=IS_POSIX, split=True)
        final_tokens = main_tokens + extra_tokens

    return (
        subprocess.list2cmdline(final_tokens)
        if IS_WINDOWS
        else shlex.join(final_tokens)
    )


# -----------------------------------------------------------------------------
# Core Classes: Script, ToolPackage, PackageBuilder
# -----------------------------------------------------------------------------


@dataclass
class Script:
    """
    Represents a command (or script) defined in a package manifest.
    Provides functionality to build its final command string and execute it.
    """

    def __init__(
        self,
        args: Union[str, List[str]],
        shell: Optional[Union[str, List[str]]] = None,
        cwd: Union[Path, str] = Path("."),
        env: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        self.args = args
        self.shell = shell
        self.cwd = Path(cwd) if not isinstance(cwd, Path) else cwd
        self.env = env
        # Only keep kwargs that subprocess.run/ Popen accepts.
        self.kwargs = {k: v for k, v in kwargs.items() if k in SUBPROCESS_ALLOWED_KEYS}

    def resolve_cwd(self, base_dir: Path, auto_create: bool = False) -> Path:
        """
        Resolve the script's working directory relative to base_dir.
        If the directory does not exist and auto_create is False, raise an error.
        Ensure the resolved path is within the package directory.
        """
        resolved = (
            self.cwd if self.cwd.is_absolute() else (base_dir / self.cwd).resolve()
        )
        if not str(resolved).startswith(str(base_dir.resolve())):
            raise ValueError(
                "Relative path cannot be outside of the package directory."
            )
        if not resolved.exists():
            if auto_create:
                logger.info("Auto-creating missing working directory '%s'", resolved)
                resolved.mkdir(parents=True, exist_ok=True)
            else:
                raise FileNotFoundError(
                    f"Working directory '{resolved}' does not exist."
                )
        if not resolved.is_dir():
            raise NotADirectoryError(f"Resolved path '{resolved}' is not a directory.")
        return resolved

    def resolve_env(self) -> Dict[str, str]:
        """Merge the current environment with the script's environment."""
        if self.env is not None:
            return {**os.environ, **self.env}
        return os.environ.copy()

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the Script instance to a dictionary."""
        return {
            "args": self.args,
            "shell": self.shell,
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
            **data.get("kwargs", {}),
        )

    def prepare_subprocess_args(
        self,
        base_dir: Path,
        extra_args: Optional[Union[str, List[str]]] = None,
        auto_create_cwd: bool = False,
    ) -> Dict[str, Any]:
        """
        Prepare and return a dictionary of subprocess.run() arguments.
        It merges extra arguments, resolves the working directory, combines the environment,
        and applies shell wrapper logic.
        """
        # Resolve working directory
        resolved_cwd = self.resolve_cwd(base_dir, auto_create=auto_create_cwd)

        # Merge environments; if none is provided, fallback to current environment
        env = self.resolve_env()

        # Determine OS specifics for tokenization
        IS_WINDOWS = os.name == "nt"
        IS_POSIX = not IS_WINDOWS

        # Prepare the final command string based on the provided shell wrapper or fallback
        if self.shell is not None:
            # Use provided shell wrapper tokens
            wrapper_tokens = to_tokens(self.shell, posix=IS_POSIX, split=True)
            # Convert self.args to a single token if it's a list
            main_token = (
                self.args if isinstance(self.args, str) else " ".join(self.args)
            )
            extra_tokens = to_tokens(extra_args, posix=IS_POSIX, split=True)
            final_tokens = wrapper_tokens + [main_token] + extra_tokens
        else:
            # No explicit shell wrapper was provided.
            # Check whether a shell fallback is needed (e.g. command not found in PATH)
            if needs_shell_fallback(self.args):
                # Wrap with a default shell prefix
                prefix_tokens = default_shell_prefix(self.args)
                extra_tokens = to_tokens(extra_args, posix=IS_POSIX, split=True)
                final_tokens = prefix_tokens + extra_tokens
            else:
                # Simply combine the command tokens with any extra arguments.
                main_tokens = to_tokens(self.args, posix=IS_POSIX, split=True)
                extra_tokens = to_tokens(extra_args, posix=IS_POSIX, split=True)
                final_tokens = main_tokens + extra_tokens

        # Reassemble tokens into a final command string appropriate for the OS
        command_str = (
            subprocess.list2cmdline(final_tokens)
            if IS_WINDOWS
            else shlex.join(final_tokens)
        )

        # Build final configuration dictionary for subprocess.run()
        final_config = {
            "args": command_str,
            "cwd": str(resolved_cwd),
            "env": env,
            "shell": True,  # Always run with shell=True as per design.
        }
        # Merge any additional allowed keyword arguments
        final_config.update(**self.kwargs)
        return final_config

    def execute(
        self,
        base_dir: Path,
        extra_args: Optional[Union[str, List[str]]] = None,
        auto_create_cwd: bool = False,
    ) -> subprocess.CompletedProcess:
        """
        Execute the script using subprocess.run() with the prepared arguments.
        Raises a CommandExecutionError if the command fails.
        """
        config = self.prepare_subprocess_args(base_dir, extra_args, auto_create_cwd)
        logger.info("Executing command: %s", config["args"])
        logger.debug("Subprocess configuration: %s", config)
        result = subprocess.run(**config)
        if result.returncode != 0:
            raise CommandExecutionError(
                "Command failed",
                result.returncode,
                stdout=getattr(result, "stdout", None),
                stderr=getattr(result, "stderr", None),
            )
        return result


@dataclass
class ToolPackage:
    """
    Represents a package built from a manifest file.
    Contains package metadata and a mapping of script names to Script instances.
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
        """Serialize the ToolPackage instance to a dictionary."""
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
    Processes a package directory by locating its manifest, validating it,
    merging global settings (like cwd and env) with per-script configuration,
    and building a ToolPackage instance.
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
        """Locate the manifest file within the package directory."""
        manifest_path = find_file_type("manifest", package_path)
        if not manifest_path:
            error_msg = (
                f"Manifest file not found in the package directory: {package_path}"
            )
            logger.error(error_msg)
            raise FileNotFoundError(error_msg)
        logger.info("Found manifest at: %s", manifest_path)
        return manifest_path

    def _load_manifest(self, manifest_path: Path) -> Dict[str, Any]:
        """Load and validate the manifest file."""
        manifest = load_manifest(manifest_path)
        if not validate_manifest(manifest):
            error_msg = f"Invalid manifest file at {manifest_path}"
            logger.error(error_msg)
            raise ValueError(error_msg)
        logger.info("Manifest loaded and validated successfully.")
        return manifest

    def _get_execute_args(self) -> Tuple[Path, Dict[str, Any]]:
        """Get the arguments for executing a script."""
        logger.debug(
            "Extracting global and script-specific configurations from the manifest."
        )
        global_dict = {
            k: v for k, v in self.manifest.items() if k in SUBPROCESS_ALLOWED_KEYS
        }
        scripts_dict = self.manifest.get("scripts", {})
        if not scripts_dict:
            error_msg = "No scripts found in the manifest file."
            logger.error(error_msg)
            raise ValueError(error_msg)
        return merge_configs(global_dict, scripts_dict)

    def _get_script_entry(
        self, scripts: Dict[str, Any], script_key: str
    ) -> Dict[str, Any]:
        """
        Retrieve the script configuration for the specified script key,
        merging in OS-specific configurations when available.
        """
        logger.debug("Retrieving script entry for key: %s", script_key)
        base_config = dict(scripts)

        # If OS-specific settings exist for the script_key, merge them
        if CURRENT_OS in base_config and script_key in base_config[CURRENT_OS]:
            logger.debug("Merging OS-specific settings for script key: %s", script_key)
            base_config = merge_configs(base_config, base_config[CURRENT_OS])

        script_entry = base_config.get(script_key)

        # If script_entry is a direct command (string or list), just merge
        if isinstance(script_entry, (str, list)):
            logger.debug("Script entry is a direct command for key: %s", script_key)
            return merge_configs(base_config, {"args": script_entry})

        # If OS-specific command or dict is present, merge accordingly
        if script_entry and CURRENT_OS in script_entry:
            os_specific = script_entry[CURRENT_OS]
            if isinstance(os_specific, (str, list)):
                logger.debug(
                    "Merging OS-specific command for script key: %s", script_key
                )
                return merge_configs(base_config, script_entry, {"args": os_specific})
            if isinstance(os_specific, dict):
                logger.debug(
                    "Merging OS-specific dictionary for script key: %s", script_key
                )
                return merge_configs(base_config, script_entry, os_specific)

        error_msg = f"Script '{script_key}' not found in the manifest."
        logger.error(error_msg)
        raise ValueError(error_msg)

    def _get_all_scripts(self) -> Dict[str, Script]:
        logger.debug("Getting all scripts from the manifest.")
        scripts = self._get_execute_args()
        script_names = set(scripts.keys()) | set(scripts.get(CURRENT_OS, {}).keys())
        return {
            script_key: self._get_script_entry(scripts, script_key)
            for script_key in script_names
            if script_key not in ("posix", "windows", *SUBPROCESS_ALLOWED_KEYS)
        }

    def _build_scripts(self) -> Dict[str, Script]:
        """
        Build Script objects from the manifest.
        Global manifest keys (e.g. cwd and env) are merged with each script's configuration.
        """
        logger.debug("Building Script objects from the manifest.")
        scripts = self._get_all_scripts()
        return {
            script_key: Script(**script_entry)
            for script_key, script_entry in scripts.items()
        }

    def build_package(self) -> ToolPackage:
        """Build and return a ToolPackage instance using the manifest and scripts."""
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
        logger.info("Built package: %s", package)
        return package


# -----------------------------------------------------------------------------
# (Optional) Convenience Runner Function
# -----------------------------------------------------------------------------


def run_package_script(
    manifest_path: Path,
    script_name: str,
    extra_args: Optional[List[str]] = None,
    auto_create_cwd: bool = False,
) -> subprocess.CompletedProcess:
    """
    Convenience function: Given a manifest file path and a script name,
    build the package, look up the script, and execute it.
    """
    builder = PackageBuilder(manifest_path.parent)
    package = builder.build_package()
    script = package.scripts.get(script_name)
    if not script:
        raise ValueError(f"Script '{script_name}' not found in the manifest.")
    return script.execute(builder.package_path, extra_args, auto_create_cwd)


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
            logger.error(
                "Error copying package directory from '%s' to '%s': %s",
                source,
                destination,
                e,
            )
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

    def import_package(
        self, source: Path, group: Optional[str] = None, overwrite: bool = False
    ) -> List[ToolPackage]:
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
                dest = self.move_package_to_tools_dir(
                    source.parent, effective_group, overwrite
                )
                if dest:
                    pkg = PackageBuilder(dest, effective_group).build_package()
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
                    dest = self.move_package_to_tools_dir(
                        source, effective_group, overwrite
                    )
                    if dest:
                        pkg = PackageBuilder(dest, effective_group).build_package()
                        packages.append(pkg)
                except Exception as e:
                    error_msg = f"Error building package from '{source}': {e}"
                    logger.error(error_msg)
                    errors.append(error_msg)
            else:
                # Search recursively for manifest files.
                for mf in source.rglob("manifest.*"):
                    try:
                        dest = self.move_package_to_tools_dir(
                            mf.parent, effective_group, overwrite
                        )
                        if dest:
                            pkg = PackageBuilder(dest, effective_group).build_package()
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
            logger.info(
                "Successfully imported %d package(s) from %s", len(packages), source
            )
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
                logger.error(
                    "Error deleting package directory '%s': %s", package_dir, e
                )
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
        # Ensure output_path is a zip file, not a directory
        if output_path.is_dir():
            output_path = output_path / f"{package_location.name}.zip"

        logger.info(
            "Exporting package from '%s' to zip file '%s'.",
            package_location,
            output_path,
        )

        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for file in package_location.rglob("*"):
                if file.is_file():
                    zf.write(file, file.relative_to(package_location))

        logger.info("Package exported successfully to '%s'.", output_path)
        return output_path

    def unpack_package(self, zip_path: Path, destination_dir: Path) -> Path:
        """
        Unpack a package zip archive to the specified destination directory.

        Args:
            zip_path: The zip archive containing the package.
            destination_dir: The directory where the package should be unpacked.

        Returns:
            The destination directory path if the unpacking was successful.
        """
        logger.info(
            "Unpacking package from zip file '%s' to directory '%s'.",
            zip_path,
            destination_dir,
        )
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(destination_dir)
        logger.info("Package unpacked successfully to '%s'.", destination_dir)
        return destination_dir
