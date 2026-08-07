# Tasks: add-mcp-authorization (M4)

Spike-first (done). The build is a fresh-context continuation — the plan, the
spike findings (design.md "Resolved"), and the DCR config (in realm-export.json)
are all committed, so `/opsx:continue` / `/opsx:apply` can proceed directly.

## 1. Spike — Keycloak DCR + MCP auth handshake ✅ PASSED

- [x] 1.1 Ground the MCP auth spec (2025-06-18): RFC 9728 PRM, RFC 8414, DCR
  (RFC 7591), OAuth 2.1 + PKCE, RFC 8707 resource param, audience validation.
- [x] 1.2 Verify RFC 8414 AS metadata is served by Keycloak.
- [x] 1.3 Enable anonymous DCR: opened the Trusted Hosts policy (trusted-hosts
  localhost/127.0.0.1; host-sending match off; client-uris match on). **Baked into
  `realm-export.json` `components`.** DCR returns 201 with a public/PKCE client.
- [x] 1.4 Drive OAuth 2.1 + PKCE with the DCR'd client → token. Confirm the RFC
  8707 gap (`resource` not reflected in `aud`). Findings in design.md "Resolved".
  (Spike script in scratchpad `mcp_spike.py`; move under `spike/mcp/` in the build.)

## 2. Keycloak audience scaffolding (RFC 8707 workaround)

- [x] 2.1 Add a bearer-only `mcp-server` resource client to `realm-export.json`.
  (Built as a confidential client mirroring `token-broker` — `bearerOnly:false` +
  service accounts — because 2.3 needs it to be the exchange subject; a bearerOnly
  client cannot request tokens. It is still the resource audience target.)
- [x] 2.2 Add an `mcp-audience` client scope (`oidc-audience-mapper` →
  `mcp-server`) and make it a **realm default** (`defaultDefaultClientScopes`) so
  DCR-registered clients carry `aud=mcp-server`. Verified: `test_mcp_authorization
  ::test_dcr_then_oauth_yields_mcp_audience_token` asserts the DCR'd token's aud.
- [x] 2.3 `mcp-server` performs RFC 8693 exchange for `aud=token-broker` /
  `aud=agent-tools-api` (`standard.token.exchange.enabled`). Agent-identity
  question resolved: exchange sets `azp=mcp-server`, so **`mcp-server` is the
  consent agent** (design §3 fallback; documented in the threat model). Verified by
  `test_mcp_chain` (consent seeded for `mcp-server`, get_provider_token succeeds).

## 3. MCP server (`services/mcp/`, port 8140)

- [x] 3.1 Scaffolded `services/mcp/` mirroring `services/token-broker/` (FastAPI,
  OTel fire-and-forget, `GET /healthz`, compose service on 8140, **no
  depends_on: lgtm**). Fire-and-forget confirmed: full suite green with lgtm stopped.
- [x] 3.2 RFC 9728: serves `/.well-known/oauth-protected-resource` naming the realm
  AS; returns `401` + `WWW-Authenticate: Bearer resource_metadata="…"` on
  unauthenticated `POST /mcp`; validates `aud` = `mcp-server`. Verified by
  `test_mcp_authorization` (discovery + wrong-audience refusal).
- [x] 3.3 Minimal MCP over streamable-HTTP JSON-RPC: `initialize`, `tools/list`,
  `tools/call`. Tools `get_provider_token` (→ broker via exchange) and `send_email`
  (→ tools-api, reactive approval). Inbound token never forwarded — each tool
  exchanges first (`test_mcp_chain::test_inbound_mcp_token_never_forwarded`).

## 4. Reactive approval (human-approval delta)

- [x] 4.1 `services/tools-api/`: an un-approved sensitive call returns a `428`
  `approval_required` challenge and **registers the real action server-side** with
  the approval service (hash from the observed request); returns the reference id +
  action token. Existing action-token path unchanged (M3 tests still green).
- [x] 4.2 SDK `drive_ciba_approval(ref, …)`: the reactive counterpart — the server
  registered the action, so the agent only drives CIBA (binding_message=ref) and
  retries with the action token. Enforcement/hash/single-use unchanged from M3,
  asserted through the reactive path by `test_reactive_approval`.

## 5. Tests (drive the live stack)

- [x] 5.1 `test_mcp_authorization.py` (5 tests): scripted spec-compliant MCP client
  does discover (401→PRM→AS metadata) → DCR → OAuth 2.1 + PKCE → token with
  `aud=mcp-server` → `tools/list`. Wrong-audience token refused (401). All pass.
- [x] 5.2 `test_mcp_chain.py` (3 tests): through MCP tools, a brokered provider
  token (consent-gated) and a human-approved `email.send` (reactive challenge →
  CIBA → approve → retry → mail in Mailpit); inbound token refused downstream.
- [x] 5.3 `test_reactive_approval.py` (3 tests): un-approved call is challenged
  (428) not executed; replay + param-mismatch still refused (M3 guarantees intact
  through the reactive path).

## 6. Verify + wrap

- [x] 6.1 Added an MCP row to the Grafana dashboard (stat "MCP tool calls (1h)" +
  "MCP — live tool audit" logs, ids 12/13). Confirmed rendering in a real browser
  (screenshot) — provisioned with 13 panels, live mcp_audit lines showing.
- [x] 6.2 Drove the full flow and **looked**: a scripted MCP client walks
  discover → DCR → login → consent-gated brokered token → reactive approved action.
  Verified in the real sinks — one linked trace in Tempo spanning
  `mcp → keycloak → tools-api → approval` under the correlation id, matching live
  `mcp_audit` in Loki. A note in the page/spec records that Claude and other MCP
  clients use the same standard handshake.
- [x] 6.3 `docs/threat-model.md`: added the "MCP authorization (Flow D, M4)"
  section — DCR "any client can register → consent is the gate", the RFC 8707 gap +
  `mcp-audience` scope workaround, no token-passthrough, and the agent-identity
  trade-off. Updated the M3 "trigger on the resource server" note to done.
- [x] 6.4 Clean-slate `down -v && up` reproduces the milestone; full smoke suite
  **54/54 green** with lgtm up, and green with lgtm stopped (only the console
  Grafana-proxy view tests fail — a pre-existing view-of-lgtm artifact, not a
  delegation-service dependency; all MCP tests pass with lgtm down). M4 blog page
  `docs/blog/m4-mcp-authorization.html` written with its sequence-diagram flow
  (verified rendering). Archive is the next action (`/opsx:archive`).
