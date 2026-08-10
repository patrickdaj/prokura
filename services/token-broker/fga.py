"""OpenFGA access for the broker: the ``can_use`` check (hand-out chain step 4)
and the sole-writer tuple operations (per-agent-consent spec). Wrapped in OTel
spans so FGA calls appear in the flow trace.

Object naming matches the smoke harness: ``grant:{user}/{provider}``,
``agent:{id}``, ``user:{id}``.
"""

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


def can_use(agent: str, user: str, provider: str) -> bool:
    with tracer().start_as_current_span("fga.check") as span:
        span.set_attribute("prokura.fga.relation", "can_use")
        r = httpx.post(
            f"{_base()}/stores/{store_id()}/check",
            json={"tuple_key": {
                "user": f"agent:{agent}",
                "relation": "can_use",
                "object": f"grant:{user}/{provider}",
            }},
            timeout=10.0,
        )
        r.raise_for_status()
        return bool(r.json().get("allowed"))


def agent_operator(agent: str) -> str | None:
    """Return the user id that operates ``agent`` (the ``operator`` relation),
    or None. Used to enforce operator == grant owner at tuple-write time."""
    r = httpx.post(
        f"{_base()}/stores/{store_id()}/read",
        json={"tuple_key": {"object": f"agent:{agent}", "relation": "operator"}},
        timeout=10.0,
    )
    r.raise_for_status()
    tuples = r.json().get("tuples", [])
    if not tuples:
        return None
    who = tuples[0]["key"]["user"]  # e.g. "user:alice"
    return who.split(":", 1)[1] if ":" in who else who


def list_can_use_agents(user: str, provider: str) -> list[str]:
    """Every agent with a ``can_use`` tuple on ``grant:{user}/{provider}`` — the
    consent register for one grant (M8 console read; same read shape as
    delete_all_can_use, without the delete)."""
    r = httpx.post(
        f"{_base()}/stores/{store_id()}/read",
        json={"tuple_key": {"object": f"grant:{user}/{provider}", "relation": "can_use"}},
        timeout=10.0,
    )
    r.raise_for_status()
    agents = []
    for t in r.json().get("tuples", []):
        who = t["key"]["user"]  # "agent:{id}"
        agents.append(who.split(":", 1)[1] if ":" in who else who)
    return sorted(agents)


def write_can_use(agent: str, user: str, provider: str) -> None:
    with tracer().start_as_current_span("fga.write") as span:
        span.set_attribute("prokura.fga.relation", "can_use")
        r = httpx.post(
            f"{_base()}/stores/{store_id()}/write",
            json={"writes": {"tuple_keys": [{
                "user": f"agent:{agent}",
                "relation": "can_use",
                "object": f"grant:{user}/{provider}",
            }]}},
            timeout=10.0,
        )
        if r.status_code >= 400 and "already exists" not in r.text:
            r.raise_for_status()


def delete_can_use(agent: str, user: str, provider: str) -> None:
    r = httpx.post(
        f"{_base()}/stores/{store_id()}/write",
        json={"deletes": {"tuple_keys": [{
            "user": f"agent:{agent}",
            "relation": "can_use",
            "object": f"grant:{user}/{provider}",
        }]}},
        timeout=10.0,
    )
    # Revoke is idempotent: a missing tuple is already-revoked, not an error.
    # OpenFGA phrases this as "cannot delete a tuple which does not exist".
    body = r.text.lower()
    if r.status_code >= 400 and "not found" not in body and "does not exist" not in body \
            and "did not exist" not in body:
        r.raise_for_status()


def delete_all_can_use(user: str, provider: str) -> None:
    """Delete every ``can_use`` tuple on a grant (used on grant revocation)."""
    obj = f"grant:{user}/{provider}"
    r = httpx.post(
        f"{_base()}/stores/{store_id()}/read",
        json={"tuple_key": {"object": obj, "relation": "can_use"}},
        timeout=10.0,
    )
    r.raise_for_status()
    keys = [t["key"] for t in r.json().get("tuples", [])]
    if keys:
        httpx.post(
            f"{_base()}/stores/{store_id()}/write",
            json={"deletes": {"tuple_keys": keys}},
            timeout=10.0,
        )
