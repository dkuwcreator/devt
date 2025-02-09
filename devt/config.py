# devt/config.py
import logging
import os
from pathlib import Path
import winreg
import typer

# Directories and Constants
USER_APP_DIR = Path(typer.get_app_dir(".devt"))
REGISTRY_DIR = USER_APP_DIR / "registry"
TOOLS_DIR = REGISTRY_DIR / "tools"
REPOS_DIR = REGISTRY_DIR / "repos"
REGISTRY_FILE = REGISTRY_DIR / "registry.json"
TEMP_DIR = USER_APP_DIR / "temp"
LOGS_DIR = USER_APP_DIR / "logs"
LOG_FILE = LOGS_DIR / "devt.log"

WORKSPACE_DIR = Path.cwd()
WORKSPACE_REGISTRY_DIR = WORKSPACE_DIR / ".registry"
WORKSPACE_TOOLS_DIR = WORKSPACE_REGISTRY_DIR / "tools"
WORKSPACE_REPOS_DIR = WORKSPACE_REGISTRY_DIR / "repos"
WORKSPACE_REGISTRY_FILE = WORKSPACE_REGISTRY_DIR / "registry.json"
WORKSPACE_FILE = WORKSPACE_DIR / "workspace.json"

# Ensure directories exist
USER_APP_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# Convert the string (e.g., "DEBUG") to a numeric level (e.g., logging.DEBUG).
LOG_LEVELS = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
}

# Logger setup
logger = logging.getLogger("devt")
logger.setLevel(logging.WARNING)
file_handler = logging.FileHandler(LOG_FILE)
stream_handler = logging.StreamHandler()
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
file_handler.setFormatter(formatter)
stream_handler.setFormatter(formatter)
logger.addHandler(file_handler)
logger.addHandler(stream_handler)


def configure_logging(log_level: str):
    """
    Configure the logging level based on the provided log level string.
    """
    level = LOG_LEVELS.get(log_level.upper())
    if level is None:
        logger.warning(
            "Log level '%s' is not recognized. Defaulting to WARNING.", log_level
        )
        level = logging.WARNING
    logger.setLevel(level)


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
    TOOLS_DIR.mkdir(parents=True, exist_ok=True)
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    os.environ["DEVT_USER_APP_DIR"] = str(USER_APP_DIR)
    os.environ["DEVT_WORKSPACE_DIR"] = str(WORKSPACE_DIR)

    set_user_environment_var("DEVT_USER_APP_DIR", str(USER_APP_DIR))
    set_user_environment_var("DEVT_WORKSPACE_DIR", str(WORKSPACE_DIR))

    logger.info("Environment variables set successfully")


setup_environment()
