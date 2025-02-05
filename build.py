import subprocess
import platform
import shutil
import typer
from pathlib import Path
from dotenv import dotenv_values

# Load environment variables
config = dotenv_values("project.env")

# Directories and files
SESSION_CWD = Path(__file__).parent
VENV_DIR = SESSION_CWD / ".venv"

# Constants from project.env
ENTRY_SCRIPT = config.get("ENTRY_SCRIPT", "my_project/cli.py")
OUTPUT_NAME = config.get("OUTPUT_NAME", "my_tool")
DIST_DIR = SESSION_CWD / config.get("DIST_DIR", "dist")

# Where your package's __init__.py lives
INIT_FILE = SESSION_CWD / OUTPUT_NAME / "__init__.py"

VERSION_FILE = SESSION_CWD / ".version"

# Platform-specific Python path in the venv
PYTHON_EXECUTABLE = (
    VENV_DIR / "Scripts" / "python"
    if platform.system() == "Windows"
    else VENV_DIR / "bin" / "python"
)

app = typer.Typer()

def get_version():
    """Retrieve the version from the .version file."""
    if VERSION_FILE.exists():
        return VERSION_FILE.read_text().strip().lstrip("v")
    return "Unknown"

def inject_version():
    """
    Inject version number into my_project/__init__.py
    where __version__ = "dev" is defined.
    """
    version = get_version()
    if version == "Unknown":
        print("No version found in .version file; skipping injection.")
        return
    
    if not INIT_FILE.exists():
        print(f"Cannot inject version: {INIT_FILE} does not exist.")
        return

    original_code = INIT_FILE.read_text(encoding="utf-8")
    updated_code = original_code.replace(
        '__version__ = "dev"',
        f'__version__ = "{version}"'
    )
    INIT_FILE.write_text(updated_code, encoding="utf-8")
    print(f"Injected version {version} into {INIT_FILE}.")

def clean():
    """Remove previous build artifacts."""
    build_dir = SESSION_CWD / "build"
    spec_file = SESSION_CWD / f"{OUTPUT_NAME}.spec"

    for path in [build_dir, DIST_DIR, spec_file]:
        if path.exists():
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
    print("Cleaned previous build artifacts.")

def setup_venv():
    """Ensure a virtual environment exists and install dependencies."""
    if not VENV_DIR.exists():
        print("Creating virtual environment...")
        subprocess.run(["python", "-m", "venv", str(VENV_DIR)], check=True)

    print("Installing dependencies...")
    subprocess.run(
        [str(PYTHON_EXECUTABLE), "-m", "pip", "install", "-r", "requirements.txt"],
        check=True,
    )

@app.command()
def build(
    clean_before: bool = typer.Option(False, "--clean", help="Clean build artifacts before building"),
    ci: bool = typer.Option(False, "--ci", help="Run in CI mode (skip virtual environment setup)"),
):
    """Build the project into a standalone executable."""
    if clean_before:
        clean()

    if not ci:
        setup_venv()

    # Determine Python executable (local venv or system python)
    python_exec = "python" if ci else str(PYTHON_EXECUTABLE)

    # Inject the version into __init__.py
    inject_version()

    print(f"Building {OUTPUT_NAME} for {platform.system()}...")

    cmd = [
        python_exec,
        "-m",
        "PyInstaller",
        "--onefile",
        "--name",
        OUTPUT_NAME,
        ENTRY_SCRIPT,
    ]

    try:
        subprocess.run(cmd, check=True)
        print(f"Build completed. Executable is in the '{DIST_DIR}' folder.")
    except subprocess.CalledProcessError as e:
        print("Error: Build process failed.")
        raise e

if __name__ == "__main__":
    app()
