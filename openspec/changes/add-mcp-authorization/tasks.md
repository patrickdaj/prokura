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

- [ ] 2.1 Add a bearer-only `mcp-server` resource client to `realm-export.json`.
- [ ] 2.2 Add an `mcp-audience` client scope (`oidc-audience-mapper` →
  `mcp-server`) and make it a **realm default** client scope so DCR-registered
  clients carry `aud=mcp-server`. Verify a DCR'd client's token has the audience.
- [ ] 2.3 Ensure the `mcp-server` service can perform RFC 8693 exchange for
  `aud=token-broker` / `aud=agent-tools-api` (probe the agent-identity question
  from design §3 / Open Questions — DCR client id vs `mcp-server` as the agent).

## 3. MCP server (`services/mcp/`, port 8140)

- [ ] 3.1 Scaffold mirroring `services/token-broker/` (FastAPI, OTel fire-and-forget,
  `GET /healthz`, compose service, **no depends_on: lgtm**).
- [ ] 3.2 RFC 9728: serve `/.well-known/oauth-protected-resource` naming the realm
  AS; return `401` + `WWW-Authenticate: Bearer resource_metadata="…"` on
  unauthenticated protected requests. Validate access-token `aud` = `mcp-server`.
- [ ] 3.3 Minimal MCP over streamable-HTTP: `initialize`, `tools/list`,
  `tools/call`. Tools: `get_provider_token` (→ broker via exchange) and
  `send_email` (→ tools-api, reactive approval). Never forward the inbound token.

## 4. Reactive approval (human-approval delta)

- [ ] 4.1 `services/tools-api/`: on an un-approved sensitive call, return an
  `approval_required` challenge and **register the real action server-side** with
  the approval service (hash from the actual request); return the reference id.
- [ ] 4.2 SDK/tool flow: attempt → challenge → CIBA (binding_message=ref) →
  retry with the action token. Enforcement/hash/single-use unchanged from M3.

## 5. Tests (drive the live stack)

- [ ] 5.1 `test_mcp_authorization.py`: scripted spec-compliant MCP client does
  discover (401→PRM→AS metadata) → DCR → OAuth 2.1 + PKCE → token with
  `aud=mcp-server` → `tools/list`. Wrong-audience token refused (401).
- [ ] 5.2 `test_mcp_chain.py`: through MCP tools, obtain a brokered provider token
  (consent-gated) and perform a human-approved `email.send` (reactive challenge →
  approve → retry → mail in Mailpit). Inbound token never forwarded downstream.
- [ ] 5.3 Reactive-approval negatives: un-approved call is challenged not executed;
  replay/param-mismatch still refused (M3 guarantees intact).

## 6. Verify + wrap

- [ ] 6.1 Add an MCP row to the Grafana dashboard; confirm it renders (screenshot).
- [ ] 6.2 Drive the full flow and **look**: a real (scripted) MCP client walks
  login → consent → brokered token → approved action; one linked trace + live Loki
  audit. Note that Claude/other MCP clients use the same standard handshake.
- [ ] 6.3 `docs/threat-model.md`: MCP AS section — DCR "any client can register →
  consent is the gate", the RFC 8707 gap + audience-scope workaround, no
  token-passthrough.
- [ ] 6.4 Clean-slate `down -v && up`; whole smoke suite green, incl. with lgtm
  stopped. Then archive + M4 blog page (with its sequence-diagram flow, per the
  docs/blog norm).
