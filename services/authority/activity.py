"""Activity feed (M8, D3): the console proxies Loki through Grafana's datasource
API exactly like services/console, but the query is composed SERVER-SIDE from the
session principal's username — ``|= "user=<username>"`` over the audit streams —
so one principal can never read another's activity. The username is never taken
from client input; it comes from the verified session only, and it is validated
against a strict charset before it enters the LogQL string (defence in depth: the
audit lines use ``user=<principal>`` and the filter is a plain substring gate)."""

import re
import time

import httpx

import config
from prokura_telemetry import tracer

# Audit streams that carry per-principal lines (broker/approval/mcp/rag).
_STREAMS = 'service_name=~"token-broker|approval|mcp|rag|keycloak"'
_USER_RE = re.compile(r"^[a-zA-Z0-9._-]{1,64}$")


def for_user(user: str, minutes: int = 720, limit: int = 60) -> list[dict]:
    """Return the principal's audit lines, newest first, as
    [{ts, service, line}]. Refuses a username that is not a plain identifier so
    it can never break out of the LogQL substring filter."""
    if not user or not _USER_RE.match(user):
        return []
    now_ns = time.time_ns()
    query = "{" + _STREAMS + '} |= `user=' + user + "`"
    with tracer().start_as_current_span("loki.activity") as span:
        span.set_attribute("prokura.activity.user", user)
        try:
            r = httpx.get(
                f"{config.GRAFANA_URL}/api/datasources/proxy/uid/loki/loki/api/v1/query_range",
                params={"query": query,
                        "start": str(now_ns - minutes * 60 * 1_000_000_000),
                        "end": str(now_ns), "limit": limit, "direction": "backward"},
                timeout=10.0)
        except httpx.HTTPError:
            return []
    if r.status_code != 200:
        return []
    out: list[dict] = []
    for stream in r.json().get("data", {}).get("result", []):
        service = stream.get("stream", {}).get("service_name", "")
        for ts_ns, line in stream.get("values", []):
            out.append({"ts": int(ts_ns) // 1_000_000_000, "service": service, "line": line})
    out.sort(key=lambda e: e["ts"], reverse=True)
    return out[:limit]
