from pathlib import Path
# from typer import get_app_dir
# from core.config import Config
# from .logger import logger
import os
import winreg

# Constants
APP_DATA_DIR = Path.cwd() / ".devt"
# APP_DATA_DIR = Path(get_app_dir(".devt"))
TOOLS_DIR = APP_DATA_DIR / "tools"
TEMP_DIR = APP_DATA_DIR / "temp"
LOGS_DIR = APP_DATA_DIR / "logs"
LOG_FILE = LOGS_DIR / "devt.log"

WORKSPACE_DIR = Path.cwd()
WORKSPACE_FILE_NAME = "workspace.json"


def set_user_environment_var(name: str, value: str):
    """
    Set a user environment variable that persists across sessions.

    Args:
        name (str): The name of the environment variable.
        value (str): The value of the environment variable.
    """
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
            # logger.info(f"Set user environment variable: {name}={value}")
    except Exception as e:
        # logger.error(f"Failed to set user environment variable {name}: {e}")
        pass

def setup_environment():
    """
    Initialize the environment by creating necessary directories and
    setting environment variables.
    """

    # Ensure directories exist
    APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
    TOOLS_DIR.mkdir(parents=True, exist_ok=True)
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    # Load the configuration
    # config = Config(APP_DATA_DIR)

    # Set environment variables for the current session
    os.environ["DEVT_APP_DATA_DIR"] = str(APP_DATA_DIR)
    os.environ["DEVT_TOOLS_DIR"] = str(TOOLS_DIR)
    os.environ["DEVT_WORKSPACE_DIR"] = str(WORKSPACE_DIR)

    # Set user-level environment variables
    set_user_environment_var("DEVT_APP_DATA_DIR", str(APP_DATA_DIR))
    set_user_environment_var("DEVT_TOOLS_DIR", str(TOOLS_DIR))
    set_user_environment_var("DEVT_WORKSPACE_DIR", str(WORKSPACE_DIR))

    # logger.info("Environment variables set successfully")
