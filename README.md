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

## Quickstart

```bash
cp .env.example .env
docker compose up -d                      # add --profile spike for the CIBA spike service
python3 -m venv .venv && .venv/bin/pip install -r tests/smoke/requirements.txt
.venv/bin/python -m pytest tests/smoke -v # waits for stack health itself
```

Service ports: Keycloak `8180` (admin `admin`/`admin`; port 8080 left free for
other local stacks), OpenFGA `8081`, OpenBao `8200`, ntfy `8090`,
Mailpit UI `8025` (SMTP `1025`), Postgres `5432`.

The M0 CIBA spike (Keycloak's built-in HTTP authentication channel — verdict:
works, no Java SPI needed) lives in `spike/ciba-http-channel/`:

```bash
docker compose --profile spike up -d --build
.venv/bin/python -m pytest spike/ciba-http-channel/test_spike.py -v
```

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

## Repository

- `openspec/` — normative capability specs and change history (OpenSpec)
- `deploy/` — Keycloak realm, OpenFGA model, OpenBao init, ntfy config
- `services/` — token broker, approval service (later milestones)
- `spike/` — M0 spike: Keycloak's built-in CIBA HTTP channel
- `tests/smoke/` — stack smoke tests
- `docs/` — architecture, threat model, ADRs
