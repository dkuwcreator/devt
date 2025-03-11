#!/usr/bin/env python3
"""
devt/cli/commands/config.py

DevT Configuration Commands

Provides commands to set, get, reset, and show the current configuration settings.
"""

import json
import logging
from typing import List

import typer

from devt.config_manager import ConfigManager

logger = logging.getLogger(__name__)
config_app = typer.Typer(help="Configuration commands")


@config_app.command("set")
def set_config(
    options: List[str] = typer.Argument(
        ..., help="Configuration options in KEY=VALUE format (e.g. scope=user log_level=DEBUG)."
    )
):
    """
    Update configuration settings by parsing KEY=VALUE pairs.
    """
    manager = ConfigManager()
    updates = manager.update_config_from_list(options)

    if updates:
        logger.info("Updated configuration: %s", updates)
    else:
        logger.warning("No valid configuration options provided.")


@config_app.command("get")
def get_config():
    """
    Display the current persisted configuration in a line-by-line format.
    """
    manager = ConfigManager()
    config = manager.to_dict()

    if not config:
        logger.warning("No configuration found. Please set configuration using 'config set'.")
    else:
        # Minimal echo for user output
        for key, value in config.items():
            typer.echo(f"{key}: {value}")
        logger.info("Displayed configuration: %s", config)


@config_app.command("reset")
def reset_config():
    """
    Reset the configuration settings to their default values.
    """
    manager = ConfigManager()
    manager.reset()
    logger.info("Configuration has been reset to default values.")


@config_app.command("show")
def show_config():
    """
    Display the current configuration in a formatted JSON output.
    """
    manager = ConfigManager()
    config = manager.to_dict()
    # Minimal echo for structured output
    typer.echo(json.dumps(config, indent=4))
    logger.info("Configuration shown: %s", config)
