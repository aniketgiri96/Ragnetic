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
