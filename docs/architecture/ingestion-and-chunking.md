# Ingestion and Chunking

## Overview

Ragnetic ingests documents asynchronously via a Celery pipeline: upload → object store → DB record → parse → chunk → embed → index in Qdrant.

## Document Types and Parsers

- **PDF:** PyMuPDF (`fitz`) — text per page, metadata includes page count.
- **TXT / MD:** Decoded as UTF-8 with replacement for invalid bytes.
- **DOCX:** `python-docx` — paragraph text concatenated.

Parsers are selected by MIME type or file extension. They return plain text and optional metadata (e.g. `pages`).

## Chunking

- **Hierarchical:** Split first by paragraph (double newline), then by size.
- **Size and overlap:** Default max chunk size 800 characters, 100-character overlap to reduce boundary loss.
- **Metadata:** Each chunk carries source filename, doc id, and any parser metadata for retrieval and citation.

## Pipeline Steps

1. **Upload:** File stored in MinIO; `Document` row created with `object_key`, `content_hash`, `status=pending`.
2. **Celery task:** `ingest_document(document_id)` loads file from MinIO, parses, chunks, embeds (sentence-transformers or stub), upserts vectors into the Qdrant collection for the document’s knowledge base.
3. **Status:** Document status updated to `processing`, then `indexed` or `failed` (with `error_message`).

## Idempotency and Dedup

- `content_hash` (SHA-256) is stored and checked at upload time.
- Re-uploading identical content into the same knowledge base returns the existing `document_id` (`deduplicated=true`) instead of re-enqueueing ingestion.
