# devt/config.py
import logging
import os
from pathlib import Path
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

# Logger setup
logger = logging.getLogger("devt")
logger.setLevel(logging.INFO)
file_handler = logging.FileHandler(LOG_FILE)
stream_handler = logging.StreamHandler()
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
file_handler.setFormatter(formatter)
stream_handler.setFormatter(formatter)
logger.addHandler(file_handler)
logger.addHandler(stream_handler)
