# Retrieval and Reranking

## Current Implementation

- **Vector search:** Query is embedded with the same model as documents; Qdrant returns top-K by cosine similarity.
- **Collection:** One Qdrant collection per knowledge base and embedding model version (`knowai_kb{id}_v1`).
- **Search API:** `GET /search/?query=...&kb_id=...` embeds the query and searches the KB’s collection; returns snippets, scores, and metadata.

## Planned (PRD)

- **Hybrid retrieval:** Dense (Qdrant) + sparse (BM25) in parallel; merge with Reciprocal Rank Fusion (RRF).
- **Reranking:** Top-20 from hybrid → cross-encoder rerank → top-5.
- **Query expansion:** Optional HyDE (hypothetical document embeddings) for vague queries.

## Context Assembly

- **Dynamic chunk selection:** Add chunks until ~75% of model context limit.
- **Ordering:** Higher-scoring chunks placed at start and end to mitigate “lost in the middle” behavior.
