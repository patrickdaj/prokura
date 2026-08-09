"""M2 per-agent-consent spec: the broker is the sole can_use writer, enforces
operator == owner, and consent is per-agent and revocable."""

import httpx
import pytest

import brokerkit
import humankit
from conftest import BROKER_URL, DEMO_USER, link_acme


@pytest.fixture(scope="module")
def grant(keycloak, broker, openbao, openfga):
    link_acme(keycloak)
    brokerkit.import_grant(brokerkit.broker_token(), "acme")


def _can_use(agent: str) -> bool:
    r = httpx.post(f"{brokerkit.OPENFGA_URL}/stores/{brokerkit.store_id()}/check",
                   json={"tuple_key": {"user": f"agent:{agent}", "relation": "can_use",
                                       "object": f"grant:{DEMO_USER}/acme"}}, timeout=10.0)
    r.raise_for_status()
    return bool(r.json().get("allowed"))


def test_consent_grants_exactly_one_agent(grant):
    brokerkit.seed_operator("agent-app", DEMO_USER)
    # The HUMAN consents on the real surface in her authenticated session (M7).
    ok, text = humankit.drive_consent("agent-app", "acme")
    assert ok, text
    assert _can_use("agent-app") is True
    # A different, unconsented agent still fails the check (no implicit consent).
    assert _can_use("some-other-agent") is False


def test_cross_user_write_refused(grant):
    # An agent operated by a different user cannot be consented onto alice's
    # grant — even by alice herself, in her real session.
    brokerkit.seed_operator("evil-agent", "mallory")
    ok, text = humankit.drive_consent("evil-agent", "acme")
    assert not ok and "consent_refused" in text, text
    assert _can_use("evil-agent") is False


def test_consent_revocation(grant):
    brokerkit.seed_operator("agent-app", DEMO_USER)
    humankit.drive_consent("agent-app", "acme")
    assert _can_use("agent-app") is True
    out = humankit.revoke_consent("agent-app", "acme")
    assert out["status"] == 200, out
    assert _can_use("agent-app") is False
    # re-consent to leave the grant usable for other test modules
    humankit.drive_consent("agent-app", "acme")
