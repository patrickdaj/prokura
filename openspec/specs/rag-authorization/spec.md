# rag-authorization

## Purpose

FGA-filtered retrieval evaluated as the end user (SPEC.md Flow D; §11 confused-deputy trade-off; corpus direction per Q6).

## Requirements

### Requirement: Documents carry FGA tuples at ingestion
Every document ingested into the RAG corpus SHALL have owner/viewer tuples written to OpenFGA at ingestion time (e.g., `document:readme viewer user:patrick`). A document with no tuples is visible to no one.

#### Scenario: Ingestion writes tuples
- **WHEN** a document is ingested with a declared owner and viewer set
- **THEN** corresponding tuples exist in OpenFGA before the document is queryable

### Requirement: Retrieval filters as the end user

At query time the retriever SHALL authorize candidate chunks against OpenFGA **as
the end user** (`batch_check` or `list_objects` pre-filter), never as the agent
principal. Only authorized chunks reach the LLM context. The user identity MUST be
threaded through every retrieval call. The end-user identity SHALL be derived from a
**validated access token addressed to the retriever's own audience** (obtained via
RFC 8693 token exchange, per SPEC-REVIEW F2 — the retriever rejects a token whose
`aud` is not itself), never from an unauthenticated caller-supplied identifier; the
FGA subject is `user:{sub}` from that token.

#### Scenario: Unauthorized top hit suppressed
- **WHEN** the vector store returns a document as the top-ranked hit and the
  querying user holds no `viewer` tuple for it
- **THEN** no content from that document appears in the LLM context or in any agent
  answer

#### Scenario: Agent identity is insufficient
- **WHEN** a retrieval is attempted with only agent credentials and no end-user
  identity
- **THEN** the retriever refuses to return any chunks

#### Scenario: Retrieval authorizes as the token subject
- **WHEN** the retriever receives a query with an access token whose `aud` is the
  retriever and whose `sub` is the end user
- **THEN** the OpenFGA `batch_check` is evaluated with subject `user:{sub}`, and a
  token addressed to a different audience is refused

### Requirement: Adversarial leakage test
The test suite SHALL include an adversarial case proving non-leakage: a corpus seeded so an unauthorized document is the best embedding match for a crafted query, asserting the answer contains none of its content.

#### Scenario: Adversarial query
- **WHEN** the adversarial test issues a query engineered to surface a document its user cannot view
- **THEN** the assertion that no protected content appears in the response passes

### Requirement: Demo corpus mirrors an external ACL source

The demo corpus SHALL derive its FGA tuples from a permission source shaped like a
real external one — **Google Drive file permissions (Q6)** — so the demo enforces
real-world-shaped ACLs, not arbitrary synthetic ones. In v0 the corpus is ingested
from a **Drive-shaped manifest** (per-document `owner` / `viewer` sets mirroring the
structure of a Google Drive permissions export), and the FGA-as-end-user retrieval
filter SHALL be **identical** to the eventual live path — only the tuple *source*
differs. Live Drive-API ingestion (pulling real file permissions via the broker's
Google grant) is deferred to a later change; this requirement fixes the design
direction and the v0/v1 boundary.

#### Scenario: Drive permissions reflected
- **WHEN** a file shared with user A but not user B is ingested (its manifest entry
  lists A as viewer, not B)
- **THEN** user A's queries can retrieve it and user B's queries cannot

#### Scenario: Manifest and live path share one filter
- **WHEN** the v0 manifest-sourced tuples and a future Drive-API-sourced tuple set
  describe the same sharing
- **THEN** the retrieval authorization path evaluating them is the same code, so the
  v1 Drive integration changes only ingestion, not enforcement

### Requirement: Retrieval is exposed as an MCP tool

FGA-filtered retrieval SHALL be reachable through the MCP surface as a `rag_search`
tool, so the demo threads the end-user identity from the validated inbound MCP token
through to the OpenFGA check on the same surface as the other gated tools. The MCP
tool MUST NOT forward the inbound token verbatim to the retriever; it exchanges for
the retriever's audience first (consistent with the M4 no-passthrough rule), and the
`sub` carried through remains the end user.

#### Scenario: RAG through MCP preserves the end user
- **WHEN** an MCP client calls `rag_search` with a valid user-delegated token
- **THEN** the retriever authorizes as that end user's `sub`, returns only that
  user's authorized chunks, and the inbound MCP token is not forwarded downstream

### Requirement: Offline, reproducible corpus and vector store

Embeddings SHALL be computed by a **local, offline** embedder — no embedding API, no
network call, no API key or secret — so the demo runs offline and the adversarial
leakage case reproduces deterministically. The vector store SHALL be **pgvector in
the existing Postgres instance**, adding no new container. Ingestion SHALL write a
document's FGA tuples **before** the document is queryable; a document with no tuples
is retrievable by no one.

#### Scenario: Runs offline and reproducibly
- **WHEN** the corpus is ingested and the adversarial query is run with no outbound
  network access
- **THEN** ingestion, embedding, and retrieval all succeed and the same protected
  document is the top embedding hit on every run

#### Scenario: Tuples precede queryability
- **WHEN** a document has been embedded but its FGA tuples have not yet been written
- **THEN** it is returned to no user until its tuples exist
