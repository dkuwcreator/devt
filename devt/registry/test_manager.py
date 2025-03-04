import pytest
from pathlib import Path

from devt.registry.manager import RegistryManager


@pytest.fixture
def registry_manager(tmp_path: Path) -> RegistryManager:
    """
    Creates a RegistryManager instance using a temporary directory for the database.
    Ensures that each test starts with a fresh registry.
    """
    rm = RegistryManager(registry_path=tmp_path)
    rm.reset_registry()
    return rm


def test_register_and_retrieve_group(registry_manager: RegistryManager):
    """
    Test registering a single group and retrieving its details.
    """
    group_manifest = {
        "name": "test_group",
        "location": "/registry/test_group",
        "packages": [{
            "name": "testy",
            "description": "This is a test package",
            "dependencies": {
                "winget": {
                    "install": {
                        "args": "echo installing winget",
                        "cwd": ".",
                        "env": {"TEST": "value"},
                        "shell": "python",
                        "kwargs": {"timeout": 10},
                    }
                }
            },
            "scripts": {
                "install": {
                    "args": "echo installing testy",
                    "cwd": ".",
                    "env": {"TEST": "value"},
                    "shell": "pwsh",
                    "kwargs": {"timeout": 10},
                }
            },
        }]
    }
    registry_manager.register_group(group_manifest)
    group = registry_manager.retrieve_group("test_group")
    assert group["name"] == "test_group"
    assert group["location"] == "/registry/test_group"
    assert "testy" in group["packages"]

    package = registry_manager.retrieve_package("testy")
    assert "install" in package["scripts"]
    script = registry_manager.retrieve_script("testy", "install")
    assert script == group_manifest["packages"][0]["scripts"]["install"]


def test_register_and_retrieve_two_groups_different_names_different_package_names(registry_manager: RegistryManager):
    """
    Test registering two groups with different names and distinct package names.
    """
    group_manifest_1 = {
        "name": "test_group_1",
        "location": "/registry/test_group_1",
        "packages": [{
            "name": "testy_1",
            "description": "Test package 1",
            "dependencies": {
                "winget": {
                    "install": {
                        "args": "echo installing winget",
                        "cwd": ".",
                        "env": {"TEST": "value"},
                        "shell": "python",
                        "kwargs": {"timeout": 10},
                    }
                }
            },
            "scripts": {
                "install": {
                    "args": "echo installing testy_1",
                    "cwd": ".",
                    "env": {"TEST": "value"},
                    "shell": "pwsh",
                    "kwargs": {"timeout": 10},
                }
            },
        }]
    }
    group_manifest_2 = {
        "name": "test_group_2",
        "location": "/registry/test_group_2",
        "packages": [{
            "name": "testy_2",
            "description": "Test package 2",
            "dependencies": {
                "winget": {
                    "install": {
                        "args": "echo installing winget",
                        "cwd": ".",
                        "env": {"TEST": "value"},
                        "shell": "python",
                        "kwargs": {"timeout": 10},
                    }
                }
            },
            "scripts": {
                "install": {
                    "args": "echo installing testy_2",
                    "cwd": ".",
                    "env": {"TEST": "value"},
                    "shell": "pwsh",
                    "kwargs": {"timeout": 10},
                }
            },
        }]
    }
    registry_manager.register_group(group_manifest_1)
    registry_manager.register_group(group_manifest_2)

    group_1 = registry_manager.retrieve_group("test_group_1")
    assert "testy_1" in group_1["packages"]
    pkg1 = registry_manager.retrieve_package("testy_1", "test_group_1")
    assert pkg1["description"] == "Test package 1"

    group_2 = registry_manager.retrieve_group("test_group_2")
    assert "testy_2" in group_2["packages"]
    pkg2 = registry_manager.retrieve_package("testy_2", "test_group_2")
    assert pkg2["description"] == "Test package 2"


