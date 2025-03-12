#!/usr/bin/env python3
"""
devt/cli/commands/self.py

DevT Self-Management Commands

Provides version display, installation directory information, and upgrade functionality.
It checks for updates on GitHub and triggers an external installer for upgrades.
"""

import shutil
import sys
import subprocess
import logging
import platform
from pathlib import Path

import typer
from packaging import version  # used for comparing versions

from devt import __version__
from devt.common import get_os_key, get_os_suffix, resolve_version, download_file
from devt.config_manager import ConfigManager
from devt.constants import APP_NAME, USER_REGISTRY_DIR
from devt.utils import force_remove, on_exc

# Removed: from devt.error_wrapper import handle_errors

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
    logger.info(
        "Current version: %s, Latest version: %s", current_version, latest_version
    )
    if latest_version and version.parse(latest_version) > version.parse(
        current_version
    ):
        typer.echo(
            f"Upgrade available: {latest_version} (installed: {current_version})\n"
            f"Run '{APP_NAME} self upgrade' to update."
        )
    else:
        typer.echo("You have the latest version.")


def get_updater_download_url(version_str: str = "latest") -> str:
    """
    Build the updater download URL dynamically.

    The URL format is:
      https://github.com/dkuwcreator/devt/releases/download/<version>/devt-<os_key>-installer<os_suffix>
    """
    resolved_version = resolve_version(version_str)
    os_key = get_os_key()
    os_suffix = get_os_suffix()
    url = f"https://github.com/dkuwcreator/devt/releases/download/{resolved_version}/devt-{os_key}-installer{os_suffix}"
    logger.info("Updater download URL: %s", url)
    return url


def get_installer_filename() -> str:
    """
    Determine the local filename for the installer executable based on the platform.
    """
    return (
        f"{APP_NAME}-installer.exe"
        if platform.system() == "Windows"
        else f"{APP_NAME}-installer"
    )


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
    typer.echo("")  # Minimal spacing for output clarity
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
    check_updates()


@self_app.command("upgrade")
def self_upgrade() -> None:
    """
    Trigger the upgrade process using the external installer.
    """
    logger.info("Starting upgrade process.")
    if __version__ == "dev":
        logger.info("Upgrade attempted in development mode; aborting.")
        return

    logger.info("Checking for updates...")
    typer.echo("Checking for updates...")

    # Check if the latest version is already installed.
    latest_version = resolve_version("latest")
    if latest_version and version.parse(latest_version) <= version.parse(__version__):
        logger.info("Latest version (%s) already installed.", __version__)
        typer.echo("You already have the latest version installed.")
        return

    install_dir = get_install_dir()
    install_dir.mkdir(exist_ok=True)
    logger.info("Ensured installation directory exists: %s", install_dir)

    typer.echo("Downloading the updater...")
    download_url = get_updater_download_url("latest")
    installer_filename = get_installer_filename()
    installer_path = install_dir / installer_filename

    if not download_file(
        download_url,
        installer_path,
        timeout_connect=TIMEOUT_CONNECT,
        timeout_read=TIMEOUT_DOWNLOAD_READ,
    ):
        logger.error("Updater download failed. Aborting upgrade.")
        raise RuntimeError("Updater download failed.")

    logger.info("Updater downloaded to %s", installer_path)

    subprocess.Popen([str(installer_path), str(install_dir)], close_fds=True)
    logger.info("Updater started. Closing DevT...")
    typer.echo("Updater started, please wait. Closing DevT...")
    sys.exit(0)


@self_app.command("reset")
def self_reset() -> None:
    """
    Reset the application to its initial state by removing the Registry directory.
    """
    logger.info("Resetting the application to its initial state.")
    typer.confirm(
        "This action will remove all user data and configurations. Continue?",
        abort=True,
    )
    # Delete the User Registry folder
    try:
        shutil.rmtree(USER_REGISTRY_DIR / "repos", onexc=on_exc)
    except Exception as e:
        logger.error(
            "Failed to remove repository %s: %s", USER_REGISTRY_DIR / "repos", e
        )
    force_remove(USER_REGISTRY_DIR)

    logger.info("User Registry folder removed.")
    # Reset the configuration
    logger.info("Resetting the configuration.")
    ConfigManager().reset()
    typer.echo("Application reset successfully.")
