"""Query expansion helpers (lexical + optional HyDE)."""
from __future__ import annotations

import asyncio
import re
from typing import Iterable

from app.core.config import settings
from app.services.llm import generate as llm_generate

TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")
STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "how",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "to",
    "we",
    "what",
    "when",
    "where",
    "which",
    "who",
    "why",
    "with",
}


def _dedupe_variants(values: Iterable[str], max_items: int) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = (value or "").strip()
        if not normalized:
            continue
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(normalized)
        if len(out) >= max_items:
            break
    return out


def _keyword_variant(query: str, max_terms: int = 12) -> str:
    tokens = [token.lower() for token in TOKEN_RE.findall(query or "")]
    filtered = [token for token in tokens if len(token) > 2 and token not in STOPWORDS]
    if not filtered:
        filtered = [token.lower() for token in TOKEN_RE.findall(query or "")][:max_terms]
    return " ".join(filtered[:max_terms]).strip()


def _semantic_variant(query: str) -> str:
    normalized = (query or "").strip()
    if not normalized:
        return ""
    return (
        f"Relevant documentation details for: {normalized}. "
        "Include policy rules, exceptions, procedures, and required approvals."
    )


async def _hyde_variant(query: str, history: str | None = None) -> str | None:
    if not settings.retrieval_enable_hyde:
        return None
    normalized = (query or "").strip()
    if not normalized:
        return None

    history_block = ""
    if history:
        compact_history = " ".join((history or "").split())
        if compact_history:
            history_block = f"Conversation context: {compact_history[:320]}\n"

    system = (
        "Write a concise hypothetical answer passage for retrieval expansion. "
        "Do not mention that it is hypothetical. Avoid lists. Keep it factual in tone."
    )
    prompt = (
        f"{history_block}"
        f"Question: {normalized}\n"
        "Produce one short paragraph (4-6 sentences) that likely contains terms and concepts from relevant documents."
    )
    try:
        synthetic = await llm_generate(prompt, system=system)
    except Exception:
        return None
    cleaned = " ".join((synthetic or "").split()).strip()
    if not cleaned:
        return None
    return cleaned[: max(120, int(settings.retrieval_hyde_max_chars))]


async def build_query_variants(query: str, history: str | None = None) -> list[str]:
    """Return expanded query variants used by hybrid retrieval."""
    normalized = (query or "").strip()
    if not normalized:
        return [""]
    if not settings.retrieval_enable_query_expansion:
        return [normalized]

    candidates: list[str] = [normalized]
    keyword = _keyword_variant(normalized)
    if keyword:
        candidates.append(keyword)
    semantic = _semantic_variant(normalized)
    if semantic:
        candidates.append(semantic)

    hyde = await _hyde_variant(normalized, history=history)
    if hyde:
        candidates.append(hyde)

    max_variants = max(1, int(settings.retrieval_query_expansion_max_variants))
    return _dedupe_variants(candidates, max_items=max_variants)


def build_query_variants_sync(query: str, history: str | None = None) -> list[str]:
    """Sync wrapper for environments (e.g., Celery tasks) without async flow."""
    try:
        asyncio.get_running_loop()
        # Already in an event loop; avoid nested loop usage and use lexical expansion only.
        normalized = (query or "").strip()
        if not settings.retrieval_enable_query_expansion or not normalized:
            return [normalized]
        candidates = [normalized]
        keyword = _keyword_variant(normalized)
        semantic = _semantic_variant(normalized)
        if keyword:
            candidates.append(keyword)
        if semantic:
            candidates.append(semantic)
        max_variants = max(1, int(settings.retrieval_query_expansion_max_variants))
        return _dedupe_variants(candidates, max_items=max_variants)
    except RuntimeError:
        return asyncio.run(build_query_variants(query=query, history=history))
