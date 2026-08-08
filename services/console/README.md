# Prokura Console (M6)

A bespoke, self-contained **observability page** — the headline demo view of the delegation
chain. It serves a dark single-page dashboard (`index.html`) and proxies its queries to
**Prometheus, Loki, and Tempo through Grafana's datasource proxy** (same reachable port, no
CORS, reusing Grafana's anonymous-admin auth). Grafana itself stays available for power-user
drill-down; this is the curated view.

## What it shows

- A **trace stream** and a **span waterfall** — click a row to see one delegated action
  decomposed across services (the "one delegated action, decomposed" view).
- Vital metrics (logins, token grants, auth requests, average latency) from Prometheus.
- The correlation seed for the trace→log jump: `prokura.correlation_id` (= trace id).

## Proxy endpoints

| Method | Path | Backing datasource |
|--------|------|--------------------|
| `GET`  | `/healthz` | liveness |
| `GET`  | `/` | the dashboard SPA |
| `GET`  | `/api/prom/instant?query=` | Prometheus instant query |
| `GET`  | `/api/prom/range?query=&minutes=&step=` | Prometheus range query |
| `GET`  | `/api/loki?query=&minutes=&limit=` | Loki `query_range` |
| `GET`  | `/api/tempo/search?q=&minutes=&limit=` | Tempo TraceQL search |
| `GET`  | `/api/tempo/trace/{trace_id}` | Tempo single-trace fetch |

All `/api/*` routes forward to `${GRAFANA_URL}/api/datasources/proxy/uid/{path}`.

> These proxies are exactly what the walkthrough capture pipeline uses to render the native
> trace waterfalls and the telemetry postmortem (`demo/capture/capture_trace.py`).

## Configuration

`GRAFANA_URL` (default `http://lgtm:3000`). Port **8095**. Fire-and-forget — no `depends_on`
beyond `lgtm`.
