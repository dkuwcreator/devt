#!/usr/bin/env python3
"""
DevT Installer

Downloads the main executable from GitHub, replaces any existing copy,
updates the user PATH, and optionally restarts the application.
"""

import platform
import sys
import subprocess
import shutil
import time
import logging
import os
from pathlib import Path

import typer

from devt.common import get_os_key, resolve_version, download_file

app = typer.Typer()
logger = logging.getLogger(__name__)

# Timeouts for HTTP requests.
TIMEOUT_CONNECT = 10.0
TIMEOUT_READ = 30.0

def get_download_url(version: str) -> str:
    """
    Build the download URL using the provided version and OS key.
    
    If version is 'latest', resolve it via the GitHub API.
    The URL points to the main executable artifact produced by the build.
    """
    resolved_version = resolve_version(version)
    os_key = get_os_key()
    ext = ".exe" if platform.system() == "Windows" else ""
    return f"https://github.com/dkuwcreator/devt/releases/download/{resolved_version}/devt-{os_key}{ext}"


def download_executable(url: str, destination: Path) -> bool:
    """
    Download the executable from the URL to the destination path.
    """
    logger.info("Downloading DevT from %s...", url)
    if not download_file(url, destination, timeout_connect=TIMEOUT_CONNECT, timeout_read=TIMEOUT_READ):
        logger.error("Download failed for URL: %s", url)
        return False
    return True


def replace_executable(new_exe: Path, current_exe: Path, wait_time: int = 3) -> None:
    """
    Backup any existing executable and replace it with the new download.
    """
    logger.info("Waiting %d seconds for DevT to close...", wait_time)
    time.sleep(wait_time)  # Pause to allow any running instance to close.
    backup = current_exe.with_suffix(".old")
    try:
        if current_exe.exists():
            shutil.move(str(current_exe), str(backup))
            logger.info("Backed up old executable to %s", backup)
        shutil.move(str(new_exe), str(current_exe))
        logger.info("Replaced executable at %s", current_exe)
    except Exception as err:
        logger.error("Error replacing executable: %s", err)
        sys.exit(1)


def restart_application(executable: Path) -> None:
    """
    Restart the installed application (e.g. to verify the new version).
    """
    logger.info("Restarting DevT...")
    try:
        subprocess.Popen([str(executable), "self", "version"])
    except Exception as err:
        logger.error("Failed to restart DevT: %s", err)


def set_env_var(name: str, value: str) -> None:
    """
    Persist a user environment variable across sessions.
    
    On Windows, writes to the registry and broadcasts the change.
    On Linux/macOS, appends export commands to ~/.bashrc and ~/.zshrc.
    """
    system = platform.system()
    if system == "Windows":
        try:
            import winreg, ctypes
            reg_type = winreg.REG_EXPAND_SZ if name.lower() == "path" else winreg.REG_SZ
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_SET_VALUE) as key:
                winreg.SetValueEx(key, name, 0, reg_type, value)
            HWND_BROADCAST = 0xFFFF
            WM_SETTINGCHANGE = 0x001A
            SMTO_ABORTIFHUNG = 0x0002
            ctypes.windll.user32.SendMessageTimeoutW(
                HWND_BROADCAST, WM_SETTINGCHANGE, 0, "Environment", SMTO_ABORTIFHUNG, 5000, None
            )
            logger.info("Set environment variable: %s = %s", name, value)
        except Exception as e:
            logger.error("Error setting %s on Windows: %s", name, e)
    elif system in ["Linux", "Darwin"]:
        rc_files = [os.path.expanduser("~/.bashrc"), os.path.expanduser("~/.zshrc")]
        export_line = f'export {name}="{value}"\n'
        for rc in rc_files:
            try:
                if os.path.exists(rc):
                    with open(rc, "r") as file:
                        content = file.read()
                    if export_line.strip() not in content:
                        with open(rc, "a") as file:
                            file.write(export_line)
            except Exception as e:
                logger.error("Error updating %s: %s", rc, e)
        os.environ[name] = value
        logger.info("Set environment variable: %s = %s", name, value)
    else:
        logger.error("Unsupported OS: %s", system)


