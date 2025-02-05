# Updated add.py to calculate relative path from registry.json to manifest.json
import logging
import os
import shlex
import subprocess
from typing import Dict, List, Optional
from pathlib import Path
import shutil
import json
from urllib.parse import urlparse
from datetime import datetime, timezone
import typer
from git import Repo
from jsonschema import validate, ValidationError

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


# Utility functions
def load_json(file_path: Path) -> Dict:
    try:
        with open(file_path, "r") as file:
            return json.load(file)
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError as e:
        logger.error(f"Error decoding JSON in {file_path}: {e}")
        return {}


def save_json(file_path, data):
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(file_path, "w") as file:
        json.dump(data, file, indent=4)


def determine_source(source: str):
    parsed_url = urlparse(source)
    if parsed_url.scheme and parsed_url.netloc:
        return "repo"
    logger.info("Source is not a URL. Checking if it's a local path...")
    source_path = Path(source)
    if source_path.exists():
        return "local"
    raise FileNotFoundError(f"Error: The source path '{source}' does not exist.")


MANIFEST_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "command": {"type": "string"},
        "scripts": {"type": "object"},
    },
    "required": ["name", "command", "scripts"],
}


def validate_manifest(manifest_path: Path):
    try:
        with open(manifest_path, "r") as file:
            manifest = json.load(file)

        validate(instance=manifest, schema=MANIFEST_SCHEMA)
        scripts = manifest.get("scripts", {})

        # Properly check for install script
        install_present = (
            "install" in scripts
            or "windows" in scripts
            and "install" in scripts["windows"]
            or "posix" in scripts
            and "install" in scripts["posix"]
        )

        if not install_present:
            logger.error(f"Manifest scripts: {json.dumps(scripts, indent=4)}")
            raise ValueError("At least one install script is required in the manifest.")

    except (FileNotFoundError, json.JSONDecodeError, ValidationError) as e:
        raise ValueError(f"Error validating manifest: {e}")


def update_registry_with_workspace(
    registry_file: Path,
    registry: Dict,
    auto_sync: bool = True,
) -> Dict:
    """
    Update the tool registry with information from a manifest file.

    Args:
        tool_dir (Path): Directory containing the tool.
        registry_file (Path): Path to the registry JSON file.
        registry (Dict): Existing registry data.
        repo (Optional[str]): Repository URL, if applicable.

    Returns:
        Dict: Updated registry.
    """
    if not WORKSPACE_FILE.exists():
        logger.error("Workspace file not found: %s", WORKSPACE_FILE)
        return registry

    with WORKSPACE_FILE.open("r") as file:
        manifest = json.load(file)

    try:
        location = str(WORKSPACE_FILE.relative_to(registry_file.parent))
    except ValueError:
        location = str(WORKSPACE_FILE)

    location_parts = location.split(os.sep)
    second_position = (
        location_parts[1] if len(location_parts) > 1 else location_parts[0]
    )

    registry_entry = {
        "manifest": manifest,
        "location": location,
        "added": datetime.now(timezone.utc).isoformat(),
        "source": WORKSPACE_DIR,
        "dir": second_position,
        "active": True,
        "auto_sync": auto_sync,
    }
    command = "workspace"
    registry[command] = registry_entry
    return registry


def update_registry(
    tool_dir: Path,
    registry_file: Path,
    registry: Dict,
    source: str,
    auto_sync: bool = True,
) -> Dict:
    """
    Update the tool registry with information from a manifest file.

    Args:
        tool_dir (Path): Directory containing the tool.
        registry_file (Path): Path to the registry JSON file.
        registry (Dict): Existing registry data.
        repo (Optional[str]): Repository URL, if applicable.

    Returns:
        Dict: Updated registry.
    """
    manifest_path = tool_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Missing manifest.json in {tool_dir}.")

    validate_manifest(manifest_path)

    with manifest_path.open("r") as file:
        manifest = json.load(file)

    try:
        location = str(manifest_path.relative_to(registry_file.parent))
    except ValueError:
        location = str(manifest_path)

    location_parts = location.split(os.sep)
    second_position = (
        location_parts[1] if len(location_parts) > 1 else location_parts[0]
    )

    registry_entry = {
        "manifest": manifest,
        "location": location,
        "added": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "dir": second_position,
        "active": True,
        "auto_sync": auto_sync,
    }
    command = manifest.get("command")
    if not command:
        raise KeyError(f"'command' key is missing in manifest: {manifest_path}")

    registry[command] = registry_entry
    return registry


