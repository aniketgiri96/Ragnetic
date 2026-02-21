"""Document parsers by type. Return plain text and optional metadata (e.g. page)."""
import re
from typing import Any

# Lazy imports for optional deps
def _parse_pdf(content: bytes) -> tuple[str, dict[str, Any]]:
    try:
        import fitz  # PyMuPDF
    except ImportError:
        return _fallback_text(content), {}
    doc = fitz.open(stream=content, filetype="pdf")
    parts = []
    meta = {"pages": doc.page_count}
    for i in range(doc.page_count):
        page = doc.load_page(i)
        parts.append(page.get_text())
    doc.close()
    return "\n\n".join(parts), meta


def _parse_txt(content: bytes) -> tuple[str, dict[str, Any]]:
    text = content.decode("utf-8", errors="replace")
    return text, {}


def _parse_md(content: bytes) -> tuple[str, dict[str, Any]]:
    return _parse_txt(content)


def _parse_docx(content: bytes) -> tuple[str, dict[str, Any]]:
    try:
        from docx import Document as DocxDocument
        import io
        doc = DocxDocument(io.BytesIO(content))
        parts = [p.text for p in doc.paragraphs]
        return "\n\n".join(parts), {}
    except ImportError:
        return _fallback_text(content), {}


def _fallback_text(content: bytes) -> str:
    return content.decode("utf-8", errors="replace")


MIME_PARSERS = {
    "application/pdf": _parse_pdf,
    "text/plain": _parse_txt,
    "text/markdown": _parse_md,
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": _parse_docx,
}

EXTENSION_MAP = {
    ".pdf": "application/pdf",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def parse_document(content: bytes, filename: str, mime_type: str | None = None) -> tuple[str, dict[str, Any]]:
    """Parse document content. Returns (text, metadata)."""
    if mime_type and mime_type in MIME_PARSERS:
        return MIME_PARSERS[mime_type](content)
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    mime = EXTENSION_MAP.get(ext)
    if mime and mime in MIME_PARSERS:
        return MIME_PARSERS[mime](content)
    return _fallback_text(content), {}
