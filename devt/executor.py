# devt/executor.py
"""
Executor module: Provides helper functions for finding a tool,
resolving the correct script, determining the working directory, and executing commands.
"""

import os
import shlex
import shutil
import subprocess
import logging
from pathlib import Path
from typing import Any, Dict, Optional, List

logger = logging.getLogger(__name__)


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

#!/usr/bin/env python3
"""
A flexible YAML manifest runner with type hints and improved error handling.

This script reads a YAML manifest file containing a global configuration
and a set of scripts. It builds a dictionary to be fed to subprocess.run(),
merging key–value pairs so that values defined deeper (e.g. OS-specific)
overwrite values defined higher up.

Special keys:
  - cwd:
      * Defaults to the manifest file's directory.
      * If defined as relative, it is resolved relative to the manifest file's directory.
  - args:
      * If given as a string, it is converted into a list via shlex.split.
      * OS-specific "args" completely overwrite script-level "args.".
      * Extra command-line arguments are appended.
  - shwr:
      * Defines a shell wrapper (string or list). If provided, the final "args"
        command is wrapped with this shell wrapper.

This script always invokes `subprocess.run` with `shell=True`.

Additionally, if an "env" key is provided in the manifest, it is merged with the
current environment (so that essential variables such as PATH remain available).

Finally, only the keys accepted by subprocess.run()
are retained in the final configuration.

Usage:
    python run_manifest.py <manifest.yaml> <script_name> [extra args...]
"""

import json
import logging
import shlex
import subprocess
import inspect
from typing import Any, Dict, List, Optional
from pathlib import Path
import os
from git import Union
import yaml

# Configure a basic logger (logs at INFO level by default)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Dynamically extract allowed arguments for subprocess.run() and subprocess.Popen()
RUN_KEYS = set(inspect.signature(subprocess.run).parameters.keys())
POPEN_KEYS = set(inspect.signature(subprocess.Popen).parameters.keys())
# Combine both to get a full set of allowed arguments
ALLOWED_KEYS = RUN_KEYS | POPEN_KEYS


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


