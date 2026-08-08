# Prokura — Architecture

**An open-source reference implementation of agentic identity** — user authentication,
delegated agent authorization, third-party token brokering, human-in-the-loop
approval, and fine-grained RAG authorization — assembled from **Keycloak, OpenFGA, and
OpenBao**. An OSS answer to "Auth0 for AI Agents."

> This document supersedes `SPEC.md` (the original v0.1 draft, kept for history). It
> describes the system **as built** across M0–M6; where the draft's design changed
> under review, the shipped decision is what appears here. The *why* behind each
> decision is in the [ADRs](./adr/); the adversarial analysis is in the
> [threat model](./threat-model.md); the control audit is in the
> [security review](./security-review.md). Reader's tour: the
> [milestone blog series](./blog/index.html) (build log) and the
> [walkthroughs](./walkthroughs/) (follow-along guided tour).

Prokura is a **reference architecture, not a production platform** (ADR-0010): the
docs, ADRs, threat model, and demo *are* the product. The compose stack is explicitly
**non-production** (single-node, dev secrets, no mTLS); §9's hard rules are stated as
"what production would require," and residual risks are disclosed, not hidden.

## What an agent needs — and where Prokura provides it

| An agent acting for a user must… | Flow | Provided by |
|----------------------------------|------|-------------|
| Know **who the user is** | login | Keycloak OIDC |
| Prove it **acts for the user, with reduced scope** | **A** delegation | Keycloak RFC 8693 token exchange |
| Call **third-party APIs** without holding long-lived secrets | **B** brokering | Token Broker + OpenBao |
| **Pause for human approval** on sensitive actions | **C** approval | Approval service + Keycloak CIBA |
| Retrieve only documents **the user may see** | **D** RAG | RAG retriever + OpenFGA (as the end user) |
| Be reachable by a **real agent client** | surface | MCP server (Keycloak as the MCP AS) |

## Components (as built)

| Component | Technology | Port | Role |
|-----------|-----------|------|------|
| IdP / AS / MCP AS | Keycloak 26.7 | 8180 | User authn, token exchange, CIBA, DCR, MCP authorization server |
| Token Broker | Python/FastAPI | 8110 | Third-party grant lifecycle, refresh, scoped hand-out, **sole `can_use` writer** |
| Approval service | Python/FastAPI | 8120 | CIBA-gated human approval; trusted payload rendering; single-use action tokens |
| Tools-API | Python/FastAPI | 8130 | Gated `email.send`; reactive step-up; hash-verify + single-use before acting |
| MCP server | Python/FastAPI | 8140 | OAuth 2.1 resource server + minimal MCP server; drives the chain through tools |
| RAG retriever | Python/FastAPI | 8150 | FGA-filtered retrieval, authorized **as the end user**; pgvector store |
| Console | Python/FastAPI | 8095 | Bespoke observability page (trace → span → correlated Loki logs) |
| OpenFGA | OpenFGA | 8081 | Per-agent consent (`can_use`) + document authorization (`viewer`) |
| OpenBao | OpenBao (dev) | 8200 | The only store of long-lived provider credentials; broker-scoped policy |
| Mailpit | Mailpit | 8025 | Local SMTP sink for the gated send (no Google friction — ADR-0015) |
| ntfy | ntfy (deny-all) | 8090 | Notify-only approval pings; decisions happen only in the authenticated UI |
| lgtm | grafana/otel-lgtm | 3001 | Tempo + Loki + Prometheus + Grafana; fire-and-forget telemetry receiver |

Every service since M2 is **born instrumented** (ADR-0017): W3C `traceparent` is the
cross-service join key, the domain correlation id rides as a span attribute and on
every audit line, and exporters are fire-and-forget (no `depends_on: lgtm`).

## Core flows

Each flow has a build-log blog and a follow-along walkthrough; the *why* is in the ADRs.

### Flow A — Delegated agent token (RFC 8693)
The agent app exchanges the user's token for one that is `sub=user`, `azp=agent`,
down-scoped, and addressed to a **specific audience** — every resource server rejects a
token not addressed to itself (ADR-0002, the confused-deputy defense). → [M1 blog](./blog/m1-token-exchange.html)