def clone_or_update_repo(repo_url: str, base_dir: Path, branch: str) -> Path:
    """
    Clone or update a git repository.

    Args:
        repo_url (str): URL of the repository.
        base_dir (Path): Base directory where the repository will be cloned.

    Returns:
        Path: Path to the repository directory.
    """
    repo_name = Path(urlparse(repo_url).path).stem
    repo_dir = base_dir / "repos" / repo_name

    try:
        if repo_dir.exists():
            repo = Repo(repo_dir)
            if repo.is_dirty():
                logger.warning(
                    "Repository %s is dirty. Resetting to a clean state...", repo_name
                )
                repo.git.reset("--hard")
            logger.info("Updating repository %s...", repo_name)
            repo.remotes.origin.pull()
        else:
            logger.info("Cloning repository %s...", repo_url)
            Repo.clone_from(repo_url, repo_dir)
    except Exception as e:
        logger.error("Failed to clone or update repository %s: %s", repo_url, e)
        raise

    return repo_dir


# Package functions
def add_local(local_path: str, base_dir: Path) -> Path:
    """
    Add a local tool to the specified base directory.

    Args:
        local_path (str): Path to the local tool.
        base_dir (Path): Base directory for adding the tool.

    Returns:
        Path: Destination path of the tool.
    """
    source_path = Path(local_path).resolve()
    if not source_path.exists():
        raise FileNotFoundError(f"Path '{local_path}' does not exist.")

    destination = base_dir / "tools" / source_path.name
    try:
        shutil.copytree(source_path, destination, dirs_exist_ok=True)
    except Exception as e:
        logger.error(
            "Failed to copy local path %s to %s: %s", source_path, destination, e
        )
        raise

    return destination


def add_repository(repo_url: str, base_dir: Path, branch: str) -> Path:
    """
    Clone or update a git repository.

    Args:
        repo_url (str): URL of the repository.
        base_dir (Path): Base directory where the repository will be cloned.
        branch (str): Branch name to checkout.

    Returns:
        Path: Path to the repository directory.
    """
    repo_name = Path(urlparse(repo_url).path).stem
    repo_dir = base_dir / "repos" / repo_name

    try:
        if repo_dir.exists():
            repo = Repo(repo_dir)
            if repo.is_dirty():
                logger.warning(
                    "Repository %s is dirty. Resetting to a clean state...", repo_name
                )
                repo.git.reset("--hard")
            logger.info("Updating repository %s...", repo_name)
            repo.remotes.origin.pull()
        else:
            logger.info("Cloning repository %s...", repo_url)
            Repo.clone_from(repo_url, repo_dir, branch=branch or "main")
    except Exception as e:
        logger.error("Failed to clone or update repository %s: %s", repo_url, e)
        raise

    return repo_dir


# Define a helper function to handle read-only files or errors
def on_exc(func, path, exc):
    if isinstance(exc, PermissionError):
        os.chmod(path, 0o777)  # Grant write permissions
        func(path)  # Retry the operation
    else:
        raise exc  # Re-raise any other exception


def remove_repository(
    repo_name: str, base_dir: Path, registry: Dict, registry_file: Path
):
    """
    Remove a repository from the registry.

    Args:
        repo_name (str): Name of the repository.
        base_dir (Path): Base directory where repositories are stored.
        registry (Dict): Existing registry data.
        registry_file (Path): Path to the registry JSON file.
    """
    repo_dir = base_dir / "repos" / repo_name
    if repo_dir.exists():
        try:
            shutil.rmtree(repo_dir, onexc=on_exc)
            logger.info("Repository %s removed successfully.", repo_name)
            registry = {
                key: value
                for key, value in registry.items()
                if value.get("dir") != repo_name
            }
            save_json(registry_file, registry)
        except Exception as e:
            logger.error("Failed to remove repository %s: %s", repo_name, e)
            raise
    else:
        logger.warning("Repository directory not found: %s", repo_dir)


