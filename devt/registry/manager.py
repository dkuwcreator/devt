"""
devt/registry/manager.py

DevT Registry Manager

Manages database operations for the DevT registry, including scripts, packages, and repositories.
"""

from contextlib import contextmanager
from datetime import datetime
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from devt.registry.models import Base, ScriptModel, PackageModel, RepositoryModel

logger = logging.getLogger(__name__)


def create_db_engine(registry_dir: Path) -> Any:
    """
    Creates and initializes the database engine.
    """
    registry_dir.mkdir(parents=True, exist_ok=True)
    db_file = (registry_dir / "registry.db").resolve()
    db_uri = f"sqlite:///{db_file}"
    engine = create_engine(db_uri, echo=False, future=True)
    Base.metadata.create_all(engine)
    logger.debug(f"Registry initialized with database at {db_file}")
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
        logger.error("Session rollback due to exception: %s", exc)
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
            "command": script.command,
            "script_name": script.script_name,
            "args": script.args,
            "cwd": str(Path(script.cwd)),
            "env": script.env,
            "shell": script.shell,
            "kwargs": script.kwargs,
        }

    def add_script(self, command: str, script_name: str, script: dict, force: bool = False) -> None:
        script_data = self._unpack_script_data(script)

        with session_scope(self.Session) as session:
            existing_script = session.query(ScriptModel).filter_by(command=command, script_name=script_name).first()
            if existing_script:
                if force:
                    session.delete(existing_script)
                    logger.info("Existing script '%s' deleted for command '%s'.", script_name, command)
                else:
                    raise ValueError("Script already exists. Use --force to overwrite.")
            session.add(ScriptModel(command=command, script_name=script_name, **script_data))
            logger.debug("Script '%s' added for command '%s'.", script_name, command)

    def get_script(self, command: str, script_name: str) -> Optional[dict]:
        with self.Session() as session:
            result = (
                session.query(ScriptModel)
                .filter_by(command=command, script_name=script_name)
                .first()
            )
            return self._pack_script_data(result) if result else None

    def list_scripts(self, command: str) -> List[dict]:
        with self.Session() as session:
            results = session.query(ScriptModel).filter_by(command=command).all()
            return [self._pack_script_data(s) for s in results]

    def update_script(self, command: str, script_name: str, script: dict) -> None:
        script_data = self._unpack_script_data(script)
        with session_scope(self.Session) as session:
            instance = (
                session.query(ScriptModel)
                .filter_by(command=command, script_name=script_name)
                .first()
            )
            if not instance:
                raise ValueError("Script not found")
            instance.args = script_data["args"]
            instance.cwd = script_data["cwd"]
            instance.env = script_data["env"]
            instance.shell = script_data["shell"]
            instance.kwargs = script_data["kwargs"]

    def delete_script(self, command: str, script_name: str) -> None:
        with session_scope(self.Session) as session:
            instance = (
                session.query(ScriptModel)
                .filter_by(command=command, script_name=script_name)
                .first()
            )
            if instance:
                session.delete(instance)
                logger.debug(
                    "Deleted script '%s' for command '%s'.", script_name, command
                )


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
            "dependencies": (
                package.dependencies if package.dependencies is not None else {}
            ),
            "group": package.group,
            "active": package.active,
            "install_date": package.install_date.isoformat(),
            "last_update": package.last_update.isoformat(),
        }

    def add_package(self, **kwargs: Any) -> None:
        now_dt = datetime.now()
        kwargs["install_date"] = now_dt
        kwargs["last_update"] = now_dt

        command = kwargs.get("command")
        force = kwargs.pop("force", False)

        with session_scope(self.Session) as session:
            existing_pkg = session.query(PackageModel).filter_by(command=command).first()
            if existing_pkg:
                if force:
                    session.delete(existing_pkg)
                    logger.info("Existing package '%s' deleted.", command)
                else:
                    raise ValueError("Package already exists. Use --force to overwrite.")
            session.add(PackageModel(**kwargs))
            logger.debug("Package '%s' added.", command)

    def get_package(self, command: str) -> Optional[Dict[str, Any]]:
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
        logger.debug("Listing packages with filters.")
        with session_scope(self.Session) as session:
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

    def update_package(self, command: str, **kwargs: Any) -> None:
        with session_scope(self.Session) as session:
            pkg = session.query(PackageModel).filter_by(command=command).first()
            if not pkg:
                raise ValueError("Package not found")

            valid_columns = {col.name for col in PackageModel.__table__.columns}
            for key, value in kwargs.items():
                if key == "install_date":
                    continue
                if key in valid_columns:
                    setattr(
                        pkg,
                        key,
                        value if key != "dependencies" else (value if value else None),
                    )
                else:
                    logger.warning("Key '%s' is not a recognized package field.", key)
            pkg.last_update = datetime.now()

    def delete_package(self, command: str) -> None:
        with session_scope(self.Session) as session:
            pkg = session.query(PackageModel).filter_by(command=command).first()
            if pkg:
                session.delete(pkg)
                logger.debug("Package '%s' deleted.", command)

    def deactivate_package(self, command: str) -> None:
        logger.info("Deactivating package '%s'.", command)
        with session_scope(self.Session) as session:
            pkg = session.query(PackageModel).filter_by(command=command).first()
            if not pkg:
                raise ValueError("Package not found")
            pkg.active = False

    def activate_package(self, command: str) -> None:
        with session_scope(self.Session) as session:
            pkg = session.query(PackageModel).filter_by(command=command).first()
            if not pkg:
                raise ValueError("Package not found")
            pkg.active = True

    def get_package_location(self, command: str) -> Optional[str]:
        with session_scope(self.Session) as session:
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

    def add_repository(self, **kwargs: Any) -> None:
        now_dt = datetime.now()
        kwargs.setdefault("install_date", now_dt)
        kwargs.setdefault("last_update", now_dt)

        url = kwargs.get("url")
        force = kwargs.pop("force", False)

        with session_scope(self.Session) as session:
            existing_repo = session.query(RepositoryModel).filter_by(url=url).first()
            if existing_repo:
                if force:
                    session.delete(existing_repo)
                    logger.info("Existing repository '%s' deleted.", url)
                else:
                    raise ValueError("Repository already exists. Use --force to overwrite.")
            session.add(RepositoryModel(**kwargs))
            logger.debug("Repository '%s' added.", url)

    def get_repository(self, url: str) -> Optional[Dict[str, Any]]:
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
        with session_scope(self.Session) as session:
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

    def update_repository(self, url: str, **kwargs: Any) -> None:
        with session_scope(self.Session) as session:
            repo = session.query(RepositoryModel).filter_by(url=url).first()
            if not repo:
                raise ValueError("Repository not found")
            valid_columns = {col.name for col in RepositoryModel.__table__.columns}
            for key, value in kwargs.items():
                if key in valid_columns:
                    setattr(repo, key, value)
                else:
                    logger.warning(
                        "Key '%s' is not a recognized repository field.", key
                    )
            repo.last_update = datetime.now()

    def delete_repository(self, url: str) -> None:
        with session_scope(self.Session) as session:
            repo = session.query(RepositoryModel).filter_by(url=url).first()
            if repo:
                session.delete(repo)

    def set_auto_sync(self, url: str, auto_sync: bool) -> None:
        with session_scope(self.Session) as session:
            repo = session.query(RepositoryModel).filter_by(url=url).first()
            if not repo:
                raise ValueError("Repository not found")
            repo.auto_sync = auto_sync

    def get_repo_location(self, url: str) -> Optional[str]:
        with session_scope(self.Session) as session:
            repo = session.query(RepositoryModel).filter_by(url=url).first()
            return repo.location if repo else None

    def get_repo_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        with session_scope(self.Session) as session:
            repo = session.query(RepositoryModel).filter_by(name=name).first()
            return self._pack_repo_data(repo) if repo else None


