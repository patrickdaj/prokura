"""M8 authority-console spec: the principal's aggregated register, per-agent
consent revoke relayed as an exchanged user-bound bearer (broker stays the sole
tuple writer), the approval user-bound read APIs, and cross-principal isolation.

humankit is the sanctioned simulated human (real OIDC login on :8160, real
button clicks for revoke/connect). Mechanism assertions then hit the APIs the
way the panel's own JS does — with the real session — and probe the bearer
audience gates directly."""

import httpx
import pytest

import brokerkit
import humankit
from conftest import (
    BROKER_URL,
    DEMO_USER,
    KEYCLOAK_URL,
    REALM,
    admin_token,
    drive_login,
    link_acme,
    wait_http,
)

AUTHORITY_URL = "http://localhost:8160"
APPROVAL_URL = "http://localhost:8120"


@pytest.fixture(scope="session")
def authority() -> str:
    wait_http(f"{AUTHORITY_URL}/healthz", ok=lambda r: r.status_code == 200)
    return AUTHORITY_URL


@pytest.fixture(scope="module")
def consented(keycloak, broker, openbao, openfga):
    """alice has an acme grant and agent-app is consented to it, so her register
    is non-empty and revoke has something to tear up."""
    link_acme(keycloak)
    brokerkit.import_grant(brokerkit.broker_token(), "acme")
    brokerkit.seed_operator("agent-app", DEMO_USER)
    humankit.drive_consent("agent-app", "acme")


def _api(cookie: str, path: str, method: str = "GET") -> httpx.Response:
    return httpx.request(method, f"{AUTHORITY_URL}{path}",
                         headers={"Cookie": f"prokura_authority_session={cookie}"},
                         timeout=20.0)


def _can_use(agent: str, user: str = DEMO_USER) -> bool:
    r = httpx.post(f"{brokerkit.OPENFGA_URL}/stores/{brokerkit.store_id()}/check",
                   json={"tuple_key": {"user": f"agent:{agent}", "relation": "can_use",
                                       "object": f"grant:{user}/acme"}}, timeout=10.0)
    r.raise_for_status()
    return bool(r.json().get("allowed"))


# --- 6.2 register aggregation (via the real session, like the panel) ----------

def test_register_aggregates_for_signed_in_principal(authority, consented):
    cookie = humankit.console_session_cookie("alice")
    reg = _api(cookie, "/api/register").json()
    assert reg["user"] == "alice"
    agents = {a["agent"] for a in reg["agents"]}
    assert "agent-app" in agents
    agent_app = next(a for a in reg["agents"] if a["agent"] == "agent-app")
    assert any(g["provider"] == "acme" for g in agent_app["consents"])
    assert any(g["provider"] == "acme" for g in reg["grants"])
    assert isinstance(reg["approvals"], list)
    assert reg["approval_base"].startswith("http")  # deep-link base for :8120


def test_topic_served_to_owner_with_qr(authority, consented):
    cookie = humankit.console_session_cookie("alice")
    t = _api(cookie, "/api/topic").json()
    assert t["topic"].startswith("prokura-approvals-")
    assert t["subscribe_url"].endswith(t["topic"])
    assert t["qr_svg"].startswith("<svg")     # rendered server-side, no external service


def test_no_session_no_register(authority):
    # A bare request without the session cookie is refused (no URL-carried creds).
    r = httpx.get(f"{AUTHORITY_URL}/api/register", timeout=10.0)
    assert r.status_code == 401


# --- 6.2 console revoke == surface revoke (same code path, tuple-gone parity) --

def test_console_revoke_equals_surface_revoke(authority, consented):
    # start consented
    if not _can_use("agent-app"):
        humankit.drive_consent("agent-app", "acme")
    assert _can_use("agent-app") is True

    # (a) revoke from the CONSOLE (exchanged user-bound bearer -> broker)
    ok, banner = humankit.console_revoke("agent-app", "acme")
    assert ok, banner
    assert _can_use("agent-app") is False

    # re-consent, then (b) revoke from the M7 consent SURFACE session
    humankit.drive_consent("agent-app", "acme")
    assert _can_use("agent-app") is True
    out = humankit.revoke_consent("agent-app", "acme")
    assert out["status"] == 200, out
    assert _can_use("agent-app") is False       # same tuple gone, same broker path

    humankit.drive_consent("agent-app", "acme")  # restore for other modules


def test_revoked_agent_refused_next_handout(authority, consented):
    if not _can_use("agent-app"):
        humankit.drive_consent("agent-app", "acme")
    ok, banner = humankit.console_revoke("agent-app", "acme")
    assert ok, banner
    # the revoked agent's very next provider-token request is refused
    bt = brokerkit.broker_token()
    r = httpx.post(f"{BROKER_URL}/v1/tokens/acme", json={"scopes": []},
                   headers={"Authorization": f"Bearer {bt}"}, timeout=15.0)
    assert r.status_code == 403 and r.json().get("error") == "not_consented", r.text
    humankit.drive_consent("agent-app", "acme")  # restore


