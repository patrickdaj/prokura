"""M7 rag-authorization delta (D7): FGA tuple reconciliation is decoupled from
the vector-seed guard. An OpenFGA store reset after first ingest used to leave
every document silently filtered (chunks present, tuples gone, seed guard
skipping the re-write). Now a rag restart reconciles the manifest's tuples
without re-embedding anything."""

import json
import subprocess
import time

import httpx
import pytest

import ragkit
from conftest import OPENFGA_URL, FGA_STORE_NAME


def _store_id() -> str:
    r = httpx.get(f"{OPENFGA_URL}/stores", timeout=10.0)
    r.raise_for_status()
    return [s["id"] for s in r.json()["stores"] if s["name"] == FGA_STORE_NAME][-1]


def _document_tuples() -> list[dict]:
    """All document:* tuples (read-all + filter; OpenFGA's read filter needs an
    object id, which we don't have)."""
    out, token = [], ""
    while True:
        body = {"page_size": 100}
        if token:
            body["continuation_token"] = token
        r = httpx.post(f"{OPENFGA_URL}/stores/{_store_id()}/read", json=body, timeout=10.0)
        r.raise_for_status()
        j = r.json()
        out += [t["key"] for t in j.get("tuples", [])
                if t["key"]["object"].startswith("document:")]
        token = j.get("continuation_token", "")
        if not token:
            return out


@pytest.fixture(scope="module")
def stack(keycloak, rag, openfga):
    httpx.get(f"{ragkit.RAG_URL}/healthz", timeout=10.0).raise_for_status()


def test_store_reset_recovers_on_restart_without_reembedding(stack):
    with httpx.Client(follow_redirects=False, timeout=30.0) as c:
        alice = ragkit.rag_token(ragkit.mcp_token(c, "alice"))

    # Baseline: alice retrieves her protected document.
    out = ragkit.search_direct(alice).json()
    assert "secret-roadmap" in ragkit.doc_ids(out), out

    # Simulate the store reset: delete every document tuple.
    doomed = _document_tuples()
    assert doomed, "expected seeded document tuples"
    for i in range(0, len(doomed), 10):
        httpx.post(f"{OPENFGA_URL}/stores/{_store_id()}/write",
                   json={"deletes": {"tuple_keys": doomed[i:i + 10]}},
                   timeout=10.0).raise_for_status()

    # The failure mode this test pins: with tuples gone, everything is filtered.
    out = ragkit.search_direct(alice).json()
    assert ragkit.doc_ids(out) == set(), f"expected everything filtered, got {out}"

    # Restart rag (the reconciliation path) and wait for health.
    subprocess.run(["docker", "compose", "restart", "rag"], check=True,
                   capture_output=True, timeout=120)
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        try:
            if httpx.get(f"{ragkit.RAG_URL}/healthz", timeout=3.0).status_code == 200:
                break
        except httpx.HTTPError:
            pass
        time.sleep(2)
    else:
        pytest.fail("rag did not come back after restart")

    # Recovered: the same query returns the document again...
    out = ragkit.search_direct(alice).json()
    assert "secret-roadmap" in ragkit.doc_ids(out), out

    # ...via tuple reconciliation, NOT a re-embed (the seed guard still skipped).
    logs = subprocess.run(["docker", "compose", "logs", "--since", "2m", "rag"],
                          capture_output=True, text=True, timeout=30).stdout
    assert "tuple reconciliation wrote" in logs
    assert "already populated" in logs, "vector store was unexpectedly re-seeded"
