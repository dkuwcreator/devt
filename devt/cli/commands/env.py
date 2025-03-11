#!/usr/bin/env python3
"""
devt/cli/commands/env.py

DevT Environment Commands

Provides commands to set, see, and remove environment variables in the dotenv file.
"""

import logging
import typer
from pathlib import Path
from dotenv import set_key, get_key, unset_key

from devt.config_manager import ConfigManager

logger = logging.getLogger(__name__)
env_app = typer.Typer(help="Environment commands wrapper for python-dotenv")


def resolve_env_file(env_file: Path = None) -> Path:
    """
    Resolves the path to the environment file.
    If no env_file is provided, retrieves the default from the ConfigManager
    (falling back to ".env" if not configured).
    """
    if env_file is None:
        config = ConfigManager().to_dict()
        env_file = config.get("env_file", ".env")
    logger.debug("Resolved environment file: %s", env_file)
    return Path(env_file)


@env_app.command("set")
def set_env(
    key: str = typer.Argument(..., help="Environment variable key"),
    value: str = typer.Argument(..., help="Environment variable value"),
    env_file: Path = typer.Option(
        None, help="Path to the environment file (overrides config setting)"
    )
):
    """
    Set an environment variable in the dotenv file.
    """
    env_path = resolve_env_file(env_file)
    env_file_str = str(env_path)

    if not env_path.exists():
        logger.info("Environment file '%s' does not exist. Creating it.", env_path)
        env_path.touch()

    set_key(env_file_str, key, value)
    logger.info("Set %s=%s in %s", key, value, env_path)


@env_app.command("see")
def see_env(
    key: str = typer.Argument(..., help="Environment variable key"),
    env_file: Path = typer.Option(
        None, help="Path to the environment file (overrides config setting)"
    )
):
    """
    View the current value of an environment variable in the dotenv file.
    """
    env_path = resolve_env_file(env_file)
    env_file_str = str(env_path)
    value = get_key(env_file_str, key)

    if value is None:
        logger.info("Environment variable '%s' not found in %s", key, env_path)
    else:
        # Minimal output for the user
        typer.echo(f"{key}={value}")
        logger.info("%s=%s", key, value)


@env_app.command("remove")
def remove_env(
    key: str = typer.Argument(..., help="Environment variable key"),
    env_file: Path = typer.Option(
        None, help="Path to the environment file (overrides config setting)"
    )
):
    """
    Remove an environment variable from the dotenv file.
    """
    env_path = resolve_env_file(env_file)
    env_file_str = str(env_path)

    if get_key(env_file_str, key) is None:
        logger.info("Environment variable '%s' not found in %s", key, env_path)
    else:
        unset_key(env_file_str, key)
        logger.info("Removed %s from %s", key, env_path)