def test_register_and_retrieve_two_groups_same_package_names(registry_manager: RegistryManager):
    """
    Test registering two groups that use the same package name.
    The global lookup should return the most recently registered package,
    while specifying the group should return the appropriate version.
    """
    group_manifest_1 = {
        "name": "group_one",
        "location": "/registry/group_one",
        "packages": [{
            "name": "shared_pkg",
            "description": "First version",
            "dependencies": {},
            "scripts": {
                "install": {
                    "args": "echo install group one",
                    "cwd": ".",
                    "env": {},
                    "shell": "bash",
                    "kwargs": {},
                },
                "uninstall": {
                    "args": "echo uninstall group one",
                    "cwd": ".",
                    "env": {},
                    "shell": "bash",
                    "kwargs": {},
                },
            },
        }]
    }
    group_manifest_2 = {
        "name": "group_two",
        "location": "/registry/group_two",
        "packages": [{
            "name": "shared_pkg",
            "description": "Second version",
            "dependencies": {},
            "scripts": {
                "install": {
                    "args": "echo install group two",
                    "cwd": ".",
                    "env": {},
                    "shell": "bash",
                    "kwargs": {},
                },
            },
        }]
    }
    registry_manager.register_group(group_manifest_1)
    registry_manager.register_group(group_manifest_2)

    # Global retrieval returns the latest version (from group_two)
    global_pkg = registry_manager.retrieve_package("shared_pkg")
    assert global_pkg["description"] == "Second version"
    assert "uninstall" not in global_pkg["scripts"]

    # Retrieval by group name returns the correct package
    pkg_group_one = registry_manager.retrieve_package("shared_pkg", "group_one")
    assert pkg_group_one["description"] == "First version"
    assert "uninstall" in pkg_group_one["scripts"]

    pkg_group_two = registry_manager.retrieve_package("shared_pkg", "group_two")
    assert pkg_group_two["description"] == "Second version"
    assert "uninstall" not in pkg_group_two["scripts"]

    # Retrieving scripts with explicit group name
    script_one = registry_manager.retrieve_script("shared_pkg", "install", "group_one")
    assert script_one["args"] == "echo install group one"

    script_two = registry_manager.retrieve_script("shared_pkg", "install", "group_two")
    assert script_two["args"] == "echo install group two"


def test_register_group_duplicate_names_without_overwrite(registry_manager: RegistryManager):
    """
    Test that attempting to register a group with a duplicate name without the overwrite flag
    raises a ValueError, and that using overwrite replaces the group.
    """
    group_manifest = {
        "name": "duplicate_group",
        "location": "/registry/duplicate_group",
        "packages": [{
            "name": "pkg1",
            "description": "Package 1",
            "dependencies": {},
            "scripts": {},
        }]
    }
    registry_manager.register_group(group_manifest)

    with pytest.raises(ValueError):
        registry_manager.register_group(group_manifest)

    # Overwriting should work without error
    new_manifest = {
        "name": "duplicate_group",
        "location": "/registry/new_duplicate_group",
        "packages": [{
            "name": "pkg2",
            "description": "Package 2",
            "dependencies": {},
            "scripts": {
                "run": {
                    "args": "echo run",
                    "cwd": ".",
                    "env": {},
                    "shell": "bash",
                    "kwargs": {},
                }
            },
        }]
    }
    registry_manager.register_group(new_manifest, overwrite=True)
    group = registry_manager.retrieve_group("duplicate_group")
    assert group["location"] == "/registry/new_duplicate_group"
    assert "pkg2" in group["packages"]

    # pkg1 should no longer exist in the overwritten group
    with pytest.raises(ValueError):
        registry_manager.retrieve_package("pkg1", "duplicate_group")


