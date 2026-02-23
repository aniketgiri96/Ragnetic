import pytest
from fastapi import HTTPException

from app.api import routes
from app.services.audit import parse_details


def test_chat_quality_signals_empty_sources_low_confidence():
    quality = routes._chat_quality_signals([])
    assert quality["confidence_score"] == 0.0
    assert quality["low_confidence"] is True


def test_enforce_citation_format_appends_when_missing(monkeypatch):
    monkeypatch.setattr(routes.settings, "chat_enforce_citation_format", True)
    out = routes._enforce_citation_format("The policy allows 20 days of PTO.", [{"snippet": "policy", "score": 0.7}])
    assert "Citations:" in out
    assert "[Source 1]" in out


def test_enforce_citation_format_keeps_existing(monkeypatch):
    monkeypatch.setattr(routes.settings, "chat_enforce_citation_format", True)
    out = routes._enforce_citation_format("PTO is 20 days [Source 1].", [{"snippet": "policy", "score": 0.7}])
    assert out == "PTO is 20 days [Source 1]."


def test_normalize_kb_name_rejects_empty():
    with pytest.raises(HTTPException):
        routes._normalize_kb_name("   ")


def test_parse_details_handles_invalid_json():
    assert parse_details('{"a":1}') == {"a": 1}
    assert parse_details("not-json") == {"raw": "not-json"}
