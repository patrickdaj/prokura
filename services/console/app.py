"""Prokura Console — a bespoke, self-contained observability page.

Serves a dark single-page dashboard and proxies its queries to Prometheus,
Loki, and Tempo *through Grafana's datasource proxy* (same reachable port,
no CORS, reuses Grafana's anonymous-admin auth). This is the headline demo
view; Grafana itself stays for power-user drill-down.
"""

import os
import time

import httpx
from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, JSONResponse

GRAFANA = os.environ.get("GRAFANA_URL", "http://lgtm:3000")
HERE = os.path.dirname(__file__)

app = FastAPI(title="prokura-console")


async def _proxy(path: str, params: dict) -> dict:
    url = f"{GRAFANA}/api/datasources/proxy/uid/{path}"
    async with httpx.AsyncClient(timeout=10.0) as c:
        r = await c.get(url, params=params)
        r.raise_for_status()
        return r.json()


@app.get("/api/prom/instant")
async def prom_instant(query: str = Query(...)) -> JSONResponse:
    data = await _proxy("prometheus/api/v1/query", {"query": query})
    return JSONResponse(data)


@app.get("/api/prom/range")
async def prom_range(
    query: str = Query(...), minutes: int = 30, step: int = 60
) -> JSONResponse:
    now = int(time.time())
    data = await _proxy(
        "prometheus/api/v1/query_range",
        {"query": query, "start": now - minutes * 60, "end": now, "step": step},
    )
    return JSONResponse(data)


@app.get("/api/loki")
async def loki(query: str = Query(...), minutes: int = 15, limit: int = 60) -> JSONResponse:
    now_ns = time.time_ns()
    data = await _proxy(
        "loki/loki/api/v1/query_range",
        {
            "query": query,
            "start": str(now_ns - minutes * 60 * 1_000_000_000),
            "end": str(now_ns),
            "limit": limit,
            "direction": "backward",
        },
    )
    return JSONResponse(data)


@app.get("/api/tempo/search")
async def tempo_search(q: str = Query(...), minutes: int = 30, limit: int = 40) -> JSONResponse:
    now = int(time.time())
    data = await _proxy(
        "tempo/api/search",
        {"q": q, "start": now - minutes * 60, "end": now, "limit": limit},
    )
    return JSONResponse(data)


@app.get("/api/tempo/trace/{trace_id}")
async def tempo_trace(trace_id: str) -> JSONResponse:
    data = await _proxy(f"tempo/api/traces/{trace_id}", {})
    return JSONResponse(data)


@app.get("/healthz")
async def healthz() -> dict:
    return {"ok": True}


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(os.path.join(HERE, "index.html"))
