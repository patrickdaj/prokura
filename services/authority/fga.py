"""OpenFGA read access for the console (M8, D3): the ``operator`` relation —
which agents does the signed-in principal operate. This is the console's own
read position (read-only, same trust as the RAG reader); it never writes tuples
(the broker stays the sole ``can_use`` writer). Per-agent consent (``can_use``)
is read via the broker's ``/v1/consents`` API, not here, so the two sources stay
non-overlapping.

Object naming matches the rest of the stack: ``agent:{id}``, ``user:{id}``."""

import httpx

import config
from telemetry import tracer

_store_id: str | None = None


def store_id() -> str:
    global _store_id
    if _store_id:
        return _store_id
    r = httpx.get(f"{config.OPENFGA_URL}/stores", timeout=10.0)
    r.raise_for_status()
    for s in r.json().get("stores", []):
        if s["name"] == config.FGA_STORE_NAME:
            _store_id = s["id"]
            return _store_id
    raise RuntimeError(f"OpenFGA store {config.FGA_STORE_NAME!r} not found")


def agents_operated_by(user: str) -> list[str]:
    """Every agent whose ``operator`` is ``user``. OpenFGA /read with an empty
    tuple_key enumerates all tuples; we page and filter to the operator relation
    and this principal (the console does not index by operator, so this is the
    honest cost of a per-principal read)."""
    want = f"user:{user}"
    agents, token = [], None
    with tracer().start_as_current_span("fga.read_operators"):
        while True:
            body: dict = {"page_size": 100}
            if token:
                body["continuation_token"] = token
            r = httpx.post(f"{config.OPENFGA_URL}/stores/{store_id()}/read",
                           json=body, timeout=10.0)
            r.raise_for_status()
            data = r.json()
            for t in data.get("tuples", []):
                k = t["key"]
                if k["relation"] == "operator" and k["user"] == want:
                    agents.append(k["object"].split(":", 1)[1])
            token = data.get("continuation_token")
            if not token:
                break
    return sorted(set(agents))
