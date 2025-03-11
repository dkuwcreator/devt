#!/usr/bin/env python
"""
devt/package/script.py

Script Execution

Provides a class to represent a script defined in a package manifest, and execute
it using subprocess.run() with the prepared arguments.
"""

import json
import os
import shlex
import shutil
import subprocess
from pathlib import Path
import tempfile
from typing import Any, Dict, List, Optional, Union
import logging

from dotenv import load_dotenv
import typer

from devt.cli.commands.env import resolve_env_file
from devt.constants import SUBPROCESS_ALLOWED_KEYS
from .utils import build_command_tokens

logger = logging.getLogger(__name__)


def get_path_from_registry() -> str:
    """Retrieve the System PATH first, then the User PATH, preserving their order."""
    import winreg

    system_path, user_path = "", ""

    try:
        # Retrieve System PATH from registry (global for all users)
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment",
            0,
            winreg.KEY_READ,
        ) as system_key:
            system_path, _ = winreg.QueryValueEx(system_key, "Path")
    except FileNotFoundError:
        pass  # No system path found, continue

    try:
        # Retrieve User PATH from registry (specific to current user)
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, r"Environment", 0, winreg.KEY_READ
        ) as user_key:
            user_path, _ = winreg.QueryValueEx(user_key, "Path")
    except FileNotFoundError:
        pass  # No user path found, continue

    # Merge while keeping order (System PATH first, then User PATH)
    all_paths = list(
        dict.fromkeys(system_path.split(";") + user_path.split(";"))
    ) # Remove duplicates
    return ";".join(filter(None, all_paths))


class CommandExecutionError(Exception):
    """
    Custom exception for wrapping command execution errors.
    """

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


# Path mapping for common working directories
CWD_PATH_MAPPING = {
    "workspace": Path.cwd(),
    "user": Path.home(),
    "temp": Path(tempfile.gettempdir()),
}


