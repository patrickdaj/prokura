# Proposal: add-token-exchange (M1)

## Why

M0 stood up the stack and proved OIDC login and the ≤15-minute Keycloak token bound, but the core of the `identity-delegation` capability — the RFC 8693 delegated token exchange and the F2-A broker-audience rule — is specified and unimplemented. M1 makes delegation real: an agent app turns a user's token into a downscoped token that is attributable to *user-via-agent* (`sub`=user, `azp`=agent), and obtains a separate token correctly addressed to the Token Broker. This is the foundation every later milestone builds on (M2 presents the broker-audience token; M3/M4 act as the delegated principal), and it produces the project's first genuine cross-service delegated trace in the Console.

## What Changes

- Configure Keycloak **standard token exchange** for the `agent-app` client against the `agent-tools-api` and `token-broker` audiences, with explicit per-(client, audience) permissions — no wildcard exchange (SPEC §9).
- Implement the Python SDK's `exchange()` helper in `sdk/prokura-py/`: user token → delegated token, with the two-step path (exchange to `agent-tools-api` for tool calls, and to `aud=token-broker` for broker calls, F2-A).
- Verify the F2-A defense end to end: the broker (a bearer-only resource for now) rejects any token whose `aud` isn't itself.
- Tests: scope-down enforced, audience-denial for un-permitted exchanges, `sub`/`azp` claims correct, broker-audience acceptance/rejection. First multi-service delegated trace visible in the Console.

## Capabilities

### New Capabilities

- `agent-sdk`: The Python client library contract agents use to obtain and use delegated identity — starting with `exchange()`. This is genuinely new surface (no existing spec covers the SDK's API), and giving it a contract now keeps the headline decision (Q5: Python v0) honest and testable, the same way the review insisted MCP get its own spec. Scope in M1 is narrow: `exchange()` only; `get_provider_token()`, `require_approval()`, `fga_filter()` arrive with their milestones.

### Modified Capabilities

(None. M1 *implements* the four existing `identity-delegation` requirements — OIDC login, RFC 8693 exchange, broker-audience rule, TTL bound — without changing their spec-level behavior. If implementation reveals a genuine gap in those requirements, a `identity-delegation` delta will be added during design; the default expectation is no change.)

## Impact

- New: `sdk/prokura-py/` first real code (`exchange()`, token handling, JWKS-less client-side use), packaging (`pyproject.toml`), SDK unit tests + an integration test against the live stack.
- Modified: `deploy/keycloak/realm-export.json` — token-exchange permissions per (client, audience); confirm the `broker-audience`/`tools-audience` client scopes wired in M0 produce the right `aud` claims.
- Verification: a new integration test drives login → exchange and asserts claims; the delegated flow appears as a linked trace in the Console (observability definition-of-done).
- No new runtime services; no changes to OpenFGA/OpenBao/approval.