def import_local_package(local_path: str, base_dir: Path) -> Path:
    """
    Import a local tool package into the registry.

    Args:
        local_path (str): Path to the local tool package.
        base_dir (Path): Base directory for the registry.

    Returns:
        Path: Destination path of the tool.
    """
    source_path = Path(local_path).resolve()
    if not source_path.exists():
        raise FileNotFoundError(f"Path '{local_path}' does not exist.")

    destination = base_dir / "tools" / source_path.name
    try:
        shutil.copytree(source_path, destination, dirs_exist_ok=True)
        logger.info("Local package imported successfully: %s", source_path.name)
    except Exception as e:
        logger.error("Failed to copy local package %s: %s", source_path, e)
        raise

    return destination


def export_local_package(package_name: str, destination_path: str, base_dir: Path):
    """
    Export a local tool package from the registry.

    Args:
        package_name (str): Name of the tool package.
        destination_path (str): Path where the package should be exported.
        base_dir (Path): Base directory for the registry.
    """
    tool_dir = base_dir / "tools" / package_name
    destination = Path(destination_path).resolve()

    if not tool_dir.exists():
        raise FileNotFoundError(f"Tool package '{package_name}' does not exist.")

    try:
        shutil.copytree(tool_dir, destination, dirs_exist_ok=True)
        logger.info("Local package exported successfully to %s", destination)
    except Exception as e:
        logger.error("Failed to export local package %s: %s", package_name, e)
        raise


def delete_local_package(
    package_name: str, base_dir: Path, registry: Dict, registry_file: Path
):
    """
    Delete a local tool package from the registry.

    Args:
        package_name (str): Name of the tool package.
        base_dir (Path): Base directory for the registry.
        registry (Dict): Existing registry data.
        registry_file (Path): Path to the registry JSON file.
    """
    tool_dir = base_dir / "tools" / package_name
    if tool_dir.exists():
        try:
            shutil.rmtree(tool_dir)
            logger.info("Tool package %s removed successfully.", package_name)
            registry.pop(package_name, None)
            save_json(registry_file, registry)
        except Exception as e:
            logger.error("Failed to remove tool package %s: %s", package_name, e)
            raise
    else:
        logger.warning("Tool package directory not found: %s", tool_dir)


def sync_repositories(base_dir: Path):
    """
    Sync all repositories in the registry by pulling the latest changes.

    Args:
        base_dir (Path): Base directory containing the repository folders.
    """
    repos_dir = base_dir / "repos"
    if not repos_dir.exists():
        logger.warning("No repositories found to sync.")
        return

    logger.info("Syncing repositories in %s...", repos_dir)

    for repo_path in repos_dir.iterdir():
        if repo_path.is_dir():
            try:
                clone_or_update_repo(repo_path, base_dir, branch=None)
            except Exception as e:
                logger.error("Failed to sync repository %s: %s", repo_path.name, e)


# ### Revised Command Structure

app = typer.Typer()

# #### **Add Command**
# ```bash
# devt add <source> [--type local|repo] [--branch <branch>] [--workspace] [--dry-run]
# ```

# - **Examples**:
#   1. Adding a local tool:
#      ```bash
#      devt add ./path/to/tool --type local
#      ```
#   2. Adding a repository tool with a specific branch:
#      ```bash
#      devt add https://github.com/example/tool-repo --type repo --branch main
#      ```
#   3. Dry run to preview actions:
#      ```bash
#      devt add ./path/to/tool --type local --dry-run
#      ```


