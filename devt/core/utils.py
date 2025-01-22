import os
import json
import subprocess
from pathlib import Path
from typing import Optional, Dict
from git import Repo
from .logger import logger

def clone_or_update_repo(repo_url: Path, repo_dir: Path):
    """
    Clone the repository if it doesn't exist or pull updates if it does.
    Args:
        repo_url (str): The repository URL to clone from.
        repo_dir (str): The local path to clone the repository into.
    """
    if not repo_dir.exists():
        logger.info(f"Cloning repository from {repo_url}...")
        Repo.clone_from(repo_url, repo_dir)
    else:
        logger.info("Checking for updates in the repository...")
        repo = Repo(repo_dir)
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

def load_tool_manifest(tool_dir: Path) -> Optional[Dict]:
    """
    Load the tool manifest from the specified directory.
    Args:
        tool_dir (Path): The path to the tool directory.
    Returns:
        dict: The loaded JSON manifest, or None if not found.
    """
    manifest_path = tool_dir / "tool.json"
    try:
        with manifest_path.open("r") as file:
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


def map_path_scripts(scripts: Dict, tool_dir: Path) -> Dict:
    """
    Script paths are relative to the tool directory, so map them to the absolute paths.
    Args:
        scripts (Dict): The scripts to map.
        tool_dir (Path): The directory of the tool.
    Returns:
        Dict: The mapped scripts with absolute paths.
    """
    mapped_scripts = {}
    for script_name, script in scripts.items():
        script_path = tool_dir / script
        if script_path.is_file():
            mapped_scripts[script_name] = str(script_path.resolve())
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


def load_tools(tools_repo_path: Path):
    """
    Load tools from the repository, registering by name.
    Args:
        tools_repo_path (Path): The path to the repository.
    """
    TOOL_REGISTRY = {}

    for tool_name in tools_repo_path.iterdir():
        tool_dir = tools_repo_path / tool_name
        if tool_dir.is_dir():
            manifest = load_tool_manifest(tool_dir)
            if manifest:
                TOOL_REGISTRY[tool_name.name] = Tool(tool_dir, manifest)
    
    return TOOL_REGISTRY