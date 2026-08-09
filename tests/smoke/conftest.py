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


_login_cache: dict[tuple, tuple[float, dict]] = {}


def drive_login(keycloak: str, client_id: str = "smoke-cli",
                client_secret: str | None = None, user: str = DEMO_USER,
                scope: str = "openid") -> dict:
    """Authorization Code + PKCE, with the HUMAN leg (login form, any consent
    screen) played by humankit in a real browser (M7 quarantine: no user
    password lives outside humankit). The agent leg — building the request,
    exchanging the code — runs here. Token responses are cached per
    (client, user, scope) until near expiry; the suite reuses sessions the way
    a person's browser would."""
    import base64
    import hashlib
    import secrets

    import humankit

    key = (client_id, user, scope)
    now = time.monotonic()
    hit = _login_cache.get(key)
    if hit and hit[0] > now:
        return hit[1]

    b64 = lambda b: base64.urlsafe_b64encode(b).rstrip(b"=").decode()  # noqa: E731
    verifier = b64(secrets.token_bytes(32))
    challenge = b64(hashlib.sha256(verifier.encode()).digest())
    redirect_uri = f"http://{humankit.CALLBACK_HOST}:{humankit.CALLBACK_PORT}/cb"
    auth_url = str(httpx.URL(
        f"{keycloak}/realms/{REALM}/protocol/openid-connect/auth",
        params={"client_id": client_id, "response_type": "code",
                "redirect_uri": redirect_uri, "scope": scope, "state": "smoke",
                "code_challenge": challenge, "code_challenge_method": "S256"}))
    final = humankit.auth_code_login(auth_url, redirect_uri, user=user)
    code = httpx.URL(final).params.get("code")
    assert code, f"no code on redirect: {final[:150]}"
    token_data = {
        "grant_type": "authorization_code", "client_id": client_id,
        "code": code, "redirect_uri": redirect_uri, "code_verifier": verifier,
    }
    if client_secret:
        token_data["client_secret"] = client_secret
    token = httpx.post(f"{keycloak}/realms/{REALM}/protocol/openid-connect/token",
                       data=token_data, timeout=15.0)
    assert token.status_code == 200, token.text
    body = token.json()
    _login_cache[key] = (now + body.get("expires_in", 900) - 120, body)
    return body


def device_bootstrap(client_id: str, client_secret: str, user: str = DEMO_USER,
                     scope: str = "openid") -> dict:
    """Headless-agent bootstrap (RFC 8628, M7): the agent initiates the device
    flow with its OWN client credential and polls; the HUMAN approves the user
    code in their browser (humankit). No user password ever reaches agent code."""
    import humankit

    key = ("device:" + client_id, user, scope)
    now = time.monotonic()
    hit = _login_cache.get(key)
    if hit and hit[0] > now:
        return hit[1]

    r = httpx.post(f"{KEYCLOAK_URL}/realms/{REALM}/protocol/openid-connect/auth/device",
                   data={"client_id": client_id, "client_secret": client_secret,
                         "scope": scope}, timeout=15.0)
    assert r.status_code == 200, f"device init failed: {r.status_code} {r.text[:200]}"
    dev = r.json()
    humankit.approve_device(dev["verification_uri_complete"], user=user)
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        t = httpx.post(f"{KEYCLOAK_URL}/realms/{REALM}/protocol/openid-connect/token",
                       data={"grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                             "device_code": dev["device_code"], "client_id": client_id,
                             "client_secret": client_secret}, timeout=15.0)
        if t.status_code == 200:
            body = t.json()
            _login_cache[key] = (now + body.get("expires_in", 900) - 120, body)
            return body
        err = t.json().get("error", "")
        assert err in ("authorization_pending", "slow_down"), t.text[:200]
        time.sleep(dev.get("interval", 5))
    raise AssertionError("device flow never completed")


@pytest.fixture(scope="session")
def fga_store_id(openfga: str) -> str:
    """Discover the store created by openfga-init by name."""
    r = httpx.get(f"{openfga}/stores", timeout=10.0)
    r.raise_for_status()
    stores = [s for s in r.json().get("stores", []) if s["name"] == FGA_STORE_NAME]
    assert stores, f"no OpenFGA store named {FGA_STORE_NAME!r} — did openfga-init run?"
    return stores[-1]["id"]


# --- M2 (token broker) support ------------------------------------------------

BROKER_URL = os.environ.get("PROKURA_BROKER_URL", "http://localhost:8110")
KC_ADMIN_USER = os.environ.get("KC_BOOTSTRAP_ADMIN_USERNAME", "admin")
KC_ADMIN_PASSWORD = os.environ.get("KC_BOOTSTRAP_ADMIN_PASSWORD", "admin")


@pytest.fixture(scope="session")
def broker() -> str:
    wait_http(f"{BROKER_URL}/healthz", ok=lambda r: r.status_code == 200)
    return BROKER_URL


