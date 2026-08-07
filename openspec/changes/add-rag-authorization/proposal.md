# Proposal: add-rag-authorization (M5)

## Why

The last feature milestone, and the second demo story (SPEC.md Flow D; §11
confused-deputy trade-off; Q6 corpus direction). M1–M4 proved the *action* side of
agentic identity — delegated exchange, brokered provider tokens, human approval —
all consumable through MCP. M5 proves the *data* side: an agent retrieves only the
documents **the querying user is entitled to see**, enforced by evaluating OpenFGA
**as the end user, never as the agent** — the exact confused-deputy defense SPEC.md
§11 names as the reason user-context checks exist. It completes the headline demo's
trilogy (read GitHub issues → gated email → RAG over ACL'd docs) on the one MCP
surface built in M4.

## What Changes

- **RAG retriever service (new, `services/rag/`, port 8150).** A FastAPI service —
  born instrumented like every service since M2 — that owns document ingestion, a
  local vector store, and the authorization-filtered retrieval. It validates a
  presented access token (its own audience, via RFC 8693 exchange, the M1/F2
  defense) and derives the **end-user `sub`** from it; it never authorizes as the
  agent principal.
- **Ingestion writes FGA tuples (Flow D step 1).** Documents are ingested from a
  seeded corpus with a **Drive-shaped manifest** (per-doc `owner` / `viewer`,
  mirroring the shape of a Google Drive permissions export). Ingestion writes
  `document:{id} owner user:{x}` / `viewer user:{y}` tuples to OpenFGA **before** a
  doc is queryable, and embeds its chunks into the vector store. A document with no
  tuples is visible to no one. **No OpenFGA model change is needed** — the baseline
  model already defines `type document` with `owner` / `viewer: [user, user:*] or
  owner`.
- **Retrieval filters as the end user (Flow D steps 2–3).** `POST /rag/search`
  embeds the query, pulls top-K candidates from the vector store, then authorizes
  them against OpenFGA with `batch_check` **as `user:{sub}`** — only authorized
  chunks reach the answer. A retrieval attempted with no end-user identity is
  refused outright.
- **Retrieval exposed as an MCP tool `rag_search`.** The demo drives retrieval
  through the same MCP surface as M4's `get_provider_token` / `send_email`, so the
  end-user identity is threaded from the validated inbound token through to the FGA
  check. This makes FGA-filtered RAG a first-class part of the headline demo, not a
  side script.
- **Adversarial leakage test.** The suite includes the SPEC's central proof: a
  corpus seeded so an unauthorized document is the **top embedding match** for a
  crafted query; the assertion is that none of its content appears in the answer for
  a user who lacks the `viewer` tuple, even as the top hit — while the authorized
  user does retrieve it.
- **Offline, reproducible corpus (Q6 / project ethos).** Embeddings are computed by
  a **local, offline** embedder (no embedding API, no API key, no secret) so the
  demo runs offline and the adversarial case reproduces deterministically —
  consistent with the Mailpit-sink / `acme`-mock pattern used through M2–M4. The
  vector store is **pgvector in the existing Postgres**, adding no new container.
- **Real Drive ingestion parked to v1 (honest scoping).** The baseline requirement
  fixes Google Drive as the external ACL source; per the spec's own carve-out the
  live Drive-API ingestion (via the broker's Google grant) lands in a later change.
  M5 honors the *direction* — the seeded manifest mirrors a Drive permission export,
  and the FGA-as-user filter is identical whether tuples come from a manifest or the
  Drive API — and documents the parked work explicitly.

## Capabilities

### New Capabilities

<!-- None. rag-authorization already exists as a baseline spec. -->

### Modified Capabilities

- `rag-authorization`: a delta refining the baseline aspirational requirements into
  the built system — the retriever validates a token and authorizes as `user:{sub}`
  (not the agent); ingestion is from a Drive-shaped seeded manifest with the local
  offline embedder and pgvector named as the v0 mechanism; retrieval is exposed as
  the `rag_search` MCP tool; and the "corpus mirrors an external ACL source"
  requirement is restated to record the seeded-now / real-Drive-API-in-v1 scoping
  decision. The confused-deputy and adversarial-leakage requirements are unchanged
  in intent — the delta makes them concrete and testable against the real stack.

## Impact

- **New:** `services/rag/` (ingestion, pgvector store, offline embedder, FGA-as-user
  `batch_check` retrieval, RFC 8693 token validation, `/healthz`, OTel), a seeded
  Drive-shaped corpus + manifest under `deploy/rag/`, and the `rag-authorization`
  delta spec.
- **Modified:** `docker-compose.yml` (rag service on 8150; pgvector extension /
  Postgres init), `deploy/keycloak/realm-export.json` (a `rag-server` resource
  audience + `mcp-server` exchange permission, mirroring the `token-broker` /
  `tools-api` pattern), `services/mcp/tools.py` (new `rag_search` tool threading the
  end-user identity), the Grafana dashboard (a RAG row: retrieval count + live
  `rag_audit`), and `docs/threat-model.md` (Flow D: FGA-as-end-user confused-deputy
  defense, ingestion tuple-writer trust, the parked-Drive residual).
- **Open M5 with a light spike** (mirroring M0/M2/M3/M4): prove that pgvector in the
  existing Postgres + the offline embedder can be seeded so a chosen protected doc
  is reliably the **top hit** for a crafted query, and that an FGA `batch_check` as
  the end user filters it out — before building the service, so the adversarial test
  is grounded in the running stack, not assumed.
- **Verification (definition of done):** through the MCP `rag_search` tool, an
  authorized user retrieves a protected document and an unauthorized user provably
  does not — even when it is the top embedding hit; the adversarial test asserts
  non-leakage; the flow appears as one linked trace (`mcp → rag → openfga`) with live
  `rag_audit` in Loki; clean-slate `down -v && up` reproduces it.
