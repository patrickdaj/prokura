"""Ingestion (Flow D step 1): seed the Drive-shaped corpus into OpenFGA + pgvector.

For each document in the manifest, ingestion (a) writes its ``owner`` / ``viewer``
tuples to OpenFGA, THEN (b) embeds its chunks into pgvector — in that order, so a
document is never queryable before its ACL exists ("tuples precede queryability").
A document with no tuples is retrievable by no one.

Runs at service startup and is idempotent: if the vector store already holds chunks
(a warm restart), it is a no-op; a clean-slate ``down -v && up`` re-seeds from
scratch. The v1 Drive path replaces only step (a)'s SOURCE (a live pull of file
permissions via the broker's Google grant); the retrieval filter is untouched.
"""

import json
import os

import config
import db
import fga
from embedder import embed
from telemetry import tracer

_log_prefix = "rag_ingest"


def _chunks(text: str) -> list[str]:
    """Split a document into chunks on blank lines (demo-grade). Each non-empty
    paragraph becomes one embedded chunk; authorization is per-document regardless."""
    parts = [p.strip() for p in text.split("\n\n")]
    return [p for p in parts if p] or [text.strip()]


def ingest_all() -> dict:
    """(Re)seed the whole corpus. Returns a summary for logging/verification."""
    with open(config.MANIFEST_PATH) as f:
        manifest = json.load(f)
    docs = manifest.get("documents", [])
    seeded = []
    with tracer().start_as_current_span("rag.ingest") as span:
        for d in docs:
            doc_id, owner = d["doc_id"], d["owner"]
            viewers = d.get("viewers", [])
            # (a) ACL first — the document is not queryable until its tuples exist.
            fga.write_document_tuples(doc_id, owner, viewers)
            # (b) then embed the chunks into pgvector.
            path = os.path.join(config.CORPUS_DIR, d["file"])
            with open(path) as cf:
                text = cf.read()
            n = 0
            for chunk in _chunks(text):
                db.insert_chunk(doc_id, chunk, embed(chunk))
                n += 1
            seeded.append({"doc_id": doc_id, "owner": owner,
                           "viewers": viewers, "chunks": n})
        span.set_attribute("prokura.rag.docs", len(seeded))
    print(f"{_log_prefix}: seeded {len(seeded)} documents "
          f"({sum(s['chunks'] for s in seeded)} chunks)", flush=True)
    return {"documents": seeded}


def ingest_if_needed() -> None:
    """Seed once. On a warm restart (chunks already present) this is a no-op; a
    clean-slate ``down -v`` empties the store and triggers a fresh seed."""
    if db.has_chunks():
        print(f"{_log_prefix}: vector store already populated — skipping seed", flush=True)
        return
    ingest_all()