@app.command()
def add(
    source: str,
    type: str = typer.Option(
        None, help="Specify the type of source: 'local' or 'repo'."
    ),
    branch: str = typer.Option(None, help="Specify the branch for repository sources."),
    workspace: bool = typer.Option(False, help="Add to workspace-level registry."),
    dry_run: bool = typer.Option(
        False, help="Preview the actions without making changes."
    ),
    auto_sync: bool = typer.Option(
        True, help="Automatically sync repositories after adding."
    ),
):
    """
    Add tools to the registry from a local path or repository.

    Args:
        source (str): Source path or repository URL.
        type (str): Type of the source, either 'local' or 'repo'.
        branch (str): Branch name for repository sources.
        workspace (bool): Whether to add to the workspace-level registry.
        dry_run (bool): Preview the actions without making changes.
        auto_sync (bool): Automatically sync repositories after adding.
    """
    app_dir = WORKSPACE_REGISTRY_DIR if workspace else REGISTRY_DIR
    registry_file = app_dir / "registry.json"
    logger.info("Adding tool(s) to registry from %s...", registry_file)

    registry = load_json(registry_file)

    try:
        source_type = type or determine_source(source)
        if source_type == "repo":
            logger.info("Adding tool(s) from repository %s...", source)
            if dry_run:
                logger.info("Dry run: would clone or update repository %s", source)
                return
            repo_dir = clone_or_update_repo(source, app_dir, branch)
            tool_dirs = [
                manifest.parent for manifest in repo_dir.rglob("manifest.json")
            ]
        elif source_type == "local":
            logger.info("Adding tool(s) from local path %s...", source)
            if dry_run:
                logger.info("Dry run: would copy local path %s", source)
                return
            tool_dir = add_local(source, app_dir)
            tool_dirs = [
                manifest.parent for manifest in tool_dir.rglob("manifest.json")
            ]
        else:
            raise ValueError(f"Unknown source type: {source_type}")

        for tool_dir in tool_dirs:
            registry = update_registry(
                tool_dir,
                registry_file,
                registry,
                source,
                auto_sync=auto_sync and source_type == "repo",
            )

        if not dry_run:
            save_json(registry_file, registry)
            logger.info("Tool(s) successfully added to the registry.")
    except Exception as e:
        logger.exception("An error occurred while adding the tool: %s", e)


# #### **Remove Command**
# ```bash
# devt remove <identifier> [--repository] [--workspace]
# ```

# - **Examples**:
#   1. Remove a tool by its identifier:
#      ```bash
#      devt remove my-tool
#      ```
#   2. Remove a repository:
#      ```bash
#      devt remove https://github.com/example/tool-repo --repository
#      ```

# ---

# ### Key Features

# 1. **Simplified Entry Point**:
#    - Use `devt add` and `devt remove` directly without `tool` as a subcommand.

# 2. **Unified Command with `--type`**:
#    - Explicitly specify whether the source is a `local` path or a `repo`, while retaining the option for automatic detection.

# 3. **Optional Enhancements**:
#    - **`--dry-run`**: Test the operation without making changes.
#    - **`--branch`**: Specify a branch for repository sources.
#    - **`--workspace`**: Add or remove tools in the workspace-specific registry.

# 4. **Intuitive Defaults**:
#    - If `--type` is omitted, auto-detect the source (local path or URL) with feedback.


