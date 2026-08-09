"""AGENT-SIDE helpers for the token-broker smoke tests (M7 quarantine, D6):
obtain a broker-audience token, import a grant, seed operator tuples (test
scaffolding). Consent writes/revocations are HUMAN capacities — they live in
humankit and happen on the real consent surface."""

import httpx

from conftest import (
    BROKER_URL,
    FGA_STORE_NAME,
    KEYCLOAK_URL,
    OPENFGA_URL,
    REALM,
    device_bootstrap,
)
from prokura import exchange

AGENT = "agent-app"
SECRET = "agent-app-dev-secret"


def user_token() -> str:
    """The agent's delegated user token for alice via the device flow (the
    human approves the user code in her own browser — humankit). Exchangeable;
    preferred_username=alice."""
    return device_bootstrap(AGENT, SECRET,
                            scope="openid tools-audience broker-audience")["access_token"]


def broker_token(ut: str | None = None) -> str:
    """A token addressed to the broker audience (azp=agent-app, sub=alice)."""
    ut = ut or user_token()
    return exchange(ut, "token-broker", base_url=KEYCLOAK_URL, realm=REALM,
                    client_id=AGENT, client_secret=SECRET)


def import_grant(bt: str, provider: str = "acme") -> httpx.Response:
    return httpx.post(f"{BROKER_URL}/v1/grants/{provider}/import",
                      headers={"Authorization": f"Bearer {bt}"}, timeout=20.0)


def store_id() -> str:
    r = httpx.get(f"{OPENFGA_URL}/stores", timeout=10.0)
    r.raise_for_status()
    return [s["id"] for s in r.json()["stores"] if s["name"] == FGA_STORE_NAME][-1]


def fga_write(tuples, delete=False) -> None:
    key = "deletes" if delete else "writes"
    r = httpx.post(f"{OPENFGA_URL}/stores/{store_id()}/write",
                   json={key: {"tuple_keys": tuples}}, timeout=10.0)
    # tolerate "already exists" / "not found"
    if r.status_code >= 400 and "exist" not in r.text and "not found" not in r.text.lower():
        r.raise_for_status()


def seed_operator(agent: str, user: str) -> None:
    fga_write([{"user": f"user:{user}", "relation": "operator", "object": f"agent:{agent}"}])
