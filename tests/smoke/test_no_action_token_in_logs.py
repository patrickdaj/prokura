"""M3: neither the single-use action token's secret nor the CIBA access token
may appear in the approval or tools-api service logs, including error paths."""

import subprocess

import httpx
import pytest

import approvalkit as ak


@pytest.fixture(scope="module")
def stack(keycloak, mailpit):
    httpx.get(f"{ak.APPROVAL_URL}/healthz", timeout=10.0).raise_for_status()
    httpx.get(f"{ak.TOOLS_URL}/healthz", timeout=10.0).raise_for_status()


def _logs(service: str) -> str:
    return subprocess.run(["docker", "compose", "logs", service],
                          capture_output=True, text=True, timeout=30).stdout


def test_no_token_secret_in_service_logs(stack):
    params = {"to": "boss@prokura.local", "subject": "Log scan", "body": "ok"}
    with httpx.Client(timeout=20.0) as c:
        ciba, action_token = ak.approved_tokens("email.send", params, c)
        ak.send_email(ciba, action_token, params, c)                 # success path
        ak.send_email(ciba, action_token, params, c)                 # error (replay) path
        secret = action_token.split(".", 1)[1]                       # the sensitive half
        logs = _logs("approval") + _logs("tools-api")
        assert secret not in logs, "action-token secret leaked into logs"
        assert ciba not in logs, "CIBA access token leaked into logs"
