"""M4 human-approval delta: the approval TRIGGER moves onto the resource server.
A sensitive call with no action token is refused with a 428 approval_required
challenge — and the tools-API registers the exact action it observed, so the
action that gets approved is the one the server saw, not one the agent described.
The M3 guarantees (hash-binding, single-use) are intact through the reactive path.
"""

import httpx
import pytest

import approvalkit as ak
from conftest import KEYCLOAK_URL, REALM
from prokura import exchange

AGENT, SECRET = "agent-app", "agent-app-dev-secret"


def tools_token(ut: str) -> str:
    """A token addressed to the tools-API (aud=agent-tools-api)."""
    return exchange(ut, "agent-tools-api", base_url=KEYCLOAK_URL, realm=REALM,
                    client_id=AGENT, client_secret=SECRET)


def attempt(tt: str, params: dict, c: httpx.Client, action_token: str | None = None) -> httpx.Response:
    body = dict(params)
    if action_token:
        body["action_token"] = action_token
    return c.post(f"{ak.TOOLS_URL}/tools/email/send",
                  headers={"Authorization": f"Bearer {tt}"}, json=body)


def subjects_in_mailpit(c: httpx.Client) -> list[str]:
    return [m.get("Subject") for m in c.get(f"{ak.MAILPIT_URL}/api/v1/messages").json().get("messages", [])]


@pytest.fixture(scope="module")
def tools(keycloak, mailpit):
    httpx.get(f"{ak.TOOLS_URL}/healthz", timeout=10.0).raise_for_status()
    httpx.get(f"{ak.APPROVAL_URL}/healthz", timeout=10.0).raise_for_status()


def test_unapproved_call_is_challenged_not_executed(tools):
    params = {"to": "boss@prokura.local", "subject": "Reactive unapproved probe", "body": "no"}
    with httpx.Client(timeout=20.0) as c:
        tt = tools_token(ak.user_token())
        r = attempt(tt, params, c)
        # 428 Precondition Required: approval must be satisfied first.
        assert r.status_code == 428, r.text
        j = r.json()
        assert j["error"] == "approval_required"
        assert j["ref"] and j["action_token"]
        # The action was NOT executed — nothing reached the sink.
        assert "Reactive unapproved probe" not in subjects_in_mailpit(c)


def _challenge_and_approve(params: dict, c: httpx.Client) -> tuple[str, str]:
    """Reactive path: attempt (server registers + challenges) → CIBA → approve.
    Returns (tools_token, action_token) ready for a retry."""
    ut = ak.user_token()
    tt = tools_token(ut)
    r = attempt(tt, params, c)
    assert r.status_code == 428, r.text
    ref, action_token = r.json()["ref"], r.json()["action_token"]
    auth_req_id = ak.ciba_init(ref, c)
    ak.wait_delegated(ref, ut, c)
    ak.decide(ut, ref, True, c)
    ak.poll_token(auth_req_id, c)
    return tt, action_token


def test_reactive_retry_executes_once_then_replay_refused(tools):
    params = {"to": "boss@prokura.local", "subject": "Reactive single-use", "body": "ok"}
    with httpx.Client(timeout=30.0) as c:
        tt, action_token = _challenge_and_approve(params, c)
        assert attempt(tt, params, c, action_token).status_code == 200
        # Single-use: the same action token cannot be replayed.
        assert attempt(tt, params, c, action_token).status_code == 409


def test_reactive_param_mismatch_refused(tools):
    # The server registered the action it OBSERVED; retrying with different params
    # than were approved is a hash mismatch — the approved action is the observed one.
    approved = {"to": "boss@prokura.local", "subject": "Reactive $10", "body": "ok"}
    with httpx.Client(timeout=30.0) as c:
        tt, action_token = _challenge_and_approve(approved, c)
        tampered = {**approved, "subject": "Reactive $10000"}
        assert attempt(tt, tampered, c, action_token).status_code == 409
        # The correctly-approved action still executes exactly once.
        assert attempt(tt, approved, c, action_token).status_code == 200
