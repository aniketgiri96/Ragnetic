"""Semantic-aware chunking: respect paragraphs and size limits."""
import re
from dataclasses import dataclass
from typing import Any


@dataclass
class Chunk:
    text: str
    metadata: dict[str, Any]
    start_char: int
    end_char: int


def chunk_text(
    text: str,
    max_chunk_chars: int = 800,
    overlap_chars: int = 100,
    metadata_base: dict[str, Any] | None = None,
) -> list[Chunk]:
    """Split text into chunks by paragraph boundaries, then by size with overlap."""
    meta = dict(metadata_base or {})
    chunks: list[Chunk] = []
    # Split by double newlines first (paragraphs)
    paragraphs = re.split(r"\n\s*\n", text)
    current = ""
    start = 0
    for i, para in enumerate(paragraphs):
        if not para.strip():
            continue
        if current and len(current) + len(para) + 2 > max_chunk_chars:
            # Emit current chunk
            chunk_meta = {**meta, "paragraph_index": i}
            chunks.append(Chunk(text=current.strip(), metadata=chunk_meta, start_char=start, end_char=start + len(current)))
            # Overlap: keep last overlap_chars
            overlap_start = max(0, len(current) - overlap_chars)
            current = current[overlap_start:] + "\n\n" + para
            start = start + overlap_start
        else:
            current = (current + "\n\n" + para).strip() if current else para
    if current.strip():
        chunks.append(Chunk(text=current.strip(), metadata={**meta}, start_char=start, end_char=start + len(current)))
    return chunks
