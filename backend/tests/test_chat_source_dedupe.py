from app.api import routes


def test_dedupe_sources_for_chat_keeps_unique_documents(monkeypatch):
    monkeypatch.setattr(routes.settings, "chat_unique_sources_per_document", True)
    sources = [
        {"snippet": "A1", "metadata": {"doc_id": 10}, "score": 0.9},
        {"snippet": "A2", "metadata": {"doc_id": 10}, "score": 0.8},
        {"snippet": "B1", "metadata": {"doc_id": 11}, "score": 0.7},
    ]
    out = routes._dedupe_sources_for_chat(sources, limit=5)
    assert len(out) == 2
    assert out[0]["metadata"]["doc_id"] == 10
    assert out[1]["metadata"]["doc_id"] == 11


def test_dedupe_sources_for_chat_can_be_disabled(monkeypatch):
    monkeypatch.setattr(routes.settings, "chat_unique_sources_per_document", False)
    sources = [
        {"snippet": "A1", "metadata": {"doc_id": 10}, "score": 0.9},
        {"snippet": "A2", "metadata": {"doc_id": 10}, "score": 0.8},
    ]
    out = routes._dedupe_sources_for_chat(sources, limit=5)
    assert len(out) == 2
