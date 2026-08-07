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


@pytest.fixture(scope="session")
def fga_store_id(openfga: str) -> str:
    """Discover the store created by openfga-init by name."""
    r = httpx.get(f"{openfga}/stores", timeout=10.0)
    r.raise_for_status()
    stores = [s for s in r.json().get("stores", []) if s["name"] == FGA_STORE_NAME]
    assert stores, f"no OpenFGA store named {FGA_STORE_NAME!r} — did openfga-init run?"
    return stores[-1]["id"]
