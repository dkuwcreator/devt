# devt/config.py
import inspect
import logging
import os
from pathlib import Path
import subprocess
import winreg
import typer

logger = logging.getLogger(__name__)

app_name = os.environ.get("APP_NAME", "devt")

REGISTRY_FILE_NAME = "registry.json"
WORKSPACE_FILE_NAME = "workspace.json"

# Directories and Constants
USER_APP_DIR = Path(typer.get_app_dir(f".{app_name}"))
USER_REGISTRY_DIR = USER_APP_DIR / "registry"
USER_TOOLS_DIR = USER_REGISTRY_DIR / "tools"
USER_REPOS_DIR = USER_REGISTRY_DIR / "repos"
USER_REGISTRY_FILE = USER_REGISTRY_DIR / REGISTRY_FILE_NAME

# Get the temporary directory for the current os
TEMP_DIR = os.environ.get("TEMP", "/tmp")


WORKSPACE_APP_DIR = Path.cwd()
WORKSPACE_REGISTRY_DIR = WORKSPACE_APP_DIR / ".registry"
WORKSPACE_TOOLS_DIR = WORKSPACE_REGISTRY_DIR / "tools"
WORKSPACE_REPOS_DIR = WORKSPACE_REGISTRY_DIR / "repos"
WORKSPACE_REGISTRY_FILE = WORKSPACE_REGISTRY_DIR / REGISTRY_FILE_NAME

# ENVIRONMENT VARIABLE NAMES
ENV_USER_APP_DIR = f"{app_name.upper()}_USER_APP_DIR"
ENV_WORKSPACE_DIR = f"{app_name.upper()}_WORKSPACE_APP_DIR"


def set_user_environment_var(name: str, value: str):
    """
    Set a user environment variable that persists across sessions.
    """
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
            logger.info("Set user environment variable: %s=%s", name, value)
    except OSError:
        logger.error("Failed to set user environment variable %s", name)


def setup_environment():
    """
    Initialize the environment by creating necessary directories and
    setting environment variables.
    """
    USER_APP_DIR.mkdir(parents=True, exist_ok=True)
    os.environ[ENV_USER_APP_DIR] = str(USER_APP_DIR)
    set_user_environment_var(ENV_USER_APP_DIR, str(USER_APP_DIR))
    logger.info("Environment variables set successfully")


# Dynamically extract allowed arguments for subprocess.run() and subprocess.Popen()
RUN_KEYS = set(inspect.signature(subprocess.run).parameters.keys())
POPEN_KEYS = set(inspect.signature(subprocess.Popen).parameters.keys())
# Combine both to get a full set of allowed arguments
SUBPROCESS_ALLOWED_KEYS = RUN_KEYS | POPEN_KEYS

# def list_executables_in_path():
#     executables = []
#     for path_dir in os.environ.get("PATH", "").split(os.pathsep):
#         p = Path(path_dir)
#         if not p.is_dir():
#             continue
#         for file in p.iterdir():
#             if file.is_file() and os.access(file, os.X_OK):
#                 executables.append(str(file))
#     return executables

# print(list_executables_in_path())
