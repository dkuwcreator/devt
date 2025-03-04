import ssl
import typer
import logging
import sys
import subprocess
import shutil
import time
import os
from pathlib import Path
import urllib3
import truststore
import winreg
import ctypes

app = typer.Typer()
logger = logging.getLogger(__name__)

# Application name from environment variable (default: "devt")
APP_NAME = os.environ.get("APP_NAME", "devt")
# Default installation directory using Typer's get_app_dir helper.
DEFAULT_INSTALL_DIR = Path(typer.get_app_dir(f".{APP_NAME}"))

# Constants for download and timeouts
LATEST_DOWNLOAD_URL = f"https://github.com/dkuwcreator/{APP_NAME}/releases/latest/download/{APP_NAME}.exe"
TIMEOUT_CONNECT = 10.0
TIMEOUT_READ = 30.0

# SSL and HTTP Manager Setup
ctx = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
http = urllib3.PoolManager(ssl_context=ctx)

def download_executable(url: str, destination: Path) -> bool:
    logger.info("Downloading %s update from %s...", APP_NAME, url)
    try:
        response = http.request(
            "GET",
            url,
            timeout=urllib3.Timeout(connect=TIMEOUT_CONNECT, read=TIMEOUT_READ)
        )
        if response.status != 200:
            raise Exception(f"HTTP Error {response.status}")
    except Exception as err:
        logger.error("Download failed: %s", err)
        return False

    try:
        destination.write_bytes(response.data)
        logger.info("Downloaded %s to %s", APP_NAME, destination)
        return True
    except IOError as err:
        logger.error("Failed to save update: %s", err)
        return False

def replace_executable(new_exe: Path, current_exe: Path) -> None:
    backup = current_exe.with_suffix(".old")
    logger.info("Waiting for %s to close...", APP_NAME)
    time.sleep(3)
    try:
        if current_exe.exists():
            shutil.move(str(current_exe), str(backup))
            logger.info("Backed up old executable to %s", backup)
        shutil.move(str(new_exe), str(current_exe))
        logger.info("Replaced %s successfully.", current_exe)
    except Exception as err:
        logger.error("Error replacing executable: %s", err)
        sys.exit(1)

def restart_application(executable: Path) -> None:
    logger.info("Restarting %s with 'self version' arguments...", APP_NAME)
    try:
        subprocess.Popen([str(executable), "self", "version"])
    except Exception as err:
        logger.error("Failed to restart %s: %s", APP_NAME, err)

def update_user_path_registry(target_path: str, remove: bool = False) -> None:
    """
    Updates the user PATH environment variable in the registry.
    If remove is False, adds target_path if not already present.
    If remove is True, removes target_path from PATH.
    """
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_READ) as key:
            try:
                current_path, _ = winreg.QueryValueEx(key, "Path")
            except FileNotFoundError:
                current_path = ""
    except Exception as e:
        logger.error("Failed to open registry key: %s", e)
        return

    path_entries = current_path.split(";") if current_path else []
    normalized_entries = [entry.strip().lower() for entry in path_entries if entry.strip()]
    target_norm = target_path.strip().lower()

    if remove:
        if target_norm in normalized_entries:
            new_entries = [entry for entry in path_entries if entry.strip().lower() != target_norm]
            new_path = ";".join(new_entries)
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_SET_VALUE) as key:
                    winreg.SetValueEx(key, "Path", 0, winreg.REG_EXPAND_SZ, new_path)
                logger.info("Removed %s from PATH", target_path)
            except Exception as e:
                logger.error("Failed to update registry: %s", e)
        else:
            logger.info("%s not found in PATH", target_path)
    else:
        if target_norm not in normalized_entries:
            path_entries.append(target_path)
            new_path = ";".join(path_entries)
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_SET_VALUE) as key:
                    winreg.SetValueEx(key, "Path", 0, winreg.REG_EXPAND_SZ, new_path)
                logger.info("Added %s to PATH", target_path)
            except Exception as e:
                logger.error("Failed to update registry: %s", e)
        else:
            logger.info("%s is already in PATH", target_path)

    # Broadcast the environment change to notify other applications.
    try:
        HWND_BROADCAST = 0xFFFF
        WM_SETTINGCHANGE = 0x001A
        SMTO_ABORTIFHUNG = 0x0002
        ctypes.windll.user32.SendMessageTimeoutW(
            HWND_BROADCAST,
            WM_SETTINGCHANGE,
            0,
            "Environment",
            SMTO_ABORTIFHUNG,
            5000,
            None
        )
    except Exception as e:
        logger.error("Failed to broadcast environment change: %s", e)

