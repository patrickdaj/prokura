# ADR-0019: pgvector in the existing Postgres — no new vector container

- **Status:** accepted
- **Source of truth:** `openspec/changes/archive/2026-08-07-add-rag-authorization/design.md`; `docker-compose.yml`; `services/rag/db.py`

## Context

M5's RAG store needed a vector database. SPEC named 'chroma/pgvector'. Adding a Chroma sidecar is another container for no benefit at this scale.

## Decision

Use **pgvector in the existing Postgres** (`pgvector/pgvector:pg17`) with a `rag_chunk(doc_id, chunk, embedding)` table. The spike proved `postgres:17-alpine` lacks the extension, so the image tag switched — no new container.

## Alternatives considered

- Chroma sidecar: an extra container for no benefit at demo scale.

## Consequences

Keeps the stack small; cosine top-K verified in the spike. The authorization property under test is unaffected by the store choice.

