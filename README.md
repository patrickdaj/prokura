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

**1. Bring up the whole stack.**

```bash
cp .env.example .env
docker compose up -d          # ~1 min; add --profile spike for the CIBA spike service
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

**3. Watch it happen** in the bespoke **Prokura Console** (`http://localhost:8095`):
click a `POST /mcp` trace, expand a span, and hit **"show correlated audit logs"** to
jump from the trace to its `mcp → rag → openfga` audit lines in Loki. Or follow the
[**guided walkthroughs**](docs/walkthroughs/) stage by stage.

**Verify it with the test suite** (the same real handshake, asserted rather than
narrated; waits for stack health itself):

```bash
.venv/bin/python -m pytest tests/smoke -v
```

Service ports: Keycloak `8180` (admin `admin`/`admin`; port 8080 left free for
other local stacks), MCP `8140`, RAG `8150`, broker `8110`, approval `8120`,
tools-api `8130`, console `8095`, OpenFGA `8081`, OpenBao `8200`, ntfy `8090`,
Mailpit UI `8025` (SMTP `1025`), Grafana `3001`, Postgres `5432`.

The M0 CIBA spike (Keycloak's built-in HTTP authentication channel — verdict:
works, no Java SPI needed) lives in `spike/ciba-http-channel/`:

```bash
docker compose --profile spike up -d --build
.venv/bin/python -m pytest spike/ciba-http-channel/test_spike.py -v
```

## Observability

Two views onto the same live telemetry:

- **Prokura Console — `http://localhost:8095`** (the headline). A bespoke,
  interactive dashboard: the delegation chain as clickable service filters, a
  live trace stream, and — the signature — click any trace to expand its **span
  waterfall**, decomposing one delegated action across services (Keycloak's
  Argon2 hashing, OpenFGA's ReBAC check resolution, …). Vitals and a live audit
  sparkline sit in the footer.
- **Grafana — `http://localhost:3001`** (no login). Metric/log drill-down plus
  Explore for ad-hoc trace waterfalls. The provisioned *Prokura — Delegation
  Chain* dashboard has stat tiles, identity-event and request-rate timeseries,
  and the realm-event log stream.

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
(M2). Correlation convention: W3C `traceparent` joins spans across services;
domain IDs (`prokura.correlation_id`, approval reference IDs) ride as span
attributes and log fields — instrumentation is part of the definition of done
for every Prokura service.

Telemetry is fire-and-forget: stop the `lgtm` container and everything else
keeps working (telemetry/console smoke tests skip; the rest of the suite passes).

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
- `services/` — token-broker, approval, tools-api, mcp, rag, console
- `sdk/prokura-py/` — the agent SDK (`exchange`, `get_provider_token`, `require_approval`)
- `spike/` — per-milestone de-risking spikes (CIBA channel, idp-link, MCP, RAG)
- `tests/smoke/` — stack smoke tests that drive the live system
- `docs/` — architecture, walkthroughs, blogs, threat model, security review, ADRs
