import typer
import logging
import json

from devt.utils import load_json, save_json
from devt.config_manager import CONFIG_FILE, DEFAULT_CONFIG

logger = logging.getLogger(__name__)
config_app = typer.Typer(help="Configuration commands")


@config_app.command("set")
def set_config(
    scope: str = typer.Option(
        None,
        help="Persisted scope for future sessions: user or workspace."
    ),
    log_level: str = typer.Option(
        None,
        help="Persisted log level for future sessions (DEBUG, INFO, WARNING, ERROR)."
    ),
    log_format: str = typer.Option(
        None,
        help="Persisted log format for future sessions: default or detailed."
    ),
    auto_sync: bool = typer.Option(
        None,
        help="Enable background auto-sync for repositories."
    ),
):
    """
    Persists configuration settings for future sessions.
    Only provided options will be updated.
    """
    logger.info("Setting configuration with scope=%s, log_level=%s, log_format=%s", scope, log_level, log_format)
    current_config = load_json(CONFIG_FILE)
    if scope:
        current_config["scope"] = scope
    if log_level:
        current_config["log_level"] = log_level
    if log_format:
        current_config["log_format"] = log_format
    if auto_sync:
        current_config["auto_sync"] = auto_sync
    save_json(CONFIG_FILE, current_config, indent=4)
    typer.echo("Configuration settings have been persisted for future sessions.")
    logger.info("Configuration persisted: %s", current_config)


@config_app.command("get")
def get_config():
    """
    Displays the current persisted configuration in a line-by-line format.
    """
    logger.info("Retrieving current configuration from %s", CONFIG_FILE)
    current_config = load_json(CONFIG_FILE)
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
    logger.info("Showing configuration from %s", CONFIG_FILE)
    current_config = load_json(CONFIG_FILE)
    if not current_config:
        typer.echo("No configuration found. Showing default configuration:")
        return
    pretty_config = json.dumps(current_config, indent=4)
    typer.echo(pretty_config)
    logger.info("Configuration shown: %s", current_config)