class Script:
    """
    Represents a command (or script) defined in a package manifest.
    Provides functionality to build its final command string and execute it.
    """

    def __init__(
        self,
        args: Union[str, List[str]],
        shell: Optional[Union[str, List[str]]] = None,
        cwd: Union[Path, str] = ".",
        env: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        self.args = args
        self.shell = shell
        self.cwd = self._map_cwd(cwd)
        self.env = env or {}
        # Filter kwargs based on allowed keys
        self.kwargs = {k: v for k, v in kwargs.items() if k in SUBPROCESS_ALLOWED_KEYS}
        logger.debug("Script instance created: %s", self.__dict__)

    def _map_cwd(self, cwd_value: Union[Path, str]) -> Path:
        """
        Map the script's working directory to a common value if provided.
        """
        if isinstance(cwd_value, str):
            parts = cwd_value.split('/', 1)
            base_key = parts[0]
            if base_key in CWD_PATH_MAPPING:
                base_path = CWD_PATH_MAPPING[base_key]
                if len(parts) == 2:
                    return base_path / parts[1]
                return base_path
        return Path(cwd_value)

    def resolve_cwd(self, base_dir: Path, auto_create: bool = False) -> Path:
        """
        Resolve the script's working directory relative to base_dir.
        """
        resolved = (
            self.cwd if self.cwd.is_absolute() else (base_dir / self.cwd).resolve()
        )
        if not (str(resolved).startswith(str(Path.home()))):
            raise ValueError(
                "Relative path cannot be resolved outside the home directory."
            )
        if not resolved.exists():
            if auto_create:
                logger.info("Auto-creating missing working directory '%s'.", resolved)
                resolved.mkdir(parents=True, exist_ok=True)
            else:
                logger.error("Working directory '%s' does not exist.", resolved)
                raise FileNotFoundError(
                    f"Working directory '{resolved}' does not exist."
                )
        if not resolved.is_dir():
            logger.error("Resolved path '%s' is not a directory.", resolved)
            raise NotADirectoryError(f"Resolved path '{resolved}' is not a directory.")
        logger.debug("Resolved working directory: %s", resolved)
        return resolved

    def resolve_env(self) -> Dict[str, str]:
        """
        Merge the current environment with the script's environment.
        """

        # 1) Load environment variables from .env in base_dir
        dotenv_path = resolve_env_file()
        if dotenv_path.is_file():
            logger.debug("Loading environment variables from %s", dotenv_path)
            load_dotenv(dotenv_path=dotenv_path)

        # 2) Merge them with self.env
        env = {**os.environ, **self.env} if self.env is not None else os.environ.copy()

        # 3) Update PATH on Windows with the latest System & User PATH from registry
        if os.name == 'nt':
            env["PATH"] = get_path_from_registry()
            logger.debug("Updated PATH from registry (System first, User second): %s", env["PATH"])

        logger.debug("Resolved environment variables.")
        return env

    def to_dict(self) -> Dict[str, Any]:
        """
        Serialize the Script instance to a dictionary.
        """
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
            cwd=Path(data["cwd"]),
            env=data.get("env", {}),
            **data.get("kwargs", {}),
        )

    def prepare_subprocess_args(
        self,
        base_dir: Path,
        shell: Optional[Union[str, List[str]]] = None,
        extra_args: Optional[Union[str, List[str]]] = None,
        auto_create_cwd: bool = False,
    ) -> Dict[str, Any]:
        """
        Prepare and return a dictionary of subprocess.run() arguments.
        """
        is_windows = os.name == "nt"
        is_posix = not is_windows

        resolved_cwd = self.resolve_cwd(base_dir, auto_create=auto_create_cwd)
        env = self.resolve_env()

        shell = shell if shell is not None else self.shell

        final_tokens = build_command_tokens(
            self.args, shell, extra_args, is_windows, is_posix
        )
        if shell == "":
            command_str = " ".join(final_tokens)
        else:
            command_str = (
                subprocess.list2cmdline(final_tokens)
                if is_windows
                else shlex.join(final_tokens)
            )
        logger.debug("Prepared command string: %s", command_str)

        final_config = {"args": command_str, "cwd": str(resolved_cwd), "env": env, "shell": False}
        final_config.update(self.kwargs)
        logger.debug("Final subprocess configuration prepared.")
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
        config = self.prepare_subprocess_args(
            base_dir, extra_args=extra_args, auto_create_cwd=auto_create_cwd
        )
        logger.info("Executing command: %s", config["args"])
        logger.info("Working directory: %s", self.cwd)
        logger.info("Environment variables: %s", self.env)
        logger.debug("Full subprocess configuration: %s", json.dumps(config, indent=3))

        terminal_width = min(shutil.get_terminal_size(fallback=(60, 20)).columns, 60)
        script_border = "═" * terminal_width

        # typer.secho(f"\n{script_border}", fg=typer.colors.BRIGHT_CYAN)
        typer.secho(f"\nExecuting command:\n{config['args']}", fg=typer.colors.BRIGHT_CYAN, bold=True)
        typer.secho(f"{script_border}\n", fg=typer.colors.BRIGHT_CYAN)
        result = subprocess.run(**config)

        # if result.returncode != 0:
        #     typer.secho(f"\n{script_border}", fg=typer.colors.YELLOW)
        #     typer.secho("Initial command failed! Attempting fallback execution...", fg=typer.colors.YELLOW, bold=True)
        #     fallback_config = self.prepare_subprocess_args(
        #     base_dir,
        #     shell="",
        #     extra_args=extra_args,
        #     auto_create_cwd=auto_create_cwd,
        #     )
        #     fallback_config["shell"] = True
        #     typer.secho(f"\n{script_border}", fg=typer.colors.CYAN)
        #     typer.secho(f"Fallback command:\n{fallback_config['args']}", fg=typer.colors.CYAN, bold=True)
        #     typer.secho(f"{script_border}\n", fg=typer.colors.CYAN)
        #     result = subprocess.run(**fallback_config)

        if result.returncode != 0:
            typer.secho(f"\n{script_border}", fg=typer.colors.BRIGHT_RED)
            typer.secho("The command execution failed.\n", fg=typer.colors.BRIGHT_RED, bold=True)
            logger.error("Command failed with return code %d", result.returncode)
            raise CommandExecutionError(
            "Command failed",
            result.returncode,
            stdout=getattr(result, "stdout", None),
            stderr=getattr(result, "stderr", None),
            )
        typer.secho(f"\n{script_border}", fg=typer.colors.GREEN)
        typer.secho("Command executed successfully.\n", fg=typer.colors.GREEN, bold=True)
        return result
