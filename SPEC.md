# AgentGate — Open-Source Identity Platform for AI Agents

**Status:** Draft v0.1
**License target:** Apache-2.0
**One-liner:** An open-source reference implementation of agentic identity — user authentication, delegated agent authorization, third-party token brokering, human-in-the-loop approval, and fine-grained RAG authorization — assembled from Keycloak, OpenFGA, and OpenBao. An OSS answer to Auth0 for AI Agents.

---

## 1. Problem Statement

AI agents acting on behalf of users need to:

1. Know **who the user is** (authentication)
2. Prove **they act on the user's behalf, with reduced scope** (delegation)
3. Call **third-party APIs** (Google, Slack, GitHub) using the user's grants without ever holding long-lived secrets (token brokering)
4. **Pause for human approval** on sensitive actions (async authorization)
5. Retrieve only documents **the user is entitled to see** in RAG pipelines (fine-grained authorization)

Commercial products (Auth0 for AI Agents) package this. No cohesive open-source assembly exists. Every piece is a published standard or a CNCF/LF project. AgentGate is the glue plus a working demo.

## 2. Non-Goals (v0)

- Multi-tenant SaaS hosting
- Connector catalog breadth (v0 ships 2 providers: Google, GitHub)
- SPIFFE/SPIRE workload attestation (v1 roadmap; v0 uses Keycloak client credentials)
- Production HA topologies (docker-compose only in v0)

## 3. Architecture Overview

```
                                ┌─────────────────────────────┐
                                │          User (browser)      │
                                └──────┬──────────────┬────────┘
                                       │ OIDC login   │ CIBA approve/deny
                                       ▼              ▼
┌──────────────┐   token exchange  ┌──────────────────────┐
│  Agent App    │◄─────────────────►│      Keycloak         │
│ (LangChain /  │   (RFC 8693)      │  - OIDC / OAuth 2.1   │
│  MCP client)  │                   │  - CIBA + PAR         │
└───┬───────┬───┘                   │  - DCR for MCP        │
    │       │                       └──────────┬───────────┘
    │       │                                  │ approval webhook (SPI)
    │       │                                  ▼
    │       │                       ┌──────────────────────┐
    │       │  approval status      │   Approval Channel    │
    │       └──────────────────────►│  (ntfy / web push)    │
    │                               └──────────────────────┘
    │
    │ POST /tokens/{provider}       ┌──────────────────────┐     ┌──────────┐
    ├──────────────────────────────►│   Token Broker svc    │────►│ OpenBao  │
    │  (returns short-lived         │  - grant mgmt         │     │ (enc.    │
    │   3rd-party access token)     │  - refresh loop       │     │  storage,│
    │                               │  - scope-down         │     │  leases) │
    │                               └──────────────────────┘     └──────────┘
    │
    │ check() / list_objects()      ┌──────────────────────┐
    └──────────────────────────────►│       OpenFGA         │◄── sync (Keycloak
        (RAG retrieval filter)      │  (ReBAC / Zanzibar)   │    event listener)
                                    └──────────────────────┘
```

### Components

| Component | Technology | Role |
|---|---|---|
| IdP / AS | Keycloak 26.2+ | User authn, agent clients, token exchange, CIBA, PAR, DCR |
| Fine-grained authz | OpenFGA | Document/relationship-level checks for RAG and tools |
| Secret storage | OpenBao | Encrypted third-party token storage with leases |
| Token Broker | **Build** (Python/FastAPI) | Third-party OAuth grant lifecycle, refresh, scoped hand-out |
| Approval Channel | **Build** (Keycloak CIBA SPI + ntfy) | Push approval requests to user, feed decision back |
| Agent SDK | **Build** (Python lib) | Token exchange dance, FGA checks, CIBA interrupts, MCP helpers |
| Demo Agent | **Build** (LangChain or MCP server) | End-to-end proof: reads user's GitHub issues, drafts email, RAG over ACL'd docs |
| FGA Sync | Existing extension + config | Keycloak event listener → OpenFGA tuples |

## 4. Core Flows

### Flow A — Delegated agent token (token exchange)

