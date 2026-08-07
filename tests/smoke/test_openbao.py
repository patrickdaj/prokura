"""Smoke 3.4: OpenBao KV via the scoped broker token — root token unused.

Also asserts the broker policy boundary: the broker token must NOT be able
to write outside secret/grants/* (token-brokering threat model).
"""

import httpx

from conftest import BROKER_BAO_TOKEN


def _headers() -> dict:
    return {"X-Vault-Token": BROKER_BAO_TOKEN}


def test_kv_write_read_with_broker_token(openbao: str) -> None:
    write = httpx.post(
        f"{openbao}/v1/secret/data/grants/alice/github",
        headers=_headers(),
        json={"data": {"refresh_token": "smoke-placeholder", "scopes": "repo:read"}},
        timeout=10.0,
    )
    assert write.status_code == 200, write.text

    read = httpx.get(
        f"{openbao}/v1/secret/data/grants/alice/github",
        headers=_headers(),
        timeout=10.0,
    )
    assert read.status_code == 200, read.text
    assert read.json()["data"]["data"]["refresh_token"] == "smoke-placeholder"


def test_broker_token_scoped_to_grants(openbao: str) -> None:
    outside = httpx.post(
        f"{openbao}/v1/secret/data/not-grants/leak",
        headers=_headers(),
        json={"data": {"x": "y"}},
        timeout=10.0,
    )
    assert outside.status_code == 403, (
        f"broker token wrote outside grants/*: {outside.status_code} {outside.text}"
    )
