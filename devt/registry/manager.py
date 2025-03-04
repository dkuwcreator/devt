"""
devt/registry/manager.py

Manages database operations for the DevT registry, including scripts, packages, and repositories.
"""

import logging
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy import create_engine, desc
from sqlalchemy.orm import sessionmaker

from devt.registry.models import Base, Group, Package

logger = logging.getLogger(__name__)


class RegistryManager:
    def __init__(self, registry_path: Path):
        self.registry_path = registry_path
        # Create a SQLite database inside the provided directory
        db_file = registry_path / "registry.db"
        self.engine = create_engine(f"sqlite:///{db_file}", echo=False)
        self.Session = sessionmaker(bind=self.engine)
        self._setup_db()

    def _setup_db(self):
        Base.metadata.create_all(self.engine)

    def reset_registry(self):
        """Drops and recreates the registry database tables."""
        Base.metadata.drop_all(self.engine)
        Base.metadata.create_all(self.engine)

    @contextmanager
    def session_scope(self):
        """Provide a transactional scope around a series of operations."""
        session = self.Session()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def register_group(self, group_manifest: dict, overwrite: bool = False):
        """
        Registers a group and its packages.
        Raises ValueError if a group with the same name exists (unless overwrite is True).
        """
        with self.session_scope() as session:
            existing_group = session.query(Group).filter_by(
                name=group_manifest["name"]
            ).first()
            if existing_group and not overwrite:
                raise ValueError(f"Group {group_manifest['name']} already exists")
            elif existing_group and overwrite:
                session.delete(existing_group)
                session.commit()  # Ensure deletion before re-registering

            # Create new group
            group = Group(name=group_manifest["name"], location=group_manifest["location"])
            session.add(group)
            session.flush()  # to get group.id

            # Register each package from the manifest
            for pkg in group_manifest.get("packages", []):
                package = Package(
                    name=pkg["name"],
                    description=pkg.get("description", ""),
                    dependencies=pkg.get("dependencies", {}),
                    scripts=pkg.get("scripts", {}),
                    group_id=group.id,
                )
                session.add(package)
            session.commit()

    def register_package(self, pkg_manifest: dict, group_name: str, overwrite: bool = False):
        """
        Registers or updates a package within an existing group.
        
        Parameters:
            pkg_manifest (dict): The package manifest containing keys 'name', 'description', 'dependencies', and 'scripts'.
            group_name (str): The name of the group in which to add/update the package.
            overwrite (bool): If True, updates the package if it already exists; otherwise, raises a ValueError.
        
        Raises:
            ValueError: If the specified group does not exist or if the package exists and overwrite is False.
        """
        with self.session_scope() as session:
            group = session.query(Group).filter_by(name=group_name).first()
            if not group:
                raise ValueError(f"Group {group_name} not found")
            existing_package = session.query(Package).filter_by(group_id=group.id, name=pkg_manifest["name"]).first()
            if existing_package and not overwrite:
                raise ValueError(f"Package {pkg_manifest['name']} already exists in group {group_name}")
            elif existing_package and overwrite:
                # Update existing package fields
                existing_package.description = pkg_manifest.get("description", "")
                existing_package.dependencies = pkg_manifest.get("dependencies", {})
                existing_package.scripts = pkg_manifest.get("scripts", {})
                session.commit()
            else:
                # Create new package record
                new_package = Package(
                    name=pkg_manifest["name"],
                    description=pkg_manifest.get("description", ""),
                    dependencies=pkg_manifest.get("dependencies", {}),
                    scripts=pkg_manifest.get("scripts", {}),
                    group_id=group.id,
                )
                session.add(new_package)
                session.commit()

    def retrieve_group(self, group_name: str) -> dict:
        """
        Retrieves a group and its packages as a dict.
        The returned dict has the keys: name, location, and packages (a dict keyed by package name).
        """
        with self.session_scope() as session:
            group = session.query(Group).filter_by(name=group_name).first()
            if not group:
                raise ValueError(f"Group {group_name} not found")
            packages_dict = {}
            for pkg in group.packages:
                packages_dict[pkg.name] = {
                    "name": pkg.name,
                    "description": pkg.description,
                    "dependencies": pkg.dependencies,
                    "scripts": pkg.scripts,
                }
            return {"name": group.name, "location": group.location, "packages": packages_dict}

    def retrieve_package(
        self, package_name: str, group_name: Optional[str] = None
    ) -> dict:
        """
        Retrieves a package.
        If group_name is provided, it retrieves the package within that group;
        otherwise, it returns the most recently registered package with the given name.
        """
        with self.session_scope() as session:
            if group_name:
                group = session.query(Group).filter_by(name=group_name).first()
                if not group:
                    raise ValueError(f"Group {group_name} not found")
                package = (
                    session.query(Package)
                    .filter_by(group_id=group.id, name=package_name)
                    .first()
                )
            else:
                # Get the package with the latest created_at timestamp among those with the given name
                package = (
                    session.query(Package)
                    .filter_by(name=package_name)
                    .order_by(desc(Package.created_at))
                    .first()
                )
            if not package:
                raise ValueError(f"Package {package_name} not found")
            return {
                "name": package.name,
                "description": package.description,
                "dependencies": package.dependencies,
                "scripts": package.scripts,
            }

    def retrieve_script(
        self, package_name: str, script_name: str, group_name: Optional[str] = None
    ) -> dict:
        """
        Retrieves a script from a package.
        If group_name is specified, the package from that group is used; otherwise,
        the globally registered (latest) package is used.
        """
        package = self.retrieve_package(package_name, group_name)
        scripts = package.get("scripts", {})
        if script_name not in scripts:
            raise ValueError(f"Script {script_name} not found in package {package_name}")
        return scripts[script_name]

    def list_groups(self) -> List[str]:
        """Lists the names of all registered groups."""
        with self.session_scope() as session:
            groups = session.query(Group).all()
            return [group.name for group in groups]

    def list_packages(self) -> List[str]:
        """
        Lists all globally visible package names.
        If multiple packages share the same name across groups,
        the most recently registered one is returned.
        """
        with self.session_scope() as session:
            packages = (
                session.query(Package)
                .order_by(desc(Package.created_at))
                .all()
            )
            seen = {}
            for pkg in packages:
                if pkg.name not in seen:
                    seen[pkg.name] = pkg
            return list(seen.keys())

    def remove_group(self, group_name: str):
        """
        Removes a group and all its associated packages.
        Raises a ValueError if the group does not exist.
        """
        with self.session_scope() as session:
            group = session.query(Group).filter_by(name=group_name).first()
            if not group:
                raise ValueError(f"Group {group_name} not found")
            session.delete(group)
            session.commit()

    def remove_package(self, package_name: str, group_name: Optional[str] = None):
        """
        Removes a package.
        If group_name is provided, removes the package from that group;
        otherwise, removes the globally registered (latest) package with the given name.
        Raises a ValueError if the package does not exist.
        """
        with self.session_scope() as session:
            if group_name:
                group = session.query(Group).filter_by(name=group_name).first()
                if not group:
                    raise ValueError(f"Group {group_name} not found")
                package = session.query(Package).filter_by(group_id=group.id, name=package_name).first()
            else:
                package = session.query(Package).filter_by(name=package_name).order_by(desc(Package.created_at)).first()
            if not package:
                raise ValueError(f"Package {package_name} not found")
            session.delete(package)
            session.commit()
