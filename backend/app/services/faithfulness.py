"""Heuristic faithfulness scoring for grounded RAG answers."""
from __future__ import annotations

import re
from typing import Any

TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")
SENTENCE_RE = re.compile(r"(?<=[.!?])\s+|\n+")
CITATION_RE = re.compile(r"\[Source\s+\d+(?:\s*,\s*\d+)*\]", re.IGNORECASE)
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
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "to",
    "was",
    "were",
    "with",
}


def _clean_answer(answer: str) -> str:
    normalized = (answer or "").strip()
    if not normalized:
        return ""
    marker = re.search(r"\n\s*source references\s*:\s*", normalized, flags=re.IGNORECASE)
    if marker:
        normalized = normalized[: marker.start()].strip()
    return normalized


def _split_claims(answer: str) -> list[str]:
    cleaned = _clean_answer(answer)
    if not cleaned:
        return []
    claims = [part.strip() for part in SENTENCE_RE.split(cleaned) if part.strip()]
    return [claim for claim in claims if len(claim) >= 8]


def _claim_tokens(claim: str) -> list[str]:
    return [
        token.lower()
        for token in TOKEN_RE.findall(claim or "")
        if len(token) > 2 and token.lower() not in STOPWORDS
    ]


def _source_text(sources: list[dict[str, Any]]) -> str:
    chunks = []
    for source in sources:
        snippet = ((source or {}).get("snippet") or "").strip()
        if snippet:
            chunks.append(snippet.lower())
    return "\n".join(chunks)


def _claim_is_supported(claim: str, source_corpus: str, source_tokens: set[str]) -> bool:
    compact_claim = CITATION_RE.sub("", claim or "").strip().lower()
    if not compact_claim:
        return False
    if compact_claim in source_corpus:
        return True

    tokens = _claim_tokens(compact_claim)
    if not tokens:
        return False
    overlap = sum(1 for token in tokens if token in source_tokens)
    ratio = overlap / max(1, len(tokens))
    return ratio >= 0.45


def faithfulness_score(answer: str, sources: list[dict[str, Any]]) -> float:
    """Return a 0..1 grounding score from citation and lexical support signals."""
    claims = _split_claims(answer)
    if not claims or not sources:
        return 0.0

    source_corpus = _source_text(sources)
    source_tokens = {token.lower() for token in TOKEN_RE.findall(source_corpus)}
    if not source_tokens:
        return 0.0

    supported = sum(1 for claim in claims if _claim_is_supported(claim, source_corpus, source_tokens))
    with_citation = sum(1 for claim in claims if CITATION_RE.search(claim))

    support_ratio = supported / max(1, len(claims))
    citation_ratio = with_citation / max(1, len(claims))
    source_coverage = min(1.0, len(sources) / 4.0)

    score = (0.60 * support_ratio) + (0.30 * citation_ratio) + (0.10 * source_coverage)
    return round(max(0.0, min(1.0, score)), 3)


def faithfulness_signals(
    answer: str,
    sources: list[dict[str, Any]],
    *,
    threshold: float,
    enabled: bool = True,
) -> dict[str, Any]:
    if not enabled:
        return {
            "faithfulness_score": None,
            "low_faithfulness": False,
        }
    score = faithfulness_score(answer, sources)
    limit = max(0.0, min(1.0, float(threshold)))
    return {
        "faithfulness_score": score,
        "low_faithfulness": score < limit,
    }
