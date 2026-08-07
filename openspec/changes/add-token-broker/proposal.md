# Proposal: add-token-broker (M2)

## Why

The heaviest milestone: it makes three specs real at once and is where the Q2-B grant-acquisition architecture gets proven. After M2, an agent can obtain a real third-party token for a user — but only after that user has (a) linked the provider and (b) consented to that specific agent — with the broker owning lease/scope-down/audit.

## What Changes

- **Mock external provider (decision):** a second Keycloak realm `acme` stands in for GitHub/Google so the whole flow runs offline with zero external credentials (consistent with Mailpit-over-Gmail, Q6). It exercises the *real* Keycloak identity-brokering + Store Tokens machinery the broker depends on. Real GitHub App (F4) / Google (Q6) become a documented bring-your-own-credentials extension, not a v0 requirement.
- **Grant acquisition (grant-acquisition spec):** `prokura` realm gets an OIDC identity provider `acme` with `storeToken=true`; account linking via `kc_action=idp_link:acme`; broker pulls the stored token from `/realms/prokura/broker/acme/token` and imports it into OpenBao.
- **Token Broker service (token-brokering spec):** FastAPI `POST /v1/tokens/{provider}` with the full validation chain (JWKS, `aud=token-broker` F2-A, scope⊆grant, FGA `can_use`), OpenBao-only credential storage, ≤15-min hand-out, provider manifest, audit log emitted to Loki in realtime. Born instrumented (traceparent + correlation IDs — observability DoD).
- **Per-agent consent (per-agent-consent spec):** a consent screen that writes the `can_use` tuple; broker is sole writer enforcing operator==owner.

## Capabilities

### Modified Capabilities

- `grant-acquisition`: likely a delta clarifying the mock-provider/BYO-credentials split (the existing requirements are provider-agnostic; confirm during design whether a new requirement is needed or the mock is purely an implementation detail).

(No other new capabilities — M2 *implements* the existing `token-brokering` and `per-agent-consent` specs.)

## Impact

- New: `deploy/keycloak/acme-realm.json` (done), `acme` OIDC IdP block in `realm-export.json`, `services/token-broker/` (FastAPI + Postgres + hvac + openfga-sdk + PyJWT), broker tables, SDK `get_provider_token()`, a consent UI, integration tests.
- **Known networking wrinkle to resolve in the spike:** realm-to-realm brokering must split browser-facing URLs (`http://localhost:8180`) from server-side backchannel URLs (`http://keycloak:8080`) because Keycloak listens on 8080 in-container but is pinned to hostname 8180 — same class of issue as the CIBA callback hostname in M0.
- Big milestone: opens with the account-linking spike (mirrors M0's CIBA spike) before the broker service is built.
