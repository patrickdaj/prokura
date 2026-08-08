# Prokura RAG retriever (M5)

Authorization-**filtered** retrieval (Flow D). A FastAPI resource server (`aud=rag-server`,
the F2 defense) that owns a pgvector store and authorizes candidate chunks **as the end
user** against OpenFGA — never as the agent principal. This is the confused-deputy defense
made concrete: an agent retrieves only the documents the querying user is entitled to see.

## Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `GET`  | `/healthz` | liveness |
| `POST` | `/rag/search` | embed query → pgvector top-K → OpenFGA `batch_check` as the user → authorized chunks + answer |

## How a search is authorized

1. **Validate the token** — JWKS + `aud=rag-server`; derive the acting user from
   `preferred_username`.
2. **Retrieve** — embed the query and pull the top-K candidate chunks from pgvector
   (`RAG_TOP_K`, default 5). Retrieval is permission-blind, so a protected doc can rank #1.
3. **Filter as the user** — one OpenFGA `batch_check` for `user:{name} viewer document:{id}`
   across the candidates; only chunks the user may view survive and reach the answer. The
   response reports `candidates` vs `allowed`, so filtering is observable.

Because the check is `user:{name}` (not the agent), the same top hit reaches the one viewer
and no one else — the adversarial leakage proof in the Flow D walkthrough.

## Corpus & ingestion

At startup, ingestion reads the **Drive-shaped manifest** (`deploy/rag/manifest.json`) and
writes each document's `owner`/`viewer` tuples to OpenFGA, then embeds the corpus
(`deploy/rag/corpus/`) into pgvector. `embedder.py` is an offline deterministic demo embedder
with a documented real-model swap point (ADR-0020); pgvector lives in the existing Postgres,
no new vector container (ADR-0019). Drive-shaped ACLs: ADR-0015.

> Note: tuple-writing is currently coupled to the seed step, so it is skipped when the vector
> store is already populated — see the "RAG tuple reconciliation on startup" item in
> `docs/architecture.md` § Roadmap.

## Configuration

Key env (see `config.py`): `KEYCLOAK_URL`, `PROKURA_REALM`, `RAG_AUDIENCE` (`rag-server`),
`OPENFGA_URL` + `FGA_STORE_NAME`, `DATABASE_URL`, `RAG_CORPUS_DIR`, `RAG_MANIFEST_PATH`,
`RAG_TOP_K`.

Port **8150**. Born instrumented — traceparent join key + `prokura.correlation_id`, realtime
`rag_audit` to Loki (the audit lines the postmortem walkthrough reconstructs).
