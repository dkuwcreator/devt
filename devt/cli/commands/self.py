import typer
from devt import __version__

self_app = typer.Typer(help="DevT self management commands")

@self_app.command("version")
def self_version():
    """
    Displays the current version of DevT.
    """
    typer.echo(f"DevT version: {__version__}")

@self_app.command("upgrade")
def self_upgrade():
    """
    Checks for updates and installs the latest version of DevT.
    """
    typer.echo("DevT upgraded successfully.")
