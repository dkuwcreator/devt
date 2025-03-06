#!/usr/bin/env python3
"""
DevT Self-Management Commands

Provides version display, installation directory information, and upgrade functionality.
It checks for updates on GitHub and triggers an external installer for upgrades.
"""

import sys
import subprocess
import logging
import platform
from pathlib import Path

import typer

from packaging import version  # used for comparing versions
from devt import __version__
from devt.config_manager import APP_NAME

# Import common functions to avoid duplication.
from devt.common import get_os_suffix, resolve_version, download_file

logger = logging.getLogger(__name__)
self_app = typer.Typer(help="DevT self management commands")

# Constants for GitHub API timeouts.
TIMEOUT_CONNECT: float = 10.0
TIMEOUT_READ: float = 10.0
TIMEOUT_DOWNLOAD_READ: float = 30.0

def notify_upgrade_if_available(current_version: str, latest_version: str) -> None:
    """
    Notify the user if an upgrade is available.
    """
    logger.info("Current version: %s, Latest version: %s", current_version, latest_version)
    try:
        if latest_version and version.parse(latest_version) > version.parse(current_version):
            typer.echo(
                f"Upgrade available: {latest_version} (installed: {current_version})\n"
                f"Run '{APP_NAME} self upgrade' to update."
            )
        else:
            typer.echo("You have the latest version.")
    except Exception as err:
        logger.error("Error comparing versions: %s", err)
        typer.echo("Error checking version compatibility.")


def get_updater_download_url(version_str: str = "latest") -> str:
    """
    Build the updater download URL dynamically.
    
    The URL format is:
      https://github.com/dkuwcreator/devt/releases/download/<version>/devt-<os_suffix>-installer
    """
    resolved_version = resolve_version(version_str)
    os_suffix = get_os_suffix()
    url = f"https://github.com/dkuwcreator/devt/releases/download/{resolved_version}/devt-{os_suffix}-installer"
    logger.info("Updater download URL: %s", url)
    return url


def get_installer_filename() -> str:
    """
    Determine the local filename for the installer executable based on the platform.
    """
    return f"{APP_NAME}-installer.exe" if platform.system() == "Windows" else f"{APP_NAME}-installer"


def get_install_dir() -> Path:
    """
    Return the installation directory of the executable or script.
    
    If the app is running as a frozen binary, the directory is determined from sys.executable.
    Otherwise, it uses the location of this file.
    """
    install_dir = (
        Path(sys.executable).parent
        if getattr(sys, "frozen", False)
        else Path(__file__).resolve().parent
    )
    logger.info("Installation directory: %s", install_dir)
    return install_dir


def check_updates() -> None:
    """
    Check for updates and notify the user accordingly.
    """
    typer.echo("")
    latest_version = resolve_version("latest")
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
    """
    Display the current DevT version and perform an update check.
    """
    typer.echo(f"DevT {__version__}")
    logger.info("Version information requested.")
    check_updates()


@self_app.command("show")
def self_show() -> None:
    """
    Display the installation directory and DevT version, then perform an update check.
    """
    install_dir = get_install_dir()
    typer.echo(f"DevT {__version__}")
    typer.echo(f"Installation directory: {install_dir}")


@self_app.command("upgrade")
def self_upgrade() -> None:
    """
    Trigger the upgrade process using the external installer.
    """
    if __version__ == "dev":
        typer.echo("Upgrade is not available in development mode.")
        logger.info("Upgrade attempted in development mode; aborting.")
        return

    typer.echo("Checking for updates...")
    logger.info("Starting upgrade process.")

    install_dir = get_install_dir()
    install_dir.mkdir(exist_ok=True)
    logger.info("Ensured installation directory exists: %s", install_dir)

    download_url = get_updater_download_url("latest")
    installer_filename = get_installer_filename()
    installer_path = install_dir / installer_filename

    if not download_file(download_url, installer_path, timeout_connect=TIMEOUT_CONNECT, timeout_read=TIMEOUT_DOWNLOAD_READ):
        logger.error("Updater download failed. Aborting upgrade.")
        typer.echo("Updater download failed. Aborting upgrade.")
        return

    typer.echo(f"Updater downloaded to {installer_path}")
    logger.info("Updater downloaded. Launching installer...")

    try:
        subprocess.Popen([str(installer_path), str(install_dir)], close_fds=True)
        typer.echo("Updater started. Closing DevT...")
        sys.exit(0)  # Exit to allow the installer to update the application safely.
    except Exception as e:
        logger.error("Failed to launch installer: %s", e)
        typer.echo("Failed to launch installer.")

