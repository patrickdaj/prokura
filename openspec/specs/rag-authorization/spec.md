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
At query time the retriever SHALL authorize candidate chunks against OpenFGA **as the end user** (`batch_check` or `list_objects` pre-filter), never as the agent principal. Only authorized chunks reach the LLM context. The user identity MUST be threaded through every retrieval call.

#### Scenario: Unauthorized top hit suppressed
- **WHEN** the vector store returns a document as the top-ranked hit and the querying user holds no `viewer` tuple for it
- **THEN** no content from that document appears in the LLM context or in any agent answer

#### Scenario: Agent identity is insufficient
- **WHEN** a retrieval is attempted with only agent credentials and no end-user identity
- **THEN** the retriever refuses to return any chunks

### Requirement: Adversarial leakage test
The test suite SHALL include an adversarial case proving non-leakage: a corpus seeded so an unauthorized document is the best embedding match for a crafted query, asserting the answer contains none of its content.

#### Scenario: Adversarial query
- **WHEN** the adversarial test issues a query engineered to surface a document its user cannot view
- **THEN** the assertion that no protected content appears in the response passes

### Requirement: Demo corpus mirrors an external ACL source
The demo corpus SHALL derive its FGA tuples from a real external permission source — Google Drive file permissions (Q6) — so the demo shows real-world ACLs being enforced, not synthetic ones. (Implementation lands in a later change; this requirement fixes the design direction.)

#### Scenario: Drive permissions reflected
- **WHEN** a Drive file shared with user A but not user B is ingested
- **THEN** user A's queries can retrieve it and user B's queries cannot