# --- 6.2 the read APIs refuse the wrong audience and cannot decide ------------

def test_broker_consents_refuses_non_broker_audience(authority, keycloak):
    # A plain user token (openid only, so aud lacks token-broker) is refused by
    # /v1/consents — the console's read must present a broker-audience bearer.
    plain = drive_login(keycloak, client_id="agent-app",
                        client_secret="agent-app-dev-secret", scope="openid")["access_token"]
    r = httpx.get(f"{BROKER_URL}/v1/consents",
                  headers={"Authorization": f"Bearer {plain}"}, timeout=15.0)
    assert r.status_code == 403 and r.json().get("error") == "wrong_audience", r.text


def test_approval_read_refuses_wrong_audience(authority):
    # A token minted for the broker (aud=token-broker) is not for the approval
    # service — /v1/my/topic must refuse before deriving anything.
    broker_tok = brokerkit.broker_token()
    r = httpx.get(f"{APPROVAL_URL}/v1/my/topic",
                  headers={"Authorization": f"Bearer {broker_tok}"}, timeout=15.0)
    assert r.status_code == 403 and r.json().get("error") == "wrong_audience", r.text


def test_approval_bearer_cannot_decide(authority):
    # There is no bearer decision path — decisions are session-only on :8120.
    broker_tok = brokerkit.broker_token()
    r = httpx.post(f"{APPROVAL_URL}/approval/apr-does-not-matter/decide",
                   headers={"Authorization": f"Bearer {broker_tok}"},
                   json={"decision": "approve"}, timeout=15.0)
    assert r.status_code == 401, r.text        # session_required — a bearer cannot decide


# --- 6.1 / 7.2 provider linking end-to-end from the console ------------------

def _reset_bob_acme():
    """TEST SETUP ONLY (not part of the ceremony): make bob a clean, unlinked
    principal so 'connect a provider' is a real first link. Removes bob's acme
    federated identity (admin) and any prior acme grant (broker), so the panel
    shows the Connect button."""
    adm = admin_token()
    H = {"Authorization": f"Bearer {adm}"}
    uid = httpx.get(f"{KEYCLOAK_URL}/admin/realms/{REALM}/users?username=bob",
                    headers=H, timeout=10.0).json()[0]["id"]
    for f in httpx.get(f"{KEYCLOAK_URL}/admin/realms/{REALM}/users/{uid}/federated-identity",
                       headers=H, timeout=10.0).json():
        if f["identityProvider"] == "acme":
            httpx.delete(f"{KEYCLOAK_URL}/admin/realms/{REALM}/users/{uid}/federated-identity/acme",
                         headers=H, timeout=10.0)
    bob_tok = drive_login(KEYCLOAK_URL, client_id="smoke-cli", user="bob")["access_token"]
    httpx.post(f"{BROKER_URL}/v1/grants/acme/revoke",
               headers={"Authorization": f"Bearer {bob_tok}"}, timeout=15.0)


def test_connect_provider_end_to_end(authority, keycloak, broker, openbao):
    _reset_bob_acme()
    # The ceremony itself touches NO admin API: a real person clicks Connect,
    # logs into the provider in their browser, and returns.
    banner = humankit.console_connect("acme", "bob")
    assert "Connected" in banner, banner
    cookie = humankit.console_session_cookie("bob")
    reg = _api(cookie, "/api/register").json()
    assert any(g["provider"] == "acme" for g in reg["grants"]), \
        f"connected grant did not land in the register: {reg['grants']}"


# --- 6.3 cross-principal isolation -------------------------------------------

def test_bob_console_never_returns_alices_world(authority, consented):
    alice = humankit.console_session_cookie("alice")
    bob = humankit.console_session_cookie("bob")

    alice_topic = _api(alice, "/api/topic").json()["topic"]
    breg = _api(bob, "/api/register").json()
    assert breg["user"] == "bob"
    assert all(a["agent"] != "agent-app" for a in breg["agents"]), \
        "bob's register leaked alice's agent"
    # bob sees none of alice's approvals
    assert all(ap["agent"] != "agent-app" for ap in breg["approvals"])

    btopic = _api(bob, "/api/topic").json()["topic"]
    assert btopic != alice_topic               # per-user unguessable topic

    activity = _api(bob, "/api/activity").json()["activity"]
    assert all("user=alice" not in e["line"] for e in activity), \
        "bob's activity feed leaked alice's audit lines"
