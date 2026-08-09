"""M3 human-approval spec: notifications are inert doorbells (F7). A spoofed
publish changes no state and decisions happen only in the authenticated UI
session; a genuine notification leaks no action parameters. M7: the deep link
in the notification is now actually followable — humankit follows it."""

import json
import time

import httpx
import pytest

import approvalkit as ak
import humankit

NTFY = "http://localhost:8090"
PUB = ("prokura-approval", "prokura-approval-dev")  # dev publisher creds


@pytest.fixture(scope="module")
def stack(keycloak, ntfy):
    httpx.get(f"{ak.APPROVAL_URL}/healthz", timeout=10.0).raise_for_status()


def _pending_approval(c: httpx.Client) -> str:
    """Register (which also initiates the server-side ceremony; the delegation
    lands before /register returns) and return the ref."""
    ut = ak.user_token()
    params = {"to": "leak@prokura.local", "subject": "TOP-SECRET-SUBJECT",
              "body": "SECRET-BODY-TEXT"}
    ref, _ = ak.register(ut, "email.send", params, c)
    return ref


def test_notification_leaks_nothing(stack):
    with httpx.Client(timeout=20.0) as c:
        ref = _pending_approval(c)
        time.sleep(1)
        r = httpx.get(f"{NTFY}/{ak.topic_for('alice')}/json", params={"poll": "1", "since": "2m"},
                      auth=PUB, timeout=10.0)
        notifs = [json.loads(l) for l in r.text.strip().splitlines() if l.strip()]
        mine = [m for m in notifs if m.get("event") == "message" and ref in json.dumps(m)]
        assert mine, "notification for this approval not found"
        blob = json.dumps(mine[-1])
        assert ref in blob                                   # carries the reference
        for secret in ("TOP-SECRET-SUBJECT", "SECRET-BODY-TEXT", "leak@prokura.local"):
            assert secret not in blob, f"notification leaked {secret!r}"


def test_spoofed_publish_is_denied_and_inert(stack):
    with httpx.Client(timeout=20.0) as c:
        ref = _pending_approval(c)
        # an attacker cannot even publish to the deny-all topic
        spoof = httpx.post(f"{NTFY}/{ak.topic_for('alice')}", content="spoofed approval",
                           timeout=10.0)
        assert spoof.status_code == 403
        # the approval is unchanged: still decidable — and ONLY decidable — in
        # the human's authenticated session (the spoof moved nothing).
        result = humankit.drive_approval(ref, approve=False)
        assert "Denied" in result, result
        # a second visit shows it as already decided (single decision holds)
        again = humankit.drive_approval(ref)
        assert "Already" in again, again
