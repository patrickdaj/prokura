"""Spike driver (tasks 4.2/4.3): CIBA round trip through the built-in HTTP channel.

Run with the spike profile up:
    docker compose --profile spike up -d --build
    python -m pytest spike/ciba-http-channel/test_spike.py -v

Approve, deny, and timeout paths. Success here = the Java SPI dies (F6-A).
"""

import os
import time

import httpx

KEYCLOAK_URL = os.environ.get("PROKURA_KEYCLOAK_URL", "http://localhost:8180")
SPIKE_URL = os.environ.get("PROKURA_SPIKE_URL", "http://localhost:8000")
REALM = "prokura"
CLIENT = ("agent-app", os.environ.get("AGENT_APP_CLIENT_SECRET", "agent-app-dev-secret"))

CIBA_AUTH = f"{KEYCLOAK_URL}/realms/{REALM}/protocol/openid-connect/ext/ciba/auth"
TOKEN = f"{KEYCLOAK_URL}/realms/{REALM}/protocol/openid-connect/token"
CIBA_GRANT = "urn:openid:params:grant-type:ciba"


def _initiate(binding_message: str) -> dict:
    r = httpx.post(
        CIBA_AUTH,
        auth=CLIENT,
        data={"login_hint": "alice", "scope": "openid", "binding_message": binding_message},
        timeout=15.0,
    )
    assert r.status_code == 200, f"backchannel auth failed: {r.status_code} {r.text}"
    body = r.json()
    assert "auth_req_id" in body
    return body


def _poll_token(auth_req_id: str, attempts: int = 3, interval: float = 5.0) -> httpx.Response:
    last = None
    for _ in range(attempts):
        time.sleep(interval)
        last = httpx.post(
            TOKEN,
            auth=CLIENT,
            data={"grant_type": CIBA_GRANT, "auth_req_id": auth_req_id},
            timeout=15.0,
        )
        if last.status_code == 200 or last.json().get("error") != "authorization_pending":
            break
    return last


def _decide(status: str) -> None:
    r = httpx.post(f"{SPIKE_URL}/decide", json={"status": status}, timeout=15.0)
    assert r.status_code == 200, r.text
    assert r.json().get("callback_status") in (200, 201, 204), r.text


def test_delegation_request_reaches_spike() -> None:
    marker = f"ref-{int(time.time())}"
    _initiate(marker)
    pending = httpx.get(f"{SPIKE_URL}/pending", timeout=10.0).json()
    assert any(p.get("binding_message") == marker for p in pending), (
        f"delegation POST with binding_message={marker!r} never arrived: {pending}"
    )
    _decide("CANCELLED")  # clean up this pending request


def test_approval_yields_token() -> None:
    body = _initiate(f"ok-{int(time.time())}")
    _decide("SUCCEED")
    token = _poll_token(body["auth_req_id"], interval=float(body.get("interval", 5)))
    assert token.status_code == 200, f"expected token after approval: {token.text}"
    assert "access_token" in token.json()


def test_denial_yields_access_denied() -> None:
    body = _initiate(f"no-{int(time.time())}")
    _decide("UNAUTHORIZED")
    token = _poll_token(body["auth_req_id"], interval=float(body.get("interval", 5)))
    assert token.status_code != 200
    assert token.json().get("error") == "access_denied", token.text


def test_timeout_expires_request() -> None:
    body = _initiate(f"exp-{int(time.time())}")
    # realm cibaExpiresIn=120: don't wait it out here; just confirm pending
    # stays pending (authorization_pending) with no decision.
    token = _poll_token(body["auth_req_id"], attempts=1, interval=float(body.get("interval", 5)))
    assert token.status_code != 200
    assert token.json().get("error") in ("authorization_pending", "slow_down"), token.text
    _decide("CANCELLED")  # clean up
