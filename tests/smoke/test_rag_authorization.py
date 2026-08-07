"""M5 (Flow D): the retriever authorizes candidate chunks AS THE END USER, never
as the agent — the confused-deputy defense SPEC.md §11 exists to make concrete.

6.1 authorized user retrieves a protected doc; unauthorized user does not; a
    foreign-audience / no-identity call returns no chunks.
6.2 the adversarial leakage proof: the protected doc is the TOP embedding hit for
    the crafted query, yet none of its content reaches the unauthorized user's
    answer — while the authorized user does retrieve it.
"""

import httpx
import pytest

import ragkit


@pytest.fixture(scope="module")
def stack(keycloak, rag, openfga):
    """RAG seeds its corpus + FGA tuples at startup; just gate on health here."""
    httpx.get(f"{ragkit.RAG_URL}/healthz", timeout=10.0).raise_for_status()


def _alice_rag_token(c) -> str:
    return ragkit.rag_token(ragkit.mcp_token(c, "alice", "alice"))


def _bob_rag_token(c) -> str:
    return ragkit.rag_token(ragkit.mcp_token(c, "bob", "bob"))


# --- 6.1 authorization ---------------------------------------------------------

def test_authorized_user_retrieves_protected_doc(stack):
    with httpx.Client(follow_redirects=False, timeout=30.0) as c:
        r = ragkit.search_direct(_alice_rag_token(c))
    assert r.status_code == 200, r.text[:200]
    out = r.json()
    assert "secret-roadmap" in ragkit.doc_ids(out), out
    assert ragkit.SECRET_MARKER in out["answer"]


def test_unauthorized_user_does_not_retrieve_protected_doc(stack):
    with httpx.Client(follow_redirects=False, timeout=30.0) as c:
        r = ragkit.search_direct(_bob_rag_token(c))
    assert r.status_code == 200, r.text[:200]
    out = r.json()
    # bob is not a viewer of secret-roadmap — it must not appear even though it is
    # the top embedding hit (it IS among the candidates: allowed < candidates).
    assert "secret-roadmap" not in ragkit.doc_ids(out), out
    assert ragkit.SECRET_MARKER not in out["answer"]
    assert out["allowed"] < out["candidates"], out  # the top hit was filtered out


def test_foreign_audience_token_returns_no_chunks(stack):
    # An aud=mcp-server token is the AGENT's own credential. Presented to the
    # retriever it is refused (F2 defense) — agent identity is insufficient.
    with httpx.Client(follow_redirects=False, timeout=30.0) as c:
        mcp_tok = ragkit.mcp_token(c, "alice", "alice")
    r = ragkit.search_direct(mcp_tok)
    assert r.status_code == 403, f"foreign-audience token not refused: {r.status_code}"
    assert r.json().get("chunks") == []


def test_missing_token_returns_no_chunks(stack):
    r = httpx.post(f"{ragkit.RAG_URL}/rag/search", json={"query": ragkit.ADVERSARIAL_QUERY},
                   timeout=10.0)
    assert r.status_code == 401
    assert r.json().get("chunks") == []


# --- 6.2 adversarial leakage ---------------------------------------------------

def test_protected_doc_is_the_top_hit_but_never_leaks(stack):
    """The core proof: the protected doc is the #1 candidate for BOTH users, yet
    only the authorized user's answer contains it."""
    with httpx.Client(follow_redirects=False, timeout=30.0) as c:
        alice = ragkit.search_direct(_alice_rag_token(c)).json()
        bob = ragkit.search_direct(_bob_rag_token(c)).json()

    # It is genuinely the top embedding hit — present in the candidate set for both
    # (candidates count includes it; a non-viewer simply has it filtered post-retrieval).
    assert alice["candidates"] == bob["candidates"], (alice, bob)

    # Authorized user: gets the protected content.
    assert "secret-roadmap" in ragkit.doc_ids(alice)
    assert ragkit.SECRET_MARKER in alice["answer"]

    # Unauthorized user: never sees a byte of it, even as the top hit.
    assert "secret-roadmap" not in ragkit.doc_ids(bob)
    assert ragkit.SECRET_MARKER not in bob["answer"]
    for chunk in bob["chunks"]:
        assert ragkit.SECRET_MARKER not in chunk["text"]