def test_list_groups_and_packages(registry_manager: RegistryManager):
    """
    Test that listing functions return the correct group and package names.
    """
    group_manifest_1 = {
        "name": "groupA",
        "location": "/registry/groupA",
        "packages": [
            {
                "name": "pkgA1",
                "description": "Package A1",
                "dependencies": {},
                "scripts": {
                    "install": {
                        "args": "echo install A1",
                        "cwd": ".",
                        "env": {},
                        "shell": "bash",
                        "kwargs": {},
                    }
                },
            },
            {
                "name": "pkgCommon",
                "description": "Common package from groupA",
                "dependencies": {},
                "scripts": {
                    "install": {
                        "args": "echo install common A",
                        "cwd": ".",
                        "env": {},
                        "shell": "bash",
                        "kwargs": {},
                    }
                },
            },
        ]
    }
    group_manifest_2 = {
        "name": "groupB",
        "location": "/registry/groupB",
        "packages": [
            {
                "name": "pkgB1",
                "description": "Package B1",
                "dependencies": {},
                "scripts": {
                    "install": {
                        "args": "echo install B1",
                        "cwd": ".",
                        "env": {},
                        "shell": "bash",
                        "kwargs": {},
                    }
                },
            },
            {
                "name": "pkgCommon",
                "description": "Common package from groupB",
                "dependencies": {},
                "scripts": {
                    "install": {
                        "args": "echo install common B",
                        "cwd": ".",
                        "env": {},
                        "shell": "bash",
                        "kwargs": {},
                    }
                },
            },
        ]
    }
    registry_manager.register_group(group_manifest_1)
    registry_manager.register_group(group_manifest_2)

    groups = registry_manager.list_groups()
    assert len(groups) == 2
    assert "groupA" in groups
    assert "groupB" in groups

    # Global packages: since pkgCommon is registered twice, the most recent one (from groupB) should be returned.
    packages = registry_manager.list_packages()
    assert "pkgA1" in packages
    assert "pkgB1" in packages
    assert "pkgCommon" in packages
    pkg_common = registry_manager.retrieve_package("pkgCommon")
    assert pkg_common["description"] == "Common package from groupB"


def test_retrieve_nonexistent_entities(registry_manager: RegistryManager):
    """
    Test that retrieving a non-existent group, package, or script raises a ValueError.
    """
    with pytest.raises(ValueError):
        registry_manager.retrieve_group("nonexistent_group")

    # Register a valid group and package
    group_manifest = {
        "name": "groupX",
        "location": "/registry/groupX",
        "packages": [{
            "name": "pkgX",
            "description": "Package X",
            "dependencies": {},
            "scripts": {
                "start": {
                    "args": "echo start",
                    "cwd": ".",
                    "env": {},
                    "shell": "bash",
                    "kwargs": {},
                }
            },
        }]
    }
    registry_manager.register_group(group_manifest)

    with pytest.raises(ValueError):
        registry_manager.retrieve_package("nonexistent_pkg")

    with pytest.raises(ValueError):
        registry_manager.retrieve_script("pkgX", "nonexistent_script")

    with pytest.raises(ValueError):
        registry_manager.retrieve_package("nonexistent_pkg", "groupX")

    with pytest.raises(ValueError):
        registry_manager.retrieve_script("pkgX", "nonexistent_script", "groupX")


def test_reset_registry_clears_all_data(registry_manager: RegistryManager):
    """
    Test that resetting the registry clears all data.
    """
    group_manifest = {
        "name": "group_reset",
        "location": "/registry/group_reset",
        "packages": [{
            "name": "pkg_reset",
            "description": "Package to be reset",
            "dependencies": {},
            "scripts": {
                "install": {
                    "args": "echo install reset",
                    "cwd": ".",
                    "env": {},
                    "shell": "bash",
                    "kwargs": {},
                }
            },
        }]
    }
    registry_manager.register_group(group_manifest)
    # Ensure the registry is not empty before reset.
    assert len(registry_manager.list_groups()) > 0

    # Reset and verify that data is cleared.
    registry_manager.reset_registry()
    with pytest.raises(ValueError):
        registry_manager.retrieve_group("group_reset")
    assert registry_manager.list_groups() == []
    assert registry_manager.list_packages() == []


# ----------------- Removal Tests ----------------- #

