"""Smoke 3.2: OIDC Authorization Code + PKCE login against the prokura realm.

Drives Keycloak's real login form the way a browser would (no direct-access
grants — the realm disables them), then exchanges the code with a PKCE
verifier via the public smoke-cli client.

Cookies are handled manually: Keycloak marks its cookies Secure even in
plain-HTTP dev mode (browsers treat localhost as a secure context), and
Python's http.cookiejar refuses to replay Secure/Version=1 cookies over
http — so the test carries them explicitly.
"""

import base64
import hashlib
import html
import json
import re
import secrets

import httpx

from conftest import DEMO_PASSWORD, DEMO_USER, REALM

REDIRECT_URI = "http://127.0.0.1/cb"


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _decode_jwt_payload(token: str) -> dict:
    payload = token.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    return json.loads(base64.urlsafe_b64decode(payload))


def test_authorization_code_pkce_login(keycloak: str) -> None:
    verifier = _b64url(secrets.token_bytes(32))
    challenge = _b64url(hashlib.sha256(verifier.encode()).digest())

    with httpx.Client(follow_redirects=False, timeout=15.0) as client:
        auth = client.get(
            f"{keycloak}/realms/{REALM}/protocol/openid-connect/auth",
            params={
                "client_id": "smoke-cli",
                "response_type": "code",
                "redirect_uri": REDIRECT_URI,
                "scope": "openid",
                "state": "smoke",
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            },
        )
        assert auth.status_code == 200, auth.text[:500]

        cookies = dict(
            sc.split(";", 1)[0].split("=", 1)
            for sc in auth.headers.get_list("set-cookie")
        )
        match = re.search(r'id="kc-form-login"[^>]*action="([^"]+)"', auth.text)
        assert match, "kc-form-login action not found in Keycloak login page"
        form_action = html.unescape(match.group(1))

        submit = client.post(
            form_action,
            data={"username": DEMO_USER, "password": DEMO_PASSWORD},
            headers={"Cookie": "; ".join(f"{k}={v}" for k, v in cookies.items())},
        )
        assert submit.status_code == 302, f"login failed: {submit.status_code} {submit.text[:300]}"
        location = submit.headers["location"]
        assert location.startswith(REDIRECT_URI), location
        code = httpx.URL(location).params["code"]

        token = client.post(
            f"{keycloak}/realms/{REALM}/protocol/openid-connect/token",
            data={
                "grant_type": "authorization_code",
                "client_id": "smoke-cli",
                "code": code,
                "redirect_uri": REDIRECT_URI,
                "code_verifier": verifier,
            },
        )
        assert token.status_code == 200, token.text

    body = token.json()
    claims = _decode_jwt_payload(body["access_token"])
    assert claims["iss"].endswith(f"/realms/{REALM}")
    assert claims["sub"], "user subject missing from access token"
    assert claims["azp"] == "smoke-cli"
    # identity-delegation spec: Keycloak-issued tokens bounded at 15 minutes
    assert body["expires_in"] <= 900
