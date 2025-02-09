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
