"""AGENT-SIDE helpers for the human-approval smoke tests (M7 quarantine, D6).

This kit holds only what an agent can legitimately do: bootstrap its delegated
user token via the device flow (its own client credential; the human approves
the user code in THEIR browser — humankit), exchange audiences, call the gated
tool, and retry with an action token after a 428.

Deliberately ABSENT (moved to the human, i.e. humankit): CIBA initiation
(server-side since ADR-0022 — no agent client even has the grant), approval
decisions, and every user password."""

import base64
import hashlib
import json

import httpx

from conftest import KEYCLOAK_URL, REALM, device_bootstrap
from prokura import exchange

APPROVAL_URL = "http://localhost:8120"
TOOLS_URL = "http://localhost:8130"
MAILPIT_URL = "http://localhost:8025"
AGENT, SECRET = "agent-app", "agent-app-dev-secret"
TOPIC_SALT = "prokura-approval-dev-salt"  # matches the approval service default


def claims(t: str) -> dict:
    p = t.split(".")[1]; p += "=" * (-len(p) % 4)
    return json.loads(base64.urlsafe_b64decode(p))


def user_token() -> str:
    """The agent's delegated user token, via RFC 8628 device flow: the agent
    holds only its own client secret; alice approves in her own session. The
    audience scopes ride along so the consent she grants covers later
    exchanges (agent-app is consentRequired since M7)."""
    return device_bootstrap(AGENT, SECRET,
                            scope="openid tools-audience broker-audience")["access_token"]


def tools_token(ut: str | None = None) -> str:
    """Exchange the delegated token for the tools-API audience (RFC 8693)."""
    return exchange(ut or user_token(), "agent-tools-api",
                    base_url=KEYCLOAK_URL, realm=REALM,
                    client_id=AGENT, client_secret=SECRET)


def register(ut: str, action: str, params: dict, c: httpx.Client) -> tuple[str, str]:
    """Register directly with the approval service (mechanism tests; the
    production trigger is the tools-api's 428 path). Registration now also
    initiates the server-side CIBA ceremony."""
    r = c.post(f"{APPROVAL_URL}/register", headers={"Authorization": f"Bearer {ut}"},
               json={"action": action, "params": params})
    r.raise_for_status()
    return r.json()["ref"], r.json()["action_token"]


def attempt(tt: str, params: dict, c: httpx.Client,
            action_token: str | None = None) -> httpx.Response:
    """Call the gated tool; without an action token this draws the 428."""
    body = dict(params)
    if action_token:
        body["action_token"] = action_token
    return c.post(f"{TOOLS_URL}/tools/email/send",
                  headers={"Authorization": f"Bearer {tt}"}, json=body)


def send_email(tt: str, action_token: str, params: dict, c: httpx.Client) -> httpx.Response:
    return attempt(tt, params, c, action_token=action_token)


def topic_for(user: str = "alice") -> str:
    d = hashlib.sha256(f"{TOPIC_SALT}:{user}".encode()).hexdigest()
    return f"prokura-approvals-{d[:20]}"


def approved_tokens(action: str, params: dict, c: httpx.Client) -> tuple[str, str]:
    """Full reactive happy path: 428 challenge -> the HUMAN approves from the
    surface (humankit) -> returns (tools_token, action_token) ready to retry.
    `action` is fixed to email.send by the tools-api; kept for call-site clarity."""
    import humankit

    assert action == "email.send"
    tt = tools_token()
    r = attempt(tt, params, c)
    assert r.status_code == 428, f"expected 428 challenge: {r.status_code} {r.text[:150]}"
    j = r.json()
    result = humankit.drive_approval(j["ref"], approve=True)
    assert "Approved" in result, result
    return tt, j["action_token"]