@app.command()
def remove(
    name: str = typer.Argument(
        ..., help="Identifier of the tool or repository directory."
    ),
    workspace: bool = typer.Option(False, help="Remove from workspace-level registry."),
    dry_run: bool = typer.Option(
        False, help="Preview the actions without making changes."
    ),
):
    """
    Remove a tool or an entire repository from the registry.

    - If `name` is a repository directory (`dir` in registry), remove all associated tools.
    - If `name` is a tool, remove it from the registry based on its type (local or repo).
    - If a tool is local but has a `dir` assigned, also remove its directory.

    Args:
        name (str): Identifier of the tool or repository directory.
        workspace (bool): Remove from workspace-level registry.
        dry_run (bool): Preview the actions without making changes.
    """
    app_dir = WORKSPACE_REGISTRY_DIR if workspace else REGISTRY_DIR
    registry_file = app_dir / "registry.json"
    registry = load_json(registry_file)

    # Step 1: Check if `name` is a repository (i.e., a `dir` in the registry)
    repo_tools = {
        tool: data for tool, data in registry.items() if data.get("dir") == name
    }

    if repo_tools:
        logger.info(
            f"'{name}' is a repository directory. Removing all associated tools."
        )
        if dry_run:
            logger.info(f"Dry run: Would remove repository '{name}' and all its tools.")
            return

        # Remove all tools associated with the repository
        for tool_name in list(repo_tools.keys()):
            del registry[tool_name]

        save_json(registry_file, registry)
        logger.info(f"Removed all tools from repository '{name}'.")
        return

    # Step 2: Check if `name` is a tool in the registry
    if name not in registry:
        logger.error(f"Tool '{name}' not found in registry.")
        return

    tool_entry = registry[name]
    location = tool_entry.get("location", "")
    tool_dir = tool_entry.get("dir", "")

    # Step 3: Remove a repository tool
    if location.startswith("repos"):
        logger.info(f"Tool '{name}' is from a repository (location: {location}).")
        if dry_run:
            logger.info(f"Dry run: Would remove '{name}' from registry.json.")
            return
        registry[name]["active"] = False
        save_json(registry_file, registry)
        logger.info(f"Removed repository tool '{name}' from registry.json.")

    # Step 4: Remove a local tool (with special handling for `dir`)
    elif location.startswith("tools"):
        logger.info(f"Tool '{name}' is a local package (location: {location}).")
        if dry_run:
            logger.info(
                f"Dry run: Would remove '{name}' from registry and delete local files."
            )
            return

        delete_local_package(name, app_dir, registry, registry_file)

        # If this tool also has a `dir`, delete the entire directory
        if tool_dir:
            tool_dir_path = app_dir / tool_dir
            if tool_dir_path.exists():
                shutil.rmtree(tool_dir_path)
                logger.info(
                    f"Deleted directory '{tool_dir_path}' as it was part of a local tool."
                )

    # Step 5: Handle unknown tools
    else:
        logger.warning(
            f"Tool '{name}' has an unrecognized location format: {location}. Removing from registry only."
        )
        registry[name]["active"] = False
        save_json(registry_file, registry)
        logger.info(f"Removed '{name}' from registry.json.")


@app.command()
def list(
    workspace: bool = typer.Option(False, help="List tools from workspace registry.")
):
    """
    List all tools in the registry.

    Args:
        workspace (bool): List tools from workspace registry.
    """
    if not workspace:
        logger.info("Listing tools from registry %s...", REGISTRY_FILE)
        registry = load_json(REGISTRY_FILE)
        for name, value in registry.items():
            if value.get("active", True):
                logger.info(f"{name}: {value.get('source')}")
    else:
        logger.info(
            "Listing tools from workspace registry %s...", WORKSPACE_REGISTRY_FILE
        )
        registry = load_json(WORKSPACE_REGISTRY_FILE)
        for name, value in registry.items():
            logger.info(f"{name}: {value.get('source')}")


@app.command()
def sync(
    workspace: bool = typer.Option(
        False, help="Sync repositories from workspace registry."
    )
):
    """
    Sync all repositories by pulling the latest changes.

    Args:
        workspace (bool): Sync repositories from workspace registry.
    """
    app_dir = WORKSPACE_REGISTRY_DIR if workspace else REGISTRY_DIR
    sync_repositories(app_dir)
    logger.info("All repositories have been synced successfully.")