### Flow B — Third-party token brokering
Grants are acquired via **Keycloak account-linking** (`kc_action=idp_link`, Store
Tokens — ADR-0011), not a parallel OAuth flow; the broker imports the refresh
credential into OpenBao and owns refresh/lease/scope-down. `POST /v1/tokens/{provider}`
validates the token, checks scope ⊆ grant and the per-agent `can_use` consent tuple,
then returns a **short-lived access token only** (`expires_in ≤ 900`; residual provider
validity documented honestly — ADR-0003). → [M2 blog](./blog/m2-token-broker.html)

### Flow C — Human-in-the-loop approval (CIBA)
Built on Keycloak's **built-in CIBA HTTP channel** (no Java SPI — ADR-0006). The agent
registers `{action, params}` with the approval service; `binding_message` carries only
a reference id; the **trusted UI renders the service-held payload** (never agent prose
— ADR-0005); the resource server hash-verifies and **atomically consumes** the action
token (single-use — ADR-0008). The approval *trigger* lives on the resource server
(reactive step-up — ADR-0018): a sensitive call without an action token is refused with
a `428 approval_required`. ntfy is notify-only (ADR-0007). → [M3 blog](./blog/m3-human-approval.html)

### Flow D — FGA-filtered RAG
Ingestion writes `document` owner/viewer tuples **before** a doc is queryable; at query
time the retriever embeds, pulls top-K from **pgvector** (ADR-0019) with a **local
offline embedder** (ADR-0020), then authorizes candidates against OpenFGA **as the end
user** (`batch_check` subject `user:{sub}`) — the top hit is filtered when the user
holds no `viewer` tuple. The corpus is **Drive-shaped** (ADR-0015). → [M5 blog](./blog/m5-rag-authorization.html)

### The MCP surface
Keycloak is the **MCP authorization server** (RFC 8414 metadata, RFC 7591 DCR, RFC 9728
PRM served by the MCP server); the delegation chain is driven through MCP tools
(`get_provider_token`, `send_email`, `rag_search`) by a real client. Each tool
re-exchanges the inbound token — never forwarded downstream. Documented gap: RFC 8707
`resource` isn't reflected into `aud`, so audience is bound by a client scope
(ADR-0013). → [M4 blog](./blog/m4-mcp-authorization.html)

## Authorization model (OpenFGA)

`type user`, `type agent` (`operator`), `type grant` (`owner`, `can_use: [agent]` —
**direct assignment**, ADR-0001), `type document` (`owner`, `viewer: [user, user:*] or
owner`), `type tool`. The broker is the **sole `can_use` writer** and enforces
`operator == owner` at write time — a trusted-code assumption named in the threat model.

## Trust boundary and security posture

The **TCB** is Keycloak, the token broker, the approval service, the RAG retriever,
OpenFGA, and OpenBao; agents, MCP/DCR clients, ntfy, and the tools-API execution
surface are outside it. The full TCB statement, assets, attacker model, STRIDE-per-flow
grids, and attack trees are in the [threat model](./threat-model.md); the control audit
against the [`security-baseline`](../openspec/specs/security-baseline/spec.md)
invariants — with a findings register (3 Low findings, all disclosed) — is in the
[security review](./security-review.md).

## Repository layout (as built)

```
prokura/
├── docker-compose.yml            # the whole stack
├── SPEC.md                       # superseded → this doc (kept for history)
├── SPEC-REVIEW.md                # F1–F9 / Q1–Q7 findings (source for the ADRs)
├── deploy/{keycloak,openfga,openbao,ntfy,lgtm,rag}/
├── services/{token-broker,approval,tools-api,mcp,rag,console}/
├── sdk/prokura-py/               # exchange(), get_provider_token(), require_approval()
├── spike/{ciba-http-channel,idp-link,mcp,rag}/   # de-risking spikes per milestone
├── tests/smoke/                  # drives the live stack end to end
├── openspec/{specs,changes}/     # the working source of truth for specs & changes
└── docs/{architecture.md, threat-model.md, security-review.md, adr/, blog/, walkthroughs/}
```

