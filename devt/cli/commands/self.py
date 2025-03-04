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
GITHUB_LATEST_RELEASE_URL = (
    "https://api.github.com/repos/dkuwcreator/devt/releases/latest"
)
GITHUB_UPDATER_URL = (
    "https://github.com/dkuwcreator/devt/releases/latest/download/devt_installer.exe"
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
        Path(sys.executable).parent
        if getattr(sys, "frozen", False)
        else Path(__file__).resolve().parent
    )
    logger.info("Installation directory: %s", install_dir)
    return install_dir


def get_latest_version() -> str:
    """Retrieve the latest version available online from GitHub."""
    try:
        response = http.request(
            "GET",
            GITHUB_LATEST_RELEASE_URL,
            timeout=urllib3.Timeout(connect=TIMEOUT_CONNECT, read=TIMEOUT_READ),
        )
        data = json.loads(response.data.decode("utf-8"))
        latest = data.get("tag_name", "")
        logger.info("Latest version retrieved: %s", latest)
        return latest
    except Exception as err:
        logger.error("Error retrieving latest version: %s", err)
        return ""


def notify_upgrade_if_available(current_version: str, latest_version: str) -> None:
    """Notify the user if an upgrade is available."""
    logger.info(
        "Current version: %s, Latest version: %s", current_version, latest_version
    )
    if latest_version and version.parse(latest_version) > version.parse(current_version):
        typer.echo(
            f"Upgrade available: {latest_version} (installed: {current_version})\n"
            f"Run '{APP_NAME} self upgrade' to update."
        )
    else:
        typer.echo("You have the latest version.")


def download_file(download_url: str, save_path: Path) -> bool:
    """Download a file from a given URL using urllib3."""
    typer.echo(f"Downloading {save_path.name} from GitHub...")
    logger.info("Starting download from %s", download_url)

    try:
        response = http.request(
            "GET",
            download_url,
            timeout=urllib3.Timeout(
                connect=TIMEOUT_CONNECT, read=TIMEOUT_DOWNLOAD_READ
            ),
        )
        if response.status != 200:
            raise Exception(f"HTTP Error {response.status}")

        save_path.write_bytes(response.data)
        logger.info("Downloaded file saved to %s", save_path)
        return True
    except Exception as err:
        logger.error("Error downloading %s: %s", save_path.name, err)
        typer.echo(f"Error downloading {save_path.name}: {err}")
        return False


def check_updates() -> None:
    """Check for updates and notify the user."""
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
def self_upgrade(
    force: bool = False,
    target_version: str = typer.Option(
        None,
        "--version",
        help="Target version to upgrade/downgrade to. If omitted, the latest version is used.",
    ),
    downgrade: bool = typer.Option(
        False, "--downgrade", help="Allow downgrading if target version is lower than the current version."
    )
) -> None:
    """Trigger the upgrade process using the external installer."""
    if __version__ == "dev":
        typer.echo("Upgrade is not available in development mode.")
        logger.info("Upgrade attempted in development mode; aborting.")
        return

    # If no target version provided, get the latest version.
    if target_version is None:
        target_version = get_latest_version()
        if not target_version:
            typer.echo("Could not determine the latest version. Aborting upgrade.")
            return

    # Check if the target version equals current version.
    if target_version == __version__ and not force:
        typer.echo(f"You are already running version {__version__}. Use --force to re-install.")
        return

    # Prevent downgrade unless explicitly allowed.
    if version.parse(target_version) < version.parse(__version__) and not downgrade:
        typer.echo(
            f"Target version {target_version} is lower than the current version ({__version__}). "
            "Use --downgrade to perform a downgrade."
        )
        return

    # If upgrading, you might also check that target_version is greater than current version.
    if version.parse(target_version) > version.parse(__version__) and not force:
        # In this example, force is not required for a normal upgrade.
        typer.echo(f"Upgrading to version {target_version}...")
    elif downgrade:
        typer.echo(f"Downgrading to version {target_version}...")

    logger.info("Starting upgrade process to target version: %s", target_version)

    install_dir = get_install_dir()
    install_dir.mkdir(exist_ok=True)
    logger.info("Ensured installation directory exists: %s", install_dir)

    installer_exe_path = install_dir / f"{APP_NAME}_installer.exe"

    # Download the installer (updater)
    if not download_file(GITHUB_UPDATER_URL, installer_exe_path):
        logger.error("Updater download failed. Aborting upgrade.")
        typer.echo("Updater download failed. Aborting upgrade.")
        return

    typer.echo(f"Updater downloaded to {installer_exe_path}")
    logger.info("Updater downloaded. Launching installer...")

    # Build the command-line arguments for the external installer.
    cmd = [str(installer_exe_path), str(install_dir), target_version]
    if downgrade:
        cmd.append("--downgrade")
    if force:
        cmd.append("--force")

    try:
        subprocess.Popen(cmd, close_fds=True)
        typer.echo("Updater started. Closing DevT...")
        sys.exit(0)  # Exit DevT to allow the installer to replace it safely.
    except Exception as e:
        logger.error("Failed to launch installer: %s", e)
        typer.echo("Failed to launch installer.")


@self_app.command("uninstall")
def self_uninstall() -> None:
    """Trigger the uninstallation process using the external installer."""
    if __version__ == "dev":
        typer.echo("Uninstall is not available in development mode.")
        logger.info("Uninstall attempted in development mode; aborting.")
        return

    install_dir = get_install_dir()
    install_dir.mkdir(exist_ok=True)
    logger.info("Ensured installation directory exists: %s", install_dir)

    installer_exe_path = install_dir / f"{APP_NAME}_installer.exe"

    # Download the installer if it doesn't exist
    if not installer_exe_path.exists():
        typer.echo("Downloading uninstaller...")
        if not download_file(GITHUB_UPDATER_URL, installer_exe_path):
            logger.error("Uninstaller download failed. Aborting uninstall.")
            typer.echo("Uninstaller download failed. Aborting uninstall.")
            return

    typer.echo(f"Uninstaller downloaded to {installer_exe_path}")
    logger.info("Uninstaller downloaded. Launching uninstaller...")

    try:
        subprocess.Popen([str(installer_exe_path), "uninstall"], close_fds=True)
        typer.echo("Uninstaller started. Closing DevT...")
        sys.exit(0)  # Exit DevT to allow the uninstaller to clean up safely
    except Exception as e:
        logger.error("Failed to launch uninstaller: %s", e)
        typer.echo("Failed to launch uninstaller.")


if __name__ == "__main__":
    self_app()
