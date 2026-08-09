"""M4 chain (re-wired in M7): through MCP tools, a scripted MCP client obtains a
brokered provider token (consent-gated) and performs a human-approved email.send
(reactive challenge → the human approves in their own session → retry). The
inbound MCP token is never forwarded downstream — each tool exchanges it for a
correctly-audienced token. The agent never touches the ceremony."""

import httpx
import pytest

import approvalkit as ak
import brokerkit
import humankit
import mcpkit
from conftest import BROKER_URL, DEMO_USER, link_acme

MCP_AGENT = "mcp-server"  # the consent identity: azp of the exchanged tokens


@pytest.fixture(scope="module")
def chain(keycloak, broker, openbao, openfga, mailpit):
    """A linked + imported acme grant, consented to the mcp-server agent."""
    httpx.get(f"{mcpkit.MCP_URL}/healthz", timeout=10.0).raise_for_status()
    httpx.get(f"{ak.TOOLS_URL}/healthz", timeout=10.0).raise_for_status()
    link_acme(keycloak)
    brokerkit.import_grant(brokerkit.broker_token(), "acme")
    brokerkit.seed_operator(MCP_AGENT, DEMO_USER)
    humankit.drive_consent(MCP_AGENT, "acme")


def test_get_provider_token_tool_is_consent_gated(chain):
    with httpx.Client(follow_redirects=False, timeout=30.0) as c:
        token = mcpkit.mcp_token(c)
        out, is_error = mcpkit.tool_call(c, token, "get_provider_token", {"provider": "acme"})
        assert not is_error, out
        assert out.get("access_token"), out
        assert out["expires_in"] <= 900  # broker TTL honesty carries through
        assert "refresh_token" not in out


def test_inbound_mcp_token_never_forwarded_downstream(chain):
    # The MCP token is addressed to mcp-server, NOT token-broker: presenting it
    # directly to the broker is refused. So the working get_provider_token tool
    # must have exchanged it (the server never passes the inbound token through).
    with httpx.Client(follow_redirects=False, timeout=30.0) as c:
        token = mcpkit.mcp_token(c)
        r = httpx.post(f"{BROKER_URL}/v1/tokens/acme",
                       headers={"Authorization": f"Bearer {token}"},
                       json={"scopes": []}, timeout=15.0)
        assert r.status_code == 403, f"MCP token accepted downstream?! {r.status_code}"


def test_reactive_approved_email_sends(chain):
    params = {"to": "boss@prokura.local", "subject": "MCP approved report", "body": "ok"}
    with httpx.Client(follow_redirects=False, timeout=30.0) as mc, \
         httpx.Client(timeout=30.0) as ac:
        token = mcpkit.mcp_token(mc)

        # 1. First call: no action token -> the tools-API registers the real action
        #    and challenges. The trigger lives on the resource server, not the agent.
        challenge, is_error = mcpkit.tool_call(mc, token, "send_email", params)
        assert not is_error, challenge
        assert challenge["status"] == "approval_required", challenge
        ref, action_token = challenge["ref"], challenge["action_token"]
        assert ref and action_token

        # 2. The ceremony was initiated SERVER-side at registration (ADR-0022);
        #    the human approves the server-registered action from the deep link.
        result = humankit.drive_approval(ref, approve=True)
        assert "Approved" in result, result

        # 3. Retry the tool with the action token -> executed exactly once.
        out, is_error = mcpkit.tool_call(mc, token, "send_email", {**params, "action_token": action_token})
        assert not is_error, out
        assert out["status"] == "sent", out

        # The mail landed in the Mailpit sink.
        msgs = ac.get(f"{ak.MAILPIT_URL}/api/v1/messages").json().get("messages", [])
        assert "MCP approved report" in [m.get("Subject") for m in msgs]
