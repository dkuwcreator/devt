import ssl
import typer
import logging
import sys
import subprocess
import shutil
import time
from pathlib import Path
import urllib3
import truststore

app = typer.Typer()

# Constants
LATEST_DOWNLOAD_URL = "https://github.com/dkuwcreator/devt/releases/latest/download/devt.exe"
TIMEOUT_CONNECT = 10.0
TIMEOUT_READ = 30.0

# SSL and HTTP Manager Setup
ctx = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
http = urllib3.PoolManager(ssl_context=ctx)


def download_executable(url: str, destination: Path) -> bool:
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
    logging.info("Restarting DevT with 'self version' arguments...")
    try:
        subprocess.Popen([str(executable), "self", "version"])
    except Exception as err:
        logging.error("Failed to restart DevT: %s", err)


@app.command()
def install(
    install_dir: Path = typer.Argument(..., help="Installation directory for DevT"),
    log_level: str = typer.Option("WARNING", "--log-level", help="Set the logging level (default: WARNING)"),
    version: str = typer.Option("latest", "--version", help="DevT version to install (default: latest)")
):
    numeric_level = getattr(logging, log_level.upper(), None)
    logging.basicConfig(level=numeric_level, format="%(asctime)s - %(levelname)s - %(message)s")

    if version == "latest":
        download_url = LATEST_DOWNLOAD_URL
    else:
        download_url = f"https://github.com/dkuwcreator/devt/releases/download/{version}/devt.exe"

    new_executable = install_dir / "devt_new.exe"
    current_executable = install_dir / "devt.exe"

    if not download_executable(download_url, new_executable):
        logging.error("Download failed. Exiting.")
        sys.exit(1)

    replace_executable(new_executable, current_executable)
    restart_application(current_executable)
    sys.exit(0)


if __name__ == "__main__":
    app()
