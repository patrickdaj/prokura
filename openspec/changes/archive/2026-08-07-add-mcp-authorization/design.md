## Context

The headline milestone. M0–M3 built the delegation chain (exchange → broker +
consent → human approval) but drove it with the Python SDK and the test harness.
M4 makes the chain reachable by any standard **MCP client** through MCP's
authorization model, with **Keycloak as the MCP authorization server**. It also
lands the M3 carry-forward: the human-approval *trigger* moves onto the resource
server (reactive step-up), rather than depending on the agent to ask.

The authoritative spec is MCP **2025-06-18 Authorization** (verified during the
spike). In it: the MCP server is an **OAuth 2.1 resource server** that serves
**RFC 9728 Protected Resource Metadata**; the client discovers the AS via RFC
9728 → RFC 8414, may **dynamically register (RFC 7591)**, runs **OAuth 2.1 +
PKCE** with the RFC 8707 `resource` parameter, and the server **validates the
token audience**. The Phase-1 spike proved the Keycloak side end to end (see
"Resolved").

Structural templates: `services/token-broker/` / `services/approval/` (flat
FastAPI modules, OTel fire-and-forget, `build:` in compose). House style: the
archived M1–M3 changes.

## Goals / Non-Goals

**Goals:**

- **Keycloak as MCP AS:** RFC 8414 metadata + anonymous **DCR (RFC 7591)** with a
  client-registration policy that permits it (baked into `realm-export.json`).
- **MCP server (`services/mcp/`, port 8140):** an OAuth 2.1 **resource server**
  that serves RFC 9728 PRM at `/.well-known/oauth-protected-resource`, returns
  `401` + `WWW-Authenticate: Bearer resource_metadata="…"` on an unauthenticated
  request, and **validates the access-token audience** (`aud=mcp-server`).
- **MCP tools that drive the chain:** at least *get a provider token* (via the
  broker) and *send an email* (the gated, approval-requiring action) — so a real
  MCP client can walk login → consent → brokered token → approved action.
- **Reactive approval (M3 carry-forward):** the sensitive tool refuses an
  un-approved call with an `approval_required` challenge, registering the real
  action server-side; the client completes the (client-initiated) CIBA and retries.
- **Document the RFC 8707 gap** honestly with the audience-scope workaround.
- Born instrumented; a real MCP client completes the flow end to end.

**Non-Goals:**

- Wiring an actual Claude Desktop/Code instance in CI — verification uses a
  **scripted, spec-compliant MCP client** that performs the exact handshake
  (discover → DCR → OAuth 2.1 + PKCE → token → tool call). A real client uses the
  same standard steps.
- The full MCP protocol surface — implement enough (initialize + tools/list +
  tools/call over HTTP, plus the auth) to demonstrate the chain, not a complete
  MCP server framework.
- Production hardening (HA, mTLS). docker-compose, non-production.

## Decisions

### 1. Keycloak is the AS; DCR is enabled via a baked client-registration policy

RFC 8414 metadata already works. Anonymous DCR is blocked by default by the
**Trusted Hosts** policy; the fix (proven in the spike, now in
`realm-export.json`) is: `trusted-hosts: [localhost, 127.0.0.1]`,
`host-sending-registration-request-must-match: false` (real MCP clients call from
arbitrary source IPs), `client-uris-must-match: true` (redirect URIs must be to
trusted hosts — OAuth 2.1 already requires localhost/HTTPS redirects). **Security
consequence, stated explicitly:** with DCR on, *any* client can register — so
**per-agent consent (M2) is the gate** between a fresh client and a user's grants.

### 2. Close the RFC 8707 audience gap with an `mcp-audience` client scope

The spike confirmed Keycloak does **not** reflect the `resource` parameter into
the token `aud` (the documented gap). Workaround, matching M1/M2's audience
pattern: add a bearer-only `mcp-server` resource client and an `mcp-audience`
client scope (an `oidc-audience-mapper` → `mcp-server`), and make it a **realm
default** client scope so **DCR-registered clients carry `aud=mcp-server`**. The
MCP server validates `aud` contains `mcp-server` (the M1 audience defense). The
client still sends `resource` per spec; we don't rely on it for binding.

### 3. The MCP server is the resource server AND the chain's orchestrator

