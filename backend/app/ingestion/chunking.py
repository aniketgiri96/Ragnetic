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
MD_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
NUMBERED_HEADING_RE = re.compile(r"^(\d+(?:\.\d+){0,5})[\).]?\s+(.+?)\s*$")


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


def _tail_overlap_chars(text: str, overlap_chars: int) -> str:
    if overlap_chars <= 0 or not text:
        return ""
    tail = text[-overlap_chars:]
    # Avoid cutting mid-word.
    first_space = tail.find(" ")
    if first_space > 0 and first_space < len(tail) - 1:
        tail = tail[first_space + 1 :]
    return tail.strip()


def _tail_overlap_sentences(text: str, overlap_sentences: int, overlap_chars: int) -> str:
    if not text:
        return ""
    if overlap_chars <= 0:
        return ""
    sentence_count = max(0, int(overlap_sentences))
    if sentence_count <= 0:
        return _tail_overlap_chars(text, overlap_chars=overlap_chars)

    sentences = [part.strip() for part in SENTENCE_SPLIT_RE.split(text) if part.strip()]
    if not sentences:
        return _tail_overlap_chars(text, overlap_chars=overlap_chars)

    overlap = " ".join(sentences[-sentence_count:]).strip()
    if overlap_chars > 0 and len(overlap) > overlap_chars:
        overlap = _tail_overlap_chars(overlap, overlap_chars=overlap_chars)
    return overlap.strip()


def _heading_level_and_title(line: str) -> tuple[int, str] | None:
    match = MD_HEADING_RE.match(line)
    if match:
        level = len(match.group(1))
        title = match.group(2).strip()
        if title:
            return level, title

    match = NUMBERED_HEADING_RE.match(line)
    if match:
        numbering = match.group(1)
        title = match.group(2).strip()
        if title:
            level = numbering.count(".") + 1
            return level, title
    return None


def _paragraph_segments_with_sections(source_text: str) -> list[tuple[str, int, int, str]]:
    lines = source_text.splitlines(keepends=True)
    if not lines:
        return []

    heading_stack: dict[int, str] = {}
    buffer: list[str] = []
    search_cursor = 0
    out: list[tuple[str, int, int, str]] = []

    def section_path() -> str:
        if not heading_stack:
            return ""
        return " > ".join(heading_stack[level] for level in sorted(heading_stack))

    def flush_buffer() -> None:
        nonlocal search_cursor
        raw = "".join(buffer)
        buffer.clear()
        body = raw.strip()
        if not body:
            return
        idx = source_text.find(body, search_cursor)
        if idx < 0:
            idx = search_cursor
        end = idx + len(body)
        search_cursor = end
        out.append((body, idx, end, section_path()))

    for line in lines:
        stripped = line.strip()
        heading = _heading_level_and_title(stripped)
        if heading:
            flush_buffer()
            level, title = heading
            heading_stack[level] = title
            for key in list(heading_stack.keys()):
                if key > level:
                    del heading_stack[key]
            continue

        buffer.append(line)
        if not stripped:
            flush_buffer()

    flush_buffer()
    return out


def chunk_text(
    text: str,
    max_chunk_chars: int = 600,
    overlap_chars: int = 80,
    overlap_sentences: int = 1,
    min_chunk_chars: int = 180,
    metadata_base: dict[str, Any] | None = None,
) -> list[Chunk]:
    """Split text into semantically coherent chunks with bounded size and overlap."""
    source_text = text or ""
    meta = dict(metadata_base or {})
    chunks: list[Chunk] = []

    # Section and paragraph-level segmentation first.
    paragraphs = _paragraph_segments_with_sections(source_text)
    if not paragraphs:
        return []

    segments: list[tuple[str, int, int, str]] = []
    for para_text, para_start, _, section_path in paragraphs:
        split_parts = _split_long_segment(
            para_text,
            para_start,
            max_chunk_chars=max_chunk_chars,
            min_chunk_chars=min_chunk_chars,
        )
        for part_text, part_start, part_end in split_parts:
            segments.append((part_text, part_start, part_end, section_path))

    current_text = ""
    current_start = 0
    current_end = 0
    paragraph_count = 0
    section_paths: list[str] = []

    def emit_chunk() -> None:
        nonlocal current_text, current_start, current_end, paragraph_count, section_paths
        body = current_text.strip()
        if not body:
            return
        unique_paths: list[str] = []
        for path in section_paths:
            normalized = (path or "").strip()
            if not normalized or normalized in unique_paths:
                continue
            unique_paths.append(normalized)
        chunk_meta = {
            **meta,
            "paragraph_count": paragraph_count,
            "char_length": len(body),
        }
        if unique_paths:
            chunk_meta["section_path"] = unique_paths[-1]
            chunk_meta["section_paths"] = unique_paths
            chunk_meta["section_title"] = unique_paths[-1].split(" > ")[-1]
        chunks.append(
            Chunk(
                text=body,
                metadata=chunk_meta,
                start_char=current_start,
                end_char=current_end,
            )
        )
        overlap = _tail_overlap_sentences(
            body,
            overlap_sentences=overlap_sentences,
            overlap_chars=overlap_chars,
        )
        current_text = overlap
        if overlap:
            current_start = max(current_end - len(overlap), 0)
        else:
            current_start = current_end
        paragraph_count = 0
        section_paths = unique_paths[-1:] if overlap and unique_paths else []

    for seg_text, seg_start, seg_end, seg_section in segments:
        if not current_text:
            current_text = seg_text
            current_start = seg_start
            current_end = seg_end
            paragraph_count = 1
            if seg_section:
                section_paths = [seg_section]
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
        if seg_section:
            if not section_paths or section_paths[-1] != seg_section:
                section_paths.append(seg_section)

    emit_chunk()

    # Guard against identical repeated chunks from duplicated document sections.
    deduped: list[Chunk] = []
    seen_texts: set[str] = set()
    for chunk in chunks:
        normalized_text = re.sub(r"\s+", " ", chunk.text).strip().lower()
        if not normalized_text or normalized_text in seen_texts:
            continue
        seen_texts.add(normalized_text)
        deduped.append(chunk)
    chunks = deduped

    total = len(chunks)
    for i, chunk in enumerate(chunks):
        chunk.metadata["chunk_index"] = i
        chunk.metadata["chunk_count"] = total
    return chunks
