import sys
import subprocess
import logging
import ssl
import json
from pathlib import Path

from packaging import version
import requests
import typer
import truststore
import urllib3

from devt import __version__
from devt.config_manager import APP_NAME

# Set up SSL context and HTTP pool manager
ctx = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
http = urllib3.PoolManager(ssl_context=ctx)

# Configure logging
logger = logging.getLogger(__name__)
self_app = typer.Typer(help="DevT self management commands")


def get_install_dir() -> Path:
    """Return the installation directory of the executable or script."""
    if getattr(sys, "frozen", False):
        install_dir = Path(sys.executable).parent
    else:
        install_dir = Path(__file__).resolve().parent
    logger.info("Installation directory: %s", install_dir)
    return install_dir


def update_path(target_path: str, remove: bool = False) -> None:
    """Add or remove a directory from the PATH environment variable."""
    user_path = sys.environ.get("PATH", "")
    paths = user_path.split(Path.pathsep) if user_path else []

    if remove:
        if target_path in paths:
            logger.info("Removing %s from PATH", target_path)
            typer.echo(f"Removing {target_path} from PATH...")
            paths = [p for p in paths if p != target_path]
            sys.environ["PATH"] = Path.pathsep.join(paths)
            typer.echo(
                "Removed. Restart your terminal or system for changes to take effect."
            )
    else:
        if target_path not in paths:
            logger.info("Adding %s to PATH", target_path)
            typer.echo(f"Adding {target_path} to PATH...")
            paths.append(target_path)
            sys.environ["PATH"] = Path.pathsep.join(paths)
            typer.echo(
                "Added. Restart your terminal or system for changes to take effect."
            )


def replace_executable(new_executable: Path, current_executable: Path) -> None:
    """Replace the current executable with a new file."""
    backup = current_executable.with_suffix(current_executable.suffix + ".old")
    logger.info("Creating backup of current executable at %s", backup)
    if backup.exists():
        backup.unlink()
    current_executable.rename(backup)
    new_executable.rename(current_executable)
    logger.info("Executable replaced successfully.")


def get_latest_version() -> str:
    """
    Retrieve the latest version available online from GitHub.
    Returns the version string (e.g. "v1.2.3") or an empty string on failure.
    """
    url = "https://api.github.com/repos/dkuwcreator/devt/releases/latest"
    try:
        response = http.request(
            "GET", url, timeout=urllib3.Timeout(connect=10.0, read=10.0)
        )
        data = json.loads(response.data.decode("utf-8"))
        latest = data.get("tag_name", "")
        logger.info("Latest version retrieved: %s", latest)
        return latest
    except Exception as err:
        logger.error("Error retrieving latest version: %s", err)
        return ""


def notify_upgrade_if_available(current_version: str, latest_version: str) -> None:
    """
    Compare current and latest versions.
    Notify the user if the latest version is newer.
    """
    logger.info(
        "Current version: %s, Latest version: %s", current_version, latest_version
    )
    if latest_version and version.parse(latest_version) > version.parse(
        current_version
    ):
        typer.echo(
            f"Upgrade available: {latest_version} (installed: {current_version})"
        )
    else:
        typer.echo("You have the latest version.")


def download_executable(download_url: str, save_path: Path) -> bool:
    """Download the executable from the provided URL using urllib3."""
    typer.echo(f"Downloading {APP_NAME} from GitHub...")
    logger.info("Starting download from %s", download_url)
    try:
        response = http.request(
            "GET", download_url, timeout=urllib3.Timeout(connect=10.0, read=30.0)
        )
        if response.status != 200:
            raise Exception(f"Received status code {response.status}")
    except Exception as err:
        logger.error("Error downloading %s: %s", APP_NAME, err)
        typer.echo(f"Error downloading {APP_NAME}: {err}")
        return False

    try:
        save_path.write_bytes(response.data)
    except IOError as err:
        logger.error("Failed to save file at %s: %s", save_path, err)
        typer.echo("Failed to save the file. Check your network connection.")
        return False

    logger.info("Downloaded file saved to %s", save_path)
    return save_path.exists()


@self_app.command("version")
def self_version() -> None:
    """Show the current version of DevT and check for upgrades."""
    typer.echo(f"DevT version: {__version__}")
    logger.info("User requested version information.")
    latest = get_latest_version()
    if latest:
        notify_upgrade_if_available(__version__, latest)
    else:
        typer.echo("Could not determine the latest version.")


@self_app.command("show")
def self_show() -> None:
    """Show the installation directory and version; check for upgrades."""
    install_dir = get_install_dir()
    typer.echo(f"DevT version: {__version__}")
    typer.echo(f"Installation directory: {install_dir}")
    latest = get_latest_version()
    if __version__ == "dev" and latest:
        typer.echo("Running in development mode. No upgrade checks.")
        typer.echo(f"Latest version: {latest}")
    elif latest:
        notify_upgrade_if_available(__version__, latest)
    else:
        typer.echo("Could not determine the latest version.")


@self_app.command("upgrade")
def self_upgrade() -> None:
    """Download and replace the executable with the latest version."""
    typer.echo("Checking for updates...")
    logger.info("Initiating upgrade process.")
    install_dir = get_install_dir()

    # Ensure installation directory exists
    install_dir.mkdir(exist_ok=True)
    logger.info("Ensured that installation directory exists: %s", install_dir)

    new_executable_path = install_dir / f"{APP_NAME}_new.exe"
    current_executable_path = install_dir / f"{APP_NAME}.exe"
    download_url = (
        "https://github.com/dkuwcreator/devt/releases/latest/download/devt.exe"
    )

    if not download_executable(download_url, new_executable_path):
        logger.error("Download failed. Aborting upgrade.")
        return

    typer.echo(f"{APP_NAME} successfully downloaded to {install_dir}")
    logger.info("Downloaded new executable for upgrade.")

    typer.echo("Replacing executable...")
    replace_executable(new_executable_path, current_executable_path)
    typer.echo("Replacement complete. Restarting application...")
    logger.info("Executable replaced. Restarting application.")

    subprocess.Popen([str(current_executable_path)])
    sys.exit()
