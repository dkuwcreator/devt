import subprocess
import platform
import shutil
import logging
import typer
from pathlib import Path
from dotenv import dotenv_values

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

# Load environment variables from project.env
config = dotenv_values("project.env")

# Directories and files
SESSION_CWD = Path(__file__).parent
VENV_DIR = SESSION_CWD / config.get("VENV_DIR", ".venv")

# Constants from project.env
# Updated default OUTPUT_NAME to "devt" to match the release filenames.
ENTRY_SCRIPT = config.get("ENTRY_SCRIPT", "my_project/cli.py")
OUTPUT_NAME = config.get("OUTPUT_NAME", "devt")
UPDATER_SCRIPT = config.get("UPDATER_SCRIPT", "my_project/updater.py")
DIST_DIR = SESSION_CWD / config.get("DIST_DIR", "dist")

# Where your package's __init__.py lives
INIT_FILE = SESSION_CWD / OUTPUT_NAME / "__init__.py"
VERSION_FILE = SESSION_CWD / ".version"

# Platform-specific Python executable in the venv
PYTHON_EXECUTABLE = (
    VENV_DIR / "Scripts" / "python.exe"
    if platform.system() == "Windows"
    else VENV_DIR / "bin" / "python"
)

app = typer.Typer()


def ensure_venv() -> None:
    """Ensure a virtual environment exists and install dependencies if missing."""
    if not VENV_DIR.exists():
        logging.info("Creating virtual environment...")
        subprocess.run(["python", "-m", "venv", str(VENV_DIR)], check=True)

    if not PYTHON_EXECUTABLE.exists():
        logging.error(
            f"Python executable not found at {PYTHON_EXECUTABLE}. The virtual environment may be corrupted."
        )
        raise FileNotFoundError(f"Python executable missing: {PYTHON_EXECUTABLE}")

    logging.info("Installing dependencies in the virtual environment...")
    subprocess.run(
        [str(PYTHON_EXECUTABLE), "-m", "pip", "install", "--upgrade", "pip"], check=True
    )
    subprocess.run(
        [str(PYTHON_EXECUTABLE), "-m", "pip", "install", "-r", "requirements.txt"],
        check=True,
    )


def ensure_pyinstaller() -> None:
    """Ensure PyInstaller is installed before running the build."""
    try:
        subprocess.run(
            [str(PYTHON_EXECUTABLE), "-m", "PyInstaller", "--version"],
            check=True,
            capture_output=True,
        )
        logging.info("PyInstaller is installed.")
    except subprocess.CalledProcessError:
        logging.info("PyInstaller not found. Installing...")
        subprocess.run(
            [str(PYTHON_EXECUTABLE), "-m", "pip", "install", "pyinstaller"], check=True
        )


def get_version() -> str:
    """Retrieve the version from the .version file."""
    if VERSION_FILE.exists():
        version = VERSION_FILE.read_text().strip().lstrip("v")
        logging.info(f"Project version: {version}")
        return version
    logging.warning("No version found in .version file.")
    return "Unknown"


def inject_version() -> None:
    """Inject the version number into __init__.py if applicable."""
    version = get_version()
    if version == "Unknown":
        logging.warning("Skipping version injection due to missing .version file.")
        return

    if not INIT_FILE.exists():
        logging.error(f"Cannot inject version: {INIT_FILE} does not exist.")
        return

    original_code = INIT_FILE.read_text(encoding="utf-8")
    updated_code = original_code.replace(
        '__version__ = "dev"', f'__version__ = "{version}"'
    )

    if original_code != updated_code:
        INIT_FILE.write_text(updated_code, encoding="utf-8")
        logging.info(f"Injected version {version} into {INIT_FILE}.")
    else:
        logging.info("Version is already correctly set. No changes made.")


def clean() -> None:
    """Remove previous build artifacts."""
    build_dir = SESSION_CWD / "build"
    spec_files = [
        SESSION_CWD / f"{OUTPUT_NAME}.spec",
        SESSION_CWD / f"{OUTPUT_NAME}_updater.spec",
    ]

    for path in [build_dir, DIST_DIR, *spec_files]:
        if path.exists():
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
            logging.info(f"Removed {path}")

    logging.info("Cleaned previous build artifacts.")


@app.command()
def build(
    clean_before: bool = typer.Option(
        False, "--clean", help="Clean build artifacts before building"
    ),
    ci: bool = typer.Option(
        False, "--ci", help="Run in CI mode (skip virtual environment setup)"
    ),
    include_updater: bool = typer.Option(
        True, "--include-updater", help="Build the updater alongside the main app"
    ),
):
    """Build the project into standalone executables."""
    if clean_before:
        clean()

    if not ci:
        ensure_venv()

    # Ensure PyInstaller is installed
    ensure_pyinstaller()

    # Inject the version into __init__.py
    inject_version()

    logging.info(f"Building {OUTPUT_NAME} for {platform.system()}...")

    # Build the main application
    cmd_main = [
        str(PYTHON_EXECUTABLE),
        "-m",
        "PyInstaller",
        "--onefile",
        "--name",
        OUTPUT_NAME,
        ENTRY_SCRIPT,
    ]

    try:
        subprocess.run(cmd_main, check=True)
        logging.info(f"Main build completed. Executable is in the '{DIST_DIR}' folder.")
    except subprocess.CalledProcessError as e:
        logging.error("Main build process failed.")
        raise e

    # Build the updater if enabled
    if include_updater:
        logging.info("Building updater...")

        if not Path(UPDATER_SCRIPT).exists():
            logging.error(f"Updater script not found: {UPDATER_SCRIPT}")
            raise FileNotFoundError(f"Updater script missing: {UPDATER_SCRIPT}")

        cmd_updater = [
            str(PYTHON_EXECUTABLE),
            "-m",
            "PyInstaller",
            "--onefile",
            "--name",
            f"{OUTPUT_NAME}_updater",
            UPDATER_SCRIPT,
        ]
        try:
            subprocess.run(cmd_updater, check=True)
            logging.info(
                f"Updater build completed. Executable is in the '{DIST_DIR}' folder."
            )
        except subprocess.CalledProcessError as e:
            logging.error("Updater build process failed.")
            raise e

    # Debug: list files in the distribution directory
    if DIST_DIR.exists():
        logging.info("Built files in the dist directory:")
        for file in DIST_DIR.iterdir():
            logging.info(file.name)


if __name__ == "__main__":
    app()
