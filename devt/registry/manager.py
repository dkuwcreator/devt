# devt/registry_manager.py
from contextlib import contextmanager
from datetime import datetime
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from devt.package.builder import ToolPackage

from .models import Base, ScriptModel, PackageModel, RepositoryModel
from sqlalchemy.exc import IntegrityError

logger = logging.getLogger(__name__)

def create_db_engine(registry_path: Path) -> Any:
    """
    Creates and initializes the database engine.
    """
    registry_path.mkdir(parents=True, exist_ok=True)
    db_file = (registry_path / "registry.db").resolve()
    db_uri = f"sqlite:///{db_file}"
    engine = create_engine(db_uri, echo=False, future=True)
    Base.metadata.create_all(engine)
    logger.info(f"Registry initialized with database at {db_file}")
    return engine

@contextmanager
def session_scope(Session) -> Generator[Any, None, None]:
    """
    Provides a transactional scope for a series of operations.
    """
    session = Session()
    try:
        yield session
        session.commit()
    except Exception as exc:
        session.rollback()
        raise exc
    finally:
        session.close()

class BaseRegistry:
    """
    Base class for registry management.
    """
    def __init__(self, engine: Any) -> None:
        self.engine = engine
        self.Session = sessionmaker(bind=self.engine, future=True)

class ScriptRegistry(BaseRegistry):
    """
    Manages all script-related operations.
    """
    def _unpack_script_data(self, script: dict) -> dict:
        if "args" not in script:
            raise ValueError("Missing required key 'args' in script configuration.")
        script.setdefault("cwd", ".")
        return {
            "args": script["args"],
            "cwd": str(script["cwd"]),
            "env": script.get("env"),
            "shell": script.get("shell"),
            "kwargs": script.get("kwargs"),
        }

    def _pack_script_data(self, script: ScriptModel) -> dict:
        return {
            "args": script.args,
            "cwd": Path(script.cwd),
            "env": script.env,
            "shell": script.shell,
            "kwargs": script.kwargs,
        }

    def add_script(self, command: str, script_name: str, script: dict) -> None:
        logger.info(f"Adding script '{script_name}' for command '{command}'.")
        script_data = self._unpack_script_data(script)
        with session_scope(self.Session) as session:
            new_script = ScriptModel(
                command=command,
                script_name=script_name,
                args=script_data["args"],
                cwd=script_data["cwd"],
                env=script_data["env"],
                shell=script_data["shell"],
                kwargs=script_data["kwargs"],
            )
            session.add(new_script)

    def get_script(self, command: str, script_name: str) -> Optional[dict]:
        logger.info(f"Retrieving script '{script_name}' for command '{command}'.")
        with self.Session() as session:
            result = session.query(ScriptModel).filter_by(
                command=command, script_name=script_name
            ).first()
            if result:
                return {"command": command, "script": script_name, **self._pack_script_data(result)}
            logger.info(f"Script '{script_name}' not found.")
            return None

    def list_scripts(self, command: str) -> List[Any]:
        logger.info(f"Listing scripts for command '{command}'.")
        with self.Session() as session:
            results = session.query(ScriptModel).filter_by(command=command).all()
            return [
                {"command": s.command, "script": s.script_name, **self._pack_script_data(s)}
                for s in results
            ]

    def update_script(self, command: str, script_name: str, script: dict) -> None:
        logger.info(f"Updating script '{script_name}' for command '{command}'.")
        script_data = self._unpack_script_data(script)
        with session_scope(self.Session) as session:
            instance = session.query(ScriptModel).filter_by(
                command=command, script_name=script_name
            ).first()
            if not instance:
                raise ValueError("Script not found")
            instance.args = script_data["args"]
            instance.cwd = script_data["cwd"]
            instance.env = script_data["env"]
            instance.shell = script_data["shell"]
            instance.kwargs = script_data["kwargs"]

    def delete_script(self, command: str, script_name: str) -> None:
        logger.info(f"Deleting script '{script_name}' for command '{command}'.")
        with session_scope(self.Session) as session:
            instance = session.query(ScriptModel).filter_by(
                command=command, script_name=script_name
            ).first()
            if not instance:
                raise ValueError("Script not found")
            session.delete(instance)