On a tool call the MCP server validates the inbound token, then acts on the
user's behalf against the existing services. To call the broker (needs
`aud=token-broker`) and the gated tool (needs `aud=agent-tools-api`), the MCP
server performs **RFC 8693 token exchange** (M1) using a confidential
`mcp-server` client. **Open decision for the build:** what "agent" identity the
consent tuple keys on — the confidential `mcp-server` client (simplest: one
consent for "the MCP server acting for you") vs. the per-DCR client id (stronger:
consent per MCP client, fully honoring "any client can register → consent gates
each"). Recommend starting with the DCR client id as the agent so the security
story is honest, and falling back to `mcp-server` if exchange can't preserve it.

### 4. Reactive approval on the sensitive tool (human-approval delta)

The MCP `send_email` tool (delegating to `tools-api`) does not require the agent
to pre-request approval. On an un-approved call it returns an `approval_required`
challenge and **registers the real action server-side** (defining the hash from
the actual request). The client runs CIBA for that reference and retries.
Enforcement, hash-binding, and single-use are unchanged from M3 — only the
trigger moves. This is a `human-approval` MODIFIED requirement.

### 5. HTTP transport, minimal MCP surface

Implement the MCP server over the streamable-HTTP transport with just
`initialize`, `tools/list`, `tools/call`, plus the RFC 9728 metadata + 401
challenge. Enough to prove the authorization story and drive the chain.

## Risks / Trade-offs

- **[DCR "any client can register" is a real exposure]** → mitigated by design:
  registration grants nothing by itself; provider grants require per-agent
  consent (M2) and sensitive actions require human approval (M3). Documented in
  the threat model as the reason consent is the gate.
- **[RFC 8707 gap could let a token be replayed at the wrong resource]** →
  audience-scope workaround binds `aud=mcp-server`; the MCP server validates it
  and never passes the inbound token through to downstream services (it exchanges
  for a fresh, correctly-audienced token).
- **[Agent-identity / exchange model unresolved]** → Decision 3 flags it; resolve
  early in the build with a small exchange probe (mirrors the M2/M3 spikes).
- **[Verifying "a real MCP client" without one in CI]** → a scripted spec-exact
  client is the test; a note documents that Claude/other clients use the same
  standard handshake.

## Migration Plan

Additive. (1) `realm-export.json`: DCR policy (**done**), the `mcp-server` client
+ `mcp-audience` default scope. (2) `services/mcp/` + compose. (3) reactive-approval
change in `services/tools-api/`. (4) dashboard MCP row; threat-model MCP section.
Rollback: remove the mcp service + revert the realm additions; `down -v && up`
returns to the M3 baseline. DoD: a scripted MCP client completes discover → DCR →
OAuth 2.1 → tool → brokered token → approved action; one linked trace + live Loki
audit; clean-slate `down -v && up` reproduces it.

## Open Questions

- **Agent identity for consent** (Decision 3) — DCR client id vs `mcp-server`.
- **Does the RFC 8693 exchange from a DCR public client work**, or must the
  `mcp-server` confidential client be the exchange subject? Probe early.
- **Streamable-HTTP vs SSE** transport specifics for the minimal MCP server.

## Resolved at implementation time

Verified against the running Keycloak 26.7.1 image (Phase-1 spike,
`spike/mcp/` — script preserved in scratchpad, to be moved under `spike/`):

- **MCP auth spec = 2025-06-18.** MCP server serves RFC 9728 PRM at
  `/.well-known/oauth-protected-resource` (MUST include `authorization_servers`);
  401 uses `WWW-Authenticate: Bearer resource_metadata="…"`; client discovers AS
  via RFC 8414; DCR via RFC 7591; OAuth 2.1 + PKCE with the `resource` param;
  server validates audience.
- **RFC 8414 AS metadata works:** `…/realms/prokura/.well-known/oauth-authorization-server`
  returns issuer, `registration_endpoint`
  (`…/clients-registrations/openid-connect`), token endpoint, and `S256`.
- **Anonymous DCR works after opening the Trusted Hosts policy** (now baked into
  `realm-export.json`): a client POSTs client metadata to the registration
  endpoint and gets a public/PKCE `client_id` + a registration access token
  (HTTP 201). Without the policy change it is 403 "Host not trusted".
- **OAuth 2.1 + PKCE completes** with the DCR'd public client (auth code + PKCE →
  token 200; `azp` = the dynamic client id).
- **RFC 8707 gap confirmed:** the `resource` param is **not** reflected in `aud`
  (came back `null`). Hence Decision 2's `mcp-audience` client-scope workaround.
- **Ports:** MCP server 8140. (broker 8110, approval 8120, tools-api 8130.)
