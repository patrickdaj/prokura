"""Smoke: the telemetry pipeline (observability spec).

Drives real traffic (a full login) and asserts it becomes observable: a trace
in Tempo, the realm event in Loki, and the provisioned dashboard in Grafana.
All assertions poll with deadlines — OTLP ingestion is asynchronous.

Receiver-outage semantics (observability spec, "Telemetry outage is non-fatal"):
these tests SKIP when the LGTM receiver is absent, and the rest of the smoke
suite must pass with the receiver stopped. Manual check:
    docker compose stop lgtm && python -m pytest tests/smoke --ignore=tests/smoke/test_telemetry.py
"""

import time

import httpx
import pytest

from conftest import LGTM_URL, drive_login


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
def login_traffic(keycloak: str) -> dict:
    """One real login whose telemetry the tests below go looking for."""
    return drive_login(keycloak)


def _poll(fn, timeout: float = 90.0, interval: float = 3.0):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        found, last = fn()
        if found:
            return last
        time.sleep(interval)
    pytest.fail(f"telemetry did not appear within {timeout}s (last: {last})")


def test_login_trace_reaches_tempo(lgtm: str, login_traffic: dict) -> None:
    def check():
        r = httpx.get(
            f"{lgtm}/api/datasources/proxy/uid/tempo/api/search",
            params={"q": '{trace:rootName =~ "POST.*token|POST.*authenticate"}', "limit": 10},
            timeout=10.0,
        )
        traces = r.json().get("traces", []) if r.status_code == 200 else []
        return bool(traces), f"{len(traces)} traces (HTTP {r.status_code})"

    _poll(check)


def test_realm_event_reaches_loki(lgtm: str, login_traffic: dict) -> None:
    def check():
        r = httpx.get(
            f"{lgtm}/api/datasources/proxy/uid/loki/loki/api/v1/query_range",
            params={"query": '{service_name="keycloak"} |= "type=\\"LOGIN\\""', "since": "15m"},
            timeout=10.0,
        )
        results = r.json().get("data", {}).get("result", []) if r.status_code == 200 else []
        return bool(results), f"{len(results)} streams (HTTP {r.status_code})"

    _poll(check)


def test_dashboard_provisioned(lgtm: str) -> None:
    r = httpx.get(f"{lgtm}/api/dashboards/uid/prokura-delegation", timeout=10.0)
    assert r.status_code == 200, "delegation-chain dashboard not provisioned"
    panels = r.json()["dashboard"]["panels"]
    assert len(panels) >= 5, f"dashboard unexpectedly small: {len(panels)} panels"


def test_datasources_healthy(lgtm: str) -> None:
    for uid in ("prometheus", "tempo", "loki"):
        r = httpx.get(f"{lgtm}/api/datasources/uid/{uid}/health", timeout=15.0)
        assert r.status_code == 200 and r.json().get("status") == "OK", (
            f"datasource {uid} unhealthy: {r.status_code} {r.text[:120]}"
        )