1. User logs into the agent app via Keycloak OIDC (Authorization Code + PKCE). App holds `subject_token` (user access token).
2. Agent needs to act autonomously with reduced scope. App calls Keycloak token endpoint:
   ```
   grant_type = urn:ietf:params:oauth:grant-type:token-exchange
   subject_token = <user access token>
   audience = agent-tools-api
   requested_token_type = urn:ietf:params:oauth:token-type:access_token
   scope = tools:read tools:execute
   ```
3. Keycloak returns a token with `sub` = user, `azp` = agent client, downscoped. Every downstream action is attributable to *user-via-agent*.

**Acceptance:** exchanged token contains original `sub`, agent `azp`, only requested scopes; exchange denied if agent client lacks exchange permission on target audience.

### Flow B — Third-party token brokering

1. **Grant setup (one-time, user-present):** Token Broker runs Authorization Code flow against the provider (Google/GitHub), stores `refresh_token` in OpenBao at `secret/grants/{user_id}/{provider}`, records granted scopes in its own DB.
2. **Agent request:** Agent presents its exchanged Keycloak token to `POST /v1/tokens/{provider}` with requested scopes.
3. Broker validates the Keycloak token (JWKS), checks requested scopes ⊆ granted scopes, checks OpenFGA tuple `agent:{azp}` `can_use` `grant:{user}/{provider}`.
4. Broker refreshes with the provider if needed, returns a **short-lived access token only** (never the refresh token), with TTL capped at 15 min.

**Acceptance:** refresh tokens never leave OpenBao; agent receives access tokens only; scope-down enforced; all issuances audit-logged with `{user, agent, provider, scopes, ttl}`.

### Flow C — Human-in-the-loop approval (CIBA)

1. Agent hits a sensitive action (e.g., `email:send`). SDK initiates CIBA backchannel auth request to Keycloak (`/ext/ciba/auth`) with `binding_message` describing the action ("Send email to bob@example.com?").
2. Keycloak invokes the custom **Authentication Channel Provider SPI** → publishes approval request to ntfy topic / web push.
3. User taps Approve/Deny in the demo approval UI; UI calls the SPI callback endpoint.
4. Agent polls the token endpoint (`grant_type=urn:openid:params:grant-type:ciba`); on approval receives a token scoped to the single action; on denial/timeout receives an error and aborts.

**Acceptance:** action token is single-use scope; denial and 120s timeout both abort cleanly; binding_message shown verbatim to the user.

### Flow D — FGA-filtered RAG

1. Docs ingested with owner/group tuples written to OpenFGA (`document:readme` `viewer` `user:patrick`).
2. At query time, retriever gets candidate chunks from the vector store, then calls OpenFGA `batch_check` (or pre-filters with `list_objects`) as the **end user**, not the agent.
3. Only authorized chunks reach the LLM context.

**Acceptance:** a user without a `viewer` tuple never sees the document's content in any agent answer, even when the vector store returns it as top hit.

## 5. OpenFGA Authorization Model (v0)

```
model
  schema 1.1

type user

type agent
  relations
    define operator: [user]          # the human this agent instance acts for

type grant                            # a third-party OAuth grant (user x provider)
  relations
    define owner: [user]
    define can_use: [agent] and operator from can_use

type document
  relations
    define owner: [user]
    define viewer: [user, user:*] or owner

type tool
  relations
    define invoker: [agent]
    define requires_approval: [agent]  # membership => CIBA required
```

## 6. Token Broker API (v0)

```
POST /v1/grants/{provider}/start        -> {authorize_url}        # user-present consent
GET  /v1/grants                          -> [{provider, scopes, created}]
DELETE /v1/grants/{provider}             -> 204                    # revoke + provider revocation call
POST /v1/tokens/{provider}
  auth: Bearer <exchanged Keycloak token>
  body: {"scopes": ["repo:read"]}
  200: {"access_token": "...", "expires_in": 900, "scopes": [...]}
  403: scope exceeds grant | FGA check failed
GET  /v1/audit                           -> issuance log (admin scope)
```

Implementation: Python 3.12, FastAPI, httpx, hvac (OpenBao client), openfga-sdk, PyJWT + JWKS caching. Postgres for grant metadata + audit.

## 7. Repository Layout

