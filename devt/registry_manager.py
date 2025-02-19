# --- Registry Class ---

from datetime import datetime
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
import json

from sqlalchemy import Boolean, create_engine, Column, String, Text, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker

# Configure a basic logger (logs at INFO level by default)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# ORM Models
# ---------------------------------------------------------------------------

Base = declarative_base()


class ScriptModel(Base):
    __tablename__ = 'scripts'
    # A composite primary key: (command, script_name)
    command = Column(String, primary_key=True)
    script_name = Column(String, primary_key=True)
    args = Column(Text, nullable=False)
    cwd = Column(Text, nullable=False)
    env = Column(Text, nullable=True)
    shell = Column(Text, nullable=True)
    kwargs = Column(Text, nullable=True)


class PackageModel(Base):
    __tablename__ = 'packages'
    command = Column(String, primary_key=True)  # Unique identifier for the package
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    location = Column(Text, nullable=False)
    dependencies = Column(Text, nullable=True)
    collection = Column(String, nullable=True)
    active = Column(Boolean, nullable=False, default=True)
    install_date = Column(DateTime, nullable=False)
    last_update = Column(DateTime, nullable=False)


# ---------------------------------------------------------------------------
# Registry Class Using SQLAlchemy ORM
# ---------------------------------------------------------------------------

