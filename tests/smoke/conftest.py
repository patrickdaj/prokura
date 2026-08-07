"""Smoke-test fixtures: service endpoints and stack-readiness gates.

All endpoints/credentials are the documented non-production defaults from
.env.example; override via environment variables when they differ.
"""

import os
import time

import httpx
import pytest

KEYCLOAK_URL = os.environ.get("PROKURA_KEYCLOAK_URL", "http://localhost:8180")
KEYCLOAK_HEALTH_URL = os.environ.get("PROKURA_KEYCLOAK_HEALTH_URL", "http://localhost:9000")
OPENFGA_URL = os.environ.get("PROKURA_OPENFGA_URL", "http://localhost:8081")
OPENBAO_URL = os.environ.get("PROKURA_OPENBAO_URL", "http://localhost:8200")
NTFY_URL = os.environ.get("PROKURA_NTFY_URL", "http://localhost:8090")
MAILPIT_URL = os.environ.get("PROKURA_MAILPIT_URL", "http://localhost:8025")
LGTM_URL = os.environ.get("PROKURA_LGTM_URL", "http://localhost:3001")
MAILPIT_SMTP = ("localhost", int(os.environ.get("PROKURA_MAILPIT_SMTP_PORT", "1025")))

REALM = "prokura"
DEMO_USER = os.environ.get("DEMO_USER", "alice")
DEMO_PASSWORD = os.environ.get("DEMO_PASSWORD", "alice")
BROKER_BAO_TOKEN = os.environ.get("PROKURA_BROKER_BAO_TOKEN", "prokura-broker-dev-token")
FGA_STORE_NAME = os.environ.get("FGA_STORE_NAME", "prokura")


def wait_http(url: str, ok=lambda r: r.status_code < 500, timeout: float = 120.0) -> None:
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        try:
            r = httpx.get(url, timeout=5.0)
            if ok(r):
                return
            last = f"HTTP {r.status_code}"
        except Exception as e:  # noqa: BLE001 - report any connection failure
            last = repr(e)
        time.sleep(2)
    pytest.fail(f"service at {url} not ready within {timeout}s (last: {last})")


@pytest.fixture(scope="session")
def keycloak() -> str:
    wait_http(f"{KEYCLOAK_HEALTH_URL}/health/ready", ok=lambda r: r.status_code == 200)
    wait_http(f"{KEYCLOAK_URL}/realms/{REALM}/.well-known/openid-configuration",
              ok=lambda r: r.status_code == 200)
    return KEYCLOAK_URL


@pytest.fixture(scope="session")
def openfga() -> str:
    wait_http(f"{OPENFGA_URL}/healthz", ok=lambda r: r.status_code == 200)
    return OPENFGA_URL


@pytest.fixture(scope="session")
def openbao() -> str:
    wait_http(f"{OPENBAO_URL}/v1/sys/health", ok=lambda r: r.status_code == 200)
    return OPENBAO_URL


@pytest.fixture(scope="session")
def ntfy() -> str:
    wait_http(f"{NTFY_URL}/v1/health", ok=lambda r: r.status_code == 200)
    return NTFY_URL


@pytest.fixture(scope="session")
def mailpit() -> str:
    wait_http(f"{MAILPIT_URL}/api/v1/info", ok=lambda r: r.status_code == 200)
    return MAILPIT_URL


def drive_login(keycloak: str) -> dict:
    """Run the full Authorization Code + PKCE flow as a browser would; returns
    the token response. Shared by the login smoke test and telemetry tests
    (which need real traffic to observe). Cookies are handled manually —
    Keycloak marks cookies Secure even on plain-HTTP dev and http.cookiejar
    refuses to replay them."""
    import base64
    import hashlib
    import html as html_mod
    import re
    import secrets

    b64 = lambda b: base64.urlsafe_b64encode(b).rstrip(b"=").decode()  # noqa: E731
    verifier = b64(secrets.token_bytes(32))
    challenge = b64(hashlib.sha256(verifier.encode()).digest())
    redirect_uri = "http://127.0.0.1/cb"

    with httpx.Client(follow_redirects=False, timeout=15.0) as client:
        auth = client.get(
            f"{keycloak}/realms/{REALM}/protocol/openid-connect/auth",
            params={
                "client_id": "smoke-cli",
                "response_type": "code",
                "redirect_uri": redirect_uri,
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
        submit = client.post(
            html_mod.unescape(match.group(1)),
            data={"username": DEMO_USER, "password": DEMO_PASSWORD},
            headers={"Cookie": "; ".join(f"{k}={v}" for k, v in cookies.items())},
        )
        assert submit.status_code == 302, f"login failed: {submit.status_code} {submit.text[:300]}"
        location = submit.headers["location"]
        assert location.startswith(redirect_uri), location
        token = client.post(
            f"{keycloak}/realms/{REALM}/protocol/openid-connect/token",
            data={
                "grant_type": "authorization_code",
                "client_id": "smoke-cli",
                "code": httpx.URL(location).params["code"],
                "redirect_uri": redirect_uri,
                "code_verifier": verifier,
            },
        )
        assert token.status_code == 200, token.text
        return token.json()


@pytest.fixture(scope="session")
def fga_store_id(openfga: str) -> str:
    """Discover the store created by openfga-init by name."""
    r = httpx.get(f"{openfga}/stores", timeout=10.0)
    r.raise_for_status()
    stores = [s for s in r.json().get("stores", []) if s["name"] == FGA_STORE_NAME]
    assert stores, f"no OpenFGA store named {FGA_STORE_NAME!r} — did openfga-init run?"
    return stores[-1]["id"]
