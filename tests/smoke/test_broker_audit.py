"""M2 token-brokering spec: 'Issuance audit log'. Every issuance is persisted in
Postgres AND emitted to the telemetry pipeline in realtime with the same
correlation id, so the trail is Loki-queryable within seconds.

Fire-and-forget: this test SKIPs when the LGTM receiver is absent (the rest of
the broker suite must still pass with lgtm stopped)."""

import time

import httpx
import pytest

import brokerkit
import humankit
from conftest import BROKER_URL, DEMO_USER, LGTM_URL, link_acme
from prokura import get_provider_token


@pytest.fixture(scope="module")
def lgtm() -> str:
    try:
        r = httpx.get(f"{LGTM_URL}/api/health", timeout=5.0)
        if r.status_code != 200:
            pytest.skip("LGTM receiver present but unhealthy")
    except Exception:
        pytest.skip("LGTM receiver not running — telemetry tests skipped")
    return LGTM_URL


@pytest.fixture(scope="module")
def issued(keycloak, broker, openbao, openfga):
    link_acme(keycloak)
    brokerkit.import_grant(brokerkit.broker_token(), "acme")
    brokerkit.seed_operator("agent-app", DEMO_USER)
    humankit.drive_consent("agent-app", "acme")
    out = get_provider_token(brokerkit.broker_token(), "acme", base_url=BROKER_URL)
    assert out["access_token"]
    return out


def _poll(fn, timeout=90.0, interval=3.0):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        found, last = fn()
        if found:
            return last
        time.sleep(interval)
    pytest.fail(f"broker audit did not appear within {timeout}s (last: {last})")


def test_issuance_audit_reaches_loki(lgtm: str, issued):
    import re

    def check():
        r = httpx.get(
            f"{lgtm}/api/datasources/proxy/uid/loki/loki/api/v1/query_range",
            params={"query": '{service_name="token-broker"} |= "broker_audit" |= "decision=issued"',
                    "since": "15m"},
            timeout=10.0,
        )
        results = r.json().get("data", {}).get("result", []) if r.status_code == 200 else []
        lines = [v[1] for s in results for v in s.get("values", [])]
        # The realtime audit event must carry a correlation id (= trace id) in the
        # log line, so it joins to the persisted Postgres row and the flow trace.
        joined = [ln for ln in lines if re.search(r"correlation_id=[0-9a-f]{32}", ln)]
        return bool(joined), f"{len(joined)}/{len(lines)} issued lines carry a correlation id"

    _poll(check)
