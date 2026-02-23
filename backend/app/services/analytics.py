"""RAG analytics aggregation from audit events and chat feedback."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.analytics import ChatFeedback, FeedbackRating
from app.models.audit import AuditLog
from app.services.audit import parse_details

RAG_QUERY_ACTIONS = {
    "search.query",
    "chat.query.sync",
    "chat.query.stream.completed",
    "chat.query.async.completed",
}


def _safe_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except Exception:
        return None


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def _normalize_query_text(raw: Any) -> str | None:
    text = str(raw or "").replace("\n", " ").strip()
    if not text:
        return None
    if len(text) > 240:
        return text[:237] + "..."
    return text


def _percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return float(values[0])
    ordered = sorted(values)
    rank = max(0.0, min(1.0, p)) * (len(ordered) - 1)
    lo = int(rank)
    hi = min(lo + 1, len(ordered) - 1)
    frac = rank - lo
    return float(ordered[lo] * (1.0 - frac) + ordered[hi] * frac)


def _is_zero_result(action: str, details: dict[str, Any]) -> bool:
    result_count = _safe_int(details.get("result_count"))
    if result_count is not None:
        return result_count <= 0
    source_count = _safe_int(details.get("source_count"))
    if source_count is not None:
        return source_count <= 0
    if action == "search.query":
        return False
    return False


def _build_drift_alerts(
    *,
    total_queries: int,
    zero_result_rate: float,
    avg_retrieval_ms: float | None,
    low_confidence_rate: float,
    low_faithfulness_rate: float,
) -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []
    if total_queries <= 0:
        return alerts

    if zero_result_rate > settings.analytics_drift_zero_result_rate_threshold:
        alerts.append(
            {
                "type": "zero_result_rate",
                "severity": "warning",
                "value": round(zero_result_rate, 4),
                "threshold": settings.analytics_drift_zero_result_rate_threshold,
                "message": "Zero-result query rate is above threshold.",
            }
        )
    if avg_retrieval_ms is not None and avg_retrieval_ms > settings.analytics_drift_retrieval_ms_threshold:
        alerts.append(
            {
                "type": "retrieval_latency",
                "severity": "warning",
                "value": round(avg_retrieval_ms, 2),
                "threshold": settings.analytics_drift_retrieval_ms_threshold,
                "message": "Average retrieval latency is above threshold.",
            }
        )
    if low_confidence_rate > settings.analytics_drift_low_confidence_rate_threshold:
        alerts.append(
            {
                "type": "low_confidence_rate",
                "severity": "warning",
                "value": round(low_confidence_rate, 4),
                "threshold": settings.analytics_drift_low_confidence_rate_threshold,
                "message": "Low-confidence answer rate is above threshold.",
            }
        )
    if low_faithfulness_rate > settings.analytics_drift_low_faithfulness_rate_threshold:
        alerts.append(
            {
                "type": "low_faithfulness_rate",
                "severity": "warning",
                "value": round(low_faithfulness_rate, 4),
                "threshold": settings.analytics_drift_low_faithfulness_rate_threshold,
                "message": "Low-faithfulness answer rate is above threshold.",
            }
        )
    return alerts


def build_rag_analytics_report(db: Session, kb_id: int, days: int | None = None) -> dict[str, Any]:
    window_days = int(days or settings.analytics_default_window_days)
    window_days = max(1, min(90, window_days))
    now = datetime.utcnow()
    since = now - timedelta(days=window_days)

    logs = (
        db.query(AuditLog)
        .filter(
            and_(
                AuditLog.knowledge_base_id == kb_id,
                AuditLog.created_at >= since,
                AuditLog.action.in_(tuple(RAG_QUERY_ACTIONS)),
            )
        )
        .order_by(AuditLog.created_at.asc(), AuditLog.id.asc())
        .all()
    )
    feedback_rows = (
        db.query(ChatFeedback)
        .filter(
            and_(
                ChatFeedback.knowledge_base_id == kb_id,
                ChatFeedback.created_at >= since,
            )
        )
        .order_by(ChatFeedback.created_at.asc(), ChatFeedback.id.asc())
        .all()
    )

    query_counts = Counter()
    zero_query_counts = Counter()
    action_counts = Counter()

    retrieval_ms_values: list[float] = []
    confidence_values: list[float] = []
    faithfulness_values: list[float] = []
    source_counts: list[int] = []

    zero_result_count = 0
    low_confidence_count = 0
    low_faithfulness_count = 0

    daily = defaultdict(
        lambda: {
            "query_count": 0,
            "zero_result_count": 0,
            "retrieval_ms_values": [],
            "confidence_values": [],
            "faithfulness_values": [],
        }
    )

    for row in logs:
        action_counts[row.action] += 1
        details = parse_details(row.details_json) or {}
        query_text = _normalize_query_text(
            details.get("query_text")
            or details.get("query")
            or details.get("message")
        )
        if query_text:
            query_counts[query_text] += 1

        zero_result = _is_zero_result(row.action, details)
        if zero_result:
            zero_result_count += 1
            if query_text:
                zero_query_counts[query_text] += 1

        retrieval_ms = _safe_float(details.get("retrieval_ms"))
        if retrieval_ms is not None and retrieval_ms >= 0:
            retrieval_ms_values.append(retrieval_ms)

        confidence = _safe_float(details.get("confidence_score"))
        if confidence is not None:
            confidence = max(0.0, min(1.0, confidence))
            confidence_values.append(confidence)
        if bool(details.get("low_confidence")):
            low_confidence_count += 1

        faithfulness = _safe_float(details.get("faithfulness_score"))
        if faithfulness is not None:
            faithfulness = max(0.0, min(1.0, faithfulness))
            faithfulness_values.append(faithfulness)
        if bool(details.get("low_faithfulness")):
            low_faithfulness_count += 1

        source_count = _safe_int(details.get("source_count"))
        if source_count is not None and source_count >= 0:
            source_counts.append(source_count)

        day_key = (row.created_at or now).date().isoformat()
        bucket = daily[day_key]
        bucket["query_count"] += 1
        if zero_result:
            bucket["zero_result_count"] += 1
        if retrieval_ms is not None and retrieval_ms >= 0:
            bucket["retrieval_ms_values"].append(retrieval_ms)
        if confidence is not None:
            bucket["confidence_values"].append(confidence)
        if faithfulness is not None:
            bucket["faithfulness_values"].append(faithfulness)

    total_queries = len(logs)
    avg_retrieval_ms = (sum(retrieval_ms_values) / len(retrieval_ms_values)) if retrieval_ms_values else None
    p95_retrieval_ms = _percentile(retrieval_ms_values, 0.95)
    avg_confidence = (sum(confidence_values) / len(confidence_values)) if confidence_values else None
    avg_faithfulness = (sum(faithfulness_values) / len(faithfulness_values)) if faithfulness_values else None
    avg_source_count = (sum(source_counts) / len(source_counts)) if source_counts else None

    zero_result_rate = (zero_result_count / total_queries) if total_queries else 0.0
    low_confidence_rate = (low_confidence_count / total_queries) if total_queries else 0.0
    low_faithfulness_rate = (low_faithfulness_count / total_queries) if total_queries else 0.0
    context_recall_proxy = (
        sum(1 for n in source_counts if n >= 2) / len(source_counts)
        if source_counts
        else 0.0
    )
    context_precision_proxy = 1.0 - zero_result_rate if total_queries else 0.0

    thumbs_up = sum(1 for r in feedback_rows if r.rating == FeedbackRating.UP)
    thumbs_down = sum(1 for r in feedback_rows if r.rating == FeedbackRating.DOWN)
    feedback_total = thumbs_up + thumbs_down
    helpful_rate = (thumbs_up / feedback_total) if feedback_total else None

    top_limit = max(1, min(25, int(settings.analytics_top_queries_limit)))
    top_queries = [{"query": q, "count": int(c)} for q, c in query_counts.most_common(top_limit)]
    zero_result_queries = [{"query": q, "count": int(c)} for q, c in zero_query_counts.most_common(top_limit)]

    daily_rows = []
    for day_key in sorted(daily.keys()):
        bucket = daily[day_key]
        queries = int(bucket["query_count"])
        zeroes = int(bucket["zero_result_count"])
        daily_rows.append(
            {
                "date": day_key,
                "query_count": queries,
                "zero_result_count": zeroes,
                "zero_result_rate": (zeroes / queries) if queries else 0.0,
                "avg_retrieval_ms": (
                    sum(bucket["retrieval_ms_values"]) / len(bucket["retrieval_ms_values"])
                    if bucket["retrieval_ms_values"]
                    else None
                ),
                "avg_confidence": (
                    sum(bucket["confidence_values"]) / len(bucket["confidence_values"])
                    if bucket["confidence_values"]
                    else None
                ),
                "avg_faithfulness": (
                    sum(bucket["faithfulness_values"]) / len(bucket["faithfulness_values"])
                    if bucket["faithfulness_values"]
                    else None
                ),
            }
        )

    drift_alerts = _build_drift_alerts(
        total_queries=total_queries,
        zero_result_rate=zero_result_rate,
        avg_retrieval_ms=avg_retrieval_ms,
        low_confidence_rate=low_confidence_rate,
        low_faithfulness_rate=low_faithfulness_rate,
    )

    return {
        "kb_id": kb_id,
        "window_days": window_days,
        "window_start": since.isoformat(),
        "window_end": now.isoformat(),
        "query_volume": {
            "total": total_queries,
            "search_queries": int(action_counts.get("search.query", 0)),
            "chat_sync_queries": int(action_counts.get("chat.query.sync", 0)),
            "chat_stream_queries": int(action_counts.get("chat.query.stream.completed", 0)),
            "chat_async_queries": int(action_counts.get("chat.query.async.completed", 0)),
            "zero_result_count": zero_result_count,
            "zero_result_rate": zero_result_rate,
        },
        "latency": {
            "avg_retrieval_ms": avg_retrieval_ms,
            "p95_retrieval_ms": p95_retrieval_ms,
        },
        "quality": {
            "avg_confidence_score": avg_confidence,
            "low_confidence_rate": low_confidence_rate,
            "avg_faithfulness_score": avg_faithfulness,
            "low_faithfulness_rate": low_faithfulness_rate,
            "avg_source_count": avg_source_count,
            # RAGAS-style proxy metrics from available production telemetry.
            "context_precision_proxy": context_precision_proxy,
            "context_recall_proxy": context_recall_proxy,
            "answer_relevance_proxy": avg_confidence,
            "faithfulness_proxy": avg_faithfulness,
        },
        "feedback": {
            "thumbs_up": thumbs_up,
            "thumbs_down": thumbs_down,
            "total": feedback_total,
            "helpful_rate": helpful_rate,
        },
        "top_queries": top_queries,
        "zero_result_queries": zero_result_queries,
        "daily": daily_rows,
        "drift_alerts": drift_alerts,
    }