def add_executable_path(exe_path: str) -> None:
    """
    Adds the specified directory to the user's PATH environment variable persistently.
    """
    system = platform.system()
    if system == "Windows":
        try:
            import winreg, ctypes
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_READ) as key:
                try:
                    current_path, _ = winreg.QueryValueEx(key, "Path")
                except FileNotFoundError:
                    current_path = ""
            path_entries = current_path.split(";") if current_path else []
            normalized_entries = [entry.strip().lower() for entry in path_entries if entry.strip()]
            target_norm = exe_path.strip().lower()
            if target_norm in normalized_entries:
                logger.info("%s is already in PATH.", exe_path)
            else:
                path_entries.append(exe_path)
                new_path = ";".join(path_entries)
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_SET_VALUE) as key:
                    winreg.SetValueEx(key, "Path", 0, winreg.REG_EXPAND_SZ, new_path)
                HWND_BROADCAST = 0xFFFF
                WM_SETTINGCHANGE = 0x001A
                SMTO_ABORTIFHUNG = 0x0002
                ctypes.windll.user32.SendMessageTimeoutW(
                    HWND_BROADCAST, WM_SETTINGCHANGE, 0, "Environment", SMTO_ABORTIFHUNG, 5000, None
                )
                logger.info("Added %s to PATH", exe_path)
        except Exception as e:
            logger.error("Error updating PATH on Windows: %s", e)
    elif system in ["Linux", "Darwin"]:
        rc_files = [os.path.expanduser("~/.bashrc"), os.path.expanduser("~/.zshrc")]
        export_line = f'export PATH="${{PATH}}:{exe_path}"\n'
        for rc in rc_files:
            try:
                if os.path.exists(rc):
                    with open(rc, "r") as file:
                        content = file.read()
                    if export_line.strip() not in content:
                        with open(rc, "a") as file:
                            file.write(export_line)
            except Exception as e:
                logger.error("Error updating %s: %s", rc, e)
        os.environ["PATH"] = os.environ.get("PATH", "") + f":{exe_path}"
        logger.info("Added %s to PATH", exe_path)
    else:
        logger.error("Unsupported OS: %s", system)


@app.command()
def install(
    install_dir: Path = typer.Argument(None, help="Installation directory for DevT"),
    log_level: str = typer.Option("WARNING", "--log-level", help="Set logging level (default: WARNING)"),
    version: str = typer.Option("latest", "--version", help="DevT version to install (default: latest)"),
    no_restart: bool = typer.Option(False, "--no-restart", help="Do not automatically restart DevT after installation"),
    wait_time: int = typer.Option(3, "--wait", help="Seconds to wait before replacing the executable (default: 3)")
):
    """
    Install DevT to the specified directory.
    
    If no directory is provided, the installer defaults to:
      - Windows: %USERPROFILE%\devt
      - Linux/macOS: ~/devt

    The installer downloads the main executable from GitHub, replaces any existing copy,
    updates the user PATH, and optionally restarts the application.
    """
    # Setup logging.
    numeric_level = getattr(logging, log_level.upper(), None)
    logging.basicConfig(level=numeric_level, format="%(asctime)s - %(levelname)s - %(message)s")
    
    # Use default installation directory if not provided.
    if install_dir is None:
        if platform.system() == "Windows":
            install_dir = Path(os.environ["USERPROFILE"]) / "devt"
        else:
            install_dir = Path.home() / "devt"
    
    # Determine paths for the executable.
    system = platform.system()
    if system == "Windows":
        current_executable = install_dir / "devt.exe"
        new_executable = install_dir / "devt_new.exe"
    else:
        current_executable = install_dir / "devt"
        new_executable = install_dir / "devt_new"
    
    # Build download URL.
    download_url = get_download_url(version)
    logger.info("Download URL: %s", download_url)
    
    # Create the installation directory.
    install_dir.mkdir(parents=True, exist_ok=True)
    typer.echo(f"Installing DevT to {install_dir}...")
    
    # Download the executable.
    if not download_executable(download_url, new_executable):
        logger.error("Download failed. Exiting.")
        sys.exit(1)
    
    # Replace the old executable.
    replace_executable(new_executable, current_executable, wait_time=wait_time)
    
    # Add the installation directory to the user's PATH.
    add_executable_path(str(install_dir))
    
    # Optionally restart the application.
    if not no_restart:
        restart_application(current_executable)
    else:
        logger.info("Skipping application restart as per --no-restart flag.")
    
    typer.echo("Installation complete. You may need to restart your terminal for PATH changes to take effect.")


if __name__ == "__main__":
    try:
        app()
    except Exception as exc:
        logger.error("Installation encountered an error: %s", exc)
        sys.exit(1)