class PackageRegistry(BaseRegistry):
    """
    Manages all package-related operations.
    """
    def _pack_package_data(self, package: PackageModel) -> Dict[str, Any]:
        return {
            "command": package.command,
            "name": package.name,
            "description": package.description,
            "location": package.location,
            "dependencies": package.dependencies if package.dependencies is not None else {},
            "group": package.group,
            "active": package.active,
            "install_date": package.install_date.isoformat(),
            "last_update": package.last_update.isoformat(),
        }

    def add_package(
        self,
        command: str,
        name: str,
        description: str,
        location: str,
        dependencies: Dict[str, Any],
        group: Optional[str] = "default",
        overwrite: bool = False,
        **kwargs: Any,
    ) -> None:
        logger.info(f"Adding package '{command}'.")
        if not command or not name or not location:
            raise ValueError(
                "Missing required package fields: command, name, and location must be provided."
            )
        now_dt = datetime.now()
        with session_scope(self.Session) as session:
            new_pkg = PackageModel(
                command=command,
                name=name,
                description=description,
                location=location,
                dependencies=dependencies if dependencies else None,
                group=group,
                active=True,
                install_date=now_dt,
                last_update=now_dt,
            )
            session.add(new_pkg)

    def get_package(self, command: str) -> Optional[Dict[str, Any]]:
        logger.info(f"Retrieving package '{command}'.")
        with self.Session() as session:
            pkg = session.query(PackageModel).filter_by(command=command).first()
            return self._pack_package_data(pkg) if pkg else None

    def list_packages(
        self,
        command: Optional[str] = None,
        name: Optional[str] = None,
        description: Optional[str] = None,
        location: Optional[str] = None,
        group: Optional[str] = None,
        active: Optional[bool] = None,
    ) -> List[Dict[str, Any]]:
        logger.info("Listing packages.")
        with self.Session() as session:
            query = session.query(PackageModel)
            if command:
                query = query.filter_by(command=command)
            if name:
                query = query.filter(PackageModel.name.like(f"%{name}%"))
            if description:
                query = query.filter(PackageModel.description.like(f"%{description}%"))
            if location:
                query = query.filter(PackageModel.location.like(f"%{location}%"))
            if group:
                query = query.filter_by(group=group)
            if active is not None:
                query = query.filter_by(active=active)
            packages = query.all()
            return [self._pack_package_data(pkg) for pkg in packages]

    def update_package(self, command: str, **kwargs) -> None:
        """
        Generalized update for a package. This method dynamically updates any attribute present
        in the PackageModel except for 'install_date', which should never be changed.
        Any keys in kwargs that do not correspond to a valid column in PackageModel will be ignored.
        """
        logger.info(f"Updating package '{command}' with updates: {kwargs}.")
        with session_scope(self.Session) as session:
            pkg = session.query(PackageModel).filter_by(command=command).first()
            if not pkg:
                raise ValueError("Package not found")
            
            valid_columns = {col.name for col in PackageModel.__table__.columns}
            for key, value in kwargs.items():
                if key == "install_date":
                    continue
                if key in valid_columns:
                    if key == "dependencies":
                        setattr(pkg, key, value if value else None)
                    else:
                        setattr(pkg, key, value)
                else:
                    logger.warning(f"Key '{key}' is not a recognized package field and will be ignored.")
            pkg.last_update = datetime.now()

    def delete_package(self, command: str) -> None:
        logger.info(f"Deleting package '{command}'.")
        with session_scope(self.Session) as session:
            pkg = session.query(PackageModel).filter_by(command=command).first()
            if not pkg:
                raise ValueError("Package not found")
            session.delete(pkg)

    def deactivate_package(self, command: str) -> None:
        logger.info(f"Deactivating package '{command}'.")
        with session_scope(self.Session) as session:
            pkg = session.query(PackageModel).filter_by(command=command).first()
            if not pkg:
                raise ValueError("Package not found")
            pkg.active = False

    def activate_package(self, command: str) -> None:
        logger.info(f"Activating package '{command}'.")
        with session_scope(self.Session) as session:
            pkg = session.query(PackageModel).filter_by(command=command).first()
            if not pkg:
                raise ValueError("Package not found")
            pkg.active = True

    def get_package_location(self, command: str) -> Optional[str]:
        logger.info(f"Retrieving location for package '{command}'.")
        with self.Session() as session:
            pkg = session.query(PackageModel).filter_by(command=command).first()
            return pkg.location if pkg else None