def test_remove_group(registry_manager: RegistryManager):
    """
    Test that removing a group removes it and its associated packages.
    """
    group_manifest = {
        "name": "remove_group",
        "location": "/registry/remove_group",
        "packages": [{
            "name": "pkg_remove",
            "description": "A package to remove",
            "dependencies": {},
            "scripts": {
                "install": {
                    "args": "echo install remove",
                    "cwd": ".",
                    "env": {},
                    "shell": "bash",
                    "kwargs": {},
                }
            },
        }]
    }
    registry_manager.register_group(group_manifest)
    # Verify the group and package exist.
    group = registry_manager.retrieve_group("remove_group")
    assert group["name"] == "remove_group"
    pkg = registry_manager.retrieve_package("pkg_remove", "remove_group")
    assert pkg["description"] == "A package to remove"

    # Remove the group.
    registry_manager.remove_group("remove_group")
    with pytest.raises(ValueError):
        registry_manager.retrieve_group("remove_group")
    with pytest.raises(ValueError):
        registry_manager.retrieve_package("pkg_remove", "remove_group")


def test_remove_package(registry_manager: RegistryManager):
    """
    Test that removing a package from a group works correctly.
    """
    group_manifest = {
        "name": "group_for_package_removal",
        "location": "/registry/group_for_package_removal",
        "packages": [
            {
                "name": "pkg1",
                "description": "First package",
                "dependencies": {},
                "scripts": {
                    "install": {
                        "args": "echo install pkg1",
                        "cwd": ".",
                        "env": {},
                        "shell": "bash",
                        "kwargs": {},
                    }
                },
            },
            {
                "name": "pkg2",
                "description": "Second package",
                "dependencies": {},
                "scripts": {
                    "install": {
                        "args": "echo install pkg2",
                        "cwd": ".",
                        "env": {},
                        "shell": "bash",
                        "kwargs": {},
                    }
                },
            }
        ]
    }
    registry_manager.register_group(group_manifest)
    # Remove pkg1 from the group.
    registry_manager.remove_package("pkg1", "group_for_package_removal")
    with pytest.raises(ValueError):
        registry_manager.retrieve_package("pkg1", "group_for_package_removal")

    # pkg2 should still be retrievable.
    pkg2 = registry_manager.retrieve_package("pkg2", "group_for_package_removal")
    assert pkg2["description"] == "Second package"


def test_remove_nonexistent_entities(registry_manager: RegistryManager):
    """
    Test that attempting to remove a non-existent group or package raises a ValueError.
    """
    with pytest.raises(ValueError):
        registry_manager.remove_group("nonexistent_group")

    group_manifest = {
        "name": "test_group_nonexistent",
        "location": "/registry/test_group_nonexistent",
        "packages": [{
            "name": "pkg_exist",
            "description": "Existing package",
            "dependencies": {},
            "scripts": {
                "install": {
                    "args": "echo install pkg_exist",
                    "cwd": ".",
                    "env": {},
                    "shell": "bash",
                    "kwargs": {},
                }
            },
        }]
    }
    registry_manager.register_group(group_manifest)
    with pytest.raises(ValueError):
        registry_manager.remove_package("nonexistent_pkg", "test_group_nonexistent")

def test_register_new_package(registry_manager: RegistryManager):
    """
    Test adding a new package to an existing group.
    """
    group_manifest = {
        "name": "group_pkg",
        "location": "/registry/group_pkg",
        "packages": []  # start with no packages
    }
    registry_manager.register_group(group_manifest)
    pkg_manifest = {
        "name": "pkg_new",
        "description": "A new package",
        "dependencies": {},
        "scripts": {
            "install": {
                "args": "echo install pkg_new",
                "cwd": ".",
                "env": {},
                "shell": "bash",
                "kwargs": {},
            }
        }
    }
    registry_manager.register_package(pkg_manifest, "group_pkg")
    group = registry_manager.retrieve_group("group_pkg")
    assert "pkg_new" in group["packages"]
    pkg = registry_manager.retrieve_package("pkg_new", "group_pkg")
    assert pkg["description"] == "A new package"


def test_register_existing_package_without_overwrite(registry_manager: RegistryManager):
    """
    Test that attempting to register an existing package without overwrite raises an error.
    """
    group_manifest = {
        "name": "group_pkg",
        "location": "/registry/group_pkg",
        "packages": [
            {
                "name": "pkg_exist",
                "description": "Existing package",
                "dependencies": {},
                "scripts": {
                    "install": {
                        "args": "echo install pkg_exist",
                        "cwd": ".",
                        "env": {},
                        "shell": "bash",
                        "kwargs": {},
                    }
                }
            }
        ]
    }
    registry_manager.register_group(group_manifest)
    # Attempt to add the same package without overwrite
    pkg_manifest = {
        "name": "pkg_exist",
        "description": "Updated description",
        "dependencies": {},
        "scripts": {
            "install": {
                "args": "echo updated install",
                "cwd": ".",
                "env": {},
                "shell": "bash",
                "kwargs": {},
            }
        }
    }
    with pytest.raises(ValueError):
        registry_manager.register_package(pkg_manifest, "group_pkg")


