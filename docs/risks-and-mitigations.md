# Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Large player (Notion, Confluence) launches self-hosted RAG | Medium | High | Move faster on community and enterprise features; open-source moat is hard to replicate. |
| LLM API costs make self-hosting unviable | Low | Medium | Local models (Ollama) are first-class; cloud APIs optional. |
| Low community contribution rate | Medium | Medium | Invest in docs and “good first issues”; acknowledge contributors in changelogs. |
| Vector DB performance at enterprise scale | Low | High | Architecture supports Qdrant distributed mode and Elasticsearch; load-test at 10M+ vectors. |
| Security vulnerability in self-hosted deployments | Medium | High | Security-first design: rate limiting, input sanitization, dependency audits, responsible disclosure. |
| Embedding model quality regression across updates | Low | Medium | Model-versioned namespaces avoid forced re-indexing on model updates. |
