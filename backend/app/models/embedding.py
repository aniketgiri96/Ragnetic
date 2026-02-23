"""Embedding namespace and registry models for zero-downtime migration."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class EmbeddingMigrationStatus:
    IDLE = "idle"
    RUNNING = "running"
    FAILED = "failed"


class EmbeddingVersionStatus:
    ACTIVE = "active"
    INACTIVE = "inactive"
    MIGRATING = "migrating"
    READY = "ready"
    FAILED = "failed"


class KBEmbeddingNamespace(Base):
    __tablename__ = "kb_embedding_namespaces"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    knowledge_base_id: Mapped[int] = mapped_column(Integer, nullable=False, unique=True, index=True)
    active_version: Mapped[str] = mapped_column(String(64), nullable=False, default="v1")
    target_version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    migration_status: Mapped[str] = mapped_column(String(32), nullable=False, default=EmbeddingMigrationStatus.IDLE)
    migration_progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class KBEmbeddingVersion(Base):
    __tablename__ = "kb_embedding_versions"
    __table_args__ = (
        UniqueConstraint("knowledge_base_id", "version", name="uq_kb_embedding_version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    knowledge_base_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    model_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    vector_dim: Mapped[int] = mapped_column(Integer, nullable=False, default=384)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=EmbeddingVersionStatus.READY, index=True)
    indexed_documents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
