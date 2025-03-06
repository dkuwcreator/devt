#!/usr/bin/env python3
import ssl
import platform
import typer
import logging
import sys
import subprocess
import shutil
import time
import json
from pathlib import Path
import urllib3
import truststore  # This module helps build a secure SSL context.
import os

app = typer.Typer()
logger = logging.getLogger(__name__)

def get_os_suffix() -> str:
    """Determine OS-specific suffix for downloaded executables."""
    os_name = platform.system()
    if os_name == "Windows":
        return "windows.exe"
    elif os_name == "Linux":
        return "linux"
    elif os_name == "Darwin":
        return "macos"
    else:
        return os_name.lower()

OS_SUFFIX = get_os_suffix()

# Timeouts for HTTP requests
TIMEOUT_CONNECT = 10.0
TIMEOUT_READ = 30.0

# Setup SSL context and HTTP manager for secure connections
ctx = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
http = urllib3.PoolManager(ssl_context=ctx)

def get_latest_version() -> str:
    """Query GitHub API for the latest release tag."""
    api_url = "https://api.github.com/repos/dkuwcreator/devt/releases/latest"
    logger.info("Fetching latest version from GitHub API...")
    try:
        response = http.request(
            "GET", api_url,
            timeout=urllib3.Timeout(connect=TIMEOUT_CONNECT, read=TIMEOUT_READ)
        )
        if response.status != 200:
            raise Exception(f"HTTP Error {response.status}")
        data = json.loads(response.data.decode("utf-8"))
        latest_tag = data.get("tag_name")
        if not latest_tag:
            raise Exception("tag_name not found in API response")
        logger.info("Latest version is %s", latest_tag)
        return latest_tag
    except Exception as err:
        logger.error("Failed to get latest version: %s", err)
        return "latest"

def get_download_url(version: str) -> str:
    """
    Build the download URL using the provided version and OS suffix.
    If version is 'latest', retrieve the actual latest version first.
    """
    if version == "latest":
        version = get_latest_version()
    return f"https://github.com/dkuwcreator/devt/releases/download/{version}/devt-{version}-{OS_SUFFIX}"

def download_executable(url: str, destination: Path) -> bool:
    """Download the executable from the URL to the destination path."""
    logger.info("Downloading DevT from %s...", url)
    try:
        response = http.request(
            "GET", url,
            timeout=urllib3.Timeout(connect=TIMEOUT_CONNECT, read=TIMEOUT_READ)
        )
        if response.status != 200:
            raise Exception(f"HTTP Error {response.status}")
    except Exception as err:
        logger.error("Download failed: %s", err)
        return False

    try:
        destination.write_bytes(response.data)
        logger.info("Downloaded DevT to %s", destination)
        return True
    except IOError as err:
        logger.error("Failed to save executable: %s", err)
        return False

def replace_executable(new_exe: Path, current_exe: Path) -> None:
    """Backup any existing executable and replace it with the new download."""
    backup = current_exe.with_suffix(".old")
    logger.info("Waiting for DevT to close...")
    time.sleep(3)  # Pause to let any running instance close.
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
    """Restart the installed application (for example, to verify the new version)."""
    logger.info("Restarting DevT...")
    try:
        subprocess.Popen([str(executable), "self", "version"])
    except Exception as err:
        logger.error("Failed to restart DevT: %s", err)

def set_env_var(name: str, value: str) -> None:
    """
    Persist a user environment variable across sessions.
    
    On Windows: writes to the registry and broadcasts the change.
    On Linux/macOS: appends export commands to ~/.bashrc and ~/.zshrc and updates the current session.
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
            print(f"Set environment variable: {name} = {value}")
        except Exception as e:
            print(f"Error setting {name} on Windows: {e}")
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
                print(f"Error updating {rc}: {e}")
        os.environ[name] = value
        print(f"Set environment variable: {name} = {value}")
    else:
        print(f"Unsupported OS: {system}")

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
                print(f"{exe_path} is already in PATH.")
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
                print(f"Added {exe_path} to PATH")
        except Exception as e:
            print(f"Error updating PATH on Windows: {e}")
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
                print(f"Error updating {rc}: {e}")
        os.environ["PATH"] = os.environ.get("PATH", "") + f":{exe_path}"
        print(f"Added {exe_path} to PATH")
    else:
        print(f"Unsupported OS: {system}")

@app.command()
def install(
    install_dir: Path = typer.Argument(None, help="Installation directory for DevT"),
    log_level: str = typer.Option("WARNING", "--log-level", help="Set logging level (default: WARNING)"),
    version: str = typer.Option("latest", "--version", help="DevT version to install (default: latest)")
):
    """
    Install DevT to the specified directory.
    
    If no directory is provided, the installer defaults to:
      - Windows: %USERPROFILE%\devt
      - Linux/macOS: ~/devt
    The installer downloads the executable from GitHub, replaces any existing copy,
    updates the user PATH, and restarts the application.
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
    os_name = platform.system()
    if os_name == "Windows":
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
    replace_executable(new_executable, current_executable)
    
    # Add the installation directory to the user's PATH.
    add_executable_path(str(install_dir))
    
    # Restart the application.
    restart_application(current_executable)
    typer.echo("Installation complete. You may need to restart your terminal for PATH changes to take effect.")

if __name__ == "__main__":
    app()
