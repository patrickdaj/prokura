"""M2 grant-acquisition spec: linking the mock acme provider seeds a grant, and
the broker imports the refresh credential into OpenBao with no credential ever
appearing in an API response."""

import httpx
import pytest

import brokerkit
from conftest import BROKER_BAO_TOKEN, DEMO_USER, OPENBAO_URL, link_acme


@pytest.fixture(scope="module")
def imported(keycloak, broker, openbao):
    link_acme(keycloak)  # idempotent: kc_action=idp_link:acme ceremony
    bt = brokerkit.broker_token()
    resp = brokerkit.import_grant(bt, "acme")
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_link_seeds_grant_offline(imported):
    # Linking the mock provider and importing yields a grant with scopes and a
    # refresh credential — no external network involved.
    assert imported["provider"] == "acme"
    assert imported["has_refresh"] is True
    assert imported["scopes"]  # e.g. "openid email profile"


def test_credential_lives_in_openbao_only(imported):
    r = httpx.get(f"{OPENBAO_URL}/v1/secret/data/grants/{DEMO_USER}/acme",
                  headers={"X-Vault-Token": BROKER_BAO_TOKEN}, timeout=10.0)
    assert r.status_code == 200, r.text
    data = r.json()["data"]["data"]
    assert data["kind"] == "refresh_token"
    assert len(data["credential"]) > 100


def test_import_response_has_no_credential(imported):
    # The import summary must never carry the refresh credential.
    blob = str(imported)
    assert "refresh_token" not in blob
    assert "credential" not in blob


def test_revoked_grant_is_unusable(imported):
    # grant-acquisition spec: after revocation, an agent request yields an error
    # and no provider token is issued. Runs last (module order) — it deletes the
    # grant, so keep it after the import/credential assertions above.
    from prokura import ProviderTokenError, get_provider_token

    brokerkit.seed_operator("agent-app", DEMO_USER)
    brokerkit.consent(brokerkit.user_token(), "agent-app", "acme")
    # sanity: hand-out works before revocation
    get_provider_token(brokerkit.broker_token(), "acme", base_url=brokerkit.BROKER_URL)

    r = httpx.post(f"{brokerkit.BROKER_URL}/v1/grants/acme/revoke",
                   headers={"Authorization": f"Bearer {brokerkit.user_token()}"}, timeout=15.0)
    assert r.status_code == 200, r.text

    # credential is gone from OpenBao
    ob = httpx.get(f"{OPENBAO_URL}/v1/secret/data/grants/{DEMO_USER}/acme",
                   headers={"X-Vault-Token": BROKER_BAO_TOKEN}, timeout=10.0)
    assert ob.status_code == 404
    # and a subsequent token request fails
    with pytest.raises(ProviderTokenError):
        get_provider_token(brokerkit.broker_token(), "acme", base_url=brokerkit.BROKER_URL)
