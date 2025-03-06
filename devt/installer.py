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
import truststore

app = typer.Typer()
logger = logging.getLogger(__name__)

def get_os_suffix() -> str:
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

# SSL and HTTP Manager Setup
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
        # Fallback: return a constant latest URL would be an option here.
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
    logger.info("Downloading DevT update from %s...", url)
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
        logger.error("Failed to save update: %s", err)
        return False

def replace_executable(new_exe: Path, current_exe: Path) -> None:
    backup = current_exe.with_suffix(".old")
    logging.info("Waiting for DevT to close...")
    time.sleep(3)
    try:
        if current_exe.exists():
            shutil.move(str(current_exe), str(backup))
            logging.info("Backed up old executable to %s", backup)
        shutil.move(str(new_exe), str(current_exe))
        logging.info("Replaced %s successfully.", current_exe)
    except Exception as err:
        logging.error("Error replacing executable: %s", err)
        sys.exit(1)

def restart_application(executable: Path) -> None:
    logger.info("Restarting DevT with 'self version' arguments...")
    try:
        subprocess.Popen([str(executable), "self", "version"])
    except Exception as err:
        logger.error("Failed to restart DevT: %s", err)

def set_user_environment_var(name: str, value: str) -> None:
    """
    Persists a user environment variable across sessions in a cross-platform way.
    """
    system = platform.system()

    try:
        if system == "Windows":
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_SET_VALUE
            ) as key:
                winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
            logger.debug("Set user environment variable on Windows: %s=%s", name, value)

        elif system in ["Linux", "Darwin"]:  # Darwin is macOS
            bashrc_path = os.path.expanduser("~/.bashrc")
            zshrc_path = os.path.expanduser("~/.zshrc")
            export_command = f'export {name}="{value}"\n'

            # Export variable in the shell profile, but only if not already present
            for rc_path in [bashrc_path, zshrc_path]:
                if os.path.exists(rc_path):
                    with open(rc_path, "r") as f:
                        content = f.read()
                    if export_command.strip() not in content:
                        with open(rc_path, "a") as f:
                            f.write(export_command)

            # Also set it for the current session
            os.environ[name] = value

            logger.debug(
                "Set user environment variable on Linux/macOS: %s=%s", name, value
            )
        else:
            logger.warning(
                "Unsupported OS: %s. Cannot persist environment variable.", system
            )

    except Exception as e:
        logger.error("Failed to set user environment variable %s: %s", name, e)

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

@app.command()
def install(
    install_dir: Path = typer.Argument(..., help="Installation directory for DevT"),
    log_level: str = typer.Option("WARNING", "--log-level", help="Set the logging level (default: WARNING)"),
    version: str = typer.Option("latest", "--version", help="DevT version to install (default: latest)")
):
    numeric_level = getattr(logging, log_level.upper(), None)
    logging.basicConfig(level=numeric_level, format="%(asctime)s - %(levelname)s - %(message)s")

    download_url = get_download_url(version)
    logging.info("Download URL: %s", download_url)

    # Determine current executable names based on OS.
    os_name = platform.system()
    if os_name == "Windows":
        current_executable = install_dir / "devt.exe"
        new_executable = install_dir / "devt_new.exe"
    else:
        current_executable = install_dir / "devt"
        new_executable = install_dir / "devt_new"

    if not download_executable(download_url, new_executable):
        logging.error("Download failed. Exiting.")
        sys.exit(1)

    replace_executable(new_executable, current_executable)
    restart_application(current_executable)
    sys.exit(0)

if __name__ == "__main__":
    app()
