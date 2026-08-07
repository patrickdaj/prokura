"""Smoke 3.2: OIDC Authorization Code + PKCE login against the prokura realm.

The flow itself lives in conftest.drive_login (shared with telemetry tests);
this test asserts the identity-delegation spec's claims about the result.
"""

import base64
import json

from conftest import REALM, drive_login


def _decode_jwt_payload(token: str) -> dict:
    payload = token.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    return json.loads(base64.urlsafe_b64decode(payload))


def test_authorization_code_pkce_login(keycloak: str) -> None:
    body = drive_login(keycloak)
    claims = _decode_jwt_payload(body["access_token"])
    assert claims["iss"].endswith(f"/realms/{REALM}")
    assert claims["sub"], "user subject missing from access token"
    assert claims["azp"] == "smoke-cli"
    # identity-delegation spec: Keycloak-issued tokens bounded at 15 minutes
    assert body["expires_in"] <= 900
