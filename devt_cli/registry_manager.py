# registry_manager.py
from datetime import datetime
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Generator
from contextlib import contextmanager

from sqlalchemy import Boolean, create_engine, Column, String, Text, DateTime, JSON
from sqlalchemy.orm import declarative_base, sessionmaker

logger = logging.getLogger(__name__)
Base = declarative_base()


class ScriptModel(Base):
    __tablename__ = "scripts"
    # Composite primary key: (command, script_name)
    command = Column(String, primary_key=True)
    script_name = Column(String, primary_key=True)
    args = Column(JSON, nullable=False)
    cwd = Column(String, nullable=False)
    env = Column(JSON, nullable=True)
    shell = Column(String, nullable=True)
    kwargs = Column(JSON, nullable=True)


class PackageModel(Base):
    __tablename__ = "packages"
    command = Column(String, primary_key=True)  # Unique identifier
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    location = Column(String, nullable=False)
    dependencies = Column(JSON, nullable=True)
    group = Column(String, nullable=True)  # renamed for consistency
    active = Column(Boolean, nullable=False, default=True)
    install_date = Column(DateTime, nullable=False)
    last_update = Column(DateTime, nullable=False)


@contextmanager
def session_scope(Session) -> Generator[Any, None, None]:
    session = Session()
    try:
        yield session
        session.commit()
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()


class Registry:
    def __init__(self, registry_path: Path) -> None:
        registry_path.mkdir(parents=True, exist_ok=True)
        self.registry_path = registry_path
        db_file = (registry_path / "registry.db").resolve()
        db_uri = f"sqlite:///{db_file}"
        self.engine = create_engine(db_uri, echo=False, future=True)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, future=True)
        logger.info(f"Registry initialized with database at {db_file}")

    # -----------------------
    # Script-related methods
    # -----------------------
    def _unpack_script_data(self, script: dict) -> dict:
        # Validate required keys and provide defaults if necessary.
        if "args" not in script:
            raise ValueError("Missing required key 'args' in script configuration.")
        if "cwd" not in script:
            # Default to current directory if not provided
            script["cwd"] = "."
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

    # -------------------------
    # Package-related methods
    # -------------------------
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
        **kwargs: Any,
    ) -> None:
        logger.info(f"Adding package '{command}'.")
        # Validate required package fields.
        if not command or not name or not location:
            raise ValueError("Missing required package fields: command, name, and location must be provided.")
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

    def delete_package(self, command: str) -> None:
        logger.info(f"Deleting package '{command}'.")
        with session_scope(self.Session) as session:
            pkg = session.query(PackageModel).filter_by(command=command).first()
            if not pkg:
                raise ValueError("Package not found")
            session.delete(pkg)

    def update_package(
        self,
        command: str,
        name: str,
        description: str,
        location: str,
        dependencies: Dict[str, Any],
        active: bool = True,
    ) -> None:
        logger.info(f"Updating package '{command}'.")
        with session_scope(self.Session) as session:
            pkg = session.query(PackageModel).filter_by(command=command).first()
            if not pkg:
                raise ValueError("Package not found")
            pkg.name = name
            pkg.description = description
            pkg.location = location
            pkg.dependencies = dependencies if dependencies else None
            pkg.active = active
            pkg.last_update = datetime.now()

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