class RepositoryRegistry(BaseRegistry):
    """
    Manages all repository-related operations.
    """
    def _pack_repo_data(self, repo: RepositoryModel) -> Dict[str, Any]:
        return {
            "url": repo.url,
            "name": repo.name,
            "branch": repo.branch,
            "location": repo.location,
            "auto_sync": repo.auto_sync,
            "install_date": repo.install_date.isoformat(),
            "last_update": repo.last_update.isoformat(),
        }

    def add_repository(
        self, url: str, name: str, branch: str, location: str, auto_sync: bool = False
    ) -> None:
        logger.info(f"Adding repository '{url}'.")
        now_dt = datetime.now()
        try:
            with session_scope(self.Session) as session:
                new_repo = RepositoryModel(
                    url=url,
                    name=name,
                    branch=branch,
                    location=location,
                    auto_sync=auto_sync,
                    install_date=now_dt,
                    last_update=now_dt,
                )
                session.add(new_repo)
        except Exception as exc:
            if isinstance(exc, IntegrityError):
                logger.error(f"Integrity error: {exc}")
                raise ValueError("Repository already exists") from exc
            else:
                raise exc

    def get_repository(self, url: str) -> Optional[Dict[str, Any]]:
        logger.info(f"Retrieving repository '{url}'.")
        with self.Session() as session:
            repo = session.query(RepositoryModel).filter_by(url=url).first()
            return self._pack_repo_data(repo) if repo else None

    def list_repositories(
        self,
        url: Optional[str] = None,
        name: Optional[str] = None,
        branch: Optional[str] = None,
        location: Optional[str] = None,
        auto_sync: Optional[bool] = None,
    ) -> List[Dict[str, Any]]:
        logger.info("Listing repositories.")
        with self.Session() as session:
            query = session.query(RepositoryModel)
            if url:
                query = query.filter_by(url=url)
            if name:
                query = query.filter(RepositoryModel.name.like(f"%{name}%"))
            if branch:
                query = query.filter(RepositoryModel.branch.like(f"%{branch}%"))
            if location:
                query = query.filter(RepositoryModel.location.like(f"%{location}%"))
            if auto_sync is not None:
                query = query.filter_by(auto_sync=auto_sync)
            repos = query.all()
            return [self._pack_repo_data(repo) for repo in repos]

    def update_repository(self, url: str, **kwargs) -> None:
        logger.info(f"Updating repository '{url}' with updates: {kwargs}.")
        with session_scope(self.Session) as session:
            repo = session.query(RepositoryModel).filter_by(url=url).first()
            if not repo:
                raise ValueError("Repository not found")
            valid_columns = {col.name for col in RepositoryModel.__table__.columns}
            for key, value in kwargs.items():
                if key in valid_columns:
                    setattr(repo, key, value)
                else:
                    logger.warning(f"Key '{key}' is not a recognized repository field and will be ignored.")
            repo.last_update = datetime.now()

    def delete_repository(self, url: str) -> None:
        logger.info(f"Deleting repository '{url}'.")
        with session_scope(self.Session) as session:
            repo = session.query(RepositoryModel).filter_by(url=url).first()
            if not repo:
                raise ValueError("Repository not found")
            session.delete(repo)

    def set_auto_sync(self, url: str, auto_sync: bool) -> None:
        logger.info(f"Setting auto-sync for repository '{url}'.")
        with session_scope(self.Session) as session:
            repo = session.query(RepositoryModel).filter_by(url=url).first()
            if not repo:
                raise ValueError("Repository not found")
            repo.auto_sync = auto_sync

    def get_repo_location(self, url: str) -> Optional[str]:
        logger.info(f"Retrieving location for repository '{url}'.")
        with self.Session() as session:
            repo = session.query(RepositoryModel).filter_by(url=url).first()
            return repo.location if repo else None

    def get_repo_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        logger.info(f"Retrieving repository by name '{name}'.")
        with self.Session() as session:
            repo = session.query(RepositoryModel).filter_by(name=name).first()
            return self._pack_repo_data(repo) if repo else None

class RegistryManager:
    """
    Manages all registry-related operations.
    """
    def __init__(self, registry_path: Path) -> None:
        self.engine = create_db_engine(registry_path)
        self.script_registry = ScriptRegistry(self.engine)
        self.package_registry = PackageRegistry(self.engine)
        self.repository_registry = RepositoryRegistry(self.engine)

    def close(self) -> None:
        self.engine.dispose()
        logger.info("Registry engine disposed.")

    def reset_registry(self) -> None:
        """
        Resets the registry by dropping all tables and recreating them.
        """
        Base.metadata.drop_all(self.engine)
        Base.metadata.create_all(self.engine)
        logger.info("Registry tables dropped and recreated.")

    def register_package(self, pkg: Dict, force: bool = False) -> None:
        """
        Add a new package (and its scripts) to the registries.
        """
        if force:
            self.unregister_package(pkg["command"])
        pkg_data = pkg.copy()
        scripts = pkg_data.pop("scripts", {})
        self.package_registry.add_package(**pkg_data)
        for script_name, script in scripts.items():
            self.script_registry.add_script(pkg_data["command"], script_name, script)

    def update_package(self, pkg: Dict) -> None:
        """
        Update an existing package (and its scripts) in the registries.
        """
        pkg_data = pkg.copy()
        scripts = pkg_data.pop("scripts", {})
        command = pkg_data.get("command")
        if not command:
            raise ValueError("Missing package 'command' field for update.")
        # Exclude 'command' from kwargs since it's passed separately.
        update_data = {k: v for k, v in pkg_data.items() if k != "command"}
        self.package_registry.update_package(command, **update_data)
        for script_name, script in scripts.items():
            self.script_registry.update_script(command, script_name, script)

    def unregister_package(self, command: str) -> None:
        """
        Remove a package and its scripts from the registries.
        """
        self.package_registry.delete_package(command)
        for script in self.script_registry.list_scripts(command):
            self.script_registry.delete_script(script["command"], script["script"])

    def retrieve_package(self, command: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a package and its scripts from the registries.
        """
        pkg = self.package_registry.get_package(command)
        if pkg:
            pkg["scripts"] = {
                script["script"]: script for script in self.script_registry.list_scripts(command)
            }
        return pkg

        
        