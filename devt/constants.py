import configparser
import inspect
import subprocess
from pathlib import Path
import typer

settings = configparser.ConfigParser()
settings.read("settings.ini")

# Application Constants
APP_NAME = settings.get("project", "output_name", fallback="devt")

# Directories and Files (User)
USER_APP_DIR = Path(typer.get_app_dir(f".{APP_NAME}"))
USER_REGISTRY_DIR = USER_APP_DIR / "registry"

# Directories and Files (Workspace)
WORKSPACE_APP_DIR = Path.cwd()
WORKSPACE_REGISTRY_DIR = WORKSPACE_APP_DIR / ".registry"

SCOPE_TO_REGISTRY_DIR = {
    "user": USER_REGISTRY_DIR,
    "workspace": WORKSPACE_REGISTRY_DIR,
}

# Dynamically extract allowed arguments for subprocess methods
RUN_KEYS = set(inspect.signature(subprocess.run).parameters.keys())
POPEN_KEYS = set(inspect.signature(subprocess.Popen).parameters.keys())
SUBPROCESS_ALLOWED_KEYS = RUN_KEYS | POPEN_KEYS

