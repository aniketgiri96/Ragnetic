"""KB-scoped embedding namespace registry and migration helpers."""
from __future__ import annotations

from datetime import datetime
import re
from typing import Any

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.ingestion.embedding import get_embedding_dim
from app.models.base import SessionLocal
from app.models.embedding import (
    EmbeddingMigrationStatus,
    EmbeddingVersionStatus,
    KBEmbeddingNamespace,
    KBEmbeddingVersion,
)

VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def normalize_embedding_version(version: str | None, default: str = "v1") -> str:
    normalized = (version or "").strip()
    if not normalized:
        normalized = default
    if not VERSION_RE.match(normalized):
        raise ValueError("embedding version must match ^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
    return normalized


def _clamp_progress(progress: int) -> int:
    return max(0, min(100, int(progress)))


def _get_or_create_namespace(db: Session, kb_id: int) -> KBEmbeddingNamespace:
    row = db.query(KBEmbeddingNamespace).filter(KBEmbeddingNamespace.knowledge_base_id == kb_id).first()
    if row is None:
        row = KBEmbeddingNamespace(knowledge_base_id=kb_id, active_version="v1")
        db.add(row)
        db.flush()
    return row


def _get_or_create_version_row(
    db: Session,
    *,
    kb_id: int,
    version: str,
    model_name: str | None,
    vector_dim: int,
) -> KBEmbeddingVersion:
    row = (
        db.query(KBEmbeddingVersion)
        .filter(
            KBEmbeddingVersion.knowledge_base_id == kb_id,
            KBEmbeddingVersion.version == version,
        )
        .first()
    )
    if row is None:
        row = KBEmbeddingVersion(
            knowledge_base_id=kb_id,
            version=version,
            model_name=model_name,
            vector_dim=vector_dim,
            status=EmbeddingVersionStatus.READY,
            indexed_documents=0,
        )
        db.add(row)
        db.flush()
    return row


def ensure_embedding_namespace(db: Session, kb_id: int) -> KBEmbeddingNamespace:
    namespace = _get_or_create_namespace(db, kb_id)
    dim = get_embedding_dim()
    active = _get_or_create_version_row(
        db,
        kb_id=kb_id,
        version=namespace.active_version,
        model_name=None,
        vector_dim=dim,
    )
    active.status = EmbeddingVersionStatus.ACTIVE
    db.commit()
    db.refresh(namespace)
    return namespace


def get_active_embedding_version(db: Session, kb_id: int) -> str:
    namespace = ensure_embedding_namespace(db, kb_id)
    return namespace.active_version


def get_active_embedding_version_for_kb(kb_id: int) -> str:
    db = SessionLocal()
    try:
        return get_active_embedding_version(db, kb_id)
    except Exception:
        # Keep retrieval/indexing paths usable in degraded test/dev environments.
        return "v1"
    finally:
        db.close()


def start_embedding_migration(
    db: Session,
    *,
    kb_id: int,
    target_version: str,
    model_name: str | None = None,
) -> KBEmbeddingNamespace:
    version = normalize_embedding_version(target_version)
    namespace = ensure_embedding_namespace(db, kb_id)
    dim = get_embedding_dim()

    target = _get_or_create_version_row(
        db,
        kb_id=kb_id,
        version=version,
        model_name=model_name,
        vector_dim=dim,
    )
    target.status = EmbeddingVersionStatus.MIGRATING
    target.model_name = model_name or target.model_name
    target.vector_dim = dim
    target.indexed_documents = 0

    namespace.target_version = version
    namespace.migration_status = EmbeddingMigrationStatus.RUNNING
    namespace.migration_progress = 0
    namespace.last_error = None
    namespace.started_at = datetime.utcnow()
    namespace.finished_at = None
    db.commit()
    db.refresh(namespace)
    return namespace


def update_embedding_migration_progress(
    db: Session,
    *,
    kb_id: int,
    target_version: str,
    progress: int,
    indexed_documents: int,
) -> None:
    namespace = _get_or_create_namespace(db, kb_id)
    namespace.target_version = normalize_embedding_version(target_version)
    namespace.migration_status = EmbeddingMigrationStatus.RUNNING
    namespace.migration_progress = _clamp_progress(progress)

    row = _get_or_create_version_row(
        db,
        kb_id=kb_id,
        version=namespace.target_version,
        model_name=None,
        vector_dim=get_embedding_dim(),
    )
    row.status = EmbeddingVersionStatus.MIGRATING
    row.indexed_documents = max(0, int(indexed_documents))
    db.commit()


def complete_embedding_migration(
    db: Session,
    *,
    kb_id: int,
    target_version: str,
    indexed_documents: int,
) -> KBEmbeddingNamespace:
    version = normalize_embedding_version(target_version)
    namespace = _get_or_create_namespace(db, kb_id)
    previous_active = namespace.active_version
    namespace.active_version = version
    namespace.target_version = None
    namespace.migration_status = EmbeddingMigrationStatus.IDLE
    namespace.migration_progress = 100
    namespace.last_error = None
    namespace.finished_at = datetime.utcnow()

    target_row = _get_or_create_version_row(
        db,
        kb_id=kb_id,
        version=version,
        model_name=None,
        vector_dim=get_embedding_dim(),
    )
    target_row.status = EmbeddingVersionStatus.ACTIVE
    target_row.indexed_documents = max(0, int(indexed_documents))

    if previous_active and previous_active != version:
        old_row = (
            db.query(KBEmbeddingVersion)
            .filter(
                KBEmbeddingVersion.knowledge_base_id == kb_id,
                KBEmbeddingVersion.version == previous_active,
            )
            .first()
        )
        if old_row is not None:
            old_row.status = EmbeddingVersionStatus.INACTIVE
    db.commit()
    db.refresh(namespace)
    return namespace


def fail_embedding_migration(db: Session, *, kb_id: int, error_message: str) -> KBEmbeddingNamespace:
    namespace = _get_or_create_namespace(db, kb_id)
    namespace.migration_status = EmbeddingMigrationStatus.FAILED
    namespace.last_error = (error_message or "").strip()[:3000] or "unknown error"
    namespace.finished_at = datetime.utcnow()

    if namespace.target_version:
        row = (
            db.query(KBEmbeddingVersion)
            .filter(
                KBEmbeddingVersion.knowledge_base_id == kb_id,
                KBEmbeddingVersion.version == namespace.target_version,
            )
            .first()
        )
        if row is not None:
            row.status = EmbeddingVersionStatus.FAILED
    db.commit()
    db.refresh(namespace)
    return namespace


def list_embedding_registry(db: Session, kb_id: int) -> dict[str, Any]:
    namespace = ensure_embedding_namespace(db, kb_id)
    rows = (
        db.query(KBEmbeddingVersion)
        .filter(KBEmbeddingVersion.knowledge_base_id == kb_id)
        .order_by(desc(KBEmbeddingVersion.updated_at), desc(KBEmbeddingVersion.id))
        .all()
    )
    return {
        "kb_id": kb_id,
        "active_version": namespace.active_version,
        "target_version": namespace.target_version,
        "migration_status": namespace.migration_status,
        "migration_progress": namespace.migration_progress,
        "last_error": namespace.last_error,
        "versions": [
            {
                "version": row.version,
                "status": row.status,
                "vector_dim": row.vector_dim,
                "model_name": row.model_name,
                "indexed_documents": row.indexed_documents,
                "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            }
            for row in rows
        ],
    }