class Registry:
    def __init__(self, registry_path: Path):
        # Ensure the registry directory exists.
        registry_path.mkdir(parents=True, exist_ok=True)
        self.registry_path = registry_path
        # Convert the path to an absolute path to avoid issues on some systems.
        db_file = (registry_path / "registry.db").resolve()
        db_uri = f"sqlite:///{db_file}"
        self.engine = create_engine(db_uri, echo=False, future=True)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, future=True)
        logger.info(f"Registry initialized with database at {db_file}")

    # -----------------------
    # Script-related methods
    # -----------------------

    def add_script(self, command: str, script_name: str, script: dict):
        """
        Add a new script to the registry.
        """
        logger.info(f"Adding script '{script_name}' for command '{command}' to the registry.")
        session = self.Session()
        try:
            # If script.args is a list, store it as JSON. Otherwise, store the string.
            args_value = json.dumps(script["args"]) if isinstance(script["args"], list) else script["args"]
            new_script = ScriptModel(
                command=command,
                script_name=script_name,
                args=args_value,
                cwd=str(script["cwd"]),
                env=json.dumps(script["env"]) if script["env"] else None,
                shell=script["shell"],
                kwargs=json.dumps(script["kwargs"]) if script["kwargs"] else None,
            )
            session.add(new_script)
            session.commit()
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    def get_script(self, command: str, script_name: str) -> Optional[dict]:
        """
        Retrieve a script from the registry and convert it into a Script instance.
        """
        logger.info(f"Retrieving script '{script_name}' for command '{command}' from the registry.")
        session = self.Session()
        try:
            result = session.query(ScriptModel).filter_by(
                command=command, script_name=script_name
            ).first()
            if result:
                logger.info(f"Script '{script_name}' found in the registry.")
                # Try to load args as JSON; if it fails, assume it is a string.
                try:
                    parsed_args = json.loads(result.args)
                except json.JSONDecodeError:
                    parsed_args = result.args

                return {
                    "args": parsed_args,
                    "shell": result.shell,
                    "cwd": Path(result.cwd),
                    "env": json.loads(result.env) if result.env else {},
                    "kwargs": json.loads(result.kwargs) if result.kwargs else {},
                }
            return None
        finally:
            session.close()

    def list_scripts(self, command: str) -> List[Any]:
        """
        List all script for a given package (identified by its command).
        """
        session = self.Session()
        try:
            result = session.query(ScriptModel).filter_by(command=command).all()
            return [
                {
                    "command": command,	
                    "script": script.script_name,
                    "args": json.loads(script.args) if script.args else [],
                    "shell": script.shell,
                    "cwd": Path(script.cwd),
                    "env": json.loads(script.env) if script.env else {},
                    "kwargs": json.loads(script.kwargs) if script.kwargs else {},
                }
                for script in result
            ]
        finally:
            session.close()

    def remove_script(self, command: str, script_name: str):
        """
        Remove a script from the registry.
        """
        session = self.Session()
        try:
            instance = session.query(ScriptModel).filter_by(
                command=command, script_name=script_name
            ).first()
            if instance:
                session.delete(instance)
                session.commit()
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    def update_script(self, command: str, script_name: str, script: dict):
        """
        Update an existing script in the registry.
        """
        session = self.Session()
        try:
            instance = session.query(ScriptModel).filter_by(
                command=command, script_name=script_name
            ).first()
            if instance:
                instance.args = json.dumps(script["args"]) if isinstance(script["args"], list) else script["args"]
                instance.cwd = str(script["cwd"])
                instance.env = json.dumps(script["env"]) if script["env"] else None
                instance.shell = script["shell"]
                instance.kwargs = json.dumps(script["kwargs"]) if script["kwargs"] else None
                session.commit()
            else:
                raise ValueError("Script not found")
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    # -------------------------
    # Package-related methods
    # -------------------------

    def add_package(
        self,
        command: str,
        name: str,
        description: str,
        location: str,
        dependencies: Dict[str, Any],
        collection: Optional[str] = "default",
    ):
        """
        Add a new package entry to the registry.
        """
        session = self.Session()
        try:
            now_dt = datetime.now()
            new_package = PackageModel(
                command=command,
                name=name,
                description=description,
                location=location,
                dependencies=json.dumps(dependencies) if dependencies else None,
                collection=collection,
                active=True,
                install_date=now_dt,
                last_update=now_dt,
            )
            session.add(new_package)
            session.commit()
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    def get_package(self, command: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve package details as a dictionary.
        """
        session = self.Session()
        try:
            package = session.query(PackageModel).filter_by(command=command).first()
            if package:
                return {
                    "command": package.command,
                    "name": package.name,
                    "description": package.description,
                    "location": package.location,
                    "dependencies": json.loads(package.dependencies) if package.dependencies else {},
                    "collection": package.collection,
                    "active": package.active,
                    "install_date": package.install_date.isoformat(),
                    "last_update": package.last_update.isoformat(),
                }
            return None
        finally:
            session.close()

    def list_packages(
        self, 
        command: Optional[str] = None,
        name: Optional[str] = None, 
        description: Optional[str] = None, 
        location: Optional[str] = None,
        collection: Optional[str] = None, 
        active: Optional[bool] = None
    ) -> List[Dict[str, Any]]:
        """
        List all packages stored in the registry. Optionally filter by collection, name, description, and location.
        """
        session = self.Session()
        try:
            query = session.query(PackageModel)
            if command:
                query = query.filter_by(command=command)
            if name:
                query = query.filter(PackageModel.name.like(f"%{name}%"))
            if description:
                query = query.filter(PackageModel.description.like(f"%{description}%"))
            if location:
                query = query.filter(PackageModel.location.like(f"%{location}%"))
            if collection:
                query = query.filter_by(collection=collection)
            if active is not None:
                query = query.filter_by(active=active)
            packages = query.all()
            return [
                {
                    "command": p.command,
                    "name": p.name,
                    "description": p.description,
                    "location": p.location,
                    "dependencies": json.loads(p.dependencies) if p.dependencies else {},
                    "collection": p.collection,
                    "active": p.active,
                    "install_date": p.install_date.isoformat(),
                    "last_update": p.last_update.isoformat(),
                }
                for p in packages
            ]
        finally:
            session.close()

    def remove_package(self, command: str):
        """
        Remove a package (and any related scripts should be removed separately).
        """
        session = self.Session()
        try:
            package = session.query(PackageModel).filter_by(command=command).first()
            if package:
                session.delete(package)
                session.commit()
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    def update_package(
        self,
        command: str,
        name: str,
        description: str,
        location: str,
        dependencies: Dict[str, Any],
        active: bool = True
    ):
        """
        Update an existing package entry.
        """
        session = self.Session()
        try:
            package = session.query(PackageModel).filter_by(command=command).first()
            if package:
                package.name = name
                package.description = description
                package.location = location
                package.dependencies = json.dumps(dependencies) if dependencies else None
                package.active = active
                package.last_update = datetime.now()
                session.commit()
            else:
                raise ValueError("Package not found")
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    def deactivate_package(self, command: str):
        """
        Deactivate a package without removing it from the registry.
        """
        session = self.Session()
        try:
            package = session.query(PackageModel).filter_by(command=command).first()
            if package:
                package.active = False
                session.commit()
            else:
                raise ValueError("Package not found")
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    def activate_package(self, command: str):
        """
        Activate a package that was previously deactivated.
        """
        session = self.Session()
        try:
            package = session.query(PackageModel).filter_by(command=command).first()
            if package:
                package.active = True
                session.commit()
            else:
                raise ValueError("Package not found")
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    def get_package_location(self, command: str) -> Optional[str]:
        """
        Retrieve the location of a package.
        """
        session = self.Session()
        try:
            package = session.query(PackageModel).filter_by(command=command).first()
            if package:
                return package.location
            return None
        finally:
            session.close()