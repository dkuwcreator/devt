"""
devt/cli/helpers.py

Helper functions for CLI initialization and common tasks.
"""

import logging
import typer
from devt.config_manager import (
    setup_environment,
    get_effective_config,
    configure_global_logging,
    USER_REGISTRY_DIR,
    WORKSPACE_REGISTRY_DIR,
)
from devt.registry.manager import PackageRegistry, RepositoryRegistry, ScriptRegistry, create_db_engine
from devt.package.manager import PackageManager
from devt.repo_manager import RepoManager


def setup_app_context(ctx: typer.Context, scope: str, log_level: str, log_format: str) -> None:
    """
    Initializes the environment, configures logging, and registers
    the necessary managers in the Typer context for CLI commands.

    Steps:
      1. Set up the required directories and environment.
      2. Merge CLI options with persisted configuration to determine
         the effective configuration.
      3. Configure global logging based on the effective configuration.
      4. Instantiate the registry, package, and repository managers based on the scope.
      5. Store these objects in the Typer context for use in subsequent commands.

    Parameters:
        ctx (typer.Context): The Typer context to store shared objects.
        scope (str): The scope of the command ('user' or 'workspace').
        log_level (str): The desired logging level (e.g., DEBUG, INFO).
        log_format (str): The logging format type (e.g., default or detailed).
    """
    if scope.lower() not in ["user", "workspace"]:
        raise typer.BadParameter("Scope must be either 'user' or 'workspace'.")
    if log_level not in ["DEBUG", "INFO", "WARNING", "ERROR"]:
        raise typer.BadParameter("Log level must be one of DEBUG, INFO, WARNING, or ERROR.")
    # Ensure required directories exist and the environment is set up.
    setup_environment()

    # Merge CLI options with persisted configuration.
    runtime_config = {"scope": scope, "log_level": log_level, "log_format": log_format}
    effective_config = get_effective_config(runtime_config)
    configure_global_logging(effective_config)

    # Determine registry directory based on effective scope.
    effective_scope = effective_config["scope"]
    registry_dir = WORKSPACE_REGISTRY_DIR if effective_scope.lower() == "workspace" else USER_REGISTRY_DIR

    # Initialize database engine
    engine = create_db_engine(registry_path=registry_dir)

    # Create and store separate registry instances
    script_registry = ScriptRegistry(engine)
    package_registry = PackageRegistry(engine)
    repository_registry = RepositoryRegistry(engine)
    pkg_manager = PackageManager(registry_dir / "tools")

    # Instantiate the registry and package managers.
    pkg_manager = PackageManager(registry_dir / "tools")

    # Store managers and configuration in the Typer context.
    ctx.obj = {
        "scope": effective_scope,
        "script_registry": script_registry,
        "package_registry": package_registry,
        "repository_registry": repository_registry,
        "pkg_manager": pkg_manager
    }
