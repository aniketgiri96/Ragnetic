import re

from app.ingestion.chunking import chunk_text


def test_chunk_text_respects_max_and_adds_metadata():
    text = (
        "Paragraph one sentence one. Paragraph one sentence two.\n\n"
        "Paragraph two sentence one. Paragraph two sentence two.\n\n"
        "Paragraph three sentence one. Paragraph three sentence two."
    )
    chunks = chunk_text(
        text,
        max_chunk_chars=90,
        overlap_chars=20,
        min_chunk_chars=40,
        metadata_base={"source": "resume.txt", "doc_id": 9},
    )
    assert len(chunks) >= 2
    for i, c in enumerate(chunks):
        assert len(c.text) <= 120  # overlap can slightly raise effective string size
        assert c.metadata["source"] == "resume.txt"
        assert c.metadata["doc_id"] == 9
        assert c.metadata["chunk_index"] == i
        assert c.metadata["chunk_count"] == len(chunks)
        assert c.start_char <= c.end_char


def test_chunk_text_splits_very_long_paragraph():
    text = " ".join(["alpha"] * 500)
    chunks = chunk_text(
        text,
        max_chunk_chars=200,
        overlap_chars=30,
        min_chunk_chars=80,
    )
    assert len(chunks) > 1
    assert all(c.text.strip() for c in chunks)


def test_chunk_text_deduplicates_identical_chunks():
    text = "Alpha beta gamma.\n\nAlpha beta gamma.\n\nAlpha beta gamma."
    chunks = chunk_text(
        text,
        max_chunk_chars=20,
        overlap_chars=0,
        min_chunk_chars=5,
        metadata_base={"source": "dup.txt", "doc_id": 1},
    )
    assert len(chunks) == 1
    assert chunks[0].metadata["chunk_count"] == 1


def test_chunk_text_adds_section_breadcrumb_metadata():
    text = (
        "# Employee Handbook\n\n"
        "PTO policy requires manager approval for extended leave.\n\n"
        "## Exceptions\n\n"
        "Refund requests above 500 dollars require director approval."
    )
    chunks = chunk_text(
        text,
        max_chunk_chars=120,
        overlap_chars=40,
        overlap_sentences=1,
        min_chunk_chars=30,
        metadata_base={"source": "handbook.md", "doc_id": 2},
    )
    assert chunks
    all_paths = []
    for chunk in chunks:
        all_paths.extend(chunk.metadata.get("section_paths") or [])
    assert "Employee Handbook" in all_paths
    assert any("Exceptions" in path for path in all_paths)
    assert any(c.metadata.get("section_title") == "Exceptions" for c in chunks)


def test_chunk_text_sentence_level_overlap():
    text = (
        "Alpha policy paragraph explains baseline rules for approvals and handoffs. "
        "Beta policy sentence explains exceptions for high-value refund cases. "
        "Gamma policy sentence explains escalations and final authorization."
    )
    chunks = chunk_text(
        text,
        max_chunk_chars=95,
        overlap_chars=220,
        overlap_sentences=1,
        min_chunk_chars=45,
    )
    assert len(chunks) >= 2
    sentence_re = re.compile(r"(?<=[.!?])\s+")
    overlaps = 0
    for prev, curr in zip(chunks, chunks[1:]):
        prev_sentences = {s.strip() for s in sentence_re.split(prev.text) if s.strip()}
        curr_sentences = {s.strip() for s in sentence_re.split(curr.text) if s.strip()}
        if prev_sentences & curr_sentences:
            overlaps += 1
    assert overlaps >= 1
