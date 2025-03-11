#!/usr/bin/env python3
"""
devt/cli/helpers.py

Helper functions for CLI initialization and common tasks.
"""

import json
import logging
from pathlib import Path
import shutil
from typing import Any, Dict, Optional, Tuple

import typer

from devt.config_manager import ConfigManager
from devt.constants import (
    SCOPE_TO_REGISTRY_DIR,
    WORKSPACE_APP_DIR,
    WORKSPACE_REGISTRY_DIR,
)
from devt.logger_manager import LoggerManager
from devt.registry.manager import RegistryManager
from devt.utils import find_file_type
import pprint

logger = logging.getLogger(__name__)


def is_git_installed() -> bool:
    """
    Check if Git is installed on the system.
    """
    return shutil.which("git") is not None


def check_git_and_exit() -> None:
    """
    Raise an exception if Git is not found.
    """
    if not is_git_installed():
        logger.error("Git is not installed on this system.")
        raise RuntimeError("Git is not installed.")


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

    Errors are raised as exceptions so they can be handled by the
    top-level commands in main.py.
    """
    # Validate scope.
    if scope and scope.lower() not in ["user", "workspace"]:
        logger.error("Invalid scope: %s. Must be 'user' or 'workspace'.", scope)
        raise ValueError("Scope must be either 'user' or 'workspace'.")

    # Validate log level.
    if log_level and log_level not in ["DEBUG", "INFO", "WARNING", "ERROR"]:
        logger.error(
            "Invalid log level: %s. Must be one of DEBUG, INFO, WARNING, ERROR.",
            log_level,
        )
        raise ValueError("Log level must be one of DEBUG, INFO, WARNING, or ERROR.")

    # Build runtime configuration from arguments.
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

    # Initialize configuration manager and logger.
    config_manager = ConfigManager(runtime_config)
    effective_config = config_manager.to_dict()
    logger_manager = LoggerManager.from_dict(effective_config)  # noqa: F841

    logger.info("Effective configuration: %s", effective_config)

    # Determine registry directory based on effective scope.
    effective_scope: str = effective_config["scope"]
    if effective_scope.lower() == "workspace" and ctx.invoked_subcommand != "workspace":
        # Verify the current directory is a Git repository (optional check).
        git_repo = Path.cwd() / ".git"
        if not git_repo.exists():
            logger.debug("Workspace scope selected, but no Git repository found.")
            # Check if there's at least a workspace registry with a manifest.
            has_registry = WORKSPACE_REGISTRY_DIR.exists() and find_file_type(
                "manifest", WORKSPACE_APP_DIR
            )
            if not has_registry:
                logger.error(
                    "No workspace registry found. Run 'devt workspace init' to create one."
                )
                raise FileNotFoundError(
                    "No workspace registry found. Run 'devt workspace init' first."
                )

    registry_dir = SCOPE_TO_REGISTRY_DIR[effective_scope]
    logger.info("Using registry directory: %s", registry_dir)

    # Store configuration and other objects in the Typer context.
    ctx.obj = {
        "config": effective_config,
        "scope": effective_scope,
        "registry_dir": registry_dir,
    }

    logger.info(
        "App context set up with scope: %s, registry_dir: %s",
        effective_scope,
        registry_dir,
    )


def get_scopes_to_query(scope: Optional[str] = None) -> Dict[str, RegistryManager]:
    """
    Returns a dictionary mapping scope names to RegistryManager instances.

    :param scope: If 'user' or 'workspace', returns that single scope.
                  If 'both' / 'all' / None, returns both user and workspace scopes.
    :raises ValueError: If an invalid scope is provided.
    """
    valid_scopes = {"user", "workspace"}
    both_scopes = {"both", "all"}
    scope_lower = scope.lower() if scope else None

    if scope_lower is None or scope_lower in both_scopes:
        logger.info("Querying both 'workspace' and 'user' scopes.")
        return {
            "workspace": RegistryManager(SCOPE_TO_REGISTRY_DIR["workspace"]),
            "user": RegistryManager(SCOPE_TO_REGISTRY_DIR["user"]),
        }
    elif scope_lower in valid_scopes:
        logger.info("Querying single scope: %s", scope_lower)
        return {scope_lower: RegistryManager(SCOPE_TO_REGISTRY_DIR[scope_lower])}
    else:
        logger.error(
            "Invalid scope provided: %s. Choose 'workspace', 'user', or 'both'.", scope
        )
        raise ValueError(
            "Invalid scope provided. Choose 'workspace', 'user', or 'both'."
        )


def get_package_from_registries(
    command: str, scope: Optional[str]
) -> Tuple[Optional[dict], Optional[str]]:
    """
    Searches for a package by its command in the specified scope (or both if scope is None).

    :param command: Unique command identifier for the package.
    :param scope: 'user', 'workspace', 'both', or None.
    :return: A tuple (package_dict, scope_found) or (None, None) if not found.
    """
    scopes = get_scopes_to_query(scope)
    for sc, registry in scopes.items():
        pkg = registry.retrieve_package(command)
        if pkg:
            logger.info("Package '%s' found in scope '%s'.", command, sc)
            return pkg, sc

    logger.warning("Package '%s' not found in any scope.", command)
    return None, scope
