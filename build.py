#!/usr/bin/env python
import subprocess
import platform
import shutil
import logging
from pathlib import Path

import typer
from dotenv import dotenv_values

# ------------------------------------------------------------------------------
# Configuration & Logging
# ------------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
config = dotenv_values("project.env")
SESSION_CWD = Path(__file__).parent

# Directories and filenames
VENV_DIR = SESSION_CWD / config.get("VENV_DIR", ".venv")
DIST_DIR = SESSION_CWD / config.get("DIST_DIR", "dist")
ENTRY_SCRIPT = config.get("ENTRY_SCRIPT", "my_project/cli.py")
OUTPUT_NAME = config.get("OUTPUT_NAME", "devt")
UPDATER_SCRIPT = config.get("UPDATER_SCRIPT", "my_project/installer.py")
INIT_FILE = SESSION_CWD / OUTPUT_NAME / "__init__.py"
VERSION_FILE = SESSION_CWD / ".version"
PYTHON_EXECUTABLE = VENV_DIR / ("Scripts/python.exe" if platform.system() == "Windows" else "bin/python")

app = typer.Typer()

# ------------------------------------------------------------------------------
# Helper Functions
# ------------------------------------------------------------------------------
def run_command(cmd: list) -> None:
    logging.info("Running: " + " ".join(cmd))
    subprocess.run(cmd, check=True)

def get_output_name(exe_type: str = "") -> str:
    """
    Returns the correct output executable name based on the executable type and OS.
    exe_type: "" for main executable or "installer"
    Raises ValueError for unsupported executable types.
    """
    if exe_type not in {"", "installer"}:
        raise ValueError("Invalid executable type specified.")

    system = platform.system()
    ext = ".exe" if system == "Windows" else ""
    platform_key = {
        "Windows": "windows",
        "Linux": "linux",
        "Darwin": "macos"
    }.get(system, system.lower())

    suffix = "-installer" if exe_type == "installer" else ""
    return f"{OUTPUT_NAME}-{platform_key}{suffix}{ext}"

def ensure_venv() -> None:
    if not VENV_DIR.exists():
        logging.info("Creating virtual environment...")
        run_command(["python", "-m", "venv", str(VENV_DIR)])
    if not PYTHON_EXECUTABLE.exists():
        logging.error(f"Python executable missing: {PYTHON_EXECUTABLE}")
        raise FileNotFoundError(f"Python executable missing: {PYTHON_EXECUTABLE}")
    logging.info("Installing dependencies...")
    run_command([str(PYTHON_EXECUTABLE), "-m", "pip", "install", "--upgrade", "pip"])
    run_command([str(PYTHON_EXECUTABLE), "-m", "pip", "install", "-r", "requirements.txt"])

def get_version() -> str:
    if VERSION_FILE.exists():
        version = VERSION_FILE.read_text().strip()
        logging.info(f"Version: {version}")
        return version
    logging.warning("No .version file found.")
    return "Unknown"

def inject_version() -> None:
    version = get_version()
    if version == "Unknown":
        logging.warning("Skipping version injection.")
        return
    if not INIT_FILE.exists():
        logging.error(f"Missing __init__.py: {INIT_FILE}")
        return
    content = INIT_FILE.read_text(encoding="utf-8")
    new_content = content.replace('__version__ = "dev"', f'__version__ = "{version}"')
    if content != new_content:
        INIT_FILE.write_text(new_content, encoding="utf-8")
        logging.info(f"Injected version {version} into {INIT_FILE}")
    else:
        logging.info("Version already set.")

def build_executable(script: str, exe_type: str = "") -> None:
    output_name = get_output_name(exe_type)
    logging.info(f"Building {output_name} for {platform.system()}...")

    if not Path(script).exists():
        logging.error(f"Missing script: {script}")
        raise FileNotFoundError(f"Installer missing: {script}")
    
    cmd = [str(PYTHON_EXECUTABLE), "-m", "PyInstaller", "--onefile", "--name", output_name, script]
    run_command(cmd)
    logging.info(f"Build completed for {output_name} in {DIST_DIR}")

# ------------------------------------------------------------------------------
# CLI Command
# ------------------------------------------------------------------------------
@app.command()
def build(
    ci: bool = typer.Option(False, "--ci", help="CI mode, skip venv setup"),
    skip_installer: bool = typer.Option(False, "--skip-installer", help="Skip installer build"),
):
    if not ci:
        ensure_venv()
    inject_version()
    build_executable(ENTRY_SCRIPT)
    if not skip_installer:
        build_executable(UPDATER_SCRIPT, "installer")
    if DIST_DIR.exists():
        logging.info("Built files:")
        for file in DIST_DIR.iterdir():
            logging.info(file.name)

if __name__ == "__main__":
    app()
