import pytest
from fastapi import HTTPException

from app.api import routes


def test_retrieve_for_chat_returns_sources(monkeypatch):
    def _fake_hybrid_retrieve(kb_id: int, query: str, top_k: int):
        assert kb_id == 7
        assert query == "pto policy"
        assert top_k == 3
        return [
            {
                "snippet": "PTO policy text",
                "metadata": {"source": "handbook.pdf"},
                "score": 0.88,
            }
        ]

    monkeypatch.setattr(routes, "hybrid_retrieve", _fake_hybrid_retrieve)
    out = routes._retrieve_for_chat(kb_id=7, query="pto policy", limit=3)
    assert out == [
        {
            "snippet": "PTO policy text",
            "metadata": {"source": "handbook.pdf"},
            "score": 0.88,
        }
    ]


def test_retrieve_for_chat_raises_http_503_when_backend_fails(monkeypatch):
    def _boom(*args, **kwargs):
        raise RuntimeError("qdrant unavailable")

    monkeypatch.setattr(routes, "hybrid_retrieve", _boom)

    with pytest.raises(HTTPException) as exc:
        routes._retrieve_for_chat(kb_id=1, query="hello")
    assert exc.value.status_code == 503
    assert "Retrieval backend unavailable" in str(exc.value.detail)
