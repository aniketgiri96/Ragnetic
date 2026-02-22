from app.api import routes


def test_reasoning_event_payload_shape():
    payload = routes._reasoning_event("draft", "Drafting answer.", 1234)
    assert payload["step"] == "draft"
    assert payload["detail"] == "Drafting answer."
    assert payload["elapsed_ms"] == 1234


def test_source_previews_compact_and_bounded():
    sources = [
        {
            "score": 0.91,
            "snippet": "Policy details " * 20,
            "metadata": {"source": "policy.pdf"},
        },
        {
            "score": 0.76,
            "snippet": "Runbook steps",
            "metadata": {"filename": "runbook.md"},
        },
    ]
    previews = routes._source_previews(sources, limit=1)
    assert len(previews) == 1
    assert previews[0]["name"] == "policy.pdf"
    assert previews[0]["score"] == 0.91
    assert previews[0]["snippet_preview"].startswith("Policy details")
