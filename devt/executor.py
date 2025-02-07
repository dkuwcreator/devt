# devt/executor.py
"""
Executor module: Provides helper functions for finding a tool,
resolving the correct script, determining the working directory, and executing commands.
"""

import subprocess
import logging
from pathlib import Path
from typing import Tuple, List
import json

from devt.registry import update_registry_with_workspace
from devt.utils import load_json
from devt.config import REGISTRY_FILE, WORKSPACE_REGISTRY_FILE, WORKSPACE_FILE, WORKSPACE_DIR, REGISTRY_DIR, WORKSPACE_REGISTRY_DIR

logger = logging.getLogger("devt")

def get_tool(tool_name: str) -> Tuple[dict, Path]:
    """
    Look up a tool in the registries.
    
    Workspace registry is checked first, then the user registry.
    Returns a tuple (tool_entry, registry_dir) where registry_dir is the base directory
    for the registry in which the tool was found.
    """
    user_registry = load_json(REGISTRY_FILE)
    workspace_registry = load_json(WORKSPACE_REGISTRY_FILE)

    cwd_registry = update_registry_with_workspace(
                Path(WORKSPACE_DIR) / "registry.json",
                {},
                WORKSPACE_FILE,
                WORKSPACE_DIR,
                auto_sync=False,
            )
               
    logger.debug("Workspace registry keys: %s", list(workspace_registry.keys()))
    logger.debug("User registry keys: %s", list(user_registry.keys()))

    if tool_name in cwd_registry:
        return cwd_registry[tool_name], WORKSPACE_DIR    
    elif tool_name in workspace_registry:
        return workspace_registry[tool_name], WORKSPACE_REGISTRY_DIR
    elif tool_name in user_registry:
        return user_registry[tool_name], REGISTRY_DIR
    else:
        raise ValueError(f"Tool '{tool_name}' not found in any registry.")

def resolve_script(tool: dict, script_name: str, shell: str) -> str:
    """
    Resolve and return the command string for the given script from the tool's manifest.
    If the script is not found, an error is raised with details.
    """
    scripts = tool.get("manifest", {}).get("scripts", {})
    cmd = scripts.get(script_name) or scripts.get(shell, {}).get(script_name)
    if not cmd:
        available = ", ".join(scripts.keys())
        shell_specific = ", ".join(scripts.get(shell, {}).keys())
        logger.error(
            "Script '%s' not found for tool '%s'. Available scripts: %s. Shell-specific scripts: %s. "
            "Try running 'devt list %s' to see available scripts.",
            script_name, tool.get('manifest', {}).get('name', tool.get('command', 'unknown')),
            available, shell_specific, tool.get('command')
        )
        raise ValueError(
            f"Script '{script_name}' not found for tool '{tool.get('manifest', {}).get('name', tool.get('command', 'unknown'))}'. "
            f"Available scripts: {available}. Shell-specific scripts: {shell_specific}. "
            f"Try running 'devt list {tool.get('command')}' to see available scripts."
        )
    return cmd

def resolve_working_directory(tool: dict, registry_dir: Path) -> Path:
    """
    Determine the working directory for the tool.
    
    It uses the location stored in the registry (the folder containing manifest.json)
    and an optional 'base_dir' defined in the tool's manifest.
    """
    tool_manifest_path = Path(registry_dir) / tool["location"]
    tool_dir = tool_manifest_path.parent if tool_manifest_path.is_file() else tool_manifest_path
    base_dir = tool.get("manifest", {}).get("base_dir", ".")
    new_cwd = (tool_dir / base_dir).resolve()
    if not new_cwd.is_dir():
        logger.warning("Working directory '%s' is not a directory. Falling back to tool directory.", new_cwd)
        new_cwd = tool_dir
    return new_cwd

def build_full_command(script: str, additional_args: List[str]) -> str:
    """
    Build the full command string by appending additional arguments.
    """
    additional = " ".join(additional_args) if additional_args else ""
    return f"{script} {additional}".strip()

def execute_command(command: str, cwd: Path) -> None:
    """
    Execute the given command string in the specified working directory.
    """
    logger.info("Executing command: %s in directory: %s", command, cwd)
    try:
        subprocess.run(command, cwd=cwd, check=True, shell=True)
    except subprocess.CalledProcessError as e:
        logger.error("Command failed with exit code %s", e.returncode)
        if e.stdout:
            logger.error("Command output:\n%s", e.stdout)
        if e.stderr:
            logger.error("Error output:\n%s", e.stderr)
        raise