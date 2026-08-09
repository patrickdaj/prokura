"""M3 human-approval spec through the M7 party boundaries: the ceremony is
initiated and completed by the approval service (ADR-0022); the human decides
in an authenticated browser session (humankit — the labeled simulated human);
the agent's whole role is 428 → wait → retry. Hash-binding and single-use are
intact through the new boundaries."""

import httpx
import pytest

import approvalkit as ak
import humankit


@pytest.fixture(scope="module")
def stack(keycloak, mailpit):
    httpx.get(f"{ak.APPROVAL_URL}/healthz", timeout=10.0).raise_for_status()
    httpx.get(f"{ak.TOOLS_URL}/healthz", timeout=10.0).raise_for_status()


def test_approved_action_executes_once(stack):
    params = {"to": "boss@prokura.local", "subject": "Approved report", "body": "ok"}
    with httpx.Client(timeout=30.0) as c:
        tt, action_token = ak.approved_tokens("email.send", params, c)
        assert ak.claims(tt)["aud"] == "agent-tools-api"  # M1 audience defense
        r = ak.send_email(tt, action_token, params, c)
        assert r.status_code == 200, r.text
        # the mail landed in the Mailpit sink
        msgs = c.get(f"{ak.MAILPIT_URL}/api/v1/messages").json().get("messages", [])
        assert "Approved report" in [m.get("Subject") for m in msgs]


def test_replay_refused(stack):
    params = {"to": "boss@prokura.local", "subject": "Replay probe", "body": "ok"}
    with httpx.Client(timeout=30.0) as c:
        tt, action_token = ak.approved_tokens("email.send", params, c)
        assert ak.send_email(tt, action_token, params, c).status_code == 200
        # second use of the single-use action token is refused
        assert ak.send_email(tt, action_token, params, c).status_code == 409


def test_parameter_mismatch_refused(stack):
    approved = {"to": "boss@prokura.local", "subject": "Send $10", "body": "ok"}
    with httpx.Client(timeout=30.0) as c:
        tt, action_token = ak.approved_tokens("email.send", approved, c)
        # execute with params that differ from what was approved -> hash mismatch
        tampered = {**approved, "subject": "Send $10000"}
        r = ak.send_email(tt, action_token, tampered, c)
        assert r.status_code == 409, r.text
        # the tampered attempt did not consume; the correct one still works once
        assert ak.send_email(tt, action_token, approved, c).status_code == 200


def test_denial_aborts_cleanly(stack):
    params = {"to": "boss@prokura.local", "subject": "Denied", "body": "no"}
    with httpx.Client(timeout=30.0) as c:
        tt = ak.tools_token()
        r = ak.attempt(tt, params, c)
        assert r.status_code == 428, r.text
        j = r.json()
        result = humankit.drive_approval(j["ref"], approve=False)
        assert "Denied" in result, result
        # the retry cannot execute a denied action
        r = ak.send_email(tt, j["action_token"], params, c)
        assert r.status_code == 403 and r.json()["error"] == "not_approved", r.text


def test_undecided_retry_refused(stack):
    # Retrying before any human decision is refused — waiting is the agent's
    # only move (the old client-driven poll/timeout leg no longer exists).
    params = {"to": "boss@prokura.local", "subject": "Impatient", "body": "no"}
    with httpx.Client(timeout=30.0) as c:
        tt = ak.tools_token()
        r = ak.attempt(tt, params, c)
        assert r.status_code == 428, r.text
        r = ak.send_email(tt, r.json()["action_token"], params, c)
        assert r.status_code == 403 and r.json()["error"] == "not_approved", r.text


def test_foreign_user_token_cannot_consume(stack):
    # An approval belongs to the user whose verified claims registered it; a
    # different user's token presenting the action token is refused (the M7
    # /consume proof binds consumption to the approved user).
    params = {"to": "boss@prokura.local", "subject": "Wrong subject probe", "body": "x"}
    with httpx.Client(timeout=30.0) as c:
        tt_alice, action_token = ak.approved_tokens("email.send", params, c)
        from conftest import KEYCLOAK_URL, drive_login
        bob = drive_login(KEYCLOAK_URL, client_id=ak.AGENT, client_secret=ak.SECRET,
                          user="bob",
                          scope="openid tools-audience broker-audience")["access_token"]
        from prokura import exchange
        from conftest import REALM
        tt_bob = exchange(bob, "agent-tools-api", base_url=KEYCLOAK_URL, realm=REALM,
                          client_id=ak.AGENT, client_secret=ak.SECRET)
        r = ak.send_email(tt_bob, action_token, params, c)
        assert r.status_code == 403 and r.json()["error"] == "wrong_subject", r.text
        # alice's own retry still works exactly once
        assert ak.send_email(tt_alice, action_token, params, c).status_code == 200


def _age_row(ref: str, seconds: int) -> None:
    """Test scaffolding: age an approval past the backchannel window in the DB
    (the alternative is a 600 s sleep)."""
    import subprocess
    subprocess.run(
        ["docker", "exec", "prokura-postgres-1", "psql", "-U", "prokura", "-d", "prokura",
         "-c", f"UPDATE approvals SET created_at = now() - interval '{seconds} seconds' "
               f"WHERE ref = '{ref}'"],
        check=True, capture_output=True, timeout=30)


def test_expired_approval_cannot_be_decided_or_consumed(stack):
    # The backchannel window elapsing with no decision expires the request: the
    # UI shows it as expired, a late decision is refused, and the agent's retry
    # is refused as expired (spec: "Denial and timeout abort cleanly").
    params = {"to": "boss@prokura.local", "subject": "Too late", "body": "no"}
    with httpx.Client(timeout=30.0) as c:
        tt = ak.tools_token()
        r = ak.attempt(tt, params, c)
        assert r.status_code == 428, r.text
        j = r.json()
        _age_row(j["ref"], 700)
        result = humankit.drive_approval(j["ref"], approve=True)
        assert "expired" in result.lower(), result
        r = ak.send_email(tt, j["action_token"], params, c)
        assert r.status_code == 403 and r.json()["error"] == "expired", r.text


def test_wrong_user_cannot_decide(stack):
    # bob's authenticated session cannot even see alice's approval, let alone
    # decide it — the surface 404s a foreign ref.
    params = {"to": "boss@prokura.local", "subject": "Not bobs business", "body": "x"}
    with httpx.Client(timeout=30.0) as c:
        tt = ak.tools_token()
        r = ak.attempt(tt, params, c)
        assert r.status_code == 428, r.text
        j = r.json()
        result = humankit.drive_approval(j["ref"], user="bob")
        assert "not found" in result.lower(), result
        # alice can still decide it — the approval survived bob's visit intact
        result = humankit.drive_approval(j["ref"], user="alice", approve=False)
        assert "Denied" in result, result
