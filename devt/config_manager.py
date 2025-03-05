import inspect
import logging
import os
import subprocess
import platform
from pathlib import Path

import typer

from devt.utils import (
    load_json,
    load_manifest,
    merge_configs,
    find_file_type,
    save_json,
)

logger = logging.getLogger(__name__)

# Application Constants
APP_NAME = os.environ.get("APP_NAME", "devt")
REGISTRY_FILE_NAME = "registry.json"
WORKSPACE_FILE_NAME = "workspace.json"

# Default Global Configuration
DEFAULT_CONFIG = {
    "scope": "user",
    "log_level": "WARNING",
    "log_format": "default",
    "auto_sync": True,
}

# Directories and Files (User)
USER_APP_DIR = Path(typer.get_app_dir(f".{APP_NAME}"))
USER_REGISTRY_DIR = USER_APP_DIR / "registry"
CONFIG_FILE = USER_APP_DIR / "config.json"
ENV_USER_APP_DIR = f"{APP_NAME.upper()}_USER_APP_DIR"

# Directories and Files (Workspace)
WORKSPACE_APP_DIR = Path.cwd()
WORKSPACE_REGISTRY_DIR = WORKSPACE_APP_DIR / ".registry"
WORKSPACE_REGISTRY_FILE = WORKSPACE_REGISTRY_DIR / REGISTRY_FILE_NAME

# Temporary directory
TEMP_DIR = os.environ.get("TEMP", "/tmp")
ENV_WORKSPACE_DIR = f"{APP_NAME.upper()}_WORKSPACE_APP_DIR"
ENV_TOOL_DIR = f"{APP_NAME.upper()}_TOOL_DIR"


def set_user_environment_var(name: str, value: str) -> None:
    """
    Persists a user environment variable across sessions in a cross-platform way.
    """
    system = platform.system()
    
    try:
        if system == "Windows":
            import winreg
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_SET_VALUE
            ) as key:
                winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
            logger.debug("Set user environment variable on Windows: %s=%s", name, value)
        
        elif system in ["Linux", "Darwin"]:  # Darwin is macOS
            bashrc_path = os.path.expanduser("~/.bashrc")
            zshrc_path = os.path.expanduser("~/.zshrc")

            # Export variable in the shell profile
            export_command = f'export {name}="{value}"\n'

            # Add it to ~/.bashrc and ~/.zshrc to persist it
            for rc_path in [bashrc_path, zshrc_path]:
                if os.path.exists(rc_path):
                    with open(rc_path, "a") as f:
                        f.write(export_command)

            # Also set it for the current session
            os.environ[name] = value

            logger.debug("Set user environment variable on Linux/macOS: %s=%s", name, value)
        else:
            logger.warning("Unsupported OS: %s. Cannot persist environment variable.", system)

    except Exception as e:
        logger.error("Failed to set user environment variable %s: %s", name, e)


def create_directories() -> None:
    """
    Creates the necessary directories for the application.
    """
    USER_APP_DIR.mkdir(parents=True, exist_ok=True)


def initialize_user_config() -> None:
    """
    Creates or updates the persistent user configuration file.
    """
    if not CONFIG_FILE.exists():
        save_json(CONFIG_FILE, DEFAULT_CONFIG)
        logger.debug("Created configuration file at %s", CONFIG_FILE)
    else:
        config = load_json(CONFIG_FILE)
        updated = merge_configs(DEFAULT_CONFIG, config)
        save_json(CONFIG_FILE, updated)
        logger.debug("Updated configuration file at %s", CONFIG_FILE)


def setup_environment() -> None:
    """
    Prepares the environment: creates directories, sets essential environment variables,
    and ensures the user configuration file is initialized.
    """
    create_directories()
    os.environ[ENV_USER_APP_DIR] = str(USER_APP_DIR)
    os.environ[ENV_WORKSPACE_DIR] = str(WORKSPACE_APP_DIR)
    set_user_environment_var(ENV_USER_APP_DIR, str(USER_APP_DIR))
    set_user_environment_var(ENV_WORKSPACE_DIR, str(WORKSPACE_APP_DIR))
    initialize_user_config()
    logger.debug("Environment variables set successfully.")


# Dynamically extract allowed arguments for subprocess methods
RUN_KEYS = set(inspect.signature(subprocess.run).parameters.keys())
POPEN_KEYS = set(inspect.signature(subprocess.Popen).parameters.keys())
SUBPROCESS_ALLOWED_KEYS = RUN_KEYS | POPEN_KEYS


def get_effective_config(runtime_options: dict) -> dict:
    """
    Merges default, user, workspace, and runtime configurations into an effective configuration.
    """
    logger.debug("Merging configurations for effective config.")
    setup_environment()
    user_config = load_json(CONFIG_FILE)
    logger.debug("Loaded user configuration: %s", user_config)

    workspace_config = {}
    workspace_file = find_file_type("manifest", WORKSPACE_APP_DIR)
    if workspace_file:
        try:
            workspace_data = load_manifest(workspace_file)
            workspace_config = workspace_data.get("config", {})
            logger.debug("Loaded workspace configuration: %s", workspace_config)
        except Exception as e:
            typer.echo(f"Error loading workspace config: {e}")
            logger.error(
                "Error loading workspace config from %s: %s", workspace_file, e
            )
    else:
        logger.debug(
            "No workspace manifest found; using empty workspace configuration."
        )

    effective_config = merge_configs(user_config, workspace_config, runtime_options)
    logger.info("Effective configuration computed.")
    return effective_config


def configure_global_logging(effective_config: dict) -> None:
    """
    Sets up global logging based on the provided configuration.
    """
    log_level = effective_config.get("log_level", "WARNING")
    log_format = effective_config.get("log_format", "default")
    logger.info(
        "Configuring global logging with level: %s, format: %s", log_level, log_format
    )

    from devt.logger_manager import configure_logging, configure_formatter

    configure_logging(log_level)
    configure_formatter(log_format)
    logger.info("Global logging configured.")
