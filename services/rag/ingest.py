"""Ingestion (Flow D step 1): seed the Drive-shaped corpus into OpenFGA + pgvector.

For each document in the manifest, ingestion (a) writes its ``owner`` / ``viewer``
tuples to OpenFGA, THEN (b) embeds its chunks into pgvector — in that order, so a
document is never queryable before its ACL exists ("tuples precede queryability").
A document with no tuples is retrievable by no one.

M7: tuple sync is DECOUPLED from the vector-seed guard. Every startup reconciles
the manifest against the FGA store (read what exists, write what's missing —
idempotent), regardless of whether pgvector already holds chunks. Before this, a
store reset after first ingest left every document silently filtered: chunks
present, tuples gone, and the seed guard skipped the re-write.
"""

import json
import os

import config
import db
import fga
from embedder import embed
from prokura_telemetry import tracer

_log_prefix = "rag_ingest"


def _manifest() -> list[dict]:
    with open(config.MANIFEST_PATH) as f:
        return json.load(f).get("documents", [])


def _chunks(text: str) -> list[str]:
    """Split a document into chunks on blank lines (demo-grade). Each non-empty
    paragraph becomes one embedded chunk; authorization is per-document regardless."""
    parts = [p.strip() for p in text.split("\n\n")]
    return [p for p in parts if p] or [text.strip()]


def sync_tuples() -> int:
    """Reconcile manifest ACLs into OpenFGA: write any missing owner/viewer
    tuple. Runs every startup; a no-op when the store already matches."""
    written = 0
    with tracer().start_as_current_span("rag.tuple_sync") as span:
        for d in _manifest():
            missing = (fga.expected_tuples(d["doc_id"], d["owner"], d.get("viewers", []))
                       - fga.read_object_tuples(d["doc_id"]))
            fga.write_missing_tuples(d["doc_id"], missing)
            written += len(missing)
        span.set_attribute("prokura.rag.tuples_written", written)
    print(f"{_log_prefix}: tuple reconciliation wrote {written} missing tuple(s)",
          flush=True)
    return written


def seed_vectors() -> dict:
    """Embed the whole corpus into pgvector. ACL tuples are reconciled by
    sync_tuples() BEFORE this runs (tuples precede queryability)."""
    seeded = []
    with tracer().start_as_current_span("rag.ingest") as span:
        for d in _manifest():
            path = os.path.join(config.CORPUS_DIR, d["file"])
            with open(path) as cf:
                text = cf.read()
            n = 0
            for chunk in _chunks(text):
                db.insert_chunk(d["doc_id"], chunk, embed(chunk))
                n += 1
            seeded.append({"doc_id": d["doc_id"], "owner": d["owner"],
                           "viewers": d.get("viewers", []), "chunks": n})
        span.set_attribute("prokura.rag.docs", len(seeded))
    print(f"{_log_prefix}: seeded {len(seeded)} documents "
          f"({sum(s['chunks'] for s in seeded)} chunks)", flush=True)
    return {"documents": seeded}


def ingest_if_needed() -> None:
    """Startup path: ALWAYS reconcile tuples; embed only when the vector store
    is empty (warm restarts keep their chunks; ``down -v`` triggers a re-seed)."""
    sync_tuples()
    if db.has_chunks():
        print(f"{_log_prefix}: vector store already populated — skipping seed", flush=True)
        return
    seed_vectors()


def ingest_all() -> dict:
    """(Re)seed everything — tuples first, then vectors (test/utility path)."""
    sync_tuples()
    return seed_vectors()
