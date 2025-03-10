#!/usr/bin/env python
import subprocess
import platform
import logging
from pathlib import Path
import configparser

import typer
import os

# -------------------------------------------------------------------------------
# Configuration & Logging
# -------------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
settings = configparser.ConfigParser()
settings.read('settings.ini')

SESSION_CWD = Path(__file__).parent

# Directories and filenames
VENV_DIR = SESSION_CWD / settings.get("project", "venv_dir", fallback=".venv")
DIST_DIR = SESSION_CWD / settings.get("project", "dist_dir", fallback="dist")
ENTRY_SCRIPT = settings.get("project", "entry_script", fallback="devt/cli/main.py")
OUTPUT_NAME = settings.get("project", "output_name", fallback="devt")
UPDATER_SCRIPT = settings.get("project", "updater_script", fallback="devt/installer.py")
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

def inject_version() -> None:
    version = os.environ.get("APP_VERSION", "dev")
    if version == "dev":
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
