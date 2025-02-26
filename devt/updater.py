import subprocess
import sys
import time
import shutil
import os
import logging
from pathlib import Path
import urllib3
import truststore

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Constants
GITHUB_DOWNLOAD_URL = "https://github.com/dkuwcreator/devt/releases/latest/download/devt.exe"
TIMEOUT_CONNECT = 10.0
TIMEOUT_READ = 30.0

ctx = truststore.SSLContext()
http = urllib3.PoolManager(ssl_context=ctx)


def download_new_executable(url: str, destination: Path) -> bool:
    """Download the latest DevT executable."""
    logging.info("Downloading DevT update from %s...", url)
    try:
        response = http.request(
            "GET",
            url,
            timeout=urllib3.Timeout(connect=TIMEOUT_CONNECT, read=TIMEOUT_READ)
        )
        if response.status != 200:
            raise Exception(f"HTTP Error {response.status}")
    except Exception as err:
        logging.error("Download failed: %s", err)
        return False

    try:
        destination.write_bytes(response.data)
        logging.info("Downloaded DevT to %s", destination)
        return True
    except IOError as err:
        logging.error("Failed to save update: %s", err)
        return False


def replace_executable(new_exe: Path, current_exe: Path) -> None:
    """Replace the existing DevT executable with the new one."""
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
    """Restart the updated DevT application with 'self version' arguments."""
    logging.info("Restarting DevT with 'self version' arguments...")
    try:
        subprocess.Popen([str(executable), "self", "version"])
    except Exception as err:
        logging.error("Failed to restart DevT: %s", err)

def main():
    """Main update logic."""
    if len(sys.argv) < 2:
        print("Usage: devt_updater.exe <install_dir>")
        sys.exit(1)

    install_dir = Path(sys.argv[1])
    new_executable = install_dir / "devt_new.exe"
    current_executable = install_dir / "devt.exe"

    if not download_new_executable(GITHUB_DOWNLOAD_URL, new_executable):
        logging.error("Download failed. Exiting.")
        sys.exit(1)

    replace_executable(new_executable, current_executable)
    restart_application(current_executable)
    sys.exit(0)


if __name__ == "__main__":
    main()
