import pytest
from pathlib import Path
import json

# Adjust these imports according to your project structure.
from .registry_manager import Registry
from .package_manager import Script

# --- Pytest Fixtures ---

@pytest.fixture
def temp_registry_dir(tmp_path_factory):
    """Create a temporary directory for the registry."""
    return tmp_path_factory.mktemp("registry")

@pytest.fixture
def registry(temp_registry_dir):
    """Create a Registry instance using the temporary directory."""
    reg = Registry(temp_registry_dir)
    yield reg
    reg.engine.dispose()

# --- Focused Test for Registry Script Operations ---

def test_add_and_get_script(registry):
    """
    Test that a Script can be added to the Registry and then retrieved correctly.

    This test does the following:
      1. Creates a Script instance with test values.
      2. Uses the registry's add_script() method to store it.
      3. Retrieves the script using get_script() and compares the values.
    """
    # Define test values.
    command = "sample_tool"
    script_name = "run_checks"
    test_script = Script(
        args="echo Running checks...",
        shell=None,
        cwd=Path("."),           # current directory for testing
        env={"TEST": "value"},   # example environment variable
        kwargs={"timeout": 30}   # example additional parameter
    )

    # Add the script to the registry.
    registry.add_script(command, script_name, test_script)

    # Retrieve the script from the registry.
    retrieved = registry.get_script(command, script_name)
    assert retrieved is not None, "Retrieved script should not be None."

    # Compare the values.
    # For args: If test_script.args is a string, it should match exactly.
    assert retrieved.args == test_script.args, f"Expected args '{test_script.args}', got '{retrieved.args}'"
    # For shell, cwd, env, and kwargs:
    assert retrieved.shell == test_script.shell, f"Expected shell '{test_script.shell}', got '{retrieved.shell}'"
    assert str(retrieved.cwd) == str(test_script.cwd), f"Expected cwd '{test_script.cwd}', got '{retrieved.cwd}'"
    assert retrieved.env == test_script.env, f"Expected env '{test_script.env}', got '{retrieved.env}'"
    # Since kwargs are stored as JSON, the types should match.
    assert retrieved.kwargs == test_script.kwargs, f"Expected kwargs '{test_script.kwargs}', got '{retrieved.kwargs}'"
