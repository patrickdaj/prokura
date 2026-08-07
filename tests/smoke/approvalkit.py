"""Shared helpers for the M3 human-approval smoke tests: register a payload,
drive CIBA, decide in the trusted surface, poll, and call the gated tool."""

import base64
import hashlib
import json
import time

import httpx

from conftest import KEYCLOAK_URL, REALM, drive_login

APPROVAL_URL = "http://localhost:8120"
TOOLS_URL = "http://localhost:8130"
MAILPIT_URL = "http://localhost:8025"
AGENT, SECRET = "agent-app", "agent-app-dev-secret"
CIBA_GRANT = "urn:openid:params:grant-type:ciba"
TOPIC_SALT = "prokura-approval-dev-salt"  # matches the approval service default


def claims(t: str) -> dict:
    p = t.split(".")[1]; p += "=" * (-len(p) % 4)
    return json.loads(base64.urlsafe_b64decode(p))


def user_token() -> str:
    return drive_login(KEYCLOAK_URL, client_id=AGENT, client_secret=SECRET)["access_token"]


def register(ut: str, action: str, params: dict, c: httpx.Client) -> tuple[str, str]:
    r = c.post(f"{APPROVAL_URL}/register", headers={"Authorization": f"Bearer {ut}"},
               json={"action": action, "params": params})
    r.raise_for_status()
    return r.json()["ref"], r.json()["action_token"]


def ciba_init(ref: str, c: httpx.Client, requested_expiry: int | None = None) -> str:
    data = {"client_id": AGENT, "client_secret": SECRET, "scope": "openid tools-audience",
            "login_hint": "alice", "binding_message": ref}
    if requested_expiry:
        data["requested_expiry"] = str(requested_expiry)
    r = c.post(f"{KEYCLOAK_URL}/realms/{REALM}/protocol/openid-connect/ext/ciba/auth", data=data)
    r.raise_for_status()
    return r.json()["auth_req_id"]


def wait_delegated(ref: str, ut: str, c: httpx.Client, timeout: float = 10.0) -> str:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        s = c.get(f"{APPROVAL_URL}/approval/{ref}", headers={"Authorization": f"Bearer {ut}"})
        if s.status_code == 200 and s.json().get("status") == "delegated":
            return "delegated"
        time.sleep(0.5)
    return "not-delegated"


def decide(ut: str, ref: str, approve: bool, c: httpx.Client) -> httpx.Response:
    return c.post(f"{APPROVAL_URL}/approval/{ref}/decide", headers={"Authorization": f"Bearer {ut}"},
                  json={"decision": "approve" if approve else "deny"})


def poll_token(auth_req_id: str, c: httpx.Client, tries: int = 8) -> tuple[str | None, str]:
    for _ in range(tries):
        r = c.post(f"{KEYCLOAK_URL}/realms/{REALM}/protocol/openid-connect/token",
                   data={"grant_type": CIBA_GRANT, "auth_req_id": auth_req_id,
                         "client_id": AGENT, "client_secret": SECRET})
        if r.status_code == 200:
            return r.json()["access_token"], "ok"
        err = r.json().get("error", "") if r.headers.get("content-type","").startswith("application/json") else r.text[:80]
        if err not in ("authorization_pending", "slow_down"):
            return None, err
        time.sleep(2)
    return None, "timeout-polling"


def send_email(ciba_token: str, action_token: str, params: dict, c: httpx.Client) -> httpx.Response:
    return c.post(f"{TOOLS_URL}/tools/email/send", headers={"Authorization": f"Bearer {ciba_token}"},
                  json={"action_token": action_token, **params})


def topic_for(user: str = "alice") -> str:
    d = hashlib.sha256(f"{TOPIC_SALT}:{user}".encode()).hexdigest()
    return f"prokura-approvals-{d[:20]}"


def approved_tokens(action: str, params: dict, c: httpx.Client) -> tuple[str, str]:
    """Full happy path helper: returns (ciba_token, action_token) after approval."""
    ut = user_token()
    ref, action_token = register(ut, action, params, c)
    auth_req_id = ciba_init(ref, c)
    wait_delegated(ref, ut, c)
    decide(ut, ref, True, c)
    ciba_token, status = poll_token(auth_req_id, c)
    assert ciba_token, f"no token: {status}"
    return ciba_token, action_token
