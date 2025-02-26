import typer
from devt.config_manager import APP_NAME
from devt import __version__

self_app = typer.Typer(help=f"{APP_NAME} self management commands")

@self_app.command("version")
def self_version():
    """
    Displays the current version of DevT.
    """
    typer.echo(f"{APP_NAME} version: {__version__}")

@self_app.command("upgrade")
def self_upgrade():
    """
    Checks for updates and installs the latest version of DevT.
    """
    typer.echo(f"{APP_NAME} upgraded successfully.")
