# Design: add-rag-authorization (M5)

## Context

M1–M4 built and demonstrated the *action* half of agentic identity, all reachable
through the MCP server (`services/mcp/`, port 8140): delegated exchange (M1),
brokered provider tokens with per-agent consent (M2), human approval (M3), and the
MCP authorization surface with reactive step-up (M4). The *data* half — SPEC.md
Flow D, "retrieve only documents the user is entitled to see" — is unbuilt. The
OpenFGA model already anticipates it: `type document` with `owner` and
`viewer: [user, user:*] or owner` has shipped since the v0.2 baseline, so **no model
change is required**. What is missing is a retriever that ingests a corpus, embeds
it, and — the whole point — authorizes candidate chunks **as the end user**, the
confused-deputy defense SPEC.md §11 exists to make concrete.

Constraints inherited from the project: docker-compose only, explicitly
non-production; offline-first and reproducible (the Mailpit-sink / `acme`-mock
pattern); every new service is born instrumented (traceparent propagation,
correlation IDs as span attributes); Python 3.12 / FastAPI. The corpus scope is
decided: **seeded, Drive-shaped** in v0; live Drive-API ingestion parked to v1.

## Goals / Non-Goals

**Goals:**
- Retrieval that authorizes as `user:{sub}` from a **validated** token of the
  retriever's own audience, never as the agent — the F2 confused-deputy defense.
- Ingestion that writes `document` owner/viewer tuples to OpenFGA before a doc is
  queryable, from a Drive-shaped manifest.
- The adversarial leakage proof: an unauthorized doc that is the **top embedding
  hit** never reaches an unauthorized user's answer; the authorized user does get it.
- Retrieval reachable as an MCP `rag_search` tool, completing the demo trilogy on
  one surface.
- Offline, deterministic, no new heavy container, no secrets.

**Non-Goals:**
- Live Google Drive API ingestion (v1 — this change fixes only the direction and the
  identical enforcement path).
- Retrieval quality / production-grade embeddings — the property under test is
  authorization, not recall. The embedder is demo-grade and says so.
- Group/folder-based sharing beyond what the baseline model expresses (`user`,
  `user:*` public, `owner`); a `group` type is a possible v1 model extension.
- Chunking/RAG-answer sophistication (re-ranking, citations) beyond what the leakage
  test needs.

## Decisions

### 1. RAG is its own service (`services/rag/`, port 8150), not folded into MCP

The retriever validates a token addressed to its **own audience** (`rag-server`) and
derives `sub` — the same shape as the broker and tools-api. Making it a distinct
resource server (rather than a function inside `services/mcp/`) keeps the
"authorize as the end user, refuse a foreign audience" boundary honest and testable,
and lets retrieval be driven by things other than MCP later. Next free port after
mcp's 8140 → **8150**. *Alternative considered:* a retrieval function inside the MCP
server — rejected because it would blur the audience boundary the F2 defense depends
on and make "agent identity is insufficient" untestable as a service contract.

### 2. Identity threading: `mcp-server` exchanges for `aud=rag-server`

The `rag_search` MCP tool does **not** forward the inbound MCP token. Mirroring M4's
`get_provider_token`, it performs an RFC 8693 exchange for `aud=rag-server`; the
exchange preserves `sub` (the end user) while `azp` becomes `mcp-server`. The RAG
service validates `aud=rag-server` and authorizes with `user:{sub}`. Realm config
adds a bearer-capable `rag-server` client (mirroring `token-broker` / `tools-api`)
and grants `mcp-server` the standard-exchange permission to that audience — a
one-for-one copy of an already-proven pattern in `realm-export.json`.

### 3. Vector store is pgvector in the existing Postgres

Postgres is already in compose (broker grant metadata, audit). Adding the `vector`
extension and a `rag_chunk(doc_id, chunk, embedding vector)` table avoids a new
container entirely — cheaper than a chroma sidecar and keeps the stack small.
*Alternative:* Chroma (SPEC named "chroma/pgvector") — rejected as an extra container
for no benefit at this scale. Requires the Postgres image to carry pgvector (or
`CREATE EXTENSION vector`); the spike verifies this against the running image.

### 4. Embedder is local, offline, and deterministic (demo-grade)

