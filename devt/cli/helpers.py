"""
devt/cli/helpers.py

Helper functions for CLI initialization and common tasks.
"""

import logging
from pathlib import Path
import shutil
from typing import Any, Dict, Optional, Tuple

import typer

from devt.config_manager import (
    setup_environment,
    get_effective_config,
    configure_global_logging,
    USER_REGISTRY_DIR,
    WORKSPACE_REGISTRY_DIR,
)
from devt.registry.manager import RegistryManager
from devt.package.manager import PackageManager
from devt.utils import find_file_type

logger = logging.getLogger(__name__)


def is_git_installed() -> bool:
    """Check if Git is installed on the system."""
    return shutil.which("git") is not None


def check_git_and_exit() -> None:
    """Exit if Git is not found."""
    if not is_git_installed():
        raise typer.Exit(code=1)


def setup_app_context(
    ctx: typer.Context,
    scope: Optional[str] = None,
    log_level: Optional[str] = None,
    log_format: Optional[str] = None,
    auto_sync: bool = None,
) -> None:
    """
    Initializes the environment, configures logging, and registers
    the necessary managers in the Typer context for CLI commands.
    """
    if scope and scope.lower() not in ["user", "workspace"]:
        raise typer.BadParameter("Scope must be either 'user' or 'workspace'.")
    if log_level and log_level not in ["DEBUG", "INFO", "WARNING", "ERROR"]:
        raise typer.BadParameter(
            "Log level must be one of DEBUG, INFO, WARNING, or ERROR."
        )

    # Ensure required directories exist and the environment is set up.
    setup_environment()

    # Merge CLI options with persisted configuration.
    runtime_config: Dict[str, Any] = {
        k: v
        for k, v in {
            "scope": scope,
            "log_level": log_level,
            "log_format": log_format,
            "auto_sync": auto_sync,
        }.items()
        if v is not None
    }
    effective_config = get_effective_config(runtime_config)
    configure_global_logging(effective_config)
    logger.info("Effective configuration: %s", effective_config)

    # Determine registry directory based on effective scope.
    effective_scope: str = effective_config["scope"]

    if effective_scope.lower() == "workspace":
        # Verify the current directory is a Git repository.
        git_repo = Path.cwd() / ".git"
        if not git_repo.exists():
            typer.echo("Workspace scope selected but no Git repository found.")
            # Ensure the workspace registry exists and has a manifest.
            has_registry = WORKSPACE_REGISTRY_DIR.exists() and find_file_type("manifest", WORKSPACE_REGISTRY_DIR)
            if not has_registry:
                typer.echo("No workspace registry found. Run 'devt workspace init' to create one.")
                raise typer.Exit(code=1)
    
    registry_dir: Path = (
        WORKSPACE_REGISTRY_DIR
        if effective_scope.lower() == "workspace"
        else USER_REGISTRY_DIR
    )

    # Create unified managers.
    registry: RegistryManager = RegistryManager(effective_scope)
    pkg_manager: PackageManager = PackageManager(effective_scope)

    # Store managers and configuration in the Typer context.
    ctx.obj = {
        "config": effective_config,
        "scope": effective_scope,
        "registry_dir": registry_dir,
        "registry": registry,
        "pkg_manager": pkg_manager,
    }
           
    logger.info(
        "App context set up with scope: %s, registry_dir: %s",
        effective_scope,
        registry_dir,
    )


def get_scopes_to_query(scope: Optional[str] = None) -> Dict[str, RegistryManager]:
    """
    Returns a dictionary mapping scope names to their corresponding RegistryManager instances.
    If scope is provided as 'user' or 'workspace', returns that one.
    If scope is 'both' or None, returns both.
    """

    if scope:
        scope_lower = scope.lower()
        if scope_lower in ("both", "all"):
            return {
                "user": RegistryManager("user"),
                "workspace": RegistryManager("workspace"),
            }
        elif scope_lower not in ("user", "workspace"):
            typer.echo("Invalid scope provided. Choose 'workspace', 'user', or 'both'.")
            raise typer.Exit(code=1)
        if scope_lower == "user":
            return {"user": RegistryManager("user")}
        else:
            return {"workspace": RegistryManager("workspace")}
    else:
        return {
            "user": RegistryManager("user"),
            "workspace": RegistryManager("workspace"),
        }


def get_package_from_registries(
    command: str, scope: Optional[str]
) -> Tuple[Optional[dict], Optional[str]]:
    """
    Searches for a package by its command in the specified scope (or both if scope is None).

    Returns a tuple of (package, scope_found) or (None, None) if not found.
    """
    scopes = get_scopes_to_query(scope)
    for sc, registry in scopes.items():
        pkg = registry.retrieve_package(command)
        if pkg:
            return pkg, sc
    return None, scope
