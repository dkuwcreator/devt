import typer
from devt.utils import load_json, save_json
from devt.config_manager import CONFIG_FILE

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
):
    """
    Persists configuration settings for future sessions.
    Only provided options will be updated.
    """
    current_config = load_json(CONFIG_FILE)
    if scope:
        current_config["scope"] = scope
    if log_level:
        current_config["log_level"] = log_level
    if log_format:
        current_config["log_format"] = log_format
    save_json(CONFIG_FILE, current_config, indent=4)
    typer.echo("Configuration settings have been persisted for future sessions.")
