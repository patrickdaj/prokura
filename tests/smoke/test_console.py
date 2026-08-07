"""Smoke: the Prokura Console (bespoke dashboard) serves and proxies live data.

The console is the headline observability view; it proxies Prometheus/Loki/Tempo
through Grafana's datasource API. These tests confirm it serves its page and that
each proxied backend returns data for a driven login. Skips cleanly if the
console isn't running (it depends on the LGTM receiver).
"""

import time

import httpx
import pytest

from conftest import drive_login

CONSOLE = "http://localhost:8095"


@pytest.fixture(scope="module")
def console() -> str:
    try:
        r = httpx.get(f"{CONSOLE}/healthz", timeout=5.0)
        if r.status_code != 200:
            pytest.skip("console present but unhealthy")
    except Exception:
        pytest.skip("console not running — skipped")
    return CONSOLE


@pytest.fixture(scope="module")
def login_traffic(keycloak: str) -> dict:
    return drive_login(keycloak)


def _poll(fn, timeout: float = 90.0, interval: float = 3.0):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        ok, last = fn()
        if ok:
            return last
        time.sleep(interval)
    pytest.fail(f"console data did not appear within {timeout}s (last: {last})")


def test_serves_page(console: str) -> None:
    r = httpx.get(f"{console}/", timeout=10.0)
    assert r.status_code == 200
    assert "PROKURA" in r.text and "Span waterfall" in r.text


def test_prom_proxy_returns_data(console: str, login_traffic: dict) -> None:
    def check():
        # raw counter (present after one scrape) — robust on a cold stack, where
        # increase()[1h] needs two samples and would be empty right after boot.
        r = httpx.get(f"{console}/api/prom/instant",
                      params={"query": 'sum(keycloak_user_events_total{event="login"})'},
                      timeout=10.0)
        res = r.json().get("data", {}).get("result", []) if r.status_code == 200 else []
        return bool(res), f"{len(res)} results"

    _poll(check)


def test_tempo_proxy_returns_traces(console: str, login_traffic: dict) -> None:
    def check():
        r = httpx.get(f"{console}/api/tempo/search",
                      params={"q": '{ trace:rootName=~"GET.*|POST.*" }', "minutes": 60, "limit": 5},
                      timeout=10.0)
        traces = r.json().get("traces", []) if r.status_code == 200 else []
        return bool(traces), f"{len(traces)} traces"

    _poll(check)


def test_loki_proxy_returns_events(console: str, login_traffic: dict) -> None:
    def check():
        r = httpx.get(f"{console}/api/loki",
                      params={"query": '{service_name="keycloak"} |= "type=\\""', "minutes": 30, "limit": 10},
                      timeout=10.0)
        res = r.json().get("data", {}).get("result", []) if r.status_code == 200 else []
        return bool(res), f"{len(res)} streams"

    _poll(check)
