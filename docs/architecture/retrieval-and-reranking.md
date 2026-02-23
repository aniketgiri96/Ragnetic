# Retrieval and Reranking

## Current Implementation

- **Hybrid retrieval:** Dense vector search (Qdrant cosine) plus sparse lexical scoring (in-process BM25 over a bounded corpus snapshot).
- **Query expansion:** Original query plus lexical variants and optional HyDE synthetic passage are fused into a single retrieval pass.
- **Fusion:** Dense and sparse ranks are merged with Reciprocal Rank Fusion (RRF).
- **Optional reranking:** Top-N fused candidates can be reranked with a local cross-encoder (`cross-encoder/ms-marco-MiniLM-L-6-v2`) when enabled and available.
- **Collection model:** One Qdrant collection per knowledge base and embedding version (`ragnetic_kb{id}_{version}`) with KB-scoped active-version routing.
- **Search API:** `GET /search/?query=...&kb_id=...` returns snippet, fused score, dense score, sparse score, and metadata.

## Configurable Parameters

- `RETRIEVAL_TOP_K` (default `5`)
- `RETRIEVAL_DENSE_LIMIT` (default `20`)
- `RETRIEVAL_SPARSE_POOL` (default `240`)
- `RETRIEVAL_RERANK_TOP_N` (default `8`)
- `RETRIEVAL_ENABLE_CROSS_ENCODER` (default `false`)
- `RETRIEVAL_ENABLE_QUERY_EXPANSION` (default `true`)
- `RETRIEVAL_QUERY_EXPANSION_MAX_VARIANTS` (default `4`)
- `RETRIEVAL_ENABLE_HYDE` (default `false`)

## Context Assembly

- **Adaptive token budgeting:** Context assembly estimates token usage and keeps retrieved evidence within a configurable budget (`CHAT_MODEL_CONTEXT_TOKENS`, `CHAT_CONTEXT_BUDGET_RATIO`, `CHAT_CONTEXT_RESERVED_TOKENS`).
- **Relevance-weighted ordering:** Retrieved chunks are reordered to place high-signal evidence near the beginning and end of the prompt (lost-in-the-middle mitigation).
- **Optional compression:** Long snippets are compressed using query-overlap sentence scoring (`CHAT_CONTEXT_COMPRESSION_ENABLED`, `CHAT_CONTEXT_COMPRESSION_TARGET_RATIO`) before final packing.
- **Per-source and source-count caps:** `CHAT_CONTEXT_MAX_SOURCES`, `CHAT_CONTEXT_MAX_TOKENS_PER_SOURCE`, `CHAT_CONTEXT_MIN_TOKENS_PER_SOURCE`, and `CHAT_CONTEXT_MAX_CHARS_PER_SOURCE` bound final context size.
- **History inclusion:** Last up to 10 messages from the same session are included for continuity.
