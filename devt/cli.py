# DevT CLI Tool - Improved Structure

# 1. Constants and Directory Setup
import logging
import os
from typing import List, Dict, Optional
from pathlib import Path
import shutil
import winreg
import json
import subprocess
from urllib.parse import urlparse
from datetime import datetime
import typer
from git import Repo

# Directories and Constants
USER_APP_DIR = Path(typer.get_app_dir(".devt"))
TOOLS_DIR = USER_APP_DIR / "tools"
REPOS_DIR = USER_APP_DIR / "repos"
TEMP_DIR = USER_APP_DIR / "temp"
LOGS_DIR = USER_APP_DIR / "logs"
LOG_FILE = LOGS_DIR / "devt.log"
REGISTRY_FILE = USER_APP_DIR / "registry.json"

WORKSPACE_DIR = Path.cwd()
WORKSPACE_FILE = WORKSPACE_DIR / "workspace.json"
WORKSPACE_APP_DIR = WORKSPACE_DIR / ".devt"
WORKSPACE_TOOLS_DIR = WORKSPACE_APP_DIR / "tools"
WORKSPACE_REPOS_DIR = WORKSPACE_APP_DIR / "repos"
WORKSPACE_REGISTRY_FILE = WORKSPACE_APP_DIR / "registry.json"

# Ensure directories exist
USER_APP_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# 2. Logging Configuration
# Create a logger
logger = logging.getLogger("devt")
logger.setLevel(logging.INFO)

# Handlers
file_handler = logging.FileHandler(LOG_FILE)
stream_handler = logging.StreamHandler()
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
file_handler.setFormatter(formatter)
stream_handler.setFormatter(formatter)
logger.addHandler(file_handler)
logger.addHandler(stream_handler)


def set_log_level(level: str):
    """
    Set the log level dynamically.
    Args:
        level (str): The log level to set. Can be 'DEBUG', 'INFO', 'WARNING', 'ERROR', or 'CRITICAL'.
    """
    levels = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL,
    }
    if level in levels:
        logger.setLevel(levels[level])
    else:
        logger.error(f"Invalid log level: {level}")


# 3. Utility Functions
# Function to load JSON data from a file
def load_json(file_path: Path) -> Dict:
    try:
        with open(file_path, "r") as file:
            return json.load(file)
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError as e:
        logger.error(f"Error decoding JSON in {file_path}: {e}")
        return {}


# Function to save JSON data to a file
def save_json(file_path, data):
    with open(file_path, "w") as file:
        json.dump(data, file, indent=4)


def merge_dicts(*dicts: Dict) -> Dict:
    """
    Merge multiple dictionaries into one.
    """
    result = {}
    for dictionary in dicts:
        result.update(dictionary)
    return result


# Determine if the source is a URL or local path
def determine_source(source: str):
    parsed_url = urlparse(source)
    if parsed_url.scheme and parsed_url.netloc:
        return "repo"
    if Path(source).exists():
        return "local"
    return None


# 4. Environment Setup
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
    os.environ["DEVT_TOOLS_DIR"] = str(TOOLS_DIR)
    os.environ["DEVT_WORKSPACE_DIR"] = str(WORKSPACE_DIR)

    set_user_environment_var("DEVT_USER_APP_DIR", str(USER_APP_DIR))
    set_user_environment_var("DEVT_TOOLS_DIR", str(TOOLS_DIR))
    set_user_environment_var("DEVT_WORKSPACE_DIR", str(WORKSPACE_DIR))

    logger.info("Environment variables set successfully")


# 5. Package Management
def clone_or_update_repo(repo_url: str, base_dir: Path):
    """
    Add a repository by cloning or updating.
    """
    repo_name = Path(urlparse(repo_url).path).stem
    repo_dir = base_dir / "repos" / repo_name

    if repo_dir.exists():
        logger.info("Updating repository %s...", repo_name)
        repo = Repo(repo_dir)
        repo.remotes.origin.pull()
    else:
        logger.info("Cloning repository %s...", repo_url)
        Repo.clone_from(repo_url, repo_dir)

    return repo_dir


