# rag-authorization — delta (close-correct-party-gaps / M7)

## MODIFIED Requirements

### Requirement: Documents carry FGA tuples at ingestion
Every document ingested into the RAG corpus SHALL have owner/viewer tuples
written to OpenFGA at ingestion time (e.g., `document:readme viewer
user:patrick`). A document with no tuples is visible to no one. Tuple writes
SHALL be reconciled on every service startup independently of the vector-store
seed guard: on startup the retriever compares the manifest's expected tuples
against the OpenFGA store and idempotently writes any that are missing, so an
OpenFGA store reset after first ingest cannot leave documents silently
unreadable.

#### Scenario: Ingestion writes tuples
- **WHEN** a document is ingested with a declared owner and viewer set
- **THEN** corresponding tuples exist in OpenFGA before the document is queryable

#### Scenario: Store reset self-heals on startup
- **WHEN** the OpenFGA store is reset after the corpus was ingested and the RAG
  service restarts
- **THEN** the manifest's owner/viewer tuples are re-written on startup and a
  previously-authorized user's query returns their documents again, with no
  re-ingestion of vectors
