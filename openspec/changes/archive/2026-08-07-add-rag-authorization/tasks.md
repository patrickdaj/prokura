# Tasks: add-rag-authorization (M5)

Spike-first, mirroring M0/M2/M3/M4. The build is grounded in the running stack — the
adversarial "top hit" and the pgvector/embedder choices are proven before the service
is written, and findings are recorded in design.md "To be resolved by the M5 spike".

## 1. Spike — pgvector + offline embedder + FGA-as-user filter

- [x] 1.1 Verify pgvector in the running Postgres image: `CREATE EXTENSION vector`, a
  `vector` column, and a cosine-distance top-K query all work (or switch to a
  pgvector-enabled image tag). Record in design.
- [x] 1.2 Prove the local deterministic embedder + a seeded corpus makes a chosen
  **protected** doc the top hit for a crafted query — offline and byte-reproducible
  across runs. Spike script in scratchpad; move under `spike/rag/` in the build.
- [x] 1.3 Prove an OpenFGA `batch_check` for `document:{id} viewer user:{sub}` over
  the candidate set filters that doc out for a non-viewer and keeps it for a viewer
  (model unchanged — `type document` already ships).
- [x] 1.4 Confirm an `mcp-server → aud=rag-server` RFC 8693 exchange preserves `sub`
  (re-confirm the M4 finding for the new audience). Record all findings in design.md.

## 2. Keycloak audience scaffolding (identity threading)

- [x] 2.1 Add a bearer-capable `rag-server` resource client to `realm-export.json`,
  mirroring `tools-api` / `token-broker` (service account so it can be an exchange
  subject if needed; it is the resource audience target).
- [x] 2.2 Grant `mcp-server` standard token-exchange permission for `aud=rag-server`
  (`standard.token.exchange.enabled`), so `rag_search` can exchange the inbound token.
  Verify a DCR'd → mcp → rag token carries `aud=rag-server` and `sub`=user.

## 3. RAG service (`services/rag/`, port 8150)

- [x] 3.1 Scaffold `services/rag/` mirroring `services/token-broker/` (FastAPI, OTel
  fire-and-forget, `GET /healthz`, compose service on 8150, **no depends_on: lgtm**).
  Confirm fire-and-forget: suite green with lgtm stopped.
- [x] 3.2 Postgres/pgvector init: `CREATE EXTENSION vector` and a
  `rag_chunk(doc_id, chunk, embedding)` table (compose init or migration).
- [x] 3.3 Local offline embedder module (deterministic; no network/secret) with the
  real-model swap point documented in a docstring.
- [x] 3.4 Token validation: accept only a token whose `aud` is `rag-server`; derive
  the FGA subject `user:{sub}`; refuse a missing/foreign-audience token with no chunks.

## 4. Ingestion (Flow D step 1)

- [x] 4.1 Seeded corpus under `deploy/rag/corpus/` + a Drive-shaped `manifest.json`
  (`{doc_id, owner, viewers[]}`), including an owner-only doc, a per-user-shared doc,
  and a `user:*` public doc for coverage.
- [x] 4.2 Ingestion writes `document:{id} owner/viewer` tuples to OpenFGA **before**
  embedding the doc's chunks into pgvector; a doc with no tuples is queryable by none.
- [x] 4.3 Seed the adversarial doc: a protected doc (viewer = alice only) authored to
  be the top embedding hit for the crafted query from 1.2.

## 5. Retrieval + MCP tool (Flow D steps 2–3)

- [x] 5.1 `POST /rag/search`: embed query → pgvector top-K → OpenFGA `batch_check` as
  `user:{sub}` → return only authorized chunks (+ demo answer). `rag_audit` log line
  (correlation id, sub, candidate/allowed counts — never content).
- [x] 5.2 `rag_search` MCP tool in `services/mcp/tools.py`: exchanges the inbound
  token for `aud=rag-server` (no passthrough), calls `/rag/search`, returns the
  authorized result. `tools/list` advertises it.

## 6. Tests (drive the live stack)

- [x] 6.1 `test_rag_authorization.py`: authorized user retrieves a protected doc;
  unauthorized user does not; a foreign-audience / no-identity call returns no chunks.
- [x] 6.2 **Adversarial leakage** test: the protected doc is the top embedding hit for
  the crafted query; assert none of its content appears in the unauthorized user's
  answer, and that the authorized user does retrieve it.
- [x] 6.3 `rag_search` through MCP: end-user `sub` preserved, only that user's chunks
  returned, inbound MCP token not forwarded downstream.

## 7. Verify + wrap

- [x] 7.1 Add a RAG row to the Grafana dashboard (retrieval count stat + live
  `rag_audit` logs); confirm rendering in a real browser (screenshot).
- [x] 7.2 Drive the full flow and **look**: through MCP `rag_search`, alice retrieves
  the protected doc and bob provably cannot — even as the top hit. Verify one linked
  trace `mcp → rag → openfga` under the correlation id in Tempo, matching live
  `rag_audit` in Loki.
- [x] 7.3 `docs/threat-model.md`: add the "RAG authorization (Flow D, M5)" section —
  FGA-as-end-user confused-deputy defense, ingestion tuple-writer trust, demo-grade
  embedder, and the parked-live-Drive residual.
- [x] 7.4 Clean-slate `down -v && up` reproduces the milestone; full smoke suite green
  (with lgtm up and with lgtm stopped, per the M4 baseline). Write the M5 blog page
  (`docs/blog/m5-rag-authorization.html`) with its flow diagram; verify rendering.
  Archive is the next action (`/opsx:archive`).