def add_local(local_path: str, base_dir: Path):
    """
    Add a local tool.
    """
    source_path = Path(local_path).resolve()
    if not source_path.exists():
        raise FileNotFoundError(f"Error: Path '{local_path}' does not exist.")

    destination = base_dir / "tools" / source_path.name
    if destination.exists():
        logger.warning("Tool '%s' already exists. Overwriting...", source_path.name)

    shutil.copytree(source_path, destination, dirs_exist_ok=True)
    return destination


def update_registry(tool_dir: Path, registry_file: Path, repo: str = None):
    """
    Update the registry with a new tool.
    """
    registry = load_json(registry_file)
    manifest_path = tool_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Error: Missing manifest.json in {tool_dir}.")

    with open(manifest_path, "r") as file:
        manifest = json.load(file)

    required_fields = ["name", "command", "scripts"]
    missing_fields = [field for field in required_fields if field not in manifest]
    if missing_fields:
        raise ValueError(
            f"Error: Missing required fields in manifest.json: {', '.join(missing_fields)}"
        )

    registry[manifest.get("command")] = {
        "manifest": manifest,
        "location": str(tool_dir.relative_to(registry_file.parent)),
        "added": datetime.utcnow().isoformat() + "Z",
        "repo": repo,
    }
    save_json(registry_file, registry)


# APP

app = typer.Typer()

# Package Management


@app.command()
def add(
    source: str,
    workspace: bool = typer.Option(False, help="Add to workspace-level registry."),
):
    """
    Add a tool from a URL or local path.
    """
    base_dir = WORKSPACE_APP_DIR if workspace else USER_APP_DIR
    registry_file = WORKSPACE_REGISTRY_FILE if workspace else REGISTRY_FILE

    source_type = determine_source(source)
    if source_type == "repo":
        repo_dir = clone_or_update_repo(source, base_dir)
        for tool in repo_dir.rglob("manifest.json"):
            update_registry(tool.parent, registry_file, source)

    elif source_type == "local":
        tool_dir = add_local(source, base_dir)
        if (tool_dir / "manifest.json").exists():
            update_registry(tool_dir, registry_file)
        else:
            for tool in tool_dir.rglob("manifest.json"):
                update_registry(tool.parent, registry_file)
    else:
        raise ValueError(f"Error: Could not determine the type of source '{source}'.")


@app.command()
def remove(
    tool_name: str,
    workspace: bool = typer.Option(False, help="Remove from workspace-level registry."),
):
    """
    Remove a tool by name.
    """
    base_dir = WORKSPACE_APP_DIR if workspace else USER_APP_DIR
    registry_file = WORKSPACE_REGISTRY_FILE if workspace else REGISTRY_FILE

    registry = load_json(registry_file)
    tool_info = registry.pop(tool_name, None)
    if not tool_info:
        raise ValueError(f"Error: Tool '{tool_name}' not found.")

    tool_path = base_dir / tool_info["location"]
    shutil.rmtree(tool_path, ignore_errors=True)
    save_json(registry_file, registry)
    typer.echo(f"Tool '{tool_name}' removed successfully.")


@app.command()
def list_tools():
    """List all tools available in USER and WORKSPACE levels."""
    user_registry = load_json(REGISTRY_FILE)
    workspace_registry = load_json(WORKSPACE_REGISTRY_FILE)
    merged_registry = merge_dicts(user_registry, workspace_registry)

    typer.echo("Available Tools:")
    for tool_name, tool_data in merged_registry.items():
        level = "WORKSPACE" if tool_name in workspace_registry else "USER"
        typer.echo(f" - {tool_name} [{level}] : {tool_data['location']}")


# Run Scripts


