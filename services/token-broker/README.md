# Prokura Token Broker (M2)

Hands agents **short-lived third-party provider tokens** without ever giving them
the durable credential. The refresh/authorization credential is acquired via
Keycloak account-linking and lives **only in OpenBao**; the broker exchanges it for
a bounded access token on each call, gated by per-agent consent (token-brokering,
grant-acquisition, per-agent-consent specs).

## Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `GET`  | `/healthz` | liveness |
| `POST` | `/v1/tokens/{provider}` | the hand-out chain → a provider access token |
| `POST` | `/v1/grants/{provider}/import` | import a Keycloak-brokered grant into OpenBao |
| `POST` | `/v1/grants/{provider}/revoke` | revoke a grant (provider + OpenBao + tuples) |
| `GET`  | `/login` · `/callback` · `/whoami` | OIDC session for the consent surface (M7: `broker-ui` client, signed cookie) |
| `GET`  | `/consent` | per-agent consent screen (session-gated) |
| `POST` | `/consent` | write the `can_use` tuple (the **sole writer**; owner = the session identity) |
| `GET`  | `/v1/consents` | M8: list the signed-in user's per-agent consents + grants (user-bound bearer) |
| `POST` | `/v1/consent/revoke` | M9 **kill switch**: per-grant revoke — tuple delete + deny-list entry + CAEP signal; returns a measured `stop_ms` + the honest in-flight residual (session OR user-bound bearer) |
| `GET`  | `/ssf/stream` | M9: CAEP/SSF revocation Security Event Tokens a receiver can poll |

## The hand-out chain (`POST /v1/tokens/{provider}`)

The hand-out validates, in order: JWKS signature, `aud=token-broker`, requested scopes ⊆
grant, the OpenFGA `can_use` check, and (M9) **no matching deny-list entry** — a
propagation-free "stop now" checked before the provider is contacted, so a revoked agent is
refused even with a fresh token. Provider-token TTL is bounded (M9, 120 s default) so the
post-revocation in-flight residual is small and reported honestly. Revocation comes in two
grains (`revocation.py`): per-grant `kill` (tuple + deny + signal, scoped) and the agent-wide
`kill_agent` (agent-wide deny + all tuples + Keycloak session/offline revocation via
`manage-users`, so the agent can't re-acquire any authority — ADR-0024).

1. **Validate the token** — JWKS signature + `aud=token-broker` (the F2 / confused-deputy
   defense; the inbound MCP token is never accepted here, so tools must re-exchange).
2. **Authorize as the user** — an OpenFGA `fga.check` for the `can_use` tuple; the
   requested scopes must be a subset of the granted scopes.
3. **Read the grant** from OpenBao (`secret/grants/{user}/{provider}`), refresh against
   the provider, **rotate** the stored secret, and return an **access token only**,
   capped at ≤ 900 s. No refresh token is ever returned or logged.

## Custody & the sole-writer invariant

- The provider credential is sealed in OpenBao; the broker's token is scoped to
  `secret/data/grants/*` and the raw credential exists in broker memory only transiently
  during a refresh.
- The broker is the **only** writer of the `can_use` tuple — `POST /consent` enforces
  `operator == owner` at write time (ADR-0001), so consent, not registration, is the gate
  (ADR-0012). Since M7 the owner in that check is a **real OIDC session identity** on the
  consent surface — no URL-carried tokens. Acquisition builds on Keycloak brokering rather than a parallel path (ADR-0011).

## Configuration

Key env (see `config.py`): `KEYCLOAK_URL`, `PROKURA_REALM`, `BROKER_AUDIENCE`/`BROKER_CLIENT_ID`
(`token-broker`), `BROKER_CLIENT_SECRET`, `OPENBAO_URL` + `BROKER_BAO_TOKEN` (policy-scoped),
`OPENFGA_URL`.

Port **8110**. Born instrumented — traceparent join key + `prokura.correlation_id`, realtime
audit to Loki (visible in the delegation-chain console and the Flow B / postmortem walkthroughs).