class ManifestRunner:
    """Class-based runner that loads and interprets a YAML manifest."""

    def __init__(self, manifest_path: str) -> None:
        self.manifest_path = Path(manifest_path).resolve()
        self.manifest_dir = self.manifest_path.parent
        self.manifest = self._load_manifest()
        self.current_os = "posix" if os.name == "posix" else "windows"

    def _load_manifest(self) -> Dict[str, Any]:
        """Load and parse the manifest file (YAML or JSON)."""
        if not self.manifest_path.is_file():
            raise FileNotFoundError(f"Manifest file not found: {self.manifest_path}")
        
        with self.manifest_path.open("r", encoding="utf-8") as f:
            if self.manifest_path.suffix in ['.yaml', '.yml']:
                data = yaml.safe_load(f)
            elif self.manifest_path.suffix in ['.json', '.cjson']:
                data = json.load(f)
            else:
                raise ValueError(f"Unsupported file extension: {self.manifest_path.suffix}")

            if not data:
                raise ValueError(
                    f"Manifest file is empty or invalid: {self.manifest_path}"
                )
        return data

    def _get_script_entry(self, script_name: str) -> Any:
        scripts = self.manifest.get("scripts", {})
        if self.current_os in scripts:
            scripts.update(scripts[self.current_os])
        if script_name not in scripts:
            raise ValueError(f"Script '{script_name}' not found in manifest.")
        return scripts[script_name]

    def _prepare_command(
        self,
        args: Union[str, List[str]],
        extra_args: Optional[Union[str, List[str]]] = None,
        shell_wrapper: Optional[Union[str, List[str]]] = None,
    ) -> str:
        """
        Constructs a properly formatted shell command string based on OS rules.

        If a shell wrapper is provided, the main command (args) is treated as a single token.
        Otherwise, args is split into tokens.
        """
        is_windows = os.name == "nt"
        posix = not is_windows  # shlex option

        # Normalize extra arguments (always split them)
        extra_tokens = to_tokens(extra_args, posix=posix, split=True)

        if shell_wrapper:
            # Normalize the shell wrapper tokens (always split)
            wrapper_tokens = to_tokens(shell_wrapper, posix=posix, split=True)
            # Do not split the main command; keep it as one token.
            main_token = args if isinstance(args, str) else " ".join(args)
            final_tokens = wrapper_tokens + [main_token] + extra_tokens
        else:
            # No shell wrapper: split the main command.
            main_tokens = to_tokens(args, posix=posix, split=True)
            final_tokens = main_tokens + extra_tokens

        # Reassemble tokens into a shell-ready command string.
        if is_windows:
            return subprocess.list2cmdline(final_tokens)
        else:
            return shlex.join(final_tokens)

    def _prepare_args(
        self, merged_config: Dict[str, Any], extra_args: Optional[List[str]]
    ) -> str:
        """Build the final args string, applying shell wrapper if needed."""
        if "args" not in merged_config:
            raise ValueError("No 'args' provided in the configuration for this script.")

        return self._prepare_command(
            merged_config["args"],
            extra_args=extra_args,
            shell_wrapper=merged_config.get("shwr", None),
        )

    def _resolve_cwd(self, merged_config: Dict[str, Any]) -> Path:
        """Resolve and validate the cwd setting."""
        cwd_value = merged_config.get("cwd", str(self.manifest_dir))
        final_cwd_path = self.resolve_path(cwd_value)
        if not final_cwd_path.is_dir():
            raise FileNotFoundError(
                f"Working directory '{final_cwd_path}' does not exist."
            )
        return final_cwd_path

    def _apply_env(self, merged_config: Dict[str, Any]) -> None:
        """Merge environment variables if 'env' key is present."""
        if "env" in merged_config:
            merged_config["env"] = {**os.environ, **merged_config["env"]}

    def _filter_allowed_keys(self, merged_config: Dict[str, Any]) -> Dict[str, Any]:
        """Filter configuration so that only keys accepted by subprocess.run() remain."""
        return {k: merged_config[k] for k in ALLOWED_KEYS if k in merged_config}

    def resolve_path(self, path_str: str) -> Path:
        """Resolve a path (possibly relative) to an absolute path within the manifest directory."""
        p = Path(path_str)
        return (self.manifest_dir / p).resolve()

    def build_command(
        self,
        script_name: str,
        extra_args: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Build the final subprocess.run configuration dictionary.

        Steps:
          1. Merges the global config (from the manifest root), the script-level config,
             and any OS-specific config ("windows" or "posix").
          2. Processes special keys ("cwd", "args", "shwr").
          3. Merges any provided "env" with the current environment.
          4. Ensures the working directory exists.
          5. Filters the resulting dictionary so that only keys accepted by subprocess.run() remain.

        Note: We always set `shell=True` for subprocess.run.
        """
        global_config = {k: v for k, v in self.manifest.items() if k != "scripts"}
        if "cwd" not in global_config:
            global_config["cwd"] = str(self.manifest_dir)

        # Gather script config
        script_entry = self._get_script_entry(script_name)
        if isinstance(script_entry, (str, list)):
            script_config = {"args": script_entry}
        elif isinstance(script_entry, dict):
            script_config = script_entry.copy()
        else:
            raise ValueError("Script entry must be a string, list, or dict.")

        # Check OS-specific config
        os_specific = {}
        if isinstance(script_entry, dict) and self.current_os in script_entry:
            os_specific = script_entry[self.current_os]
        if isinstance(os_specific, (str, list)):
            os_specific = {"args": os_specific}

        # Merge config in order: global < script < os-specific
        merged_config = merge_configs(global_config, script_config, os_specific)

        # Always run with shell=True
        merged_config["shell"] = True

        # Prepare final args
        final_args_str = self._prepare_args(merged_config, extra_args)
        # final_args_str = self._prepare_command(final_args_str)
        merged_config["args"] = final_args_str

        # Resolve & validate cwd
        final_cwd_path = self._resolve_cwd(merged_config)
        merged_config["cwd"] = str(final_cwd_path)

        # Merge environment
        self._apply_env(merged_config)

        # Filter out keys that subprocess.run won't accept
        final_config = self._filter_allowed_keys(merged_config)
        logger.debug("Merged config for '%s': %s", script_name, final_config)
        return final_config

    def run_script(
        self,
        script_name: str,
        extra_args: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> subprocess.CompletedProcess:
        """
        Build and run the specified script from the manifest.
        Additional kwargs are forwarded to subprocess.run.
        """
        final_config = self.build_command(script_name, extra_args)
        # Filter out any extra kwargs that subprocess.run() doesn't accept
        kwargs = self._filter_allowed_keys(kwargs)
        # Merge any extra kwargs (like 'check=True', etc.)
        final_config.update(kwargs)
        logger.info("Running script '%s' with config: %s", script_name, final_config)
        return subprocess.run(**final_config)

class Executor:
    def __init__(
        self,
        tool: Dict[str, Any],
        registry_dir: Path,
        env: Optional[Dict[str, str]] = None,
        timeout: Optional[int] = None,
    ) -> None:
        """
        Initialize the Executor with the tool entry, its registry directory,
        and optional environment variables and a timeout for command execution.

        :param tool: Dictionary representing the tool's registry entry.
        :param registry_dir: Path to the registry's base directory.
        :param env: Optional dictionary of environment variables.
        :param timeout: Optional timeout (in seconds) for executing commands.
        """
        self.tool = tool
        self.registry_dir = registry_dir
        self.env = env or os.environ.copy()
        self.timeout = timeout
        self.logger = logger

    def resolve_working_directory(self) -> Path:
        """
        Determine the working directory for executing the command.
        """
        tool_location = self.tool.get("location")
        if tool_location:
            tool_manifest_path = Path(self.registry_dir) / tool_location
            tool_dir = (
                tool_manifest_path.parent
                if tool_manifest_path.is_file()
                else tool_manifest_path
            )
        else:
            tool_dir = self.registry_dir

        base_dir = self.tool.get("manifest", {}).get("base_dir", ".")
        base_dir_path = Path(base_dir)
        if base_dir_path.is_absolute():
            new_cwd = base_dir_path
        else:
            new_cwd = (tool_dir / base_dir).resolve()

        if not new_cwd.is_dir():
            self.logger.warning(
                "Working directory '%s' is not a directory. Falling back to tool directory.",
                new_cwd,
            )
            new_cwd = tool_dir

        return new_cwd

    def _execute_with_shell(
        self,
        command: str,
        shell_type: str,
        cwd: Path,
        additional_args: Optional[List[str]],
    ) -> None:
        """
        Executes the command using the given shell type (bash or PowerShell).
        Uses `-NoExit` to keep the virtual environment active.
        """
        if additional_args:
            command += " " + " ".join(shlex.quote(arg) for arg in additional_args)

        self.logger.info(f"Executing command in {shell_type}: {command}")
        shell_cmd = []

        if shell_type == "pwsh":
            if shutil.which("pwsh"):
                shell_cmd = ["pwsh", "-Command", f"& {command}"]
            else:
                shell_cmd = ["powershell", "-Command", f"& {command}"]
        elif shell_type == "bash":
            shell_cmd = ["bash", "-c", command]

        subprocess.run(
            shell_cmd, cwd=cwd, env=self.env, timeout=self.timeout, check=True
        )

    def _execute_fallback(
        self, command: str, cwd: Path, additional_args: Optional[List[str]]
    ) -> None:
        """
        Executes the command in a fallback mode:
        - On Windows: Uses cmd.exe (`cmd /c`).
        - On POSIX: Executes directly.
        """
        if additional_args:
            command += " " + " ".join(shlex.quote(arg) for arg in additional_args)

        self.logger.info(f"Executing fallback command: {command}")
        if os.name == "nt":
            subprocess.run(
                ["cmd", "/c", command],
                cwd=cwd,
                env=self.env,
                timeout=self.timeout,
                check=True,
            )
        else:
            subprocess.run(
                command,
                cwd=cwd,
                env=self.env,
                timeout=self.timeout,
                check=True,
                shell=True,
            )

    def execute_command(
        self, command: str, cwd: Path, additional_args: Optional[List[str]]
    ) -> None:
        """
        Try executing the command in its appropriate OS shell first.
        If execution fails, fallback to a general execution mode.
        """
        try:
            if os.name == "nt":
                self._execute_with_shell(command, "pwsh", cwd, additional_args)
            else:
                self._execute_with_shell(command, "bash", cwd, additional_args)
        except subprocess.CalledProcessError:
            self.logger.warning(f"Shell execution failed for: {command}. Falling back.")
            self._execute_fallback(command, cwd, additional_args)

    def execute_script(
        self, script_name: str, additional_args: Optional[List[str]] = None
    ) -> None:
        """
        Resolve, build, and execute a script command for the tool.

        Execution logic:
          1. Look for an OS-specific script first (e.g., under 'windows' or 'posix' in "scripts").
          2. If found, attempt to run it using the proper shell.
          3. If shell execution fails, retry using a general execution mode.
          4. If no OS-specific script exists, run the non-OS-specific script.

        :param script_name: The name of the script to execute.
        :param additional_args: Optional list of additional command-line arguments.
        """
        shell = "windows" if os.name == "nt" else "posix"
        scripts = self.tool.get("manifest", {}).get("scripts", {})

        os_script = scripts.get(shell, {}).get(script_name)
        generic_script = scripts.get(script_name)

        candidates = []
        if os_script:
            candidates.append(os_script)
        if generic_script and generic_script != os_script:
            candidates.append(generic_script)

        if not candidates:
            raise ValueError(
                f"Script '{script_name}' not found. Available: {list(scripts.keys())}"
            )

        cwd = self.resolve_working_directory()
        last_exception = None

        for candidate in candidates:
            try:
                self.logger.info(f"Trying script: {candidate}")
                self.execute_command(candidate, cwd, additional_args)
                return
            except Exception as e:
                self.logger.error(f"Script execution failed: {candidate}")
                last_exception = e

        if last_exception:
            raise last_exception