Embeddings come from a **local deterministic embedder** (a hashing/lexical vectorizer
over the seeded corpus, cosine similarity) — no embedding API, no model download at
build, no secret, and byte-identical results every run. This is what makes the
adversarial case *reproducible* and the whole demo runnable offline. It is explicitly
demo-grade: the property under test is authorization (non-leakage), which a lexical
embedder proves exactly as well as a semantic one, and swapping in a real
sentence-transformer is a documented one-function change. *Alternatives:* a bundled
MiniLM model (heavier image, still offline, non-deterministic across versions) or a
hosted embedding API (violates offline/no-secret ethos) — both rejected for v0.

### 5. Ingestion from a Drive-shaped manifest; tuples before queryability

A seeded corpus under `deploy/rag/corpus/` plus a `manifest.json` whose entries carry
`{doc_id, owner, viewers[]}` — the shape of a Google Drive permissions export.
Ingestion (a) writes `document:{id} owner user:{owner}` and `viewer user:{v}` tuples
to OpenFGA, then (b) embeds chunks into pgvector — in that order, so a doc is never
queryable before its ACL exists. The v1 Drive path replaces only step (a)'s *source*
(the broker's Google grant → live file permissions); the retrieval filter is
untouched.

### 6. Retrieval: candidates then `batch_check` as the end user

`POST /rag/search` → embed query → pgvector top-K → OpenFGA `batch_check` for
`document:{id} viewer user:{sub}` across the candidates → keep only allowed → return
chunks (+ a demo answer). No end-user identity (or a foreign-audience token) → refuse
with no chunks. `batch_check` over K candidates is one round trip and keeps the
authorization decision at retrieval time, as SPEC.md Flow D step 2 specifies.

### 7. Born instrumented; RAG row on the dashboard

OTel fire-and-forget like every service since M2 (no `depends_on: lgtm`);
traceparent propagates `mcp → rag → openfga`; `rag_audit` log lines carry the
correlation ID, querying `sub`, candidate count, and allowed count (never document
content). A Grafana RAG row (retrieval count + live `rag_audit`) is added and
verified by looking.

## Risks / Trade-offs

- **Embedder too weak to make the protected doc the top hit** → the spike seeds the
  corpus and authors the adversarial query against the real embedder and asserts the
  protected doc ranks #1 before the service is built; the corpus is ours to tune.
- **Confused deputy via a spoofed identity** → the retriever never trusts a
  caller-supplied user id; it derives `sub` only from a token whose `aud` it
  validates as `rag-server`. "Agent identity is insufficient" is a service-level
  test, not a convention.
- **pgvector missing from the Postgres image** → spike verifies `CREATE EXTENSION
  vector` (or switches to a pgvector-enabled image tag) before the build depends on
  it.
- **Ingestion ordering race (embedded before tuples)** → ingestion writes tuples
  first and only then makes the chunk retrievable; a "tuples precede queryability"
  scenario guards it.
- **Demo-grade embedder read as a real one** → stated plainly in the spec, README,
  and threat model; the swap point is documented.
- **Inbound token passthrough leak** → the MCP tool exchanges for `rag-server` and
  never forwards the inbound token, asserted the same way M4 asserts it for the other
  tools.

## Migration Plan

Purely additive. New `rag` service + pgvector table + a `rag-server` realm client and
exchange permission; new `rag_search` MCP tool; dashboard row. No existing behavior
changes; the OpenFGA model is unchanged. Deploy: `docker-compose up` brings up `rag`;
Postgres init enables the extension; an ingestion step (compose init or a make target)
seeds the corpus. Rollback: remove the `rag` service and the `rag_search` tool
registration — nothing else depends on it. Definition of done is a clean-slate
`down -v && up` reproducing the full flow with the adversarial test green.

## Open Questions

- Exact demo "answer" shape returned by `rag_search` (raw authorized chunks vs a
  templated stitched answer) — settle in the build; the leakage assertion is on
  content presence either way.
- Whether the seeded manifest also exercises a `user:*` (public) doc and an
  owner-only doc to show all three sharing modes — likely yes; cheap coverage.

## To be resolved by the M5 spike (before building the service)

Mirroring M0/M2/M3/M4, open M5 with a light spike and record findings here:
- pgvector available in the running Postgres image (extension creates; a `vector`
  column + cosine query works).
- The local embedder + seeded corpus makes a chosen protected doc the **top hit** for
  a crafted query, deterministically and offline.
- An OpenFGA `batch_check` as `user:{sub}` over the candidate set filters that doc out
  for a non-viewer and keeps it for a viewer.
- The `mcp-server → rag-server` RFC 8693 exchange preserves `sub` (re-confirming the
  M4 finding for the new audience).
