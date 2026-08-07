"""M3 human-approval spec: CIBA-gated sensitive action with hash-verified,
single-use execution — plus denial and timeout aborting cleanly."""

import threading
import time

import httpx
import pytest

import approvalkit as ak
from conftest import KEYCLOAK_URL, REALM


@pytest.fixture(scope="module")
def stack(keycloak, mailpit):
    ak.wait_delegated  # ensure services imported; approval/tools health implied by traffic
    httpx.get(f"{ak.APPROVAL_URL}/healthz", timeout=10.0).raise_for_status()
    httpx.get(f"{ak.TOOLS_URL}/healthz", timeout=10.0).raise_for_status()


def test_approved_action_executes_once(stack):
    params = {"to": "boss@prokura.local", "subject": "Approved report", "body": "ok"}
    with httpx.Client(timeout=20.0) as c:
        ciba, action_token = ak.approved_tokens("email.send", params, c)
        assert ak.claims(ciba)["aud"] == "agent-tools-api"  # M1 audience defense
        r = ak.send_email(ciba, action_token, params, c)
        assert r.status_code == 200, r.text
        # the mail landed in the Mailpit sink
        msgs = c.get(f"{ak.MAILPIT_URL}/api/v1/messages").json().get("messages", [])
        assert "Approved report" in [m.get("Subject") for m in msgs]


def test_replay_refused(stack):
    params = {"to": "boss@prokura.local", "subject": "Replay probe", "body": "ok"}
    with httpx.Client(timeout=20.0) as c:
        ciba, action_token = ak.approved_tokens("email.send", params, c)
        assert ak.send_email(ciba, action_token, params, c).status_code == 200
        # second use of the single-use action token is refused
        assert ak.send_email(ciba, action_token, params, c).status_code == 409


def test_parameter_mismatch_refused(stack):
    approved = {"to": "boss@prokura.local", "subject": "Send $10", "body": "ok"}
    with httpx.Client(timeout=20.0) as c:
        ciba, action_token = ak.approved_tokens("email.send", approved, c)
        # execute with params that differ from what was approved -> hash mismatch
        tampered = {**approved, "subject": "Send $10000"}
        r = ak.send_email(ciba, action_token, tampered, c)
        assert r.status_code == 409, r.text
        # and the approved action can no longer run either (nothing was consumed wrongly)
        # (the tampered attempt did not consume; the correct one still works once)
        assert ak.send_email(ciba, action_token, approved, c).status_code == 200


def test_denial_aborts_cleanly(stack):
    params = {"to": "boss@prokura.local", "subject": "Denied", "body": "no"}
    with httpx.Client(timeout=20.0) as c:
        ut = ak.user_token()
        ref, action_token = ak.register(ut, "email.send", params, c)
        auth_req_id = ak.ciba_init(ref, c)
        ak.wait_delegated(ref, ut, c)
        ak.decide(ut, ref, False, c)  # deny
        token, err = ak.poll_token(auth_req_id, c)
        assert token is None and err == "access_denied", err


def test_timeout_aborts_cleanly(stack):
    params = {"to": "boss@prokura.local", "subject": "Timeout", "body": "no"}
    with httpx.Client(timeout=30.0) as c:
        ut = ak.user_token()
        ref, _ = ak.register(ut, "email.send", params, c)
        auth_req_id = ak.ciba_init(ref, c)  # realm pins a 30 s CIBA window
        # never decide; poll until Keycloak expires the request
        token, err = None, ""
        for _ in range(20):
            r = c.post(f"{KEYCLOAK_URL}/realms/{REALM}/protocol/openid-connect/token",
                       data={"grant_type": ak.CIBA_GRANT, "auth_req_id": auth_req_id,
                             "client_id": ak.AGENT, "client_secret": ak.SECRET})
            if r.status_code == 200:
                token = "issued"; break
            err = r.json().get("error", "")
            if err not in ("authorization_pending", "slow_down"):
                break
            time.sleep(2)
        assert token is None and err in ("expired_token", "invalid_grant"), f"{token} / {err}"


def test_sdk_require_approval_round_trip(stack):
    """The SDK helper blocks on the poll; approve in a background thread."""
    from prokura import require_approval
    params = {"to": "boss@prokura.local", "subject": "SDK path", "body": "ok"}

    ut0 = ak.user_token()
    with httpx.Client(timeout=20.0) as c0:
        seen = {a["ref"] for a in c0.get(f"{ak.APPROVAL_URL}/my/approvals",
                headers={"Authorization": f"Bearer {ut0}"}).json()}

    def approve_when_ready():
        with httpx.Client(timeout=20.0) as c:
            ut = ak.user_token()
            for _ in range(30):  # approve only a NEW delegated approval, not a stale one
                mine = c.get(f"{ak.APPROVAL_URL}/my/approvals",
                             headers={"Authorization": f"Bearer {ut}"}).json()
                fresh = [a for a in mine if a["status"] == "delegated"
                         and a["action"] == "email.send" and a["ref"] not in seen]
                if fresh:
                    ak.decide(ut, fresh[0]["ref"], True, c)
                    return
                time.sleep(1)

    t = threading.Thread(target=approve_when_ready)
    t.start()
    out = require_approval(ak.user_token(), "email.send", params,
                           base_url=KEYCLOAK_URL, realm=REALM,
                           client_id=ak.AGENT, client_secret=ak.SECRET,
                           approval_url=ak.APPROVAL_URL)
    t.join(timeout=5)
    assert out["action_token"].startswith("apr-")
    with httpx.Client(timeout=20.0) as c:
        assert ak.send_email(out["ciba_token"], out["action_token"], params, c).status_code == 200
