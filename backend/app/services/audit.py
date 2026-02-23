"""Audit logging helpers."""
from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy.orm import Session

from app.models.audit import AuditLog

logger = logging.getLogger(__name__)


def _serialize_details(details: dict[str, Any] | None) -> str | None:
    if details is None:
        return None
    try:
        return json.dumps(details, ensure_ascii=True)
    except Exception as exc:  # pragma: no cover - defensive serialization fallback
        logger.warning("Failed to serialize audit details: %s", exc)
        return json.dumps({"raw": str(details)}, ensure_ascii=True)


def parse_details(details_json: str | None) -> dict[str, Any] | None:
    if not details_json:
        return None
    try:
        parsed = json.loads(details_json)
        if isinstance(parsed, dict):
            return parsed
        return {"value": parsed}
    except json.JSONDecodeError:
        return {"raw": details_json}


def log_audit_event(
    db: Session,
    *,
    user_id: int | None,
    knowledge_base_id: int | None,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    if not action or not resource_type:
        return
    db.add(
        AuditLog(
            user_id=user_id,
            knowledge_base_id=knowledge_base_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details_json=_serialize_details(details),
        )
    )
