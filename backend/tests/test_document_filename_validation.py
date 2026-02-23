import pytest
from fastapi import HTTPException

from app.api import routes


def test_normalize_document_filename_trims():
    assert routes._normalize_document_filename("  handbook.pdf  ") == "handbook.pdf"


def test_normalize_document_filename_rejects_empty():
    with pytest.raises(HTTPException):
        routes._normalize_document_filename("   ")


def test_normalize_document_filename_rejects_too_long():
    with pytest.raises(HTTPException):
        routes._normalize_document_filename("a" * 513)


def test_document_filename_key_is_case_insensitive():
    assert routes._document_filename_key(" Report.PDF ") == "report.pdf"
