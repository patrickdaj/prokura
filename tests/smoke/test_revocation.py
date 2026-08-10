"""M9 revocation spec — the kill switch. A per-grant revoke stops an agent on the
revoked grant with a measured time-to-stop: the tuple is gone, a deny-list entry
denies even a stale tuple (and re-acquiring the grant with a fresh token), the
in-flight residual is reported honestly, and a CAEP Security Event Token is
emitted. Per-grant revoke is scoped — the agent's session and other grants are
untouched (the agent-wide Keycloak session/offline kill is the broader action,
proven in spike/kill-switch). humankit drives the real revoke; mechanism
assertions probe the broker directly."""

import base64
import json
import subprocess

import httpx
import pytest

import brokerkit
import conftest
import humankit
from conftest import DEMO_USER, KEYCLOAK_URL, REALM, link_acme

BROKER = "http://localhost:8110"


@pytest.fixture(scope="module")
def consented(keycloak, broker, openbao, openfga):
    link_acme(keycloak)
    brokerkit.import_grant(brokerkit.broker_token(), "acme")
    brokerkit.seed_operator("agent-app", DEMO_USER)
    humankit.drive_consent("agent-app", "acme")


def _can_use(agent: str) -> bool:
    r = httpx.post(f"{brokerkit.OPENFGA_URL}/stores/{brokerkit.store_id()}/check",
                   json={"tuple_key": {"user": f"agent:{agent}", "relation": "can_use",
                                       "object": f"grant:{DEMO_USER}/acme"}}, timeout=10)
    r.raise_for_status()
    return bool(r.json().get("allowed"))


def _handout(bt: str) -> httpx.Response:
    return httpx.post(f"{BROKER}/v1/tokens/acme", json={"scopes": []},
                      headers={"Authorization": f"Bearer {bt}"}, timeout=15)


def _fresh_broker_token() -> str:
    """A broker-audience token from a fresh agent-app session (clears the login
    cache), to prove re-acquisition is blocked by state, not a stale token."""
    for k in [k for k in conftest._login_cache if "agent-app" in k[0]]:
        conftest._login_cache.pop(k, None)
    return brokerkit.broker_token()


def _psql(sql: str) -> None:
    subprocess.run(["docker", "compose", "exec", "-T", "postgres", "psql", "-U", "prokura",
                    "-d", "prokura", "-c", sql], capture_output=True, text=True, check=False)


def _claims(t: str) -> dict:
    p = t.split(".")[1]
    p += "=" * (-len(p) % 4)
    return json.loads(base64.urlsafe_b64decode(p))


# --- kill measurement + stop -------------------------------------------------

def test_kill_is_measured_and_stops(consented):
    humankit.drive_consent("agent-app", "acme")
    bt = brokerkit.broker_token()
    assert _handout(bt).status_code == 200
    out = humankit.revoke_consent("agent-app", "acme")   # M7 surface session → kill()
    assert out["status"] == 200, out
    body = out["body"]
    assert isinstance(body["stop_ms"], int) and body["stop_ms"] < 5000, body
    assert body["residual_seconds"] == 120
    assert _can_use("agent-app") is False
    assert _handout(bt).status_code == 403
    humankit.drive_consent("agent-app", "acme")          # restore (tuple + clears deny)


# --- re-acquiring the revoked grant is blocked even with a fresh token --------

def test_revoked_grant_cannot_be_reacquired(consented):
    humankit.drive_consent("agent-app", "acme")
    humankit.revoke_consent("agent-app", "acme")
    # a brand-new user token (fresh session) still cannot obtain the revoked grant:
    # the deny-list denies before the provider is contacted — no stale-token trick.
    r = _handout(_fresh_broker_token())
    assert r.status_code == 403, r.text
    humankit.drive_consent("agent-app", "acme")


# --- deny-list: propagation-free stop, independent of the tuple --------------

def test_denylist_refuses_even_with_stale_tuple(consented):
    humankit.drive_consent("agent-app", "acme")
    assert _can_use("agent-app") is True                  # tuple present
    _psql("INSERT INTO broker_denylist(agent,user_id,provider,reason,azp) "
          "VALUES('agent-app','alice','acme','test','pytest') "
          "ON CONFLICT (agent,user_id,COALESCE(provider,'')) DO NOTHING;")
    try:
        r = _handout(brokerkit.broker_token())
        assert r.status_code == 403 and r.json().get("error") == "revoked", r.text
    finally:
        _psql("DELETE FROM broker_denylist WHERE azp='pytest';")


def test_agent_wide_kill_denies_all_grants(consented):
    humankit.drive_consent("agent-app", "acme")
    _psql("INSERT INTO broker_denylist(agent,user_id,provider,reason,azp) "
          "VALUES('agent-app','alice',NULL,'agent-wide','pytest') "
          "ON CONFLICT (agent,user_id,COALESCE(provider,'')) DO NOTHING;")
    try:
        r = _handout(brokerkit.broker_token())            # null-provider entry denies acme too
        assert r.status_code == 403 and r.json().get("error") == "revoked", r.text
    finally:
        _psql("DELETE FROM broker_denylist WHERE azp='pytest';")


# --- honest in-flight residual -----------------------------------------------

def test_in_flight_residual_is_honest(consented):
    humankit.drive_consent("agent-app", "acme")
    r = _handout(brokerkit.broker_token())
    assert r.status_code == 200
    acme_at, ttl = r.json()["access_token"], r.json()["expires_in"]
    assert ttl <= 120                                     # bounded residual
    ui = httpx.get(f"{KEYCLOAK_URL}/realms/acme/protocol/openid-connect/userinfo",
                   headers={"Authorization": f"Bearer {acme_at}"}, timeout=10)
    assert ui.status_code == 200
    humankit.revoke_consent("agent-app", "acme")
    # the already-issued provider token still works at the mock provider (no
    # provider revocation) — reported honestly, not falsely claimed revoked.
    ui2 = httpx.get(f"{KEYCLOAK_URL}/realms/acme/protocol/openid-connect/userinfo",
                    headers={"Authorization": f"Bearer {acme_at}"}, timeout=10)
    assert ui2.status_code == 200, "the in-flight residual is real and must be honest"
    humankit.drive_consent("agent-app", "acme")


# --- the CAEP Security Event Token is emitted --------------------------------

def test_caep_set_emitted(consented):
    humankit.drive_consent("agent-app", "acme")
    n0 = len(httpx.get(f"{BROKER}/ssf/stream", timeout=10).json()["events"])
    humankit.revoke_consent("agent-app", "acme")
    events = httpx.get(f"{BROKER}/ssf/stream", timeout=10).json()["events"]
    assert len(events) > n0
    ev = events[-1]
    assert ev["type"] == "session-revoked" and ev["agent"] == "agent-app" and ev["user"] == "alice"
    claims = _claims(ev["set"])                           # the signed SET
    assert "session-revoked" in json.dumps(claims["events"])
    assert claims["sub_id"]["id"] == "agent:agent-app/user:alice"
    humankit.drive_consent("agent-app", "acme")
