import os
import shutil
import subprocess
import tempfile
import json
from pathlib import Path
from datetime import datetime
import logging
import pytest

# Configure logging for tests
logging.basicConfig(level=logging.DEBUG)

# Adjust these imports based on your project structure.
from .registry_manager import Registry
from .package_manager import PackageManager, PackageBuilder, Script, ToolPackage, now

# --- Pytest Fixtures ---

@pytest.fixture
def temp_registry_dir():
    """Create a temporary directory for the registry."""
    with tempfile.TemporaryDirectory() as tmp:
        yield Path(tmp)

@pytest.fixture
def registry(temp_registry_dir):
    """Create a Registry instance using a temporary directory."""
    reg = Registry(temp_registry_dir)
    yield reg
    # Dispose of the engine to close all open connections and release file locks.
    reg.engine.dispose()

@pytest.fixture
def temp_package_dir(temp_registry_dir):
    """
    Create a temporary package directory (inside a parent folder) with the sample manifest.
    """
    pkg_parent = temp_registry_dir / "packages"
    pkg_parent.mkdir(parents=True, exist_ok=True)
    return create_sample_package(pkg_parent)

# --- Sample Manifest Data ---

SAMPLE_MANIFEST_YAML = """
name: Sample Tool
description: A tool to run sample checks.
command: sample_tool
scripts:
  run_checks: "echo Running checks..."
  install: "echo Installing..."
"""

UPDATED_MANIFEST_YAML = """
name: Sample Tool Updated
description: Updated tool for sample checks.
command: sample_tool
scripts:
  run_checks: "echo Updated running checks..."
  install: "echo Updated installing..."
"""

# --- Utility Function for Tests ---

def create_sample_package(directory: Path, manifest_content: str = SAMPLE_MANIFEST_YAML) -> Path:
    """
    Create a sample package directory with a manifest.yaml file.
    Returns the path to the package directory.
    """
    package_dir = directory / "sample_package"
    package_dir.mkdir(parents=True, exist_ok=True)
    manifest_file = package_dir / "manifest.yaml"
    manifest_file.write_text(manifest_content, encoding="utf-8")
    return package_dir

# --- Tests ---

def test_load_and_validate_manifest(temp_package_dir):
    """
    Test that PackageBuilder correctly loads and validates the manifest.
    """
    pb = PackageBuilder(temp_package_dir)
    pkg = pb.build_package()
    assert pkg.name == "Sample Tool", "Manifest name should be 'Sample Tool'"
    assert pkg.command == "sample_tool", "Manifest command should be 'sample_tool'"
    assert "run_checks" in pkg.scripts, "'run_checks' script should be defined"
    script = pkg.scripts["run_checks"]
    assert isinstance(script, Script), "'run_checks' should be a Script instance"
    logging.info("Manifest loaded and validated successfully.")

def test_import_and_list_package(registry, temp_package_dir):
    """
    Test importing a package into the registry and then listing it.
    """
    pm = PackageManager(registry)
    manifest_path = temp_package_dir / "manifest.yaml"
    pm.import_package(manifest_path)

    packages = pm.list_packages()
    assert "sample_tool" in packages, "The package 'sample_tool' should be in the registry"
    logging.info("Package 'sample_tool' found in registry: %s", packages)

def test_run_script(registry, temp_package_dir):
    """
    Test running the run_checks script.
    """
    pm = PackageManager(registry)
    manifest_path = temp_package_dir / "manifest.yaml"
    pm.import_package(manifest_path)
    
    # The package is copied into the registry's tools folder.
    base_dir = registry.db_path / "tools" / temp_package_dir.name
    
    # Retrieve the script from the registry.
    script = registry.get_script("sample_tool", "run_checks")
    assert script is not None, "Script 'run_checks' must exist."
    
    # Prepare the subprocess arguments.
    args = script.prepare_subprocess_args(base_dir)
    logging.info("Running command: %s", args["args"])
    
    # Run the command and capture output.
    result = subprocess.run(args, capture_output=True, text=True)
    logging.info("Subprocess output: %s", result.stdout)
    assert "Running checks" in result.stdout, "Output should contain 'Running checks'"

def test_update_package(registry, temp_package_dir):
    """
    Test updating an existing package.
    """
    pm = PackageManager(registry)
    manifest_path = temp_package_dir / "manifest.yaml"
    # First import package with the initial manifest.
    pm.import_package(manifest_path)
    packages = pm.list_packages()
    assert "sample_tool" in packages, "The package should be imported first"

    # Now update: write an updated manifest to the same package folder.
    manifest_path.write_text(UPDATED_MANIFEST_YAML, encoding="utf-8")
    pm.update_package(manifest_path)

    # Retrieve updated package data.
    pkg = registry.get_package("sample_tool")
    assert pkg is not None, "Updated package should exist"
    assert pkg["name"] == "Sample Tool Updated", "Package name should be updated"
    logging.info("Package updated: %s", pkg)

def test_remove_package(registry, temp_package_dir):
    """
    Test removing a package from the registry.
    """
    pm = PackageManager(registry)
    manifest_path = temp_package_dir / "manifest.yaml"
    pm.import_package(manifest_path)
    packages = pm.list_packages()
    assert "sample_tool" in packages, "Package should be present before removal"

    pm.remove_package("sample_tool")
    packages = pm.list_packages()
    assert "sample_tool" not in packages, "Package should be removed from registry"
    logging.info("Package 'sample_tool' successfully removed.")
