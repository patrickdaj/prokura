# Prokura

> **Prokura** (n., civil law): the registered power of attorney by which a company
> grants an agent the authority to act on its behalf. This project is Prokura
> for AI agents.

An open-source **reference implementation of agentic identity** — user
authentication, delegated agent authorization, third-party token brokering,
human-in-the-loop approval, and fine-grained RAG authorization — assembled from
[Keycloak](https://www.keycloak.org/), [OpenFGA](https://openfga.dev/), and
[OpenBao](https://openbao.org/). An OSS counterpoint to Auth0 for AI Agents.

**⚠️ Non-production.** This is a reference architecture and demo. The compose
stack runs dev-mode components with documented dev credentials. The docs state
what production would require; the stack does not provide it.

## What it shows

| Flow | What | Where |
|---|---|---|
| A | Delegated agent tokens (RFC 8693 exchange; `sub`=user, `azp`=agent) | Keycloak |
| B | Third-party token brokering (leases, scope-down, per-agent consent) | Token Broker + OpenBao + OpenFGA |
| C | Human-in-the-loop approval (CIBA, structured payloads, replay-proof) | Keycloak + approval service |
| D | FGA-filtered RAG (checks run as the *user*, never the agent) | OpenFGA |

Headline demo: **Keycloak as an MCP authorization server** — point an MCP
client (e.g. Claude) at the Prokura MCP server and watch discovery, dynamic
client registration, login, per-agent consent, and push-approved gated actions
work end to end.

## Quickstart (5 minutes)

**1. Bring up the stack.** The compose file is three tiers: **prokura** (the trusted
surfaces — token-broker, approval, authority), **infra** (keycloak, openfga, openbao,
postgres, ntfy, lgtm), and **test/demo** (the *toy* resource servers that prove the
chain — mcp, tools-api, rag, mailpit). A bare `docker compose up` brings the product;
the demo and smoke suite need the toy servers too, so use `--profile demo`:

```bash
cp .env.example .env
docker compose --profile demo up -d   # ~1 min; full chain. (Bare `up` = product only;
                                      # add --profile spike for the CIBA spike service.)
python3 -m venv .venv && .venv/bin/pip install -r tests/smoke/requirements.txt
```

**2. Watch the headline demo.** A spec-compliant **MCP client** connects exactly as a
real client (Claude among them) would — discover → dynamic registration → login →
tools — and drives the whole chain, narrating each step as it happens:

```bash
.venv/bin/python demo/run_demo.py
```

You'll watch, in four acts: the client connect with an `aud=mcp-server` token; obtain a
**consent-gated** provider token (and the raw MCP token get **refused downstream** — no
passthrough); a **human approve** a gated email that lands in the **Mailpit** sink
(`http://localhost:8025`); and a **FGA-filtered RAG** query where alice retrieves a
protected doc and **bob provably cannot — even though it's his top embedding hit**.

**3. Watch it happen** in **Grafana** (`http://localhost:3001`, no login): open
**Explore → Tempo** and search `{ prokura.flow = "C" }` to land on one end-to-end
trace, expand a span, and use the **Tempo→Loki** derived field to jump from the trace
to its `mcp → rag → openfga` audit lines in Loki. Or follow the
[**guided walkthroughs**](docs/walkthroughs/) stage by stage.

**Verify it with the test suite** (the same real handshake, asserted rather than
narrated; waits for stack health itself):

```bash
.venv/bin/python -m pytest tests/smoke -v
```

Service ports: Keycloak `8180` (admin `admin`/`admin`; port 8080 left free for
other local stacks), MCP `8140`, RAG `8150`, broker `8110`, approval `8120`,
tools-api `8130`, OpenFGA `8081`, OpenBao `8200`, ntfy `8090`,
Mailpit UI `8025` (SMTP `1025`), Grafana `3001`, Postgres `5432`.

The M0 CIBA spike (Keycloak's built-in HTTP authentication channel — verdict:
works, no Java SPI needed) lives in `spike/ciba-http-channel/`:

```bash
docker compose --profile spike up -d --build
.venv/bin/python -m pytest spike/ciba-http-channel/test_spike.py -v
```

## Observability

**Grafana — `http://localhost:3001`** (no login) is the single observability
surface, onto live telemetry from every service:

- **Explore → Tempo** for the flow waterfall. Traces are **flow-scoped**: search
  `{ prokura.flow = "B" }` (or C/D, or `authority-console`) to land on exactly one
  end-to-end trace for that logical action — health-check noise carries no flow tag
  and stays out. Denied steps render **red** (span error status) and the domain
  decisions (`issued`/`approved`/`consumed`/`revoked`/…) appear inline as span
  **events**, so the waterfall narrates the story. The CIBA ceremony's async legs
  (register → delegate → decide → complete) are joined by span **links**.
- **Tempo→Loki derived field** — from any span, one click to its correlated audit
  lines in Loki, joined on the native trace id (no hand-copied correlation id).
- The provisioned ***Prokura — Delegation Chain*** dashboard for the at-a-glance
  overview: stat tiles, identity-event and request-rate timeseries, per-service
  live audit streams, and the kill-switch time-to-stop panel.

Useful Tempo query (Grafana Explore → Tempo):

```traceql
{trace:rootName =~ "GET.*|POST.*|PUT.*|PATCH.*"}   # real activity only, no healthcheck noise
```

How each component is observable: Keycloak exports traces, metrics, and logs
via OTLP (realm events appear in the Loki stream in realtime); OpenFGA exports
traces (its authorization checks decompose into ReBAC resolution spans);
OpenBao has no OTLP/trace export — its authoritative record is the file audit
device (`docker compose exec openbao cat /tmp/bao-audit.log`), and its
operations become trace-visible through caller-side spans once the broker lands
(M2). Correlation convention: W3C `traceparent` joins spans across services, and
trace↔log correlation is the **native OTel trace context** (the `trace_id` the
logging handler attaches to every audit line, joined in Grafana by a Tempo→Loki
derived field) — not a hand-copied correlation id; domain IDs (approval reference
IDs) still ride as span attributes so a flow is also findable by domain ID.
Instrumentation is part of the definition of done for every Prokura service, via
the shared `prokura-telemetry` module.

Telemetry is fire-and-forget: stop the `lgtm` container and everything else
keeps working (telemetry smoke tests skip; the rest of the suite passes).

## Prior art

The token broker here is deliberately minimal. [Nango](https://github.com/NangoHQ/nango)
is a mature OSS third-party OAuth broker with a large connector catalog — if you
need production grant lifecycle management, use it. Prokura's value is the
*assembly*: delegation + human approval + fine-grained authorization + brokering
under **one identity model**, which no OSS project demonstrates end to end.

| | Prokura | Nango | Auth0 for AI Agents |
|---|---|---|---|
| Focus | Reference architecture, whole identity story | Production OAuth brokering | Commercial SaaS platform |
| Delegation (RFC 8693) | ✅ | — | ✅ (Token Vault exchange) |
| Human approval (CIBA) | ✅ structured payloads | — | ✅ (CIBA + RAR + Guardian) |
| Per-agent consent | ✅ (FGA tuples) | — | — (app-scoped) |
| Fine-grained RAG authz | ✅ (OpenFGA) | — | ✅ (Auth0 FGA) |
| Provider catalog | 2 (GitHub, Google) | 250+ | ~15 pre-integrated |
| License | Apache-2.0 | Elastic License v2 (check terms) | Commercial |

## Documentation

- [**Architecture**](docs/architecture.md) — the consolidated as-built design (supersedes `SPEC.md`)
- [**Walkthroughs**](docs/walkthroughs/) — follow-along guided tour (master + per-flow)
- [**Milestone blog series**](docs/blog/index.html) — the build log, M0 → M6
- [**Threat model**](docs/threat-model.md) — assets, STRIDE per flow, attack trees
- [**Security review**](docs/security-review.md) — control audit + findings register
- [**ADRs**](docs/adr/) — one decision record per material choice (F1–F9, Q1–Q7, …)

## Repository

- `openspec/` — normative capability specs and change history (OpenSpec, the source of truth)
- `deploy/` — Keycloak realm, OpenFGA model, OpenBao init, ntfy, RAG corpus
- `services/` — token-broker, approval, tools-api, mcp, rag, authority
- `sdk/prokura-py/` — the agent SDK (`exchange`, `get_provider_token`, `require_approval`)
- `spike/` — per-milestone de-risking spikes (CIBA channel, idp-link, MCP, RAG)
- `tests/smoke/` — stack smoke tests that drive the live system
- `docs/` — architecture, walkthroughs, blogs, threat model, security review, ADRs