## Roadmap / v1

The forward-looking items from `SPEC.md` §10 and the SPEC-REVIEW roadmap notes live
here. The list below is largely **parity and completeness** — the table stakes a mature
agent-identity platform (an "Auth0 for AI agents") would be expected to carry:

- **SPIFFE/SPIRE** workload attestation, replacing static client secrets for agent
  identity.
- **Real Google/GitHub providers end-to-end** — live Google Drive ingestion feeding
  the RAG corpus's FGA tuples (the enforcement path is already built; only the tuple
  *source* changes — ADR-0015/ADR-0011), and a GitHub App read action.
- **TypeScript SDK** (v0 is Python — ADR-0014), to match where agent-app developers are.
- **RAR (Rich Authorization Requests)** in Keycloak for structured approval payloads
  (Prokura reproduces RAR's properties out-of-band today — ADR-0005).
- **Multi-agent delegation chains** (agent→agent exchange) and how `act` claims compose.
- **Cross-App-Access (XAA) / ID-JAG** (`draft-ietf-oauth-identity-assertion-authz-grant`)
  for app-to-app agent access (ADR-0016).
- **CIBA push mode** (v0 uses poll), and the security-review `fix` findings (SR-01,
  SR-02) hardened.
- Production posture: mTLS between services, secret rotation, HA topologies — the
  accepted residuals in the threat model's register.

### Beyond parity — where Prokura earns its keep

Parity makes it credible; these make it worth adopting. v0 proves delegation can be
*safe*; v1 should make safe delegation something people can **live with, on the tools they
actually use**. Roughly ranked by leverage — the first three are the proposed v1 spine.

1. **MCP gateway mode — protect tools you didn't write.** Today the guarantees apply only
   to Prokura's three demo tools. A **proxy that fronts any upstream MCP server** — passing
   through `tools/list`, classifying tools by risk, and transparently wrapping sensitive
   calls in the `428 → approve → consume` ceremony while re-exchanging tokens per upstream
   audience — turns Prokura from a reference-with-demo-tools into **drop-in delegation for
   the whole MCP ecosystem**. It's a re-aiming of the existing MCP service, not a rebuild,
   and it's the single highest-leverage move: the difference between an exhibit and an appliance.

2. **The authority console — one surface where a human governs their agents.** The
   delegation-chain console is operator-facing; the *human's* own experience is scattered
   across four surfaces (two consents, the approval UI, ntfy). v1's usability centerpiece is
   a user-facing **"my agents" panel**: every agent acting for me, what each may do, pending
   approvals, a live activity feed (the already-correlated Loki audit lines), and
   **one-click revoke** per agent. Power of attorney is only tolerable if you can read the
   register and tear up the grant — and nothing today aggregates that view for the principal.

3. **Instant revocation & continuous evaluation (the kill switch).** TTL-as-only-revocation
   is the biggest gap for real use. Revoking consent should *immediately* deny in-flight
   authority — the per-hand-out consent-tuple check (already there) plus Keycloak
   session/offline-token revocation plus a broker deny-list, propagated in seconds; the
   standards-track version adopts **Shared Signals / CAEP** so revocation and risk events
   become signals other systems can consume. "How fast can you make an agent stop?" is the
   first question a security team asks; today the answer is "up to 15 minutes," and v1 can
   make it "now."

4. **Risk-tiered approval — beat approval fatigue.** Human-in-the-loop dies of fatigue: if
   everything needs a click, humans rubber-stamp and the control becomes theater. Make
   approval a **graduated policy** (a small Cedar-style engine between the tool and the
   approval service): auto-allow within policy, approve the genuinely sensitive, hard-deny
   the forbidden — with **bounded standing approvals** ("this and similar for 1 hour, max 5
   sends") that are themselves hash-scoped and audited. This is where security and usability
   are the *same* feature.

5. **Taint-aware step-up — prompt-injection containment as a mechanism, not a hope.** When a
   delegated session ingests **untrusted content** (a low-trust RAG chunk, a fetched web
   page), mark the session *tainted* and have the MCP layer raise the bar for subsequent
   side-effectful calls — require approval where it would normally auto-allow, or shrink
   scopes. The model above the boundary can be lied to; a boundary that reacts to *what the
   model has read* is genuine defense-in-depth. Flows C and D already supply the parts.

6. **Metered delegation — authority that depletes.** Real powers of attorney have limits
   ("up to $X"). Add **budgets** to consent — N emails/day, M token issuances/hour,
   cumulative caps — enforced at the broker/tools layer (counters keyed by the tuples that
   already exist) and shown in the console. It turns "the agent can send email" into "the
   agent can send *3* emails *today*," which is how people actually extend trust to automation.

Two smaller but high-signal additions: **organizational approval routing** (the approver ≠
the delegator — manager sign-off or 4-eyes for high-tier actions; real orgs won't accept an
agent's own user rubber-stamping its actions), and **invariant monitors** — the postmortem's
queries run continuously as live assertions ("no token ever exceeds 900 s," "no send without
a consumed approval") that alert on violation: security regression tests against production
telemetry.

**Proposed v1 spine:** gateway (1) + authority console (2) + instant revocation (3) together
change the category — from *a reference proving delegation can work* to *the thing you put in
front of your agents' tools so a human can see, bound, and stop them*. Risk-tiered approval
(4) is the fast-follow that keeps it livable; taint-aware step-up (5) is the differentiator
worth writing a paper about.

### Drive it with a real MCP client

v0 is exercised by the in-repo smoke client; v1 proves the same chain from a **real
external agent** (opencode, Claude Code) and fills in the delegation modes a real
deployment needs. Each is meant to be driven end-to-end by hand:

- **Local delegation, real client** — point opencode / Claude Code at the MCP URL and
  complete discovery → DCR → OAuth 2.1 + PKCE over a **loopback redirect** (RFC 8252) →
  login + "act on your behalf" consent → `aud=mcp-server` token, then drive
  `get_provider_token` / `send_email` / `rag_search`. (`demo/capture/flow_a.py` already
  performs this exact handshake headlessly; v1 is a real client doing it interactively.)
- **Headless delegation via Device Authorization Grant** (RFC 8628) — enable device flow
  on the realm so a browserless agent (cloud/CI) delegates by having the user approve a
  short code on a second device.
- **CIBA for the *initial* delegation** — reuse the approval service's existing CIBA push
  channel (today only step-up, Flow C) to bootstrap the *first* token for a headless agent
  via `login_hint` — no browser, no device code. Distinct from the "CIBA push mode" item
  above, which is about step-up.
- **Multiple clients, one user** — opencode and Claude Code side-by-side as **distinct DCR
  clients** (distinct `azp`), each with its own consent and audit trail, both acting as you.
- **Adversarial LLM-in-the-loop** — drive the model (Claude, inside opencode) into a
  prompt-injected or hallucinated action and confirm the controls hold beneath it: approval
  binds the **server-stored** payload (Flow C), RAG filters **as the user** (Flow D), and the
  provider refresh secret never leaves OpenBao (Flow B). The model proposes; Prokura disposes.

### Hardening found while building the walkthroughs

- **RAG tuple reconciliation on startup** — decouple the OpenFGA document owner/viewer tuple
  writes from the pgvector seed guard in `services/rag/ingest.py`, so an OpenFGA store reset
  after first ingest can't silently leave every document filtered.
- **Persist the consent-screen scope** — bake `act-on-your-behalf` into `realm-export.json`
  as a **per-client** default scope so Flow A's explicit consent is reproducible from a cold
  `docker compose up` (today `demo/capture/flow_a.py` configures it live, per-client, to avoid
  forcing consent on every DCR client).
- **Console trace→log jump** — surface the correlated Loki audit lines from an open span in
  the delegation-chain console; the join (`correlation_id = trace_id`) is proven in the
  telemetry postmortem and the `/api/loki` proxy is already built.

## Prior art

Prokura's broker is a from-scratch minimal subset of **[Nango](https://nango.dev)** (an
established OSS third-party OAuth token broker). Prokura's value is the *assembly* —
delegation + CIBA + FGA + brokering under one identity model, reachable over MCP — not
the broker in isolation (ADR-0016).