```
agentgate/
├── README.md
├── SPEC.md                        # this file
├── docker-compose.yml             # keycloak, openfga, openbao, postgres, broker, demo
├── deploy/
│   ├── keycloak/
│   │   ├── realm-export.json      # realm: agentgate; clients, exchange policies, CIBA config
│   │   └── extensions/            # built SPI jar mounted here
│   ├── openfga/model.fga
│   └── openbao/init.sh            # dev-mode init, KV v2 mount, broker policy
├── services/
│   └── token-broker/
│       ├── app/ (main.py, auth.py, providers/{google,github}.py, vault.py, fga.py, audit.py)
│       └── tests/
├── extensions/
│   └── keycloak-ciba-ntfy/        # Java SPI: AuthenticationChannelProvider -> ntfy + callback resource
├── sdk/
│   └── agentgate-py/              # exchange(), get_provider_token(), require_approval(), fga_filter()
├── demo/
│   ├── agent/                     # LangChain agent: GitHub issues summary + gated email send + RAG
│   └── approval-ui/               # minimal web app: pending approvals, approve/deny
└── docs/
    ├── architecture.md
    ├── threat-model.md
    └── adr/                       # ADR-0001 keycloak-as-as, ADR-0002 openbao-vs-broker-storage, ...
```

## 8. Milestones

**M0 — Skeleton (week 1)**
docker-compose brings up Keycloak (realm imported), OpenFGA (model loaded), OpenBao (dev mode), Postgres. Smoke test: OIDC login works, FGA check answers, Bao KV read/write.

**M1 — Token exchange (week 1–2)**
Configure standard token exchange in Keycloak; SDK `exchange()` returns downscoped delegated token; tests for scope-down and audience denial.

**M2 — Token Broker (week 2–3)**
GitHub provider end-to-end: grant setup, Bao storage, refresh loop, `POST /v1/tokens/github`, FGA gate, audit log. Google as second provider proves the abstraction.

**M3 — CIBA approval (week 3–4)**
SPI jar builds and deploys; ntfy round-trip; SDK `require_approval()` blocks/aborts correctly; approval UI.

**M4 — FGA RAG demo (week 4–5)**
Small doc corpus with mixed ACLs, embedded in a local vector store (chroma/pgvector); retriever wraps `batch_check`; adversarial test proves leakage is blocked.

**M5 — Polish (week 5–6)**
Threat model doc, ADRs, README with architecture diagram and 5-minute quickstart, demo video/gif.

## 9. Security Requirements (hard rules)

- Refresh tokens exist only inside OpenBao; broker memory only transiently during refresh.
- All agent-held tokens ≤ 15 min TTL.
- Token exchange must be explicitly permitted per (client, audience) pair in Keycloak — no wildcard exchange.
- CIBA `binding_message` must be human-readable and rendered verbatim; no approval without it.
- FGA checks always evaluate as the **end user**, never as the agent principal, for data access.
- Every token issuance and approval decision is audit-logged with correlation IDs.
- No secrets in compose files or repo: `.env` + Bao dev token only, documented as non-production.

## 10. Open Questions / v1 Roadmap

- SPIFFE/SPIRE for agent workload attestation replacing static client secrets (ADR needed).
- MCP authorization server mode: expose Keycloak via MCP's OAuth 2.1 + DCR expectations; test against Claude/other MCP clients.
- RAR (Rich Authorization Requests) for structured approval payloads instead of free-text binding_message.
- Multi-agent delegation chains (agent→agent exchange) and how `act` claims should compose.
- Connector abstraction: declarative provider manifests vs. code-per-provider.

## 11. Trade-offs Acknowledged

- **Keycloak vs. building a minimal AS:** Keycloak is heavy but gives CIBA/PAR/DCR/exchange for free; a custom AS would be a security liability.
- **OpenBao vs. Postgres-with-pgcrypto for grants:** Bao adds an operational component but gives leases, audit, and a credible security story; pgcrypto would be simpler but weaker positioning.
- **OpenFGA as user-context check vs. agent-context:** user-context is the correct confused-deputy defense, at the cost of needing the user identity threaded through every retrieval call.
- **Polling CIBA vs. ping/push mode:** poll mode is simpler for v0; push mode is a v1 upgrade.
