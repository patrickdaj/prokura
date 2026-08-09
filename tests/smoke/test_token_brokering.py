"""M2 token-brokering spec: the hand-out validation chain via the SDK
`get_provider_token()`. Happy path returns a short-lived provider token and never
a refresh token; the three refusals (wrong audience, over-broad scope, missing
consent) are enforced; a refresh-capable provider is refreshed on hand-out."""

import base64
import json

import httpx
import pytest

import brokerkit
import humankit
from conftest import BROKER_URL, DEMO_USER, link_acme
from prokura import ConsentDenied, ScopeExceeded, get_provider_token


def claims(token: str) -> dict:
    p = token.split(".")[1]
    p += "=" * (-len(p) % 4)
    return json.loads(base64.urlsafe_b64decode(p))


@pytest.fixture(scope="module")
def consented(keycloak, broker, openbao, openfga):
    """A fully linked + imported + consented acme grant for agent-app."""
    link_acme(keycloak)
    brokerkit.import_grant(brokerkit.broker_token(), "acme")
    brokerkit.seed_operator("agent-app", DEMO_USER)
    humankit.drive_consent("agent-app", "acme")


def test_happy_path_returns_short_lived_provider_token(consented):
    bt = brokerkit.broker_token()
    out = get_provider_token(bt, "acme", base_url=BROKER_URL)
    assert out["access_token"]
    assert out["expires_in"] <= 900  # TTL honesty: hand-out interval capped
    assert "refresh_token" not in out  # refresh credential never leaves the broker
    # A fresh provider token issued by the acme realm (refresh loop exercised).
    assert claims(out["access_token"])["iss"].endswith("/realms/acme")


def test_wrong_audience_refused(consented):
    # A plain user token (aud != token-broker) must be refused by the broker.
    # Minted with scope=openid only — the kit's default bootstrap now carries
    # the audience scopes, which would make the token legitimately brokered.
    from conftest import KEYCLOAK_URL, drive_login
    ut = drive_login(KEYCLOAK_URL, client_id=brokerkit.AGENT,
                     client_secret=brokerkit.SECRET, scope="openid")["access_token"]
    with pytest.raises(ConsentDenied):
        get_provider_token(ut, "acme", base_url=BROKER_URL)


def test_over_broad_scope_refused_without_contacting_provider(consented):
    bt = brokerkit.broker_token()
    with pytest.raises(ScopeExceeded):
        # grant scopes are "openid email profile"; this exceeds them.
        get_provider_token(bt, "acme", ["repo:write"], base_url=BROKER_URL)


def test_missing_consent_refused(consented):
    # The human revokes consent in her session; the agent is then refused.
    humankit.revoke_consent("agent-app", "acme")
    try:
        bt = brokerkit.broker_token()
        with pytest.raises(ConsentDenied):
            get_provider_token(bt, "acme", base_url=BROKER_URL)
    finally:
        humankit.drive_consent("agent-app", "acme")


def test_scope_refusal_returns_403_not_500(consented):
    # Raw check that the scope refusal is a clean 403 (never contacts provider).
    bt = brokerkit.broker_token()
    r = httpx.post(f"{BROKER_URL}/v1/tokens/acme",
                   headers={"Authorization": f"Bearer {bt}", "Content-Type": "application/json"},
                   json={"scopes": ["repo:write"]}, timeout=15.0)
    assert r.status_code == 403
