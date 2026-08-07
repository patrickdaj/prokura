# Proposal: add-mcp-authorization (M4)

## Why

The headline. M0–M3 built the whole delegation chain — delegated exchange, the
token broker with per-agent consent, and human approval — but every flow so far
has been driven by the Python SDK and the test harness. M4 makes the chain
consumable by **any standard MCP client** (Claude among them) through MCP's
authorization model, with **Keycloak as the MCP authorization server**. This is
the moment Prokura stops being "a library you call" and becomes "an authorization
server a real agent connects to": a real MCP client discovers the server, registers
itself, logs the user in, and then — through MCP tools — obtains a brokered
provider token and performs a **human-approved** action. It is also where we land
the M3 carry-forward: the **approval trigger moves onto the resource server** (the
MCP tool), reactively, rather than depending on the agent to ask.

## What Changes

- **Keycloak as the MCP Authorization Server.** Enable OAuth 2.1 (PKCE) +
  **Dynamic Client Registration (RFC 7591)** so an MCP client can self-register,
  and expose AS metadata (RFC 8414). The security consequence is explicit: with
  DCR on, *any* client can register — so **per-agent consent (M2) is the gate**
  that stands between a freshly-registered client and a user's grants.
- **MCP server (new, `services/mcp/`).** An MCP server that is also an OAuth 2.1
  **resource server**: it serves **RFC 9728 Protected Resource Metadata** pointing
  at Keycloak, validates presented access tokens (audience check, the M1 defense),
  and exposes tools that drive the chain — e.g. *get a provider token* (via the
  broker) and *send an email* (the gated, approval-requiring action).
- **Reactive approval (M3 carry-forward).** The sensitive MCP tool does not rely
  on the agent to pre-request approval: it refuses an un-approved call with an
  **`approval_required` challenge**, registers the real action server-side, and the
  client completes the (client-initiated) CIBA approval and retries. The trigger
  now lives on the resource server.
- **Documented RFC 8707 gap.** MCP expects resource indicators to bind a token to
  a specific server; Keycloak's support is the known gap — the workaround is the
  existing audience-scoping (`broker-audience` / `tools-audience`), documented
  honestly in the spec and threat model.

## Capabilities

### New Capabilities

- `mcp-authorization`: the contract for Keycloak-as-MCP-AS and the MCP server as a
  resource server — AS metadata + DCR (RFC 7591), OAuth 2.1 / PKCE, RFC 9728
  protected-resource metadata served by the MCP server, access-token validation,
  and the documented RFC 8707 resource-indicator gap with its scopes workaround.

### Modified Capabilities

- `human-approval`: a delta moving the approval **trigger** to the resource server
  (reactive `approval_required` step-up; the server registers the real action).
  Enforcement, hash-binding, and single-use are unchanged — only who initiates.

## Impact

- **New:** `services/mcp/` (MCP server + tools, OAuth 2.1 resource server, RFC 9728
  metadata), Keycloak DCR + AS-metadata config, the `mcp-authorization` spec, and a
  **demo driving a real MCP client** (e.g. Claude) through login → consent →
  brokered token → approved action.
- **Modified:** `docker-compose.yml` (mcp service; DCR enablement),
  `deploy/keycloak/realm-export.json` (DCR / client-registration policy, AS
  metadata), the Grafana dashboard (an MCP row), `docs/threat-model.md` (MCP AS,
  DCR "any client can register → consent is the gate", the RFC 8707 gap), and the
  reactive-approval change to `services/tools-api/` (or folded into the MCP tool).
- **Open M4 with a spike** (mirroring M0/M2/M3): prove that Keycloak DCR + the MCP
  authorization handshake (metadata discovery → dynamic registration → OAuth 2.1
  token) actually works against a **real MCP client** before building the server —
  the exact MCP auth spec revision and Keycloak DCR specifics are verified against
  the running image, not assumed.
- **Verification (definition of done):** a real MCP client completes the full
  chain via MCP tools and a human approval; the flow appears as one linked trace
  with live audit in Loki; clean-slate `down -v && up` reproduces it.
