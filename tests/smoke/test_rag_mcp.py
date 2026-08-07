"""M5 6.3: the rag_search MCP tool threads the end-user identity from the validated
inbound MCP token through to the OpenFGA check — on the same surface as the other
gated tools. The inbound MCP token is never forwarded downstream (the M4
no-passthrough rule), and the sub carried through remains the end user."""

import httpx
import pytest

import ragkit


@pytest.fixture(scope="module")
def stack(keycloak, rag, openfga):
    httpx.get(f"{ragkit.RAG_URL}/healthz", timeout=10.0).raise_for_status()


def test_rag_search_is_advertised(stack):
    with httpx.Client(follow_redirects=False, timeout=30.0) as c:
        token = ragkit.mcp_token(c, "alice", "alice")
        r = c.post(f"{ragkit.MCP_URL}/mcp", headers={"Authorization": f"Bearer {token}"},
                   json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    names = [t["name"] for t in r.json()["result"]["tools"]]
    assert "rag_search" in names, names


def test_rag_search_preserves_end_user_alice(stack):
    with httpx.Client(follow_redirects=False, timeout=30.0) as c:
        token = ragkit.mcp_token(c, "alice", "alice")
        out, is_error = ragkit.search_via_mcp(c, token)
    assert not is_error, out
    assert out["user"] == "alice"
    assert "secret-roadmap" in ragkit.doc_ids(out)


def test_rag_search_filters_for_non_viewer_bob(stack):
    with httpx.Client(follow_redirects=False, timeout=30.0) as c:
        token = ragkit.mcp_token(c, "bob", "bob")
        out, is_error = ragkit.search_via_mcp(c, token)
    assert not is_error, out
    assert out["user"] == "bob"
    # bob's own authorized docs, but NOT alice's protected one.
    assert "secret-roadmap" not in ragkit.doc_ids(out)
    assert ragkit.SECRET_MARKER not in out["answer"]


def test_inbound_mcp_token_not_forwarded_downstream(stack):
    # The MCP token is addressed to mcp-server, not rag-server: presenting it
    # directly to the retriever is refused. So a working rag_search tool must have
    # exchanged it — the server never passes the inbound token through.
    with httpx.Client(follow_redirects=False, timeout=30.0) as c:
        token = ragkit.mcp_token(c, "alice", "alice")
    r = httpx.post(f"{ragkit.RAG_URL}/rag/search",
                   headers={"Authorization": f"Bearer {token}"},
                   json={"query": ragkit.ADVERSARIAL_QUERY}, timeout=15.0)
    assert r.status_code == 403, f"MCP token accepted downstream?! {r.status_code}"
