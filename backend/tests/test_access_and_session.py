import pytest
from fastapi import HTTPException

from app.api.routes import _normalize_session_id
from app.models.document import KnowledgeBaseRole
from app.services.access import _role_at_least


def test_role_hierarchy():
    assert _role_at_least(KnowledgeBaseRole.OWNER, KnowledgeBaseRole.VIEWER) is True
    assert _role_at_least(KnowledgeBaseRole.EDITOR, KnowledgeBaseRole.VIEWER) is True
    assert _role_at_least(KnowledgeBaseRole.VIEWER, KnowledgeBaseRole.EDITOR) is False


def test_normalize_session_id_accepts_valid():
    assert _normalize_session_id("session-1.test_A:42") == "session-1.test_A:42"
    generated = _normalize_session_id(None)
    assert isinstance(generated, str)
    assert len(generated) >= 8


def test_normalize_session_id_rejects_invalid():
    with pytest.raises(HTTPException):
        _normalize_session_id("bad id with spaces")
