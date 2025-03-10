import json
import logging

import typer

from devt.config_manager import ConfigManager
from devt.utils import save_json

logger = logging.getLogger(__name__)
config_app = typer.Typer(help="Configuration commands")


@config_app.command("set")
def set_config(
    scope: str = typer.Option(None, help="Persisted scope for future sessions: user or workspace."),
    log_level: str = typer.Option(None, help="Persisted log level for future sessions (DEBUG, INFO, WARNING, ERROR)."),
    log_format: str = typer.Option(None, help="Persisted log format for future sessions: default or detailed."),
    auto_sync: bool = typer.Option(None, help="Enable background auto-sync for repositories."),
):
    """
    Persists configuration settings for future sessions.
    Only provided options will be updated.
    """
    logger.info(
        "Setting configuration with scope=%s, log_level=%s, log_format=%s, auto_sync=%s",
        scope, log_level, log_format, auto_sync,
    )
    manager = ConfigManager()
    if scope:
        manager.set_config_value("scope", scope)
    if log_level:
        manager.set_config_value("log_level", log_level)
    if log_format:
        manager.set_config_value("log_format", log_format)
    if auto_sync is not None:
        manager.set_config_value("auto_sync", auto_sync)
    typer.echo("Configuration settings have been persisted for future sessions.")
    logger.info("Configuration persisted: %s", manager.to_dict())


@config_app.command("get")
def get_config():
    """
    Displays the current persisted configuration in a line-by-line format.
    """
    manager = ConfigManager()
    current_config = manager.to_dict()
    if not current_config:
        typer.echo("No configuration found. Please set configuration using 'config set'.")
        logger.warning("No configuration found in %s", CONFIG_FILE)
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
    logger.info("Resetting configuration to defaults: %s", DEFAULT_CONFIG)
    save_json(CONFIG_FILE, DEFAULT_CONFIG)
    typer.echo("Configuration has been reset to default values.")
    logger.info("Configuration reset complete.")


@config_app.command("show")
def show_config():
    """
    Displays the current persisted configuration in a formatted JSON output.
    If no persisted configuration is found, displays the default configuration.
    """
    manager = ConfigManager()
    current_config = manager.to_dict() or DEFAULT_CONFIG
    pretty_config = json.dumps(current_config, indent=4)
    typer.echo(pretty_config)
    logger.info("Configuration shown: %s", current_config)
