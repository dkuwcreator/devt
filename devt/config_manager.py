# devt/config_manager.py
import inspect
import logging
import os
import subprocess
import winreg
from pathlib import Path
import typer

from devt.utils import load_json, load_manifest, merge_configs, find_file_type, save_json

logger = logging.getLogger(__name__)

# Application Name
APP_NAME = os.environ.get("APP_NAME", "devt")

# File Names
REGISTRY_FILE_NAME = "registry.json"
WORKSPACE_FILE_NAME = "workspace.json"

# Directories and Constants
USER_APP_DIR = Path(typer.get_app_dir(f".{APP_NAME}"))
USER_REGISTRY_DIR = USER_APP_DIR / "registry"
USER_TOOLS_DIR = USER_REGISTRY_DIR / "tools"
USER_REPOS_DIR = USER_REGISTRY_DIR / "repos"
USER_REGISTRY_FILE = USER_REGISTRY_DIR / REGISTRY_FILE_NAME

# Persistent config file
CONFIG_FILE = USER_APP_DIR / "config.json"

# Temporary directory
TEMP_DIR = os.environ.get("TEMP", "/tmp")

WORKSPACE_APP_DIR = Path.cwd()
WORKSPACE_REGISTRY_DIR = WORKSPACE_APP_DIR / ".registry"
WORKSPACE_TOOLS_DIR = WORKSPACE_REGISTRY_DIR / "tools"
WORKSPACE_REPOS_DIR = WORKSPACE_REGISTRY_DIR / "repos"
WORKSPACE_REGISTRY_FILE = WORKSPACE_REGISTRY_DIR / REGISTRY_FILE_NAME

# Environment Variable Names
ENV_USER_APP_DIR = f"{APP_NAME.upper()}_USER_APP_DIR"
ENV_WORKSPACE_DIR = f"{APP_NAME.upper()}_WORKSPACE_APP_DIR"


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
    save_json(CONFIG_FILE, {})
    logger.info("Environment variables set successfully")


# Dynamically extract allowed arguments for subprocess.run() and subprocess.Popen
RUN_KEYS = set(inspect.signature(subprocess.run).parameters.keys())
POPEN_KEYS = set(inspect.signature(subprocess.Popen).parameters.keys())
SUBPROCESS_ALLOWED_KEYS = RUN_KEYS | POPEN_KEYS


def get_effective_config(runtime_options: dict) -> dict:
    """
    Merges default, user, workspace, and runtime configurations to produce
    the effective configuration.
    """
    # Set up environment (directories, env vars, etc.)
    setup_environment()

    # 1. Default configuration.
    default_config = {"scope": "user", "log_level": "WARNING", "log_format": "default"}

    # 2. User configuration from persistent file.
    user_config = load_json(CONFIG_FILE)

    # 3. Workspace configuration (if available).
    workspace_file = find_file_type("manifest", WORKSPACE_APP_DIR)
    try:
        if workspace_file:
            workspace_data = load_manifest(workspace_file)
            workspace_config = workspace_data.get("config", {})
        else:
            workspace_config = {}
    except Exception as e:
        typer.echo(f"Error loading workspace config: {e}")
        workspace_config = {}
        
    # 4. Merge configurations in order: default < user < workspace < runtime.
    effective_config = merge_configs(default_config, user_config, workspace_config, runtime_options)
    return effective_config


def configure_global_logging(effective_config: dict) -> None:
    """
    Configures global logging based on the effective configuration.
    """
    log_level = effective_config.get("log_level", "WARNING")
    log_format = effective_config.get("log_format", "default")
    # Import locally to avoid circular dependency.
    from devt.logger_manager import configure_logging, configure_formatter
    configure_logging(log_level)
    configure_formatter(log_format)
