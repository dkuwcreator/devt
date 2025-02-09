# devt/executor.py
"""
Executor module: Provides helper functions for finding a tool,
resolving the correct script, determining the working directory, and executing commands.
"""

import asyncio
import os
import shlex
import shutil
import subprocess
import logging
from pathlib import Path
import sys
from typing import Any, Dict, Optional, List, Tuple, Union

logger = logging.getLogger(__name__)


class CommandExecutionError(Exception):
    """
    Custom exception for wrapping command execution errors.
    """
    def __init__(self, message: str, returncode: int, stdout: Optional[str] = None, stderr: Optional[str] = None) -> None:
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
                     Typically the entry contains a nested "manifest" object,
                     a "location" (relative to the registry file), etc.
        :param registry_dir: Path to the registry's base directory.
        :param env: Optional dictionary of environment variables.
        :param timeout: Optional timeout (in seconds) for executing commands.
        """
        self.tool = tool
        self.registry_dir = registry_dir
        self.env = env or os.environ.copy()
        self.timeout = timeout
        self.logger = logger

    def should_use_shell(self, command: str) -> bool:
        """
        Returns True if the command string contains shell operators.
        This indicates that the command should be run via the shell.
        """
        shell_operators = [';', '&&', '||', '|']
        return any(op in command for op in shell_operators)

    def build_command(self, command: str, additional_args: Optional[List[str]] = None) -> Tuple[bool, Union[str, List[str]]]:
        """
        Given a command string and optional additional arguments, return a tuple:
          (use_shell, built_command)
        - If the command contains shell operators, then use_shell is True and
          built_command is the full string (with additional arguments appended).
        - Otherwise, built_command is a list of tokens (using shlex.split).
        """
        if self.should_use_shell(command):
            # If using shell, append additional args to the command string.
            if additional_args:
                command = command + " " + " ".join(additional_args)
            return True, command
        else:
            # Otherwise, split the command into tokens.
            cmd_list = shlex.split(command)
            if additional_args:
                cmd_list.extend(additional_args)
            return False, cmd_list

    def resolve_working_directory(self) -> Path:
        """
        Determine the working directory for executing the command.
        
        Uses the tool's "location" to locate the manifest file (if provided),
        then looks up "base_dir" from the manifest. If base_dir is a relative path,
        it is considered relative to the manifest file's location. If base_dir is absolute,
        that directory is used directly.
        """
        tool_location = self.tool.get("location")
        if tool_location:
            tool_manifest_path = Path(self.registry_dir) / tool_location
            tool_dir = tool_manifest_path.parent if tool_manifest_path.is_file() else tool_manifest_path
        else:
            tool_dir = self.registry_dir

        # Look for base_dir in the nested manifest if present; otherwise at top level.
        if "manifest" in self.tool:
            base_dir = self.tool.get("manifest", {}).get("base_dir", ".")
        else:
            base_dir = self.tool.get("base_dir", ".")
        base_dir_path = Path(base_dir)
        if base_dir_path.is_absolute():
            new_cwd = base_dir_path
        else:
            new_cwd = (tool_dir / base_dir).resolve()
        if not new_cwd.is_dir():
            self.logger.warning("Working directory '%s' is not a directory. Falling back to tool directory.", new_cwd)
            new_cwd = tool_dir
        return new_cwd

    def _execute_command(self, command: str, additional_args: Optional[List[str]] = None) -> None:
        """
        Build and execute one candidate command.
        Uses our build_command() helper to decide whether to run via shell.
        On Windows, if not using the shell and if the first token isn’t an external executable,
        the command is run via "cmd /c" (or via PowerShell if it ends with ".ps1").
        """
        use_shell, built_command = self.build_command(command, additional_args)
        cwd = self.resolve_working_directory()
        self.logger.info("Using working directory: %s", cwd)
        if not cwd.exists():
            raise ValueError(f"Working directory '{cwd}' does not exist.")
        if use_shell:
            self.logger.info("Executing command with shell: %s", built_command)
            subprocess.run(built_command, cwd=cwd, env=self.env, timeout=self.timeout, check=True, shell=True)
        else:
            # built_command is a list
            if os.name == "nt" and isinstance(built_command, list):
                if built_command and built_command[0].lower().endswith(".ps1"):
                    built_command = ["powershell", "-ExecutionPolicy", "Bypass", "-File"] + built_command
                elif not shutil.which(built_command[0]):
                    built_command = ["cmd", "/c"] + built_command
            self.logger.info("Executing command: %s", built_command)
            subprocess.run(built_command, cwd=cwd, env=self.env, timeout=self.timeout, check=True, stdout=sys.stdout, stderr=sys.stderr)

    async def _execute_command_async(self, command: str, additional_args: Optional[List[str]] = None) -> None:
        """
        Asynchronous version of _execute_command.
        If using shell, create a subprocess via create_subprocess_shell;
        otherwise, use create_subprocess_exec.
        """
        use_shell, built_command = self.build_command(command, additional_args)
        cwd = self.resolve_working_directory()
        self.logger.info("Using working directory: %s", cwd)
        if not cwd.exists():
            raise ValueError(f"Working directory '{cwd}' does not exist.")
        if use_shell:
            self.logger.info("Executing async command with shell: %s", built_command)
            process = await asyncio.create_subprocess_shell(
                built_command, cwd=str(cwd), env=self.env
            )
        else:
            if os.name == "nt" and isinstance(built_command, list):
                if built_command and built_command[0].lower().endswith(".ps1"):
                    built_command = ["powershell", "-ExecutionPolicy", "Bypass", "-File"] + built_command
                elif not shutil.which(built_command[0]):
                    built_command = ["cmd", "/c"] + built_command
            self.logger.info("Executing async command: %s", built_command)
            process = await asyncio.create_subprocess_exec(
                *built_command, cwd=str(cwd), env=self.env,
                stdout=None, stderr=None  # Inherit parent's streams.
            )
        await process.wait()
        if process.returncode != 0:
            self.logger.error("Async command failed with exit code %s", process.returncode)
            raise CommandExecutionError("Async command execution failed", process.returncode)
        self.logger.info("Async command executed successfully.")

    def execute_script(self, script_name: str, additional_args: Optional[List[str]] = None) -> None:
        """
        Resolve, build, and execute a script command for the tool.
        
        The resolution works as follows:
          1. The executor first looks for an OS-specific script (under the key for your OS, e.g. "windows" or "posix")
             in the manifest’s "scripts" object.
          2. If found, that candidate is tried first.
          3. If the OS-specific candidate fails and a generic (non‑OS‑specific) script is also defined,
             the generic version is then tried.
          4. If no OS‑specific candidate exists, the generic version (if any) is used.
        """
        shell = "windows" if os.name == "nt" else "posix"
        # Get the scripts dictionary from either the nested manifest or top-level.
        if "manifest" in self.tool:
            scripts = self.tool.get("manifest", {}).get("scripts", {})
        else:
            scripts = self.tool.get("scripts", {})
        os_specific = None
        generic = None
        if isinstance(scripts.get(shell), dict):
            os_specific = scripts.get(shell).get(script_name)
        if script_name in scripts:
            generic = scripts.get(script_name)
        candidates: List[str] = []
        if os_specific:
            candidates.append(os_specific)
            if generic and generic != os_specific:
                candidates.append(generic)
        elif generic:
            candidates.append(generic)
        else:
            raise ValueError(f"Script '{script_name}' not found. Available: {list(scripts.keys())}")
        last_exception = None
        for candidate in candidates:
            try:
                self.logger.info("Trying candidate script: %s", candidate)
                self._execute_command(candidate, additional_args)
                return  # Success!
            except Exception as e:
                self.logger.error("Candidate script failed: %s", candidate)
                last_exception = e
        if last_exception:
            raise last_exception
        else:
            raise ValueError(f"Script '{script_name}' not found.")

    async def execute_script_async(self, script_name: str, additional_args: Optional[List[str]] = None) -> None:
        """
        Asynchronously resolve and execute a script command for the tool.
        Follows the same candidate (OS‑specific then generic) fallback logic as execute_script().
        """
        shell = "windows" if os.name == "nt" else "posix"
        if "manifest" in self.tool:
            scripts = self.tool.get("manifest", {}).get("scripts", {})
        else:
            scripts = self.tool.get("scripts", {})
        os_specific = None
        generic = None
        if isinstance(scripts.get(shell), dict):
            os_specific = scripts.get(shell).get(script_name)
        if script_name in scripts:
            generic = scripts.get(script_name)
        candidates: List[str] = []
        if os_specific:
            candidates.append(os_specific)
            if generic and generic != os_specific:
                candidates.append(generic)
        elif generic:
            candidates.append(generic)
        else:
            raise ValueError(f"Script '{script_name}' not found. Available: {list(scripts.keys())}")
        last_exception = None
        for candidate in candidates:
            try:
                self.logger.info("Trying async candidate script: %s", candidate)
                await self._execute_command_async(candidate, additional_args)
                return  # Success!
            except Exception as e:
                self.logger.error("Async candidate script failed: %s", candidate)
                last_exception = e
        if last_exception:
            raise last_exception
        else:
            raise ValueError(f"Script '{script_name}' not found.")
