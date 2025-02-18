# devt/executor.py
"""
A flexible script runner with type hints and improved error handling.

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
  - shell:
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

import inspect
import logging
import os
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from utils import merge_configs, resolve_rel_path

# Configure a basic logger (logs at INFO level by default)
logger = logging.getLogger(__name__)

IS_WINDOWS = os.name == "nt"
IS_POSIX = not IS_WINDOWS
CURRENT_OS = "posix" if IS_POSIX else "windows"

# Dynamically extract allowed arguments for subprocess.run() and subprocess.Popen()
RUN_KEYS = set(inspect.signature(subprocess.run).parameters.keys())
POPEN_KEYS = set(inspect.signature(subprocess.Popen).parameters.keys())
# Combine both to get a full set of allowed arguments
ALLOWED_KEYS = RUN_KEYS | POPEN_KEYS


# TODO: BEGIN - Use the CommandExecutionError class
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


# TODO: END


def needs_shell_fallback(tokens: Union[str, List[str]]) -> bool:
    # On Windows, built-in commands (like echo) are executed by cmd.exe,
    # so we do not need to wrap the command.
    if os.name == "nt":
        return False
    if isinstance(tokens, list):
        first_token = tokens[0]
    else:
        first_token = shlex.split(tokens, posix=IS_POSIX)[0]
    return shutil.which(first_token) is None



def default_shell_prefix(command: str) -> list:
    if os.name == "nt":
        # Try to find PowerShell (pwsh or powershell)
        shell_prog = shutil.which("pwsh") or shutil.which("powershell")
        if shell_prog:
            # Removed the ampersand; simply pass the command.
            return [shell_prog, "-Command", command]
        else:
            # Fallback to cmd.exe
            cmd_path = shutil.which("cmd")
            if not cmd_path:
                raise FileNotFoundError("Cannot find cmd.exe on your system.")
            return [cmd_path, "/c", command]
    else:
        return ["bash", "-c", command]

def to_tokens(
    val: Union[str, List[str]], *, split: bool = True
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
    return shlex.split(val, posix=IS_POSIX) if split else [val]

class ManifestRunner:
    """Class-based runner that loads and interprets a YAML manifest."""

    def __init__(self, base_dir: Path, scripts_dict: Dict[str, Any]) -> None:
        self.base_dir = base_dir
        self.scripts_dict = scripts_dict

    def _get_script_entry(
        self, scripts: Dict[str, Any], script_key: str
    ) -> Dict[str, Any]:
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

    def _apply_cwd(self, merged_config: Dict[str, Any]) -> None:
        """Resolve and apply the 'cwd' key if present."""
        if "cwd" in merged_config:
            final_cwd = resolve_rel_path(self.base_dir, merged_config["cwd"])
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

    def _prepare_args_base(
        self,
        merged_config: Dict[str, Any],
        extra_args: Optional[Union[str, List[str]]] = None,
    ) -> str:
        """
        Build the final args string, applying shell wrapper if needed,
        and construct a properly formatted shell command string.
        """
        args = merged_config["args"]
        shell_wrapper = merged_config.get("shell", None)

        # Normalize extra arguments (always split them)
        extra_tokens = to_tokens(extra_args, posix=IS_POSIX, split=True)

        if shell_wrapper:
            # Keep the main command as a single token
            wrapper_tokens = to_tokens(shell_wrapper, posix=IS_POSIX, split=True)
            main_token = args if isinstance(args, str) else " ".join(args)
            final_tokens = wrapper_tokens + [main_token] + extra_tokens
        else:
            # Split the main command
            main_tokens = to_tokens(args, posix=IS_POSIX, split=True)
            final_tokens = main_tokens + extra_tokens

        # Reassemble tokens into a shell-ready command string
        return (
            subprocess.list2cmdline(final_tokens)
            if IS_WINDOWS
            else shlex.join(final_tokens)
        )

    def _prepare_args_with_default_shell(
        self,
        merged_config: Dict[str, Any],
        extra_args: Optional[Union[str, List[str]]] = None,
    ) -> str:
        """
        Build the final args string, applying shell wrapper if needed,
        and construct a properly formatted shell command string.
        """
        args = merged_config["args"]
        args = default_shell_prefix(args)

        # Normalize extra arguments (always split them)
        extra_tokens = to_tokens(extra_args, posix=IS_POSIX, split=True)

        final_tokens = args + extra_tokens

        # Reassemble tokens into a shell-ready command string
        return (
            subprocess.list2cmdline(final_tokens)
            if IS_WINDOWS
            else shlex.join(final_tokens)
        )

    def _execute_script(
        self,
        config: Dict[str, Any],
    ) -> None:
        # Apply working directory
        self._apply_cwd(config)

        # Merge environment
        self._apply_env(config)

        # Always run with shell=True
        config["shell"] = True

        # Filter out any kwargs that subprocess.run() doesn't accept
        config = self._filter_allowed_keys(config)
        logger.info(f"Executing command: {config['args']}")
        logger.debug(f"Final configuration: {config}")
        return subprocess.run(**config)

    def run_shell_fallback(
        self,
        script_name: str,
        extra_args: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> subprocess.CompletedProcess:
        """
        Try executing the command in its appropriate OS shell first.
        If execution fails, fallback to a general execution mode.
        """
        merged_config = self._get_script_entry(self.scripts_dict, script_name)
        logger.debug("Merged config for '%s': %s", script_name, merged_config)
        if "args" not in merged_config:
            raise ValueError("No 'args' provided in the configuration for this script.")
        merged_config = merge_configs(merged_config, kwargs)

        if "shell" not in merged_config and needs_shell_fallback(merged_config["args"]):
            try:
                command = self._prepare_args_with_default_shell(
                    merged_config, extra_args
                )
                self._execute_script({**merged_config, "args": command})
            except subprocess.CalledProcessError:
                self.logger.warning("Shell execution failed. Falling back.")
                command = self._prepare_args_base(merged_config, extra_args)
                self._execute_script({**merged_config, "args": command})
        else:
            command = self._prepare_args_base(merged_config, extra_args)
            self._execute_script({**merged_config, "args": command})

    def run_script(
        self,
        script_name: str,
        extra_args: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> subprocess.CompletedProcess:
        """
        Build and run the specified script from the manifest.
        Additional kwargs are forwarded to subprocess.run.

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
        logger.debug("Merged config for '%s': %s", script_name, merged_config)
        if "args" not in merged_config:
            raise ValueError("No 'args' provided in the configuration for this script.")
        # Prepare final args
        merged_config["args"] = self._prepare_args_base(merged_config, extra_args)
        # Merge any extra kwargs (like 'check=True', etc.)
        final_config = merge_configs(merged_config, kwargs)
        self._execute_script(final_config)
