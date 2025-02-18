# --- Registry Class ---

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import json

from sqlalchemy import create_engine, Column, String, Text, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker
from dataclasses import dataclass, field

from package_manager import Script

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
    install_date = Column(DateTime, nullable=False)
    last_update = Column(DateTime, nullable=False)


# ---------------------------------------------------------------------------
# Registry Class Using SQLAlchemy ORM
# ---------------------------------------------------------------------------

class Registry:
    def __init__(self, db_path: Path):
        # Ensure the registry directory exists.
        db_path.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path
        # Convert the path to an absolute path to avoid issues on some systems.
        db_file = (db_path / "registry.db").resolve()
        db_uri = f"sqlite:///{db_file}"
        self.engine = create_engine(db_uri, echo=False, future=True)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, future=True)

    # -----------------------
    # Script-related methods
    # -----------------------

    def add_script(self, command: str, script_name: str, script: Script):
        """
        Add a new script to the registry.
        """
        session = self.Session()
        try:
            # If script.args is a list, store it as JSON. Otherwise, store the string.
            args_value = json.dumps(script.args) if isinstance(script.args, list) else script.args
            new_script = ScriptModel(
                command=command,
                script_name=script_name,
                args=args_value,
                cwd=str(script.cwd),
                env=json.dumps(script.env) if script.env else None,
                shell=script.shell,
                kwargs=json.dumps(script.kwargs) if script.kwargs else None,
            )
            session.add(new_script)
            session.commit()
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    def get_script(self, command: str, script_name: str) -> Optional[Script]:
        """
        Retrieve a script from the registry and convert it into a Script instance.
        """
        session = self.Session()
        try:
            result = session.query(ScriptModel).filter_by(
                command=command, script_name=script_name
            ).first()
            if result:
                # Try to load args as JSON; if it fails, assume it is a string.
                try:
                    parsed_args = json.loads(result.args)
                except json.JSONDecodeError:
                    parsed_args = result.args

                return Script(
                    args=parsed_args,
                    shell=result.shell,
                    cwd=Path(result.cwd),
                    env=json.loads(result.env) if result.env else {},
                    kwargs=json.loads(result.kwargs) if result.kwargs else {},
                )
            return None
        finally:
            session.close()

    def list_scripts(self, command: str) -> List[str]:
        """
        List all script names for a given package (identified by its command).
        """
        session = self.Session()
        try:
            scripts = session.query(ScriptModel).filter_by(command=command).all()
            return [s.script_name for s in scripts]
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

    def update_script(self, command: str, script_name: str, script: Script):
        """
        Update an existing script in the registry.
        """
        session = self.Session()
        try:
            instance = session.query(ScriptModel).filter_by(
                command=command, script_name=script_name
            ).first()
            if instance:
                instance.args = json.dumps(script.args) if isinstance(script.args, list) else script.args
                instance.cwd = str(script.cwd)
                instance.env = json.dumps(script.env) if script.env else None
                instance.shell = script.shell
                instance.kwargs = json.dumps(script.kwargs) if script.kwargs else None
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
                    "install_date": package.install_date.isoformat(),
                    "last_update": package.last_update.isoformat(),
                }
            return None
        finally:
            session.close()

    def list_packages(self) -> List[str]:
        """
        List all package commands stored in the registry.
        """
        session = self.Session()
        try:
            packages = session.query(PackageModel).all()
            return [p.command for p in packages]
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
                package.last_update = datetime.now()
                session.commit()
            else:
                raise ValueError("Package not found")
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()