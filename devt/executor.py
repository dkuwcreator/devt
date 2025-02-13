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

from devt.utils import merge_configs

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


class ManifestRunner:
    """Class-based runner that loads and interprets a YAML manifest."""

    def __init__(self, base_dir: Path, scripts_dict: Dict[str, Any]) -> None:
        self.base_dir = base_dir
        self.scripts_dict = scripts_dict
        self.current_os = "posix" if os.name == "posix" else "windows"

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

    def _get_script_entry(
        self, scripts: Dict[str, Any], script_key: str
    ) -> Dict[str, Any]:
        os_specific = scripts.get(self.current_os)
        if isinstance(os_specific, (str, list)):
            scripts[self.current_os] = {"args": os_specific}
        elif os_specific is not None and not isinstance(os_specific, dict):
            raise ValueError("OS-specific scripts must be strings, lists, or dicts.")
        
        base = merge_configs(scripts, scripts.get(self.current_os, {}))
        entry = base.get(script_key)
        if entry is None:
            raise ValueError(f"Script '{script_key}' not found in manifest.")

        if isinstance(entry, (str, list)):
            entry = {"args": entry}
        elif not isinstance(entry, dict):
            raise ValueError("Script entry must be a string, list, or dict.")

        os_specific = entry.get(self.current_os)
        if isinstance(os_specific, (str, list)):
            entry[self.current_os] = {"args": os_specific}
        elif os_specific is not None and not isinstance(os_specific, dict):
            raise ValueError("OS-specific script entry must be a string, list, or dict.")

        entry = merge_configs(entry, entry.get(self.current_os, {}))
        return merge_configs(base, entry)

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

    def _apply_cwd(self, merged_config: Dict[str, Any]) -> None:
        """Resolve and apply the 'cwd' key if present."""
        if "cwd" in merged_config:
            final_cwd = (self.base_dir / Path(merged_config["cwd"])).resolve()
        else:
            final_cwd = self.base_dir

        if not final_cwd.is_dir():
            raise FileNotFoundError(f"Working directory '{final_cwd}' does not exist.")

        merged_config["cwd"] = str(final_cwd)

    def _apply_env(self, merged_config: Dict[str, Any]) -> None:
        """Merge environment variables if 'env' key is present."""
        if "env" in merged_config:
            merged_config["env"] = {**os.environ, **merged_config["env"]}

    def _filter_allowed_keys(self, merged_config: Dict[str, Any]) -> Dict[str, Any]:
        """Filter configuration so that only keys accepted by subprocess.run() remain."""
        return {k: merged_config[k] for k in ALLOWED_KEYS if k in merged_config}

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
        # Build merged config
        merged_config = self._get_script_entry(self.scripts_dict, script_name)

        # Always run with shell=True
        merged_config["shell"] = True

        # Prepare final args
        merged_config["args"] = self._prepare_args(merged_config, extra_args)

        # Apply working directory
        self._apply_cwd(merged_config)

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
        # logger.info("Running script '%s' with config: %s", script_name, final_config)
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
