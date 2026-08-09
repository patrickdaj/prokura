"""M2 token-brokering spec: 'Refresh credentials never leave OpenBao'. Neither
the stored refresh credential nor a handed-out provider access token may appear
in the broker's logs — including on error paths."""

import subprocess

import pytest

import brokerkit
import humankit
from conftest import BROKER_BAO_TOKEN, DEMO_USER, OPENBAO_URL, link_acme

import httpx


@pytest.fixture(scope="module")
def stored_credential(keycloak, broker, openbao, openfga):
    link_acme(keycloak)
    brokerkit.import_grant(brokerkit.broker_token(), "acme")
    brokerkit.seed_operator("agent-app", DEMO_USER)
    humankit.drive_consent("agent-app", "acme")
    r = httpx.get(f"{OPENBAO_URL}/v1/secret/data/grants/{DEMO_USER}/acme",
                  headers={"X-Vault-Token": BROKER_BAO_TOKEN}, timeout=10.0)
    return r.json()["data"]["data"]["credential"]


def _broker_logs() -> str:
    return subprocess.run(
        ["docker", "compose", "logs", "token-broker"],
        capture_output=True, text=True, timeout=30,
    ).stdout


def test_refresh_credential_absent_from_logs(stored_credential):
    # Exercise import + a hand-out + an error path, then scan the logs.
    from prokura import get_provider_token
    from conftest import BROKER_URL
    get_provider_token(brokerkit.broker_token(), "acme", base_url=BROKER_URL)
    httpx.post(f"{BROKER_URL}/v1/tokens/acme",
               headers={"Authorization": f"Bearer {brokerkit.broker_token()}",
                        "Content-Type": "application/json"},
               json={"scopes": ["repo:write"]}, timeout=15.0)  # error path
    logs = _broker_logs()
    assert stored_credential not in logs, "refresh credential leaked into broker logs"
