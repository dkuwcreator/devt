import os
import json
import subprocess
from typing import List, Optional, Dict
import typer
from git import Repo
import logging
import winreg

app = typer.Typer()

APP_DATA_DIR = os.path.expanduser("~/.devt")
if not os.path.exists(APP_DATA_DIR):
    os.makedirs(APP_DATA_DIR)

# Configuration constants
CWD = os.getcwd()
CONFIG_FILE = os.path.join(CWD, "config.json")
UTILS_DIR = os.path.join(APP_DATA_DIR, ".utils")
TOOLS_DIR = os.path.join(UTILS_DIR, "tools")

# Create a logger
logger = logging.getLogger(__name__)

# Set the logging level
logger.setLevel(logging.INFO)

# Create a file handler and a stream handler
file_handler = logging.FileHandler(os.path.join(APP_DATA_DIR, "devt.log"))
stream_handler = logging.StreamHandler()

# Create a formatter and attach it to the handlers
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
file_handler.setFormatter(formatter)
stream_handler.setFormatter(formatter)

# Add the handlers to the logger
logger.addHandler(file_handler)
logger.addHandler(stream_handler)


def set_user_environment_var(name: str, value: str):
    """
    Set a user environment variable.
    Args:
        name (str): The name of the environment variable.
        value (str): The value of the environment variable.
    """
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
            os.environ[name] = value
            logger.info(f"Set user environment variable: {name}={value}")
    except Exception as e:
        logger.error(f"Failed to set user environment variable {name}: {e}")


# Set environment variables for the session
os.environ["devt_CWD"] = CWD

# Set environment variables for the user
set_user_environment_var("devt_UTILS_DIR", UTILS_DIR)
set_user_environment_var("devt_TOOLS_DIR", TOOLS_DIR)

TOOL_REGISTRY = {}


# To set the log level dynamically, you can use the following function
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


# You can add this function as a command to your Typer app
@app.command()
def set_log_level(level: str):
    """
    Set the log level dynamically.
    Args:
        level (str): The log level to set. Can be 'DEBUG', 'INFO', 'WARNING', 'ERROR', or 'CRITICAL'.
    """
    set_log_level(level)


def clone_or_update_utils(utils_url: str, utils_dir: str):
    """
    Clone the repository if it doesn't exist or pull updates if it does.
    Args:
        utils_url (str): The repository URL to clone from.
        utils_dir (str): The local path to clone the repository into.
    """
    if not os.path.exists(utils_dir):
        logger.info(f"Cloning repository from {utils_url}...")
        Repo.clone_from(utils_url, utils_dir)
    else:
        logger.info("Checking for updates in the repository...")
        repo = Repo(utils_dir)
        repo.git.fetch()
        local_head = repo.git.rev_parse("HEAD")
        remote_head = repo.git.rev_parse("origin/HEAD")
        if local_head != remote_head:
            if repo.is_dirty():
                # Reset the changes
                logger.info("Resetting local changes...")
                repo.git.reset("--hard")
            logger.info("Pulling the latest changes from the remote repository...")
            repo.remotes.origin.pull()


def load_config(config_path: str) -> Dict:
    """
    Load the JSON config file from the specified path.
    Args:
        config_path (str): The path to the config file.
    Returns:
        dict: The loaded JSON config, or an empty dictionary on error.
    """
    try:
        with open(config_path, "r") as file:
            return json.load(file)
    except FileNotFoundError:
        logger.error(f"Config file '{config_path}' not found.")
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in config file '{config_path}': {e}")
    return {}


def load_tool_manifest(tool_dir: str) -> Optional[Dict]:
    """
    Load the tool manifest from the specified directory.
    Args:
        tool_dir (str): The path to the tool directory.
    Returns:
        dict: The loaded JSON manifest, or None if not found.
    """
    manifest_path = os.path.join(tool_dir, "tool.json")
    try:
        with open(manifest_path, "r") as file:
            return json.load(file)
    except FileNotFoundError:
        logger.warning(f"Manifest not found for tool at {tool_dir}.")
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in manifest for tool at {tool_dir}: {e}")
    return None


def map_scripts(scripts: Dict, platform: str) -> Dict:
    """
    Map the scripts for the specified platform and add the the scripts that are not platform-specific.
    Args:
        scripts (Dict): The scripts to map.
        platform (str): The platform to map the scripts for.
    Returns:
        Dict: The mapped scripts for the platform.
    """
    mapped_scripts = {}
    # Check if the scripts have platform-specific sections
    if "posix" in scripts or "windows" in scripts:
        # If platform-specific, map the scripts for the specified platform
        if platform in scripts:
            mapped_scripts.update(scripts[platform])
        # Add scripts that are not platform-specific
        for script_name, script in scripts.items():
            if script_name not in ["posix", "windows"]:
                mapped_scripts[script_name] = script
    else:
        # If not platform-specific, use the scripts as is
        mapped_scripts = scripts
    return mapped_scripts


