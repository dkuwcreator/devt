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
        ...,
        help="One or more configuration options in the KEY=VALUE format. Example: scope=user log_level=DEBUG"
    )
):
    """
    Updates one or more configuration settings by parsing KEY=VALUE pairs.
    """
    manager = ConfigManager()
    try:
        updates = manager.update_config_from_list(options)
    except ValueError as err:
        typer.echo(f"Error: {err}")
        raise typer.Exit(1)
    if updates:
        typer.echo("Configuration settings have been updated:")
        for key, value in updates.items():
            typer.echo(f"  {key} = {value}")
        logger.info("Updated configuration: %s", updates)
    else:
        typer.echo("No valid configuration options provided.")


@config_app.command("get")
def get_config():
    """
    Displays the current persisted configuration in a line-by-line format.
    """
    manager = ConfigManager()
    current_config = manager.to_dict()
    if not current_config:
        typer.echo("No configuration found. Please set configuration using 'config set'.")
        logger.warning("No configuration found.")
    else:
        typer.echo("Current configuration:")
        for key, value in current_config.items():
            typer.echo(f"{key}: {value}")
        logger.info("Current configuration: %s", current_config)


@config_app.command("reset")
def reset_config():
    """
    Resets the configuration settings to their default values.
    """
    manager = ConfigManager()
    manager.reset()
    typer.echo("Configuration has been reset to default values.")
    logger.info("Configuration reset complete.")


@config_app.command("show")
def show_config():
    """
    Displays the current configuration in a formatted JSON output.
    """
    manager = ConfigManager()
    current_config = manager.to_dict()
    pretty_config = json.dumps(current_config, indent=4)
    typer.echo(pretty_config)
    logger.info("Configuration shown: %s", current_config)
