import sys
import subprocess
import logging
import ssl
import json
from pathlib import Path
import os

from packaging import version
import typer
import truststore
import urllib3

from devt import __version__
from devt.config_manager import APP_NAME

# Constants
GITHUB_LATEST_RELEASE_URL = "https://api.github.com/repos/dkuwcreator/devt/releases/latest"
GITHUB_DOWNLOAD_URL = (
    "https://github.com/dkuwcreator/devt/releases/latest/download/devt.exe"
)
TIMEOUT_CONNECT = 10.0
TIMEOUT_READ = 10.0
TIMEOUT_DOWNLOAD_READ = 30.0
TIMEOUT_PROCESS = 60

# SSL and HTTP Manager Setup
ctx = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
http = urllib3.PoolManager(ssl_context=ctx)

# Logging and Typer setup
logger = logging.getLogger(__name__)
self_app = typer.Typer(help="DevT self management commands")


def get_install_dir() -> Path:
    """Return the installation directory of the executable or script."""
    install_dir = (
        Path(sys.executable).parent if getattr(sys, "frozen", False)
        else Path(__file__).resolve().parent
    )
    logger.info("Installation directory: %s", install_dir)
    return install_dir


def update_path(target_path: str, remove: bool = False) -> None:
    """Add or remove a directory from the PATH environment variable."""
    current_path = os.environ.get("PATH", "")
    paths = current_path.split(os.pathsep) if current_path else []

    action = "Removing" if remove else "Adding"
    if remove and target_path in paths:
        logger.info("%s %s from PATH", action, target_path)
        typer.echo(f"{action} {target_path} from PATH...")
        paths = [p for p in paths if p != target_path]
    elif not remove and target_path not in paths:
        logger.info("%s %s to PATH", action, target_path)
        typer.echo(f"{action} {target_path} to PATH...")
        paths.append(target_path)
    else:
        return

    os.environ["PATH"] = os.pathsep.join(paths)
    typer.echo("Changed. Restart your terminal or system for changes to take effect.")


def replace_executable(new_executable: Path, current_executable: Path) -> None:
    """Replace the current executable with a new file."""
    backup = current_executable.with_suffix(current_executable.suffix + ".old")
    logger.info("Creating backup at %s", backup)
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
    try:
        response = http.request(
            "GET",
            GITHUB_LATEST_RELEASE_URL,
            timeout=urllib3.Timeout(connect=TIMEOUT_CONNECT, read=TIMEOUT_READ)
        )
        data = json.loads(response.data.decode("utf-8"))
        latest = data.get("tag_name", "")
        logger.info("Latest version retrieved: %s", latest)
        return latest
    except Exception as err:
        logger.error("Error retrieving latest version: %s", err)
        return ""


def notify_upgrade_if_available(current_version: str, latest_version: str) -> None:
    """Compare versions and notify the user if an upgrade is available."""
    logger.info("Current version: %s, Latest version: %s", current_version, latest_version)
    if latest_version and version.parse(latest_version) > version.parse(current_version):
        typer.echo(
            f"Upgrade available: {latest_version} (installed: {current_version})\n"
            f"Run '{APP_NAME} self upgrade' to update."
        )
    else:
        typer.echo("You have the latest version.")


def download_executable(download_url: str, save_path: Path) -> bool:
    """Download the executable from the given URL using urllib3."""
    typer.echo(f"Downloading {APP_NAME} from GitHub...")
    logger.info("Starting download from %s", download_url)

    try:
        response = http.request(
            "GET",
            download_url,
            timeout=urllib3.Timeout(connect=TIMEOUT_CONNECT, read=TIMEOUT_DOWNLOAD_READ)
        )
        if response.status != 200:
            raise Exception(f"Status code: {response.status}")
    except Exception as err:
        logger.error("Error downloading %s: %s", APP_NAME, err)
        typer.echo(f"Error downloading {APP_NAME}: {err}")
        return False

    try:
        save_path.write_bytes(response.data)
        logger.info("Downloaded file saved to %s", save_path)
    except IOError as err:
        logger.error("Failed to save file at %s: %s", save_path, err)
        typer.echo("Failed to save the file. Check your network connection.")
        return False

    return save_path.exists()


def check_updates() -> None:
    """
    Check for updates and notify the user.
    In development mode upgrade checks are omitted but the latest version is shown.
    """
    latest_version = get_latest_version()
    if __version__ == "dev":
        typer.echo("Running in development mode. Upgrade checks are disabled.")
        if latest_version:
            typer.echo(f"Latest version available: {latest_version}")
    elif latest_version:
        notify_upgrade_if_available(__version__, latest_version)
    else:
        typer.echo("Could not determine the latest version.")


@self_app.command("version")
def self_version() -> None:
    """Display the current DevT version and perform an update check."""
    typer.echo(f"DevT version: {__version__}")
    logger.info("Version information requested.")
    check_updates()


@self_app.command("show")
def self_show() -> None:
    """Display the installation directory and DevT version, then perform an update check."""
    install_dir = get_install_dir()
    typer.echo(f"DevT version: {__version__}")
    typer.echo(f"Installation directory: {install_dir}")
    check_updates()


@self_app.command("upgrade")
def self_upgrade() -> None:
    """Download and replace the executable with the latest version."""
    if __version__ == "dev":
        typer.echo("Upgrade is not available in development mode.")
        logger.info("Upgrade attempted in development mode; aborting.")
        return

    typer.echo("Checking for updates...")
    logger.info("Starting upgrade process.")
    install_dir = get_install_dir()
    install_dir.mkdir(exist_ok=True)
    logger.info("Ensured installation directory exists: %s", install_dir)

    new_executable_path = install_dir / f"{APP_NAME}_new.exe"
    current_executable_path = install_dir / f"{APP_NAME}.exe"

    if not download_executable(GITHUB_DOWNLOAD_URL, new_executable_path):
        logger.error("Download failed. Aborting upgrade.")
        typer.echo("Download failed. Aborting upgrade.")
        return

    typer.echo(f"{APP_NAME} successfully downloaded to {install_dir}")
    logger.info("Downloaded new executable.")

    typer.echo("Replacing executable...")
    try:
        replace_executable(new_executable_path, current_executable_path)
        typer.echo("Replacement complete. Restarting application...")
        logger.info("Executable replaced. Launching new process.")
    except Exception as e:
        logger.error("Failed to replace executable: %s", e)
        typer.echo("Failed to replace executable.")
        return

    sys.exit(0)

    # creationflags = subprocess.DETACHED_PROCESS if sys.platform.startswith("win") else 0
    # try:
    #     subprocess.run(
    #         [str(current_executable_path)],
    #         creationflags=creationflags,
    #         timeout=TIMEOUT_PROCESS
    #     )
    #     logger.info("New process launched successfully.")
    #     sys.exit(0)
    # except subprocess.TimeoutExpired:
    #     logger.error("Process launch timed out.")
    #     typer.echo("Process launch timed out.")
    # except Exception as e:
    #     logger.error("Failed to launch new process: %s", e)
    #     typer.echo("Failed to launch new process.")