# --- M5 (RAG retriever) support -----------------------------------------------

RAG_URL = os.environ.get("PROKURA_RAG_URL", "http://localhost:8150")


@pytest.fixture(scope="session")
def rag() -> str:
    wait_http(f"{RAG_URL}/healthz", ok=lambda r: r.status_code == 200)
    return RAG_URL


def admin_token() -> str:
    r = httpx.post(
        f"{KEYCLOAK_URL}/realms/master/protocol/openid-connect/token",
        data={"grant_type": "password", "client_id": "admin-cli",
              "username": KC_ADMIN_USER, "password": KC_ADMIN_PASSWORD},
        timeout=10.0,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def _alice_id(admin: str) -> str:
    r = httpx.get(f"{KEYCLOAK_URL}/admin/realms/{REALM}/users?username={DEMO_USER}",
                  headers={"Authorization": f"Bearer {admin}"}, timeout=10.0)
    r.raise_for_status()
    return r.json()[0]["id"]


def _is_acme_linked(admin: str) -> bool:
    uid = _alice_id(admin)
    r = httpx.get(f"{KEYCLOAK_URL}/admin/realms/{REALM}/users/{uid}/federated-identity",
                  headers={"Authorization": f"Bearer {admin}"}, timeout=10.0)
    r.raise_for_status()
    return any(fi.get("identityProvider") == "acme" for fi in r.json())


def link_acme(keycloak: str) -> None:
    """Drive kc_action=idp_link:acme for alice headlessly (the M2 spike ceremony),
    idempotent — a no-op if already linked. Cookies keyed per realm path because
    Keycloak marks them Secure on plain HTTP and per-realm names collide."""
    import base64
    import hashlib
    import html as html_mod
    import re
    import secrets

    admin = admin_token()
    if _is_acme_linked(admin):
        return

    b64 = lambda x: base64.urlsafe_b64encode(x).rstrip(b"=").decode()  # noqa: E731
    verifier = b64(secrets.token_bytes(32))
    challenge = b64(hashlib.sha256(verifier.encode()).digest())
    redirect = "http://127.0.0.1/cb"
    jars: dict[str, dict] = {}

    def realm_of(u: str) -> str:
        m = re.search(r"/realms/([^/]+)/", u)
        return m.group(1) if m else REALM

    def merge(u, resp):
        jar = jars.setdefault(realm_of(u), {})
        for sc in resp.headers.get_list("set-cookie"):
            k, v = sc.split(";", 1)[0].split("=", 1)
            jar[k] = v

    def cookie(u):
        return "; ".join(f"{k}={v}" for k, v in jars.get(realm_of(u), {}).items())

    def form(t):
        m = re.search(r'id="kc-form-login"[^>]*action="([^"]+)"', t)
        return html_mod.unescape(m.group(1)) if m else None

    with httpx.Client(follow_redirects=False, timeout=20.0) as c:
        auth = f"{keycloak}/realms/{REALM}/protocol/openid-connect/auth"
        r = c.get(auth, params={
            "client_id": "smoke-cli", "response_type": "code", "redirect_uri": redirect,
            "scope": "openid", "state": "link", "kc_action": "idp_link:acme",
            "prompt": "login", "code_challenge": challenge, "code_challenge_method": "S256"})
        merge(auth, r)
        action = form(r.text)
        assert action, "no prokura login form"
        r = c.post(action, data={"username": DEMO_USER, "password": DEMO_PASSWORD},
                   headers={"Cookie": cookie(action)})
        merge(action, r)
        loc = r.headers["location"]
        acme_done = False
        for _ in range(10):
            if loc.startswith("http://127.0.0.1"):
                break
            u = loc if loc.startswith("http") else keycloak + loc
            r = c.get(u, headers={"Cookie": cookie(u)})
            merge(u, r)
            if r.status_code in (301, 302, 303, 307):
                loc = r.headers["location"]
                continue
            if r.status_code == 200 and "login-actions/required-action" in u and 'name="continue"' in r.text:
                a = html_mod.unescape(re.search(r'<form[^>]*action="([^"]+)"', r.text).group(1))
                r = c.post(a, data={"continue": ""}, headers={"Cookie": cookie(a)})
                merge(a, r)
                loc = r.headers["location"]
                continue
            if r.status_code == 200 and "/realms/acme/" in u and not acme_done:
                a = form(r.text)
                r = c.post(a, data={"username": DEMO_USER, "password": DEMO_PASSWORD},
                           headers={"Cookie": cookie(a)})
                merge(a, r)
                acme_done = True
                loc = r.headers["location"]
                continue
            raise AssertionError(f"unexpected link hop {r.status_code} at {u}")
    assert _is_acme_linked(admin), "acme link did not persist"