@app.command()
def do(
    tool_name: str = typer.Argument(..., help="The tool to run the script for."),
    script_name: str = typer.Argument(..., help="The name of the script to run."),
    additional_args: List[str] = typer.Argument(
        None, help="Additional arguments to pass to the script."
    ),
):
    """
    Run a specified script for the given tool.
    Args:
        tool_name (str): The tool to run the script for.
        script_name (str): The name of the script to run.
        additional_args (List[str]): Additional arguments to pass to the script.
    """
    user_registry = load_json(REGISTRY_FILE)
    workspace_registry = load_json(WORKSPACE_REGISTRY_FILE)
    workspace_package = {
        "workspace": {
            "manifest": load_json(WORKSPACE_FILE),
        }
    }
    merged_registry = merge_dicts(user_registry, workspace_registry, workspace_package)

    tool = merged_registry.get(tool_name)
    if not tool:
        raise ValueError(f"Error: Tool '{tool_name}' not found.")

    if tool_name == "workspace":
        tool_dir = WORKSPACE_DIR
    else:
        tool_dir = (
            Path(WORKSPACE_APP_DIR if tool_name in workspace_registry else USER_APP_DIR)
            / tool["location"]
        )
    base_dir = tool.get("manifest").get("base_dir", ".")
    new_cwd = tool_dir / base_dir
    repo = tool.get("repo")
    if repo:
        repo_dir = (
            Path(WORKSPACE_APP_DIR if tool_name in workspace_registry else USER_APP_DIR)
            / repo
        )
        repo = Repo(repo_dir)
        repo.remotes.origin.pull()

    platform = "windows" if os.name == "nt" else "posix"
    # Determine the script based on platform and script_name
    script = tool.get("manifest").get("scripts").get(platform, {}).get(
        script_name
    ) or tool.get("manifest").get("scripts").get(script_name)
    if not script:
        raise ValueError(f"Script '{script_name}' not found for tool '{tool_name}'")

    if additional_args is not None:
        additional_args = [additional_args]

    # Combine script and additional arguments
    command = [script] + (additional_args if additional_args else [])

    logger.info(
        "Running '%s' for %s with args: %s", script_name, tool_name, additional_args
    )
    if platform == "windows":
        command = ["cmd", "/c"] + command
    subprocess.run(command, cwd=new_cwd, shell=(platform == "windows"), check=True)


@app.command()
def run(
    script_name: str = typer.Argument(..., help="The name of the script to run."),
    additional_args: Optional[List[str]] = typer.Argument(
        None, help="Additional arguments to pass to the script."
    ),
):
    """
    Run a specified script for the given tools.
    Args:
        script_name (str): The name of the script to run from the workspace.
    """
    do("workspace", script_name, additional_args)


@app.command()
def install(
    tools: List[str] = typer.Argument(..., help="List of tool names to install"),
):
    """
    Install the specified tools.
    Args:
        tools (List[str]): List of tool names to install.
    """
    for tool in tools:
        do(tool, "install")


@app.command()
def uninstall(
    tools: List[str] = typer.Argument(..., help="List of tool names to uninstall"),
):
    """
    Uninstall the specified tools.
    Args:
        tools (List[str]): List of tool names to uninstall.
    """
    for tool in tools:
        do(tool, "uninstall")


@app.command()
def upgrade(
    tools: List[str] = typer.Argument(..., help="List of tool names to upgrade"),
):
    """
    Upgrade the specified tools.
    Args:
        tools (List[str]): List of tool names to upgrade.
    """
    for tool in tools:
        do(tool, "upgrade")


@app.command()
def version(
    tools: List[str] = typer.Argument(
        ..., help="List of tool names to display the version for"
    ),
):
    """
    Display the version of the specified tools.
    Args:
        tools (List[str]): List of tool names to display the version for.
    """
    for tool in tools:
        do(tool, "version")


@app.command()
def test(
    tools: List[str] = typer.Argument(
        ..., help="List of tool names to run the test for"
    ),
):
    """
    Run the test script for the specified tools.
    Args:
        tools (List[str]): List of tool names to run the test for.
    """
    for tool in tools:
        do(tool, "test")


# Initialize Workspace


@app.command()
def init():
    """
    Initialize the environment and repository as required.
    """
    logger.info("Initializing the environment...")
    user_registry = load_json(REGISTRY_FILE)
    workspace_registry = load_json(WORKSPACE_REGISTRY_FILE)
    workspace_package = {
        "workspace": {
            "manifest": load_json(WORKSPACE_FILE),
        }
    }
    merged_registry = merge_dicts(user_registry, workspace_registry, workspace_package)
    git_tool = merged_registry.get("git")
    vscode_tool = merged_registry.get("vscode")
    cwd = WORKSPACE_DIR
    if (cwd / ".git").exists() and git_tool:
        logger.info("Setting up git configuration...")
        do("git", "set")
    if not (cwd / ".vscode").exists() and vscode_tool:
        logger.info("Setting up VS Code configuration...")
        do("vscode", "set")
    logger.info("Repository and tools are ready")


if __name__ == "__main__":
    app()