def test_register_existing_package_with_overwrite(registry_manager: RegistryManager):
    """
    Test updating an existing package using the overwrite flag.
    """
    group_manifest = {
        "name": "group_pkg",
        "location": "/registry/group_pkg",
        "packages": [
            {
                "name": "pkg_exist",
                "description": "Existing package",
                "dependencies": {"old": "data"},
                "scripts": {
                    "install": {
                        "args": "echo install pkg_exist",
                        "cwd": ".",
                        "env": {},
                        "shell": "bash",
                        "kwargs": {},
                    }
                }
            }
        ]
    }
    registry_manager.register_group(group_manifest)
    # Update package with new details
    pkg_manifest = {
        "name": "pkg_exist",
        "description": "Updated package description",
        "dependencies": {"new": "data"},
        "scripts": {
            "install": {
                "args": "echo updated install",
                "cwd": "./new",
                "env": {"UPDATED": "true"},
                "shell": "bash",
                "kwargs": {"timeout": 20},
            }
        }
    }
    registry_manager.register_package(pkg_manifest, "group_pkg", overwrite=True)
    pkg = registry_manager.retrieve_package("pkg_exist", "group_pkg")
    assert pkg["description"] == "Updated package description"
    assert pkg["dependencies"] == {"new": "data"}
    assert pkg["scripts"]["install"]["args"] == "echo updated install"
    assert pkg["scripts"]["install"]["cwd"] == "./new"
    assert pkg["scripts"]["install"]["env"] == {"UPDATED": "true"}
    assert pkg["scripts"]["install"]["kwargs"] == {"timeout": 20}


def test_register_package_in_nonexistent_group(registry_manager: RegistryManager):
    """
    Test that trying to register a package in a non-existent group raises an error.
    """
    pkg_manifest = {
        "name": "pkg_nonexistent",
        "description": "Should not be registered",
        "dependencies": {},
        "scripts": {
            "install": {
                "args": "echo install pkg_nonexistent",
                "cwd": ".",
                "env": {},
                "shell": "bash",
                "kwargs": {},
            }
        }
    }
    with pytest.raises(ValueError):
        registry_manager.register_package(pkg_manifest, "nonexistent_group")


def test_remove_updated_package(registry_manager: RegistryManager):
    """
    Test that a package updated via register_package can be removed.
    """
    group_manifest = {
        "name": "group_pkg",
        "location": "/registry/group_pkg",
        "packages": [
            {
                "name": "pkg_to_remove",
                "description": "Initial description",
                "dependencies": {},
                "scripts": {
                    "install": {
                        "args": "echo initial",
                        "cwd": ".",
                        "env": {},
                        "shell": "bash",
                        "kwargs": {},
                    }
                }
            }
        ]
    }
    registry_manager.register_group(group_manifest)
    # Update the package first
    pkg_manifest = {
        "name": "pkg_to_remove",
        "description": "Updated description",
        "dependencies": {"dep": "v1"},
        "scripts": {
            "install": {
                "args": "echo updated",
                "cwd": "./updated",
                "env": {"KEY": "value"},
                "shell": "bash",
                "kwargs": {"timeout": 30},
            }
        }
    }
    registry_manager.register_package(pkg_manifest, "group_pkg", overwrite=True)
    pkg = registry_manager.retrieve_package("pkg_to_remove", "group_pkg")
    assert pkg["description"] == "Updated description"

    # Remove the package and verify removal
    registry_manager.remove_package("pkg_to_remove", "group_pkg")
    with pytest.raises(ValueError):
        registry_manager.retrieve_package("pkg_to_remove", "group_pkg")
