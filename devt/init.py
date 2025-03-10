import logging
import os
from pathlib import Path

from devt.constants import APP_NAME, USER_APP_DIR, WORKSPACE_APP_DIR

logger = logging.getLogger(__name__)

ENV_USER_APP_DIR = f"{APP_NAME.upper()}_USER_APP_DIR"
ENV_WORKSPACE_DIR = f"{APP_NAME.upper()}_WORKSPACE_APP_DIR"
ENV_TOOL_DIR = f"{APP_NAME.upper()}_TOOL_DIR"

def create_directories() -> None:
    """
    Creates the necessary directories for the application.
    If USER_APP_DIR does not exist, logs that it's the first use.
    Checks if WORKSPACE_APP_DIR exists, and if not, logs that it hasn't been initiated.
    """
    if not USER_APP_DIR.exists():
        logger.info("First time use detected. Initializing user application directory.")
    USER_APP_DIR.mkdir(parents=True, exist_ok=True)

    if not WORKSPACE_APP_DIR.exists():
        logger.info("Workspace has not yet been initiated.")
    else:
        logger.debug("Workspace directory exists.")


def setup_environment() -> None:
    """
    Prepares the environment: checks for first-time use,
    creates directories, sets environment variables,
    and ensures the setup is logged properly.
    """
    create_directories()
    os.environ[ENV_USER_APP_DIR] = str(USER_APP_DIR)
    os.environ[ENV_WORKSPACE_DIR] = str(WORKSPACE_APP_DIR)
    logger.debug("Environment variables set successfully.")