# Run Scripts
def merge_dicts(*dicts: Dict) -> Dict:
    """
    Merge multiple dictionaries into one.
    """
    result = {}
    for dictionary in dicts:
        result.update(dictionary)
    return result


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
    # Load both the user and workspace registries.
    user_registry = load_json(REGISTRY_FILE)
    workspace_registry = load_json(WORKSPACE_REGISTRY_FILE)
    # Add workspace.json to the workspace registry if it doesn't exist.
    workspace_registry = update_registry_with_workspace(
        WORKSPACE_REGISTRY_FILE, workspace_registry
    )

    # Decide which registry contains the tool.
    if tool_name in workspace_registry:
        tool = workspace_registry[tool_name]
        registry_dir = WORKSPACE_REGISTRY_DIR
        registry = workspace_registry
    elif tool_name in user_registry:
        tool = user_registry[tool_name]
        registry_dir = REGISTRY_DIR
        registry = user_registry
    else:
        raise ValueError(f"Error: Tool '{tool_name}' not found in any registry.")

    # Resolve repository directory and tool location.
    repo_name = tool.get("dir")
    repo_dir = Path(registry_dir) / repo_name

    # Determine the path to the tool's manifest.
    tool_manifest_path = Path(registry_dir) / tool["location"]

    # If tool_manifest_path is a file (e.g. "manifest.json"), get its parent directory.
    tool_dir = (
        tool_manifest_path.parent
        if tool_manifest_path.is_file()
        else tool_manifest_path
    )

    # Determine the shell type.
    shell = "posix" if os.name != "nt" else "windows"

    scripts = tool.get("manifest", {}).get("scripts", {})
    script = scripts.get(script_name) or scripts.get(shell, {}).get(script_name)

    print(f"{script}")

    # Auto-syncing if enabled.
    if tool.get("auto_sync", False):
        logger.info("Auto-syncing repository for tool '%s'...", tool_name)
        clone_or_update_repo(tool["source"], repo_dir, branch=None)
        tool_dirs = [manifest.parent for manifest in repo_dir.rglob("manifest.json")]
        for tool_dir in tool_dirs:
            registry = update_registry(
                tool_dir,
                registry_dir / "registry.json",
                registry,
                tool["source"],
            )
        # Save the updated registry.
        save_json(registry_dir / "registry.json", registry)
        if tool_name in registry:
            tool = registry[tool_name]

        scripts = tool.get("manifest", {}).get("scripts", {})
        script = scripts.get(script_name) or scripts.get(shell, {}).get(script_name)

        print(f"{script}")

    # Determine the base directory from the tool's manifest.
    base_dir = tool.get("manifest", {}).get("base_dir", ".")
    new_cwd = (tool_dir / base_dir).resolve()

    if not new_cwd.is_dir():
        logger.warning(
            f"Warning: '{new_cwd}' is not a directory. Falling back to tool directory."
        )
        new_cwd = tool_dir  # Fallback to the tool's main directory

    # Determine the shell type.
    shell = "posix" if os.name != "nt" else "windows"

    # Retrieve the scripts dictionary from the tool's manifest.
    scripts = tool.get("manifest", {}).get("scripts", {})
    script = scripts.get(script_name) or scripts.get(shell, {}).get(script_name)
    if not script:
        available_scripts = ", ".join(scripts.keys())
        shell_specific_scripts = ", ".join(scripts.get(shell, {}).keys())
        raise ValueError(
            f"Script '{script_name}' not found for tool '{tool_name}'. "
            f"Available scripts: {available_scripts}. "
            f"Shell-specific scripts: {shell_specific_scripts}"
        )

    # additional_args = additional_args or []
    # command = shlex.split(script) + additional_args

    # Reconstruct the command as a string.
    # If additional_args are provided, append them to the command string.
    additional = " ".join(additional_args) if additional_args else ""
    full_command = f"{script} {additional}".strip()

    logger.info(f"Full command string: {full_command}")

    logger.info(f"Running script '{script_name}' for tool '{tool_name}'...")
    logger.info(f"Command: {full_command}")
    logger.info(f"Tool directory: {tool_dir}")
    logger.info(f"Base directory: {base_dir}")
    logger.info(f"Resolved working directory: {new_cwd}")

    if not new_cwd.exists():
        raise ValueError(f"Error: Working directory '{new_cwd}' does not exist.")

    try:
        subprocess.run(
            full_command,
            cwd=new_cwd,
            check=True,
            shell=True,
        )
    except subprocess.CalledProcessError as e:
        logger.error(f"Command failed with exit code {e.returncode}")
        if e.stdout:
            logger.error(f"Command output:\n{e.stdout}")
        if e.stderr:
            logger.error(f"Error output:\n{e.stderr}")
        raise


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


if __name__ == "__main__":
    app()
