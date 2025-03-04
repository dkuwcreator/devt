import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
from datetime import datetime
from .builder import PackageBuilder, ToolPackage
from devt.utils import merge_configs, find_file_type
from devt.config_manager import SUBPROCESS_ALLOWED_KEYS
from .script import Script

@pytest.fixture
def sample_manifest():
    return {
        "name": "sample-package",
        "description": "A sample package",
        "command": "run-sample",
        "cwd": "./",
        "dependencies": {"dep1": "1.0.0"},
        "scripts": {
            "build": {"args": "echo Building"},
            "test": {"args": "pytest tests/"},
        },
    }

@pytest.fixture
def mock_package_path():
    return Path("/fake/path")

@pytest.fixture
def mock_manifest_path():
    return Path("/fake/path/manifest.json")

@pytest.fixture
def mock_script():
    return MagicMock(spec=Script)

@patch("devt.cli.package_builder.find_file_type")
@patch("devt.cli.package_builder.load_and_validate_manifest")
def test_package_builder_initialization(
    mock_load_manifest, mock_find_file_type, mock_package_path, sample_manifest
):
    mock_find_file_type.return_value = mock_package_path / "manifest.json"
    mock_load_manifest.return_value = sample_manifest
    
    builder = PackageBuilder(mock_package_path)
    
    assert builder.package_path == mock_package_path.resolve()
    assert builder.manifest == sample_manifest
    assert builder.group == "default"
    assert isinstance(builder.scripts, dict)
    assert "build" in builder.scripts
    assert "test" in builder.scripts
    mock_find_file_type.assert_called_once()
    mock_load_manifest.assert_called_once()

@patch("devt.cli.package_builder.find_file_type")
@patch("devt.cli.package_builder.load_and_validate_manifest")
def test_find_manifest_failure(mock_load_manifest, mock_find_file_type, mock_package_path):
    mock_find_file_type.return_value = None
    with pytest.raises(FileNotFoundError):
        PackageBuilder(mock_package_path)

@patch("devt.cli.package_builder.find_file_type")
@patch("devt.cli.package_builder.load_and_validate_manifest")
def test_build_package(mock_load_manifest, mock_find_file_type, mock_package_path, sample_manifest, mock_script):
    mock_find_file_type.return_value = mock_package_path / "manifest.json"
    mock_load_manifest.return_value = sample_manifest
    
    with patch("devt.cli.package_builder.Script", return_value=mock_script):
        builder = PackageBuilder(mock_package_path)
        package = builder.build_package()
    
    assert isinstance(package, ToolPackage)
    assert package.name == "sample-package"
    assert package.description == "A sample package"
    assert package.command == "run-sample"
    assert package.location == mock_package_path
    assert package.dependencies == {"dep1": "1.0.0"}
    assert "build" in package.scripts
    assert "test" in package.scripts

    assert isinstance(package.scripts["build"], Script)
    assert isinstance(package.scripts["test"], Script)
    
    assert isinstance(package.install_date, str)
    assert isinstance(package.last_update, str)
    assert datetime.fromisoformat(package.install_date)
    assert datetime.fromisoformat(package.last_update)

@patch("devt.cli.package_builder.merge_configs")
def test_merge_configs(mock_merge_configs, sample_manifest):
    mock_merge_configs.return_value = {"key": "value"}
    result = merge_configs(sample_manifest, {"other_key": "other_value"})
    assert result == {"key": "value"}
    mock_merge_configs.assert_called_once()
