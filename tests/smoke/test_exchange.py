"""M1: RFC 8693 delegated token exchange via the prokura SDK (agent-sdk spec).

Logs in through the confidential agent-app client (so the user token is
exchangeable), then exercises exchange() to both audiences and the denial path.
"""

import base64
import json

import pytest

from conftest import DEMO_USER, KEYCLOAK_URL, REALM, drive_login
from prokura import ExchangeDenied, exchange

AGENT = "agent-app"
SECRET = "agent-app-dev-secret"


def claims(token: str) -> dict:
    p = token.split(".")[1]
    p += "=" * (-len(p) % 4)
    return json.loads(base64.urlsafe_b64decode(p))


@pytest.fixture(scope="module")
def user_token(keycloak: str) -> str:
    return drive_login(keycloak, client_id=AGENT, client_secret=SECRET)["access_token"]


def _exchange(user_token: str, audience: str, scopes=()):
    return exchange(user_token, audience, scopes,
                    base_url=KEYCLOAK_URL, realm=REALM, client_id=AGENT, client_secret=SECRET)


def test_exchange_to_tools_audience(user_token: str) -> None:
    tok = _exchange(user_token, "agent-tools-api", ["tools:read"])
    c = claims(tok)
    assert c["azp"] == AGENT
    assert c["sub"] == claims(user_token)["sub"]  # attributable to user-via-agent
    aud = c["aud"] if isinstance(c["aud"], list) else [c["aud"]]
    assert "agent-tools-api" in aud
    assert "tools:read" in c["scope"].split()
    assert "tools:execute" not in c["scope"].split()  # scope-down: only what was asked


def test_exchange_to_broker_audience(user_token: str) -> None:
    tok = _exchange(user_token, "token-broker")
    aud = claims(tok)["aud"]
    aud = aud if isinstance(aud, list) else [aud]
    assert "token-broker" in aud  # satisfies the broker's F2-A audience check


def test_unpermitted_audience_raises(user_token: str) -> None:
    # an audience agent-app has no client scope for and cannot mint → denied
    with pytest.raises(ExchangeDenied) as ei:
        _exchange(user_token, "nonexistent-api")
    assert "nonexistent-api" in str(ei.value)


def test_no_token_in_logs(user_token: str, caplog) -> None:
    import logging
    with caplog.at_level(logging.DEBUG):
        _exchange(user_token, "token-broker")
    assert user_token not in caplog.text
