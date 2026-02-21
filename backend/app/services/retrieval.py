"""Hybrid retrieval and optional reranking for RAG queries."""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any

from app.core.config import settings
from app.ingestion.embedding import embed_texts
from app.services.qdrant_client import ensure_collection, get_qdrant, search_collection

TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")
RRF_K = 60.0
_cross_encoder = None


@dataclass
class Candidate:
    """Unified retrieval candidate."""

    point_id: str
    text: str
    metadata: dict[str, Any]
    doc_id: int | None
    dense_score: float = 0.0
    sparse_score: float = 0.0
    final_score: float = 0.0


def _tokenize(text: str) -> list[str]:
    return [t.lower() for t in TOKEN_RE.findall(text)]


def _bm25_scores(query: str, docs: list[str]) -> list[float]:
    """Simple BM25 implementation over candidate documents."""
    if not docs:
        return []
    tokenized_docs = [_tokenize(d) for d in docs]
    q_terms = _tokenize(query)
    if not q_terms:
        return [0.0 for _ in docs]

    n_docs = len(tokenized_docs)
    avg_len = sum(len(d) for d in tokenized_docs) / max(1, n_docs)
    k1 = 1.2
    b = 0.75

    df: dict[str, int] = {}
    tf_per_doc: list[dict[str, int]] = []
    for tokens in tokenized_docs:
        tf: dict[str, int] = {}
        for term in tokens:
            tf[term] = tf.get(term, 0) + 1
        tf_per_doc.append(tf)
        for term in set(tokens):
            df[term] = df.get(term, 0) + 1

    scores: list[float] = []
    for tokens, tf in zip(tokenized_docs, tf_per_doc):
        doc_len = max(1, len(tokens))
        score = 0.0
        for term in q_terms:
            if term not in tf:
                continue
            term_df = df.get(term, 0)
            # BM25 idf variant with +1 for numerical stability.
            idf = math.log(1 + (n_docs - term_df + 0.5) / (term_df + 0.5))
            freq = tf[term]
            denom = freq + k1 * (1 - b + b * (doc_len / max(1e-9, avg_len)))
            score += idf * ((freq * (k1 + 1)) / max(1e-9, denom))
        scores.append(score)
    return scores


def _rrf_fuse(dense_rank: dict[str, int], sparse_rank: dict[str, int]) -> dict[str, float]:
    scores: dict[str, float] = {}
    ids = set(dense_rank.keys()) | set(sparse_rank.keys())
    for pid in ids:
        dr = dense_rank.get(pid)
        sr = sparse_rank.get(pid)
        val = 0.0
        if dr is not None:
            val += 1.0 / (RRF_K + dr)
        if sr is not None:
            val += 1.0 / (RRF_K + sr)
        scores[pid] = val
    return scores


def _optional_cross_encoder_score(query: str, docs: list[str]) -> list[float] | None:
    """Return cross-encoder scores when dependency is available."""
    global _cross_encoder
    try:
        from sentence_transformers import CrossEncoder
    except Exception:
        return None
    try:
        if _cross_encoder is None:
            _cross_encoder = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
        pairs = [(query, d) for d in docs]
        return [float(s) for s in _cross_encoder.predict(pairs)]
    except Exception:
        return None


def _dense_search(kb_id: int, query: str, limit: int) -> list[Candidate]:
    coll = ensure_collection(kb_id)
    vector = embed_texts([query])[0]
    hits = search_collection(collection=coll, vector=vector, limit=limit)
    out: list[Candidate] = []
    for h in hits:
        payload = h.payload or {}
        out.append(
            Candidate(
                point_id=str(h.id),
                text=(payload.get("text") or ""),
                metadata=(payload.get("metadata") or {}),
                doc_id=payload.get("doc_id"),
                dense_score=float(h.score or 0.0),
            )
        )
    return out


def _scroll_candidates(kb_id: int, max_points: int = 800) -> list[Candidate]:
    """Read a bounded corpus snapshot for sparse retrieval."""
    coll = ensure_collection(kb_id)
    client = get_qdrant()
    offset = None
    gathered: list[Candidate] = []
    page_limit = 128
    while len(gathered) < max_points:
        points, offset = client.scroll(
            collection_name=coll,
            offset=offset,
            limit=min(page_limit, max_points - len(gathered)),
            with_payload=True,
            with_vectors=False,
        )
        if not points:
            break
        for p in points:
            payload = p.payload or {}
            text = payload.get("text") or ""
            if not text:
                continue
            gathered.append(
                Candidate(
                    point_id=str(p.id),
                    text=text,
                    metadata=(payload.get("metadata") or {}),
                    doc_id=payload.get("doc_id"),
                )
            )
        if offset is None:
            break
    return gathered


def hybrid_retrieve(
    kb_id: int,
    query: str,
    top_k: int | None = None,
    dense_limit: int | None = None,
    sparse_pool: int | None = None,
    rerank_top_n: int | None = None,
) -> list[dict[str, Any]]:
    """Hybrid retrieve with dense + BM25 sparse + RRF and optional reranking."""
    top_k = top_k or settings.retrieval_top_k
    dense_limit = dense_limit or settings.retrieval_dense_limit
    sparse_pool = sparse_pool or settings.retrieval_sparse_pool
    rerank_top_n = rerank_top_n or settings.retrieval_rerank_top_n

    dense_hits = _dense_search(kb_id, query, dense_limit)
    sparse_corpus = _scroll_candidates(kb_id, max_points=sparse_pool)

    # Sparse ranking over bounded corpus snapshot.
    sparse_scores = _bm25_scores(query, [c.text for c in sparse_corpus])
    for c, score in zip(sparse_corpus, sparse_scores):
        c.sparse_score = score

    dense_rank = {c.point_id: i + 1 for i, c in enumerate(sorted(dense_hits, key=lambda x: x.dense_score, reverse=True))}
    sparse_rank = {
        c.point_id: i + 1
        for i, c in enumerate(sorted(sparse_corpus, key=lambda x: x.sparse_score, reverse=True))
        if c.sparse_score > 0
    }
    fused = _rrf_fuse(dense_rank, sparse_rank)

    # Union the best from both lists before final rerank.
    by_id: dict[str, Candidate] = {}
    for c in dense_hits:
        by_id[c.point_id] = c
    for c in sparse_corpus:
        if c.point_id not in by_id:
            by_id[c.point_id] = c
        else:
            by_id[c.point_id].sparse_score = max(by_id[c.point_id].sparse_score, c.sparse_score)

    merged = list(by_id.values())
    for c in merged:
        c.final_score = fused.get(c.point_id, 0.0)
    merged.sort(key=lambda x: x.final_score, reverse=True)

    pre_rerank = merged[: max(top_k, rerank_top_n)]
    ce_scores = _optional_cross_encoder_score(query, [c.text for c in pre_rerank])
    if ce_scores:
        for c, s in zip(pre_rerank, ce_scores):
            # Cross-encoder becomes primary; RRF remains tie-breaker.
            c.final_score = (2.0 * s) + c.final_score
        pre_rerank.sort(key=lambda x: x.final_score, reverse=True)

    out = pre_rerank[:top_k]
    return [
        {
            "snippet": c.text,
            "score": c.final_score,
            "metadata": c.metadata,
            "doc_id": c.doc_id,
            "dense_score": c.dense_score,
            "sparse_score": c.sparse_score,
        }
        for c in out
    ]
