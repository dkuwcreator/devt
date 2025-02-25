"""
devt/cli/helpers.py

Helper functions for CLI initialization and common tasks.
"""

import logging
from pathlib import Path
from typing import Any, List
import typer
from devt.config_manager import (
    setup_environment,
    get_effective_config,
    configure_global_logging,
    USER_REGISTRY_DIR,
    WORKSPACE_REGISTRY_DIR,
)
from devt.registry.manager import (
    PackageRegistry,
    RegistryManager,
    RepositoryRegistry,
    ScriptRegistry,
    create_db_engine,
)
from devt.package.manager import PackageManager
from devt.repo_manager import RepoManager


def setup_app_context(
    ctx: typer.Context, scope: str = None, log_level: str = None, log_format: str = None
) -> None:
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
    if scope and scope.lower() not in ["user", "workspace"]:
        raise typer.BadParameter("Scope must be either 'user' or 'workspace'.")
    if log_level and log_level not in ["DEBUG", "INFO", "WARNING", "ERROR"]:
        raise typer.BadParameter(
            "Log level must be one of DEBUG, INFO, WARNING, or ERROR."
        )
    # Ensure required directories exist and the environment is set up.
    setup_environment()

    # Merge CLI options with persisted configuration.
    runtime_config = {
        k: v
        for k, v in {
            "scope": scope,
            "log_level": log_level,
            "log_format": log_format,
        }.items()
        if v is not None
    }
    effective_config = get_effective_config(runtime_config)
    configure_global_logging(effective_config)

    # Determine registry directory based on effective scope.
    effective_scope = effective_config["scope"]
    registry_dir = (
        WORKSPACE_REGISTRY_DIR
        if effective_scope.lower() == "workspace"
        else USER_REGISTRY_DIR
    )

    # Initialize database engine
    engine = create_db_engine(registry_path=registry_dir)

    # Create and store separate registry instances
    script_registry = ScriptRegistry(engine)
    package_registry = PackageRegistry(engine)
    repository_registry = RepositoryRegistry(engine)
    pkg_manager = PackageManager(registry_dir)

    # Store managers and configuration in the Typer context.
    ctx.obj = {
        "scope": effective_scope,
        "registry_dir": registry_dir,
        "script_registry": script_registry,
        "package_registry": package_registry,
        "repository_registry": repository_registry,
        "pkg_manager": pkg_manager,
    }


def import_and_register_packages(
    pkg_manager: PackageManager,
    registry: RegistryManager,
    path: Path,
    group: str,
    force: bool,
):
    """
    Import packages from a repository directory into the local environment
    and register them.
    """
    packages = pkg_manager.import_package(path, group=group, force=force)
    for pkg in packages:
        existing_pkg = registry.package_registry.get_package(pkg.command)
        if existing_pkg:
            if force:
                registry.unregister_package(pkg.command)
            else:
                typer.echo(
                    f"Package '{pkg.command}' already exists. Use --force to overwrite."
                )
                continue
        registry.register_package(pkg.to_dict())


def update_and_register_single_package(
    pkg_manager: PackageManager,
    registry: RegistryManager,
    command: str,
):
    """
    Update packages in the local environment and register them.
    """
    existing_pkg = registry.package_registry.get_package(command)
    if not existing_pkg:
        typer.echo(f"Package '{command}' does not exist.")
        return

    pkg = pkg_manager.update_package(Path(existing_pkg["location"]), group=existing_pkg["group"])
    if not pkg:
        typer.echo(f"Failed to update package '{command}'.")
        return

    registry.update_package(pkg.to_dict())


def update_and_register_group_packages(
    pkg_manager: PackageManager,
    registry: RegistryManager,
    group: str,
):
    """
    Update packages in the local environment and register them.
    """
    existing_packages = registry.package_registry.list_packages(group=group)
    if not existing_packages:
        typer.echo(f"No packages found in group '{group}'.")
        return

    for existing_pkg in existing_packages:
        pkg = pkg_manager.update_package(Path(existing_pkg["location"]), group=group)
        if not pkg:
            typer.echo(f"Failed to update package '{existing_pkg['command']}'.")
            continue

        registry.update_package(pkg.to_dict())


def remove_and_unregister_single_package(
    pkg_manager: PackageManager,
    registry: RegistryManager,
    command: str,
):
    """
    Remove packages from the local environment and unregister them.
    """
    existing_pkg = registry.package_registry.get_package(command)
    if not existing_pkg:
        typer.echo(f"Package '{command}' does not exist.")
        return

    registry.unregister_package(command)
    pkg_manager.delete_package(Path(existing_pkg["location"]))


def remove_and_unregister_group_packages(
    pkg_manager: PackageManager,
    registry: RegistryManager,
    group: str,
):
    """
    Remove packages from the local environment and unregister them.
    """
    existing_packages = registry.package_registry.list_packages(group=group)
    if not existing_packages:
        typer.echo(f"No packages found in group '{group}'.")
        return

    for existing_pkg in existing_packages:
        remove_and_unregister_single_package(
            pkg_manager, registry, existing_pkg["command"]
        )
