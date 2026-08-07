"""M4 mcp-authorization spec: the MCP server as an OAuth 2.1 resource server, and
Keycloak as the MCP authorization server. A scripted spec-compliant MCP client
discovers (401 → PRM → AS metadata), dynamically registers (RFC 7591), completes
OAuth 2.1 + PKCE to an aud=mcp-server token, and lists tools. A wrong-audience
token is refused."""

import httpx
import pytest

import brokerkit
import mcpkit
from conftest import KEYCLOAK_URL, REALM


@pytest.fixture(scope="module")
def mcp(keycloak):
    httpx.get(f"{mcpkit.MCP_URL}/healthz", timeout=10.0).raise_for_status()


def test_discovery_from_401_challenge(mcp):
    with httpx.Client(follow_redirects=False, timeout=20.0) as c:
        meta_url = mcpkit.discover_challenge(c)
        assert meta_url == mcpkit.METADATA_URL
        prm = c.get(meta_url).json()
        # RFC 9728: names the Keycloak realm as this resource's authorization server.
        assert prm["resource"] == f"{mcpkit.MCP_URL}/mcp"
        issuer = f"{KEYCLOAK_URL}/realms/{REALM}"
        assert issuer in prm["authorization_servers"]


def test_as_metadata_is_discoverable(mcp):
    with httpx.Client(timeout=20.0) as c:
        md = mcpkit.as_metadata(c)
        assert md["registration_endpoint"].endswith("/clients-registrations/openid-connect")
        assert md.get("token_endpoint")
        assert "S256" in md.get("code_challenge_methods_supported", [])


def test_dcr_then_oauth_yields_mcp_audience_token(mcp):
    with httpx.Client(follow_redirects=False, timeout=20.0) as c:
        client_id = mcpkit.register_client(c)
        assert client_id  # DCR: a client id with no operator involvement
        token = mcpkit.login(c, client_id)
        cl = mcpkit.claims(token)
        assert cl.get("azp") == client_id
        aud = cl.get("aud")
        aud = aud if isinstance(aud, list) else [aud]
        # RFC 8707 gap workaround: audience is bound by the mcp-audience client scope.
        assert "mcp-server" in aud, f"aud={aud} lacks mcp-server"


def test_tools_list_with_valid_token(mcp):
    with httpx.Client(follow_redirects=False, timeout=20.0) as c:
        token = mcpkit.mcp_token(c)
        r = mcpkit.rpc(c, token, "tools/list")
        assert r.status_code == 200, r.text[:200]
        names = {t["name"] for t in r.json()["result"]["tools"]}
        assert {"get_provider_token", "send_email"} <= names


def test_wrong_audience_token_refused(mcp, broker):
    # A broker-audience token (aud=token-broker, not mcp-server) is not for this
    # resource — the MCP server must challenge it and perform no action.
    with httpx.Client(follow_redirects=False, timeout=20.0) as c:
        bt = brokerkit.broker_token()
        r = mcpkit.rpc(c, bt, "tools/list")
        assert r.status_code == 401, f"wrong-audience token not refused: {r.status_code}"
        assert "resource_metadata=" in r.headers.get("WWW-Authenticate", "")
