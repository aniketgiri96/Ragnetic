"""Citation formatting helpers for grounded answers."""
from __future__ import annotations

import re
from typing import Any

CITATION_RE = re.compile(r"\[Source\s+(\d+)\]", re.IGNORECASE)


def source_name(source: dict[str, Any], index: int) -> str:
    metadata = source.get("metadata") or {}
    name = metadata.get("source") or metadata.get("filename") or metadata.get("title")
    if isinstance(name, str) and name.strip():
        return name.strip()
    return f"Source {index + 1}"


def has_citation(answer: str) -> bool:
    return bool(CITATION_RE.search(answer or ""))


def citation_indices(answer: str, sources: list[dict[str, Any]]) -> list[int]:
    max_idx = len(sources) - 1
    indices: set[int] = set()
    for match in CITATION_RE.finditer(answer or ""):
        try:
            idx = int(match.group(1)) - 1
        except (TypeError, ValueError):
            continue
        if 0 <= idx <= max_idx:
            indices.add(idx)
    return sorted(indices)


def enforce_citation_format(answer: str, sources: list[dict[str, Any]], enabled: bool = True) -> str:
    normalized = (answer or "").strip()
    if not enabled or not sources:
        return normalized
    if has_citation(normalized):
        return normalized
    refs = ", ".join(f"[Source {i + 1}]" for i in range(min(len(sources), 3)))
    return f"{normalized}\n\nCitations: {refs}".strip()


def append_citation_legend(
    answer: str,
    sources: list[dict[str, Any]],
    *,
    legend_header: str = "Source references",
    max_items: int = 8,
) -> str:
    normalized = (answer or "").strip()
    if not normalized or not sources:
        return normalized

    header_line = f"{legend_header}:"
    if header_line.lower() in normalized.lower():
        return normalized

    used = citation_indices(normalized, sources)
    if not used:
        return normalized

    grouped: dict[str, list[int]] = {}
    order: list[str] = []
    max_groups = max(1, max_items)
    for idx in used:
        name = source_name(sources[idx], idx)
        if name not in grouped:
            if len(order) >= max_groups:
                continue
            grouped[name] = []
            order.append(name)
        grouped[name].append(idx)

    lines = [header_line]
    for name in order:
        refs = ", ".join(str(idx + 1) for idx in grouped[name])
        lines.append(f"[Source {refs}] {name}")
    return f"{normalized}\n\n" + "\n".join(lines)
