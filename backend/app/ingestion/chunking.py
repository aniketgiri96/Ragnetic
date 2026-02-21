"""Semantic-aware chunking with paragraph + sentence-aware splitting."""
import re
from dataclasses import dataclass
from typing import Any


@dataclass
class Chunk:
    text: str
    metadata: dict[str, Any]
    start_char: int
    end_char: int


SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
WORD_SPLIT_RE = re.compile(r"\s+")


def _split_long_segment(text: str, start_char: int, max_chunk_chars: int, min_chunk_chars: int) -> list[tuple[str, int, int]]:
    """Split oversized text by sentence boundaries, fallback to word wrapping."""
    clean = text.strip()
    if not clean:
        return []
    if len(clean) <= max_chunk_chars:
        return [(clean, start_char, start_char + len(clean))]

    pieces = [p.strip() for p in SENTENCE_SPLIT_RE.split(clean) if p.strip()]
    if len(pieces) <= 1:
        # Word-wrap fallback when there are no sentence boundaries.
        words = [w for w in WORD_SPLIT_RE.split(clean) if w]
        out: list[tuple[str, int, int]] = []
        buf = ""
        cursor = start_char
        for word in words:
            candidate = f"{buf} {word}".strip()
            if buf and len(candidate) > max_chunk_chars:
                part = buf.strip()
                out.append((part, cursor, cursor + len(part)))
                cursor += len(part) + 1
                buf = word
            else:
                buf = candidate
        if buf:
            out.append((buf, cursor, cursor + len(buf)))
        return out

    out: list[tuple[str, int, int]] = []
    current = ""
    current_start = start_char
    cursor = start_char
    for sentence in pieces:
        candidate = f"{current} {sentence}".strip() if current else sentence
        if current and len(candidate) > max_chunk_chars:
            part = current.strip()
            out.append((part, current_start, current_start + len(part)))
            current = sentence
            current_start = cursor
        else:
            current = candidate
        cursor += len(sentence) + 1

    if current.strip():
        part = current.strip()
        out.append((part, current_start, current_start + len(part)))

    # Merge tiny trailing parts to avoid retrieval fragmentation.
    if len(out) > 1 and len(out[-1][0]) < min_chunk_chars:
        prev_text, prev_start, _ = out[-2]
        tail_text, _, tail_end = out[-1]
        merged = f"{prev_text}\n{tail_text}".strip()
        out[-2] = (merged, prev_start, tail_end)
        out.pop()
    return out


def _tail_overlap(text: str, overlap_chars: int) -> str:
    if overlap_chars <= 0 or not text:
        return ""
    tail = text[-overlap_chars:]
    # Avoid cutting mid-word.
    first_space = tail.find(" ")
    if first_space > 0 and first_space < len(tail) - 1:
        tail = tail[first_space + 1 :]
    return tail.strip()


def chunk_text(
    text: str,
    max_chunk_chars: int = 600,
    overlap_chars: int = 80,
    min_chunk_chars: int = 180,
    metadata_base: dict[str, Any] | None = None,
) -> list[Chunk]:
    """Split text into semantically coherent chunks with bounded size and overlap."""
    source_text = text or ""
    meta = dict(metadata_base or {})
    chunks: list[Chunk] = []

    # Paragraph-level segmentation first.
    paragraphs = [p for p in re.split(r"\n\s*\n", source_text) if p.strip()]
    if not paragraphs:
        return []

    segments: list[tuple[str, int, int]] = []
    cursor = 0
    for para in paragraphs:
        idx = source_text.find(para, cursor)
        if idx < 0:
            idx = cursor
        cursor = idx + len(para)
        segments.extend(_split_long_segment(para, idx, max_chunk_chars=max_chunk_chars, min_chunk_chars=min_chunk_chars))

    current_text = ""
    current_start = 0
    current_end = 0
    paragraph_count = 0

    def emit_chunk() -> None:
        nonlocal current_text, current_start, current_end, paragraph_count
        body = current_text.strip()
        if not body:
            return
        chunk_meta = {
            **meta,
            "paragraph_count": paragraph_count,
            "char_length": len(body),
        }
        chunks.append(
            Chunk(
                text=body,
                metadata=chunk_meta,
                start_char=current_start,
                end_char=current_end,
            )
        )
        overlap = _tail_overlap(body, overlap_chars=overlap_chars)
        current_text = overlap
        if overlap:
            current_start = max(current_end - len(overlap), 0)
        else:
            current_start = current_end
        paragraph_count = 0

    for seg_text, seg_start, seg_end in segments:
        if not current_text:
            current_text = seg_text
            current_start = seg_start
            current_end = seg_end
            paragraph_count = 1
            continue

        candidate = f"{current_text}\n\n{seg_text}".strip()
        if len(candidate) > max_chunk_chars and len(current_text) >= min_chunk_chars:
            emit_chunk()
            if current_text:
                candidate = f"{current_text}\n\n{seg_text}".strip()
            else:
                candidate = seg_text
        current_text = candidate
        current_end = max(current_end, seg_end)
        paragraph_count += 1

    emit_chunk()

    total = len(chunks)
    for i, chunk in enumerate(chunks):
        chunk.metadata["chunk_index"] = i
        chunk.metadata["chunk_count"] = total
    return chunks
