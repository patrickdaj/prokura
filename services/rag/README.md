Prokura RAG retriever (M5) — authorization-filtered retrieval (SPEC.md Flow D).

Validates an `aud=rag-server` token (F2 defense), derives the end user, embeds the
query, pulls top-K candidates from pgvector, then authorizes them against OpenFGA
**as the end user** — only chunks the user may view reach the answer. See
`../../deploy/rag/` for the seeded Drive-shaped corpus and `embedder.py` for the
offline demo embedder (with its real-model swap point).
