# Product Overview

- **Product name:** Ragnetic  
- **Type:** Open-source, self-hosted RAG platform  
- **License:** Apache 2.0  

## Target Users

1. **Engineering teams** that want a self-hosted AI knowledge base with API access.  
2. **Non-technical business users** who want to chat with internal documents.  
3. **IT/DevOps teams** deploying and managing the platform at enterprise scale.

## Product Summary

Ragnetic provides a single deployable stack (Docker Compose) that includes:

- Document ingestion (upload and connectors) with semantic-aware chunking  
- Hybrid retrieval (vector + BM25) and reranking  
- Chat over your data with source attribution and citation enforcement  
- Knowledge base–scoped access control and audit logging  
- Optional local LLM and embeddings (Ollama, sentence-transformers)

All data stays within your deployment boundary unless you explicitly configure external APIs.
