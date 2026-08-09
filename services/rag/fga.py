"""OpenFGA access for the RAG retriever.

Two operations, both on ``type document`` (already in the baseline model — no model
change for M5):
- ``batch_check`` — at retrieval time, authorize the candidate documents as the END
  USER (``user:{username} viewer document:{id}``) in one round trip. This is the
  confused-deputy defense: the retriever evaluates as the user, never as the agent.
- ``write_document_tuples`` — at ingestion time, write a doc's ``owner`` / ``viewer``
  tuples BEFORE its chunks are queryable (Flow D step 1).

Wrapped in OTel spans so FGA calls appear in the ``mcp -> rag -> openfga`` trace.
"""

import uuid

import httpx

import config
from telemetry import tracer

_store_id: str | None = None


def _base() -> str:
    return config.OPENFGA_URL


def store_id() -> str:
    """Discover the ``prokura`` store id by name (cached)."""
    global _store_id
    if _store_id:
        return _store_id
    r = httpx.get(f"{_base()}/stores", timeout=10.0)
    r.raise_for_status()
    for s in r.json().get("stores", []):
        if s["name"] == config.FGA_STORE_NAME:
            _store_id = s["id"]
            return _store_id
    raise RuntimeError(f"OpenFGA store {config.FGA_STORE_NAME!r} not found")


def batch_check_viewer(username: str, doc_ids: list[str]) -> dict[str, bool]:
    """For each ``doc_id``, is ``user:{username}`` a ``viewer``? One round trip.

    Returns a ``{doc_id: allowed}`` map. Uses the OpenFGA ``/batch-check`` endpoint,
    which correlates results by a per-check ``correlation_id``."""
    if not doc_ids:
        return {}
    checks = [{
        "tuple_key": {"user": f"user:{username}", "relation": "viewer",
                      "object": f"document:{d}"},
        "correlation_id": uuid.uuid4().hex,
    } for d in doc_ids]
    with tracer().start_as_current_span("fga.batch_check") as span:
        span.set_attribute("prokura.fga.relation", "viewer")
        span.set_attribute("prokura.fga.candidates", len(doc_ids))
        r = httpx.post(f"{_base()}/stores/{store_id()}/batch-check",
                       json={"checks": checks}, timeout=10.0)
        r.raise_for_status()
    result = r.json().get("result", {})
    by_corr = {cid: v.get("allowed", False) for cid, v in result.items()}
    return {d: by_corr.get(checks[i]["correlation_id"], False) for i, d in enumerate(doc_ids)}


def read_object_tuples(doc_id: str) -> set[tuple[str, str]]:
    """All stored (user, relation) tuples for one document — the reconciliation
    read (M7): what the store ACTUALLY holds, regardless of vector-seed state."""
    r = httpx.post(f"{_base()}/stores/{store_id()}/read",
                   json={"tuple_key": {"object": f"document:{doc_id}"}}, timeout=10.0)
    r.raise_for_status()
    return {(t["key"]["user"], t["key"]["relation"])
            for t in r.json().get("tuples", [])}


def expected_tuples(doc_id: str, owner: str, viewers: list[str]) -> set[tuple[str, str]]:
    keys = {(f"user:{owner}", "owner")}
    for v in viewers:
        keys.add(("user:*" if v == "*" else f"user:{v}", "viewer"))
    return keys


def write_missing_tuples(doc_id: str, missing: set[tuple[str, str]]) -> None:
    """Write exactly the absent tuples (one transactional batch of genuinely
    missing keys — a mixed batch with duplicates would fail wholesale, which is
    how a store reset used to leave documents silently filtered)."""
    if not missing:
        return
    obj = f"document:{doc_id}"
    keys = [{"user": u, "relation": rel, "object": obj} for u, rel in sorted(missing)]
    with tracer().start_as_current_span("fga.write") as span:
        span.set_attribute("prokura.fga.object", obj)
        r = httpx.post(f"{_base()}/stores/{store_id()}/write",
                       json={"writes": {"tuple_keys": keys}}, timeout=10.0)
    r.raise_for_status()


def write_document_tuples(doc_id: str, owner: str, viewers: list[str]) -> None:
    """Write ``owner`` / ``viewer`` tuples for a document. ``viewers`` entries may be
    a username or ``"*"`` (public, written as ``user:*``). Idempotent."""
    obj = f"document:{doc_id}"
    keys = [{"user": f"user:{owner}", "relation": "owner", "object": obj}]
    for v in viewers:
        user = "user:*" if v == "*" else f"user:{v}"
        keys.append({"user": user, "relation": "viewer", "object": obj})
    with tracer().start_as_current_span("fga.write") as span:
        span.set_attribute("prokura.fga.object", obj)
        r = httpx.post(f"{_base()}/stores/{store_id()}/write",
                       json={"writes": {"tuple_keys": keys}}, timeout=10.0)
    if r.status_code >= 400 and "already exists" not in r.text:
        r.raise_for_status()
