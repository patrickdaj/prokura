# ADR-0020: A local, offline, deterministic embedder for RAG (demo-grade)

- **Status:** accepted
- **Source of truth:** `openspec/changes/archive/2026-08-07-add-rag-authorization/design.md`; `services/rag/embedder.py`

## Context

RAG needs embeddings. A hosted embedding API adds a secret and breaks offline reproducibility; a bundled semantic model is heavier and non-deterministic across versions.

## Decision

Use a **local, offline, deterministic** hashing embedder (no API, no secret) so the demo runs offline and the adversarial 'protected doc is the top hit' case reproduces byte-for-byte. Explicitly demo-grade — the property under test is *authorization*, which a lexical embedder proves as well as a semantic one; the real-model swap point is a documented one-function change.

## Alternatives considered

- A bundled MiniLM model: heavier image, non-deterministic across versions.
- A hosted embedding API: violates the offline/no-secret ethos.

## Consequences

The adversarial leakage test is reproducible and offline. Stated plainly in the spec, README, and `embedder.py`.

