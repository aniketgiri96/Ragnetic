"""Helpers for ingestion job lifecycle, DLQ, and connector sync state."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.models.ingestion import (
    ConnectorSyncState,
    IngestionDeadLetter,
    IngestionJob,
    IngestionJobReason,
    IngestionJobStatus,
)


def next_ingestion_attempt(previous_attempt: int | None) -> int:
    if previous_attempt is None:
        return 1
    return max(1, int(previous_attempt)) + 1


def clamp_progress(progress: int | None) -> int:
    if progress is None:
        return 0
    return max(0, min(100, int(progress)))


def should_replace_existing_upload(existing_hash: str | None, incoming_hash: str, replace_existing: bool) -> bool:
    if not replace_existing:
        return False
    if not incoming_hash:
        return False
    return (existing_hash or "") != incoming_hash


def create_ingestion_job(
    db: Session,
    *,
    document_id: int,
    knowledge_base_id: int,
    requested_by_user_id: int | None,
    reason: str,
) -> IngestionJob:
    latest = (
        db.query(IngestionJob)
        .filter(IngestionJob.document_id == document_id)
        .order_by(desc(IngestionJob.id))
        .first()
    )
    attempt = next_ingestion_attempt(latest.attempt if latest else None)
    job = IngestionJob(
        document_id=document_id,
        knowledge_base_id=knowledge_base_id,
        requested_by_user_id=requested_by_user_id,
        reason=reason,
        status=IngestionJobStatus.QUEUED,
        progress=0,
        attempt=attempt,
    )
    db.add(job)
    db.flush()
    return job


def mark_ingestion_job_queued(db: Session, *, job_id: int, celery_task_id: str | None) -> None:
    job = db.query(IngestionJob).filter(IngestionJob.id == job_id).first()
    if job is None:
        return
    job.status = IngestionJobStatus.QUEUED
    job.progress = max(0, job.progress)
    job.celery_task_id = celery_task_id
    job.error_message = None
    db.commit()


def mark_ingestion_job_running(
    db: Session,
    *,
    job_id: int,
    progress: int | None = None,
) -> None:
    job = db.query(IngestionJob).filter(IngestionJob.id == job_id).first()
    if job is None:
        return
    job.status = IngestionJobStatus.RUNNING
    if job.started_at is None:
        job.started_at = datetime.utcnow()
    if progress is not None:
        job.progress = clamp_progress(progress)
    job.error_message = None
    db.commit()


def update_ingestion_job_progress(db: Session, *, job_id: int, progress: int) -> None:
    job = db.query(IngestionJob).filter(IngestionJob.id == job_id).first()
    if job is None:
        return
    job.status = IngestionJobStatus.RUNNING
    if job.started_at is None:
        job.started_at = datetime.utcnow()
    job.progress = clamp_progress(progress)
    db.commit()


def mark_ingestion_job_completed(db: Session, *, job_id: int, progress: int = 100) -> None:
    job = db.query(IngestionJob).filter(IngestionJob.id == job_id).first()
    if job is None:
        return
    job.status = IngestionJobStatus.COMPLETED
    if job.started_at is None:
        job.started_at = datetime.utcnow()
    job.finished_at = datetime.utcnow()
    job.progress = clamp_progress(progress)
    job.error_message = None
    db.commit()


def mark_ingestion_job_failed(
    db: Session,
    *,
    job_id: int,
    error_message: str,
    failure_stage: str | None = None,
    record_dead_letter: bool = True,
) -> None:
    job = db.query(IngestionJob).filter(IngestionJob.id == job_id).first()
    if job is None:
        return
    job.status = IngestionJobStatus.FAILED
    if job.started_at is None:
        job.started_at = datetime.utcnow()
    job.finished_at = datetime.utcnow()
    job.error_message = (error_message or "").strip()[:4000] or "unknown error"
    db.flush()
    if record_dead_letter:
        db.add(
            IngestionDeadLetter(
                ingestion_job_id=job.id,
                document_id=job.document_id,
                knowledge_base_id=job.knowledge_base_id,
                failure_stage=(failure_stage or "").strip()[:64] or None,
                error_message=job.error_message,
                resolved=False,
                retry_count=0,
            )
        )
    db.commit()


def resolve_dead_letters_for_document(db: Session, *, document_id: int) -> int:
    now = datetime.utcnow()
    rows = (
        db.query(IngestionDeadLetter)
        .filter(
            IngestionDeadLetter.document_id == document_id,
            IngestionDeadLetter.resolved.is_(False),
        )
        .all()
    )
    for row in rows:
        row.resolved = True
        row.resolved_at = now
    db.commit()
    return len(rows)


def list_dead_letters(
    db: Session,
    *,
    knowledge_base_id: int,
    limit: int = 100,
    resolved: bool = False,
) -> list[dict[str, Any]]:
    safe_limit = max(1, min(500, int(limit)))
    rows = (
        db.query(IngestionDeadLetter)
        .filter(
            IngestionDeadLetter.knowledge_base_id == knowledge_base_id,
            IngestionDeadLetter.resolved.is_(bool(resolved)),
        )
        .order_by(desc(IngestionDeadLetter.created_at), desc(IngestionDeadLetter.id))
        .limit(safe_limit)
        .all()
    )
    return [
        {
            "dead_letter_id": row.id,
            "ingestion_job_id": row.ingestion_job_id,
            "document_id": row.document_id,
            "kb_id": row.knowledge_base_id,
            "failure_stage": row.failure_stage,
            "error_message": row.error_message,
            "retry_count": row.retry_count,
            "resolved": row.resolved,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "resolved_at": row.resolved_at.isoformat() if row.resolved_at else None,
        }
        for row in rows
    ]


def increment_dead_letter_retry(db: Session, *, dead_letter_id: int) -> IngestionDeadLetter | None:
    row = db.query(IngestionDeadLetter).filter(IngestionDeadLetter.id == dead_letter_id).first()
    if row is None:
        return None
    row.retry_count = int(row.retry_count or 0) + 1
    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return row


def mark_connector_sync(
    db: Session,
    *,
    knowledge_base_id: int,
    source_type: str,
    scope_key: str,
    cursor: str | None,
    synced_at: datetime | None,
    error: str | None = None,
    successful: bool = True,
) -> ConnectorSyncState:
    row = (
        db.query(ConnectorSyncState)
        .filter(
            ConnectorSyncState.knowledge_base_id == knowledge_base_id,
            ConnectorSyncState.source_type == source_type,
            ConnectorSyncState.scope_key == scope_key,
        )
        .first()
    )
    if row is None:
        row = ConnectorSyncState(
            knowledge_base_id=knowledge_base_id,
            source_type=source_type,
            scope_key=scope_key,
        )
        db.add(row)
        db.flush()

    row.cursor = cursor
    row.last_synced_at = synced_at
    if successful:
        row.last_success_at = synced_at or datetime.utcnow()
        row.last_error = None
    else:
        row.last_error = (error or "").strip()[:2000] or "sync failed"
    db.commit()
    db.refresh(row)
    return row


def get_connector_sync_state(
    db: Session,
    *,
    knowledge_base_id: int,
    source_type: str,
    scope_key: str,
) -> ConnectorSyncState | None:
    return (
        db.query(ConnectorSyncState)
        .filter(
            ConnectorSyncState.knowledge_base_id == knowledge_base_id,
            ConnectorSyncState.source_type == source_type,
            ConnectorSyncState.scope_key == scope_key,
        )
        .first()
    )


def is_incremental_sync_due(last_synced_at: datetime | None, source_updated_at: datetime | None) -> bool:
    if source_updated_at is None:
        return False
    if last_synced_at is None:
        return True
    return source_updated_at > last_synced_at


VALID_INGESTION_REASONS = {
    IngestionJobReason.UPLOAD,
    IngestionJobReason.RETRY,
    IngestionJobReason.REPLACE,
    IngestionJobReason.REINDEX,
}
