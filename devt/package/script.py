import os
import shlex
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import logging

from devt.config_manager import SUBPROCESS_ALLOWED_KEYS
from .utils import build_command_tokens

logger = logging.getLogger(__name__)


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
        # Filter kwargs based on allowed keys
        self.kwargs = {k: v for k, v in kwargs.items() if k in SUBPROCESS_ALLOWED_KEYS}

    def resolve_cwd(self, base_dir: Path, auto_create: bool = False) -> Path:
        """
        Resolve the script's working directory relative to base_dir.
        """
        resolved = self.cwd if self.cwd.is_absolute() else (base_dir / self.cwd).resolve()
        if not str(resolved).startswith(str(base_dir.resolve())):
            raise ValueError("Relative path cannot be outside of the package directory.")
        if not resolved.exists():
            if auto_create:
                logger.info("Auto-creating missing working directory '%s'.", resolved)
                resolved.mkdir(parents=True, exist_ok=True)
            else:
                logger.error("Working directory '%s' does not exist.", resolved)
                raise FileNotFoundError(f"Working directory '{resolved}' does not exist.")
        if not resolved.is_dir():
            logger.error("Resolved path '%s' is not a directory.", resolved)
            raise NotADirectoryError(f"Resolved path '{resolved}' is not a directory.")
        logger.debug("Resolved working directory: %s", resolved)
        return resolved

    def resolve_env(self) -> Dict[str, str]:
        """
        Merge the current environment with the script's environment.
        """
        env = {**os.environ, **self.env} if self.env is not None else os.environ.copy()
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
            command_str = ' '.join(final_tokens)
        else:
            command_str = (
                subprocess.list2cmdline(final_tokens) if is_windows else shlex.join(final_tokens)
            )
        logger.debug("Prepared command string: %s", command_str)

        final_config = {
            "args": command_str,
            "cwd": str(resolved_cwd),
            "env": env,
            "shell": True,  # Always run with shell=True as per design.
        }
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
        logger.debug("Subprocess configuration: %s", config)
        result = subprocess.run(**config)
        if result.returncode != 0:
            # Try a fallback execution without shell wrapper
            fallback_config = self.prepare_subprocess_args(
                base_dir, shell="", extra_args=extra_args, auto_create_cwd=auto_create_cwd
            )
            logger.info("Executing fallback command: %s", fallback_config["args"])
            logger.debug("Fallback subprocess configuration: %s", fallback_config)
            result = subprocess.run(**fallback_config)
        if result.returncode != 0:
            logger.error("Command failed with return code %d", result.returncode)
            raise CommandExecutionError(
                "Command failed",
                result.returncode,
                stdout=getattr(result, "stdout", None),
                stderr=getattr(result, "stderr", None),
            )
        logger.info("Command executed successfully with return code %d", result.returncode)
        return result