def get_install_dir() -> Path:
    """Return the installation directory of the executable or script."""
    install_dir = (
        Path(sys.executable).parent
        if getattr(sys, "frozen", False)
        else Path(__file__).resolve().parent
    )
    logger.info("Installation directory: %s", install_dir)
    return install_dir

def schedule_directory_deletion(target_dir: Path) -> None:
    """
    Schedules deletion of the target directory after the current process exits.
    This function spawns a new command prompt that waits a few seconds before deleting the directory.
    """
    # Create a command that waits 3 seconds and then deletes the directory
    cmd = f'cmd /c "timeout /T 3 >nul && rmdir /S /Q \"{target_dir}\""'
    try:
        subprocess.Popen(cmd, shell=True, creationflags=subprocess.CREATE_NEW_CONSOLE)
        logger.info("Scheduled deletion of %s", target_dir)
    except Exception as e:
        logger.error("Failed to schedule deletion of %s: %s", target_dir, e)

@app.command()
def install(
    install_dir: Path = typer.Argument(DEFAULT_INSTALL_DIR, help="Installation directory for " + APP_NAME),
    log_level: str = typer.Option("WARNING", "--log-level", help="Set the logging level (default: WARNING)"),
    version: str = typer.Option("latest", "--version", help=APP_NAME + " version to install (default: latest)")
):
    numeric_level = getattr(logging, log_level.upper(), None)
    logging.basicConfig(level=numeric_level, format="%(asctime)s - %(levelname)s - %(message)s")

    if version == "latest":
        download_url = LATEST_DOWNLOAD_URL
    else:
        download_url = f"https://github.com/dkuwcreator/{APP_NAME}/releases/download/{version}/{APP_NAME}.exe"

    new_executable = install_dir / f"{APP_NAME}_new.exe"
    current_executable = install_dir / f"{APP_NAME}.exe"

    # Ensure installation directory exists
    if not install_dir.exists():
        install_dir.mkdir(parents=True, exist_ok=True)
        logger.info("Created installation directory: %s", install_dir)

    if not download_executable(download_url, new_executable):
        logger.error("Download failed. Exiting.")
        sys.exit(1)

    replace_executable(new_executable, current_executable)

    # Update the user PATH in the registry with the installation directory
    update_user_path_registry(str(install_dir))

    restart_application(current_executable)
    sys.exit(0)

@app.command()
def uninstall(
    log_level: str = typer.Option("WARNING", "--log-level", help="Set logging level (default: WARNING)")
):
    numeric_level = getattr(logging, log_level.upper(), None)
    logging.basicConfig(level=numeric_level, format="%(asctime)s - %(levelname)s - %(message)s")

    # Get installation directory using the helper function.
    install_dir = get_install_dir()
    logger.info("Using installation directory: %s", install_dir)

    # Remove the installation directory from the user PATH registry
    update_user_path_registry(str(install_dir), remove=True)
    logger.info("Removed %s from PATH", install_dir)

    # Instead of directly deleting the folder (which contains the running installer),
    # schedule its deletion after the current process exits.
    schedule_directory_deletion(install_dir)
    logger.info("Uninstallation complete. The installation directory will be removed shortly.")
    sys.exit(0)

if __name__ == "__main__":
    app()