def map_path_scripts(scripts: Dict, tool_dir: str) -> Dict:
    """
    Script paths are relative to the tool directory, so map them to the absolute paths.
    Args:
        scripts (Dict): The scripts to map.
        tool_dir (str): The directory of the tool.
    Returns:
        Dict: The mapped scripts with absolute paths.
    """
    mapped_scripts = {}
    for script_name, script in scripts.items():
        script_path = os.path.abspath(os.path.join(tool_dir, script))
        if os.path.isfile(script_path):
            mapped_scripts[script_name] = script_path
        else:
            mapped_scripts[script_name] = script
    return mapped_scripts


class Tool:
    """Class for tools"""

    def __init__(self, tool_dir: str, manifest: Dict):
        self.tool_dir = tool_dir
        self.name = manifest.get("name", os.path.basename(tool_dir))
        self.manifest = manifest
        self.platform = "windows" if os.name == "nt" else "posix"
        self.shell = "pwsh" if os.name == "nt" else "bash"
        self.scripts = map_path_scripts(
            map_scripts(manifest.get("scripts", {}), self.platform),
            tool_dir,
        )

    def run_script(self, script_name: str):
        """
        Run the specified script for the tool.
        Args:
            script_name (str): The name of the script to run.
        """
        script = self.scripts.get(script_name)
        if script:
            logger.info(f"Running script '{script_name}' for tool '{self.name}'...")
            logger.info(f"Executing command: {script}")
            if os.path.isfile(script):
                subprocess.run([self.shell, "-File", script], shell=True)
            else:
                try:
                    subprocess.run([self.shell, "-Command", script], shell=True)
                except subprocess.CalledProcessError as e:
                    subprocess.run(script, shell=True)
                except Exception as e:
                    logger.error(f"Failed to run script '{script_name}': {e}")
        else:
            logger.error(f"Script '{script_name}' not found for tool '{self.name}'.")


def load_tools(tools_repo_path: str):
    """
    Load tools from the repository, registering by name.
    Args:
        tools_repo_path (str): The path to the repository.
    """
    for tool_name in os.listdir(tools_repo_path):
        tool_dir = os.path.join(tools_repo_path, tool_name)
        if os.path.isdir(tool_dir):
            manifest = load_tool_manifest(tool_dir)
            if manifest:
                TOOL_REGISTRY[tool_name] = Tool(tool_dir, manifest)


@app.command()
def run(
    task_name: str,
    tools: Optional[List[str]] = typer.Argument(
        None, help="List of tool names to run the task for"
    ),
):
    """
    Run a specified task for the given tools.
    Args:
        task_name (str): The name of the task to run.
        tools (Optional[List[str]]): List of tool names to run the task for. Uses all configured tools if not specified.
    """
    clone_or_update_utils(UTILS_URL, UTILS_DIR)
    load_tools(TOOLS_DIR)
    config = {}
    if not tools:
        if os.path.exists(CONFIG_FILE):
            config = load_config(CONFIG_FILE)
        else:
            logger.error("No configuration found and no tools specified.")
            logger.error(
                "Please provide a configuration file or specify a tool to run the task for."
            )
            return
    task_tools = tools if tools else config.get("tasks", {}).get(task_name, {}).keys()
    for tool_name in task_tools:
        tool_instance = TOOL_REGISTRY.get(tool_name)
        if tool_instance:
            logger.info(f"Running '{task_name}' for {tool_name}...")
            tool_instance.run_script(task_name)
        else:
            logger.error(f"Tool not found or not configured: {tool_name}")
            logger.error(f"The available tools are: {', '.join(TOOL_REGISTRY.keys())}")


@app.command()
def init():
    """
    Initialize the environment and repository as required.
    """
    clone_or_update_utils(UTILS_URL, UTILS_DIR)
    load_tools(TOOLS_DIR)
    logger.info("Initializing the environment...")
    git_tool = TOOL_REGISTRY.get("git")
    vscode_tool = TOOL_REGISTRY.get("vscode")
    if os.path.exists(os.path.join(CWD, ".git")) and git_tool:
        logger.info("Setting up git configuration...")
        git_tool.run_script("set")
    if not os.path.exists(os.path.join(CWD, ".vscode")) and vscode_tool:
        logger.info("Setting up VS Code configuration...")
        vscode_tool.run_script("set")
    logger.info("Repository and tools are ready")


if __name__ == "__main__":
    app()
