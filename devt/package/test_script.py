import pytest
import subprocess
import os
from pathlib import Path
from unittest.mock import patch, MagicMock
from .script import Script, CommandExecutionError  # Update with actual module name

@pytest.fixture
def sample_script():
    return Script(args=["echo", "Hello, World!"], cwd=Path("/tmp"))

@patch("os.environ", {"EXISTING_VAR": "1"})
def test_resolve_env(sample_script):
    sample_script.env = {"NEW_VAR": "2"}
    resolved_env = sample_script.resolve_env()
    assert resolved_env["EXISTING_VAR"] == "1"
    assert resolved_env["NEW_VAR"] == "2"

@patch("pathlib.Path.exists", return_value=True)
def test_resolve_cwd(mock_exists, sample_script):
    base_dir = Path("/home/user/project")
    resolved_cwd = sample_script.resolve_cwd(base_dir)
    assert resolved_cwd == Path("/tmp")

@patch("pathlib.Path.exists", return_value=False)
def test_resolve_cwd_missing_dir(mock_exists, sample_script):
    base_dir = Path("/home/user/project")
    with pytest.raises(FileNotFoundError):
        sample_script.resolve_cwd(base_dir)

@patch("subprocess.run")
def test_execute_success(mock_run, sample_script):
    mock_run.return_value = subprocess.CompletedProcess(args=["echo", "Hello, World!"], returncode=0)
    base_dir = Path("/home/user/project")
    result = sample_script.execute(base_dir)
    assert result.returncode == 0

@patch("subprocess.run")
def test_execute_failure(mock_run, sample_script):
    mock_run.return_value = subprocess.CompletedProcess(args=["false"], returncode=1)
    base_dir = Path("/home/user/project")
    with pytest.raises(CommandExecutionError):
        sample_script.execute(base_dir)

@patch("subprocess.run")
def test_execute_fallback(mock_run, sample_script):
    mock_run.side_effect = [
        subprocess.CompletedProcess(args=["false"], returncode=1),
        subprocess.CompletedProcess(args=["echo", "Fallback"], returncode=0),
    ]
    base_dir = Path("/home/user/project")
    result = sample_script.execute(base_dir)
    assert result.returncode == 0