class RegistryManager:
    """
    Manages all registry-related operations.
    """

    @classmethod
    def from_context(cls, ctx: Any) -> "RegistryManager":
        return cls(ctx.obj.get("registry_dir"))

    def __init__(self, registry_dir: Path) -> None:
        self.engine = create_db_engine(registry_dir)
        self.script_registry = ScriptRegistry(self.engine)
        self.package_registry = PackageRegistry(self.engine)
        self.repository_registry = RepositoryRegistry(self.engine)

    def reset_registry(self) -> None:
        """Drops and recreates registry tables."""
        Base.metadata.drop_all(self.engine)
        Base.metadata.create_all(self.engine)
        logger.info("Registry tables dropped and recreated.")

    def register_package(self, pkg: Dict[str, Any], force: bool = False) -> None:
        logger.info("Registering package: %s", pkg.get("command"))
        scripts = pkg.pop("scripts", {})
        for script_name, script in scripts.items():
            self.script_registry.add_script(pkg["command"], script_name, script, force=force)
        self.package_registry.add_package(**pkg)
        
    def update_package(self, pkg: Dict[str, Any]) -> None:
        logger.info("Updating package: %s", pkg.get("command"))
        scripts = pkg.pop("scripts", {})
        command = pkg.get("command")
        if not command:
            raise ValueError("Missing package 'command' field for update.")
        update_data = {k: v for k, v in pkg.items() if k != "command"}
        self.package_registry.update_package(command, **update_data)
        for script_name, script in scripts.items():
            self.script_registry.update_script(command, script_name, script)

    def unregister_package(self, command: str) -> None:
        logger.info("Unregistering package: %s", command)
        self.package_registry.delete_package(command)
        for script in self.script_registry.list_scripts(command):
            self.script_registry.delete_script(script["command"], script["script_name"])

    def retrieve_package(self, command: str) -> Optional[Dict[str, Any]]:
        logger.debug("Retrieving package: %s", command)
        pkg = self.package_registry.get_package(command)
        if pkg:
            pkg["scripts"] = {
                script["script_name"]: script
                for script in self.script_registry.list_scripts(command)
            }
        return pkg

    def list_packages(
        self,
        command: Optional[str] = None,
        name: Optional[str] = None,
        description: Optional[str] = None,
        location: Optional[str] = None,
        group: Optional[str] = None,
        active: Optional[bool] = None,
    ) -> List[Dict[str, Any]]:
        logger.debug("Listing packages with filters.")
        return self.package_registry.list_packages(
            command=command,
            name=name,
            description=description,
            location=location,
            group=group,
            active=active,
        )

    def register_repository(self, **kwargs: Any) -> None:
        logger.info("Registering repository: %s", kwargs.get("url"))
        self.repository_registry.add_repository(**kwargs)

    def update_repository(self, url: str, **kwargs: Any) -> None:
        logger.info("Updating repository: %s", url)
        self.repository_registry.update_repository(url, **kwargs)

    def unregister_repository(self, url: str) -> None:
        logger.info("Unregistering repository: %s", url)
        self.repository_registry.delete_repository(url)

    def retrieve_repository(self, url: str) -> Optional[Dict[str, Any]]:
        logger.debug("Retrieving repository: %s", url)
        return self.repository_registry.get_repository(url)

    def list_repositories(
        self,
        url: Optional[str] = None,
        name: Optional[str] = None,
        branch: Optional[str] = None,
        location: Optional[str] = None,
        auto_sync: Optional[bool] = None,
    ) -> List[Dict[str, Any]]:
        logger.debug(
            "Listing repositories with filters: url=%s, name=%s, branch=%s, "
            "location=%s, auto_sync=%s",
            url,
            name,
            branch,
            location,
            auto_sync,
        )
        return self.repository_registry.list_repositories(
            url=url, name=name, branch=branch, location=location, auto_sync=auto_sync
        )

    def get_repo_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        logger.debug("Retrieving repository by name: %s", name)
        return self.repository_registry.get_repo_by_name(name)
