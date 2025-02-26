# devt/models.py
import logging
from sqlalchemy import Boolean, Column, String, Text, DateTime, JSON
from sqlalchemy.orm import declarative_base

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

    def __repr__(self) -> str:
        return f"<ScriptModel(command={self.command}, script_name={self.script_name})>"

class PackageModel(Base):
    __tablename__ = "packages"
    command = Column(String, primary_key=True)  # Unique identifier
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    location = Column(String, nullable=False)
    dependencies = Column(JSON, nullable=True)
    group = Column(String, nullable=True)
    active = Column(Boolean, nullable=False, default=True)
    install_date = Column(DateTime, nullable=False)
    last_update = Column(DateTime, nullable=False)

    def __repr__(self) -> str:
        return f"<PackageModel(command={self.command}, name={self.name})>"

class RepositoryModel(Base):
    __tablename__ = "repositories"
    url = Column(String, primary_key=True)  # Unique identifier
    name = Column(String, nullable=False)
    branch = Column(String, nullable=True)
    location = Column(String, nullable=False)
    auto_sync = Column(Boolean, nullable=False, default=False)
    install_date = Column(DateTime, nullable=False)
    last_update = Column(DateTime, nullable=False)

    def __repr__(self) -> str:
        return f"<RepositoryModel(url={self.url}, name={self.name})>"
