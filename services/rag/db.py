"""RAG vector store: pgvector in the existing Postgres (no new container).

Enables the ``vector`` extension and owns the ``rag_chunk`` table. Tables are
created idempotently at startup (no migration framework for v0; the stack is
clean-slate ``down -v && up``). Requires a pgvector-enabled Postgres image
(``pgvector/pgvector:pg17`` — the stock ``postgres:*-alpine`` does NOT bundle the
extension; the M5 spike proved this)."""

import psycopg

import config
from embedder import DIM, to_pgvector
from telemetry import tracer

_DDL = f"""
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS rag_chunk (
    id         bigserial     PRIMARY KEY,
    doc_id     text          NOT NULL,
    chunk      text          NOT NULL,
    embedding  vector({DIM}) NOT NULL
);
"""


def connect() -> psycopg.Connection:
    return psycopg.connect(config.DATABASE_URL, autocommit=True)


def init_db() -> None:
    with connect() as conn:
        conn.execute(_DDL)


def has_chunks() -> bool:
    with connect() as conn:
        row = conn.execute("SELECT 1 FROM rag_chunk LIMIT 1").fetchone()
    return row is not None


def clear_chunks() -> None:
    with connect() as conn:
        conn.execute("TRUNCATE rag_chunk")


def insert_chunk(doc_id: str, chunk: str, embedding: list[float]) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO rag_chunk (doc_id, chunk, embedding) VALUES (%s, %s, %s)",
            (doc_id, chunk, to_pgvector(embedding)),
        )


def top_k(query_embedding: list[float], k: int) -> list[dict]:
    """Return the ``k`` nearest chunks by cosine distance, closest first.

    Ordering is done in pgvector (``<=>``); this is the candidate set that is then
    authorized as the end user — the authorization decision happens AFTER retrieval,
    exactly as Flow D specifies."""
    q = to_pgvector(query_embedding)
    with tracer().start_as_current_span("pgvector.top_k") as span:
        span.set_attribute("prokura.rag.k", k)
        with connect() as conn:
            rows = conn.execute(
                "SELECT doc_id, chunk, 1 - (embedding <=> %s) AS similarity "
                "FROM rag_chunk ORDER BY embedding <=> %s LIMIT %s",
                (q, q, k),
            ).fetchall()
    return [{"doc_id": r[0], "chunk": r[1], "similarity": float(r[2])} for r in rows]
