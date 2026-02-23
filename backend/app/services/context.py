"""Adaptive context assembly for grounded chat prompts."""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from app.core.config import settings

TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")
SENTENCE_RE = re.compile(r"(?<=[.!?])\s+|\n+")


@dataclass
class ContextAssembly:
    sources: list[dict[str, Any]]
    context_blocks: str
    token_budget: int
    token_used: int
    compressed_sources: int


def approximate_token_count(text: str) -> int:
    """Fast token estimate without model-specific tokenizer dependency."""
    normalized = (text or "").strip()
    if not normalized:
        return 0
    by_chars = max(1, len(normalized) // 4)
    by_words = len(TOKEN_RE.findall(normalized))
    return max(by_chars, by_words)


def _truncate_to_token_budget(text: str, max_tokens: int) -> str:
    normalized = (text or "").strip()
    if not normalized or max_tokens <= 0:
        return ""
    if approximate_token_count(normalized) <= max_tokens:
        return normalized
    max_chars = max(24, max_tokens * 4)
    trimmed = normalized[:max_chars].strip()
    if " " in trimmed:
        trimmed = trimmed.rsplit(" ", 1)[0].strip()
    if not trimmed:
        trimmed = normalized[:max_chars].strip()
    return f"{trimmed}..."


def _sentence_chunks(text: str) -> list[str]:
    return [p.strip() for p in SENTENCE_RE.split(text or "") if p.strip()]


def _query_terms(query: str) -> set[str]:
    return {term.lower() for term in TOKEN_RE.findall(query or "") if len(term) > 2}


def _relevance_score(sentence: str, terms: set[str]) -> float:
    tokens = [term.lower() for term in TOKEN_RE.findall(sentence or "")]
    if not tokens:
        return 0.0
    overlap = sum(1 for token in tokens if token in terms)
    density = overlap / max(1, len(tokens))
    length_bonus = min(1.0, len(tokens) / 24.0)
    return (2.0 * overlap) + (2.5 * density) + length_bonus


def _compress_snippet(snippet: str, query: str, max_tokens: int, min_tokens: int) -> tuple[str, bool]:
    normalized = (snippet or "").strip()
    if not normalized:
        return "", False

    baseline = _truncate_to_token_budget(normalized, max_tokens=max_tokens)
    if not settings.chat_context_compression_enabled:
        return baseline, baseline != normalized

    original_tokens = approximate_token_count(normalized)
    if original_tokens <= max_tokens:
        return normalized, False

    sentences = _sentence_chunks(normalized)
    if len(sentences) <= 1:
        return baseline, baseline != normalized

    terms = _query_terms(query)
    ranked = [
        (_relevance_score(sentence, terms), idx, sentence)
        for idx, sentence in enumerate(sentences)
    ]
    ranked.sort(key=lambda item: (item[0], -item[1]), reverse=True)

    ratio = max(0.25, min(1.0, float(settings.chat_context_compression_target_ratio)))
    target_tokens = max(
        min_tokens,
        min(max_tokens, int(original_tokens * ratio)),
    )

    selected_indices: list[int] = []
    selected_tokens = 0
    for score, idx, sentence in ranked:
        sentence_tokens = approximate_token_count(sentence)
        if sentence_tokens <= 0:
            continue
        if score <= 0 and selected_tokens >= min_tokens:
            continue
        if selected_tokens + sentence_tokens > max_tokens and selected_tokens >= min_tokens:
            continue
        selected_indices.append(idx)
        selected_tokens += sentence_tokens
        if selected_tokens >= target_tokens:
            break

    if not selected_indices:
        return baseline, baseline != normalized

    selected_indices.sort()
    compressed = " ".join(sentences[idx] for idx in selected_indices).strip()
    compressed = _truncate_to_token_budget(compressed, max_tokens=max_tokens)
    return compressed, compressed != normalized


def _lost_middle_order(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    front: list[dict[str, Any]] = []
    tail: list[dict[str, Any]] = []
    for idx, item in enumerate(candidates):
        if idx % 2 == 0:
            front.append(item)
        else:
            tail.append(item)
    return front + list(reversed(tail))


def assemble_context(
    *,
    query: str,
    history: str,
    sources: list[dict[str, Any]],
    max_sources: int,
    per_source_char_limit: int,
) -> ContextAssembly:
    """Select and compress retrieved sources under a dynamic token budget."""
    safe_max_sources = max(1, int(max_sources))
    safe_char_limit = max(120, int(per_source_char_limit))

    filtered: list[dict[str, Any]] = []
    for source in sources:
        snippet = ((source or {}).get("snippet") or "").strip()
        if not snippet:
            continue
        filtered.append(
            {
                **source,
                "snippet": snippet[:safe_char_limit].strip(),
                "score": float((source or {}).get("score", 0.0)),
            }
        )

    ranked = sorted(filtered, key=lambda item: float(item.get("score", 0.0)), reverse=True)
    arranged = _lost_middle_order(ranked)

    total_ctx = max(1024, int(settings.chat_model_context_tokens))
    ratio = max(0.25, min(0.95, float(settings.chat_context_budget_ratio)))
    reserved = max(0, int(settings.chat_context_reserved_tokens))
    prompt_tokens = approximate_token_count(query) + approximate_token_count(history)
    token_budget = int(total_ctx * ratio) - reserved - prompt_tokens

    min_tokens_per_source = max(24, int(settings.chat_context_min_tokens_per_source))
    max_tokens_per_source = max(min_tokens_per_source, int(settings.chat_context_max_tokens_per_source))
    token_budget = max(min_tokens_per_source, token_budget)

    chosen: list[dict[str, Any]] = []
    used_tokens = 0
    compressed_sources = 0

    for source in arranged:
        if len(chosen) >= safe_max_sources:
            break
        remaining = token_budget - used_tokens
        if remaining < min_tokens_per_source and chosen:
            break

        source_budget = min(max_tokens_per_source, max(min_tokens_per_source, remaining))
        snippet, compressed = _compress_snippet(
            source.get("snippet", ""),
            query=query,
            max_tokens=source_budget,
            min_tokens=min_tokens_per_source,
        )
        snippet = snippet.strip()
        if not snippet:
            continue

        snippet_tokens = approximate_token_count(snippet)
        if snippet_tokens > remaining:
            if chosen:
                continue
            snippet = _truncate_to_token_budget(snippet, max_tokens=remaining)
            snippet_tokens = approximate_token_count(snippet)
            if not snippet_tokens:
                continue

        candidate = dict(source)
        candidate["snippet"] = snippet
        candidate["context_tokens"] = snippet_tokens
        chosen.append(candidate)
        used_tokens += snippet_tokens
        if compressed:
            compressed_sources += 1

    if not chosen and ranked:
        fallback_source = ranked[0]
        snippet = _truncate_to_token_budget(
            fallback_source.get("snippet", ""),
            max_tokens=min(max_tokens_per_source, token_budget),
        )
        snippet_tokens = approximate_token_count(snippet)
        chosen = [{**fallback_source, "snippet": snippet, "context_tokens": snippet_tokens}]
        used_tokens = snippet_tokens
        compressed_sources = int(snippet != fallback_source.get("snippet", ""))

    context_blocks = "\n\n---\n\n".join(
        f"[Source {idx + 1}]\n{(item.get('snippet') or '').strip()}"
        for idx, item in enumerate(chosen)
        if (item.get("snippet") or "").strip()
    )

    return ContextAssembly(
        sources=chosen,
        context_blocks=context_blocks,
        token_budget=token_budget,
        token_used=used_tokens,
        compressed_sources=compressed_sources,
    )
