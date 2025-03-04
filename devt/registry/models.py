"""
devt/registry/models.py

Defines the SQLAlchemy models for the DevT registry.
"""
import logging
from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    String,
    DateTime,
    UniqueConstraint,
    Integer,
    ForeignKey,
    JSON,
)
from sqlalchemy.orm import declarative_base, relationship

logger = logging.getLogger(__name__)
Base = declarative_base()


class Group(Base):
    __tablename__ = "groups"

    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    location = Column(String, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    packages = relationship(
        "Package", back_populates="group", cascade="all, delete-orphan"
    )


class Package(Base):
    __tablename__ = "packages"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    description = Column(String)
    dependencies = Column(JSON)
    scripts = Column(JSON)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    group_id = Column(Integer, ForeignKey("groups.id"), nullable=False)
    group = relationship("Group", back_populates="packages")

    __table_args__ = (
        UniqueConstraint("group_id", "name", name="_group_package_uc"),
    )
