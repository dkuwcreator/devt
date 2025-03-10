import json
import logging
import typer

from devt.config_manager import ConfigManager

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
    manager = ConfigManager()
    # Build a dictionary of the provided (non-None) options.
    updates = {}
    if scope:
        updates["scope"] = scope
    if log_level:
        updates["log_level"] = log_level
    if log_format:
        updates["log_format"] = log_format
    if auto_sync is not None:
        updates["auto_sync"] = auto_sync

    if updates:
        manager.update_config(**updates)
        typer.echo("Configuration settings have been persisted for future sessions.")
        logger.info("Updated configuration: %s", updates)
    else:
        typer.echo("No configuration options provided to update.")
        logger.info("No configuration changes were made.")


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
