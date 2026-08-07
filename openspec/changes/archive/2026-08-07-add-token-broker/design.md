## Context

M2 is the heaviest milestone: it makes three existing specs real at once —
`grant-acquisition`, `token-brokering`, `per-agent-consent` — and proves the
Q2-B "brokering, not broker-run OAuth" architecture end to end. After M2 an
agent can obtain a real third-party token for a user, but only after that user
has (a) linked the provider to their Keycloak identity and (b) consented to that
specific agent; the broker owns lease, scope-down, per-agent gating, and audit.

Current state (verified against the repo, not memory):

- **Infra the broker consumes already exists and is smoke-tested.** OpenBao has
  a least-privilege `broker` policy and a bound token `prokura-broker-dev-token`
  scoped to `secret/data/grants/*`. OpenFGA's model already declares
  `type grant { owner: [user]; can_use: [agent] }` and `type agent { operator:
  [user] }` in store `prokura`. The `prokura` realm has the `token-broker`
  confidential client (secret `token-broker-dev-secret`, service accounts on)
  and the `broker-audience` client scope (audience mapper → `token-broker`).
- **Mock provider is scaffolded (commit 6bc87ca) but not wired.**
  `deploy/keycloak/acme-realm.json` defines realm `acme` with user `alice`, an
  `accessTokenLifespan` of 3600, and client `prokura-broker-idp` (secret
  `acme-idp-dev-secret`) whose redirect URI is already
  `http://localhost:8180/realms/prokura/broker/acme/endpoint`. The realm is
  mounted and imported by compose.
- **What M2 must build.** The `prokura` realm has **no `identityProviders`
  block** — the `acme` OIDC IdP (with `storeToken=true`) must be added. There is
  no broker service code (`services/token-broker/` is a placeholder README), no
  broker Postgres tables, no consent UI, no SDK `get_provider_token()`, and no
  broker integration tests.
- **The broker is the first instrumented Python service.** The console is not
  instrumented; the observability change wired the OTLP receiver in
  *specifically so the broker is born instrumented*. There is no shared Python
  instrumentation helper yet — M2 establishes that pattern.

Structural template: `services/console/` (flat `app.py`, `Dockerfile`,
`requirements.txt`, env-based config, `build: ./services/<name>` in compose).
House style for tasks/design: the archived M1 `add-token-exchange` change.

## Goals / Non-Goals

**Goals:**

- Add the `acme` OIDC identity provider to the `prokura` realm with Store Tokens
  on, resolving the browser-URL vs backchannel-URL split so realm-to-realm
  brokering works inside compose.
- Prove, via a spike that opens the milestone, that `kc_action=idp_link:acme` →
  the broker retrieves the stored token from `/realms/prokura/broker/acme/token`
  → the credential is importable into OpenBao. (Mirrors how the M0 CIBA spike
  de-risked that milestone.)
- Build the Token Broker FastAPI service implementing the full `token-brokering`
  validation chain (JWKS signature, `aud=token-broker`, scope ⊆ grant, FGA
  `can_use`), OpenBao-only credential storage, ≤900s hand-out, provider manifest,
  and realtime Loki-queryable audit — born instrumented (traceparent +
  `prokura.correlation_id`).
- Implement grant acquisition: after linking, the broker imports the refresh
  credential into `secret/grants/{user}/{provider}` and owns the grant lifecycle,
  including revocation.
- Implement per-agent consent: an authenticated consent screen that writes the
  `agent:{id} can_use grant:{user}/{provider}` tuple, with the broker as the sole
  tuple writer enforcing `operator == owner` at write time.
- Add SDK `get_provider_token()` mirroring `exchange()` conventions.
- Integration tests driving the live stack that exercise the happy path and the
  three refusal paths (over-broad scope, missing consent, cross-user write), plus
  a "no provider token in logs" test.

**Non-Goals:**

- Real GitHub App / Google credentials. These become a documented
  bring-your-own-credentials extension; the mock `acme` realm is the v0 provider.
- Incremental / per-request scope escalation. Scopes are configured statically
  per IdP in the realm (documented trade-off, matches the commercial reference).
- MCP authorization (M4), human approval / CIBA gating of the token hand-out
  (M3), and RAG (M5). The broker emits audit and enforces consent; it does not
  yet call an approval service.
- Production hardening (HA, secret rotation policy, mTLS between services). This
  is docker-compose, explicitly non-production.

## Decisions

### 1. Mock external provider = a second Keycloak realm, not a stub HTTP server

The `acme` realm stands in for GitHub/Google. **Why over a hand-rolled OAuth
stub:** it exercises the *real* Keycloak identity-brokering + Store Tokens code
path the broker depends on (authorization code flow, token storage, stored-token
retrieval, refresh) with zero external credentials and fully offline —
consistent with Mailpit-over-Gmail (Q6). A stub would prove nothing about
whether Keycloak brokering actually works. Real GitHub/Google are then a config
swap (add an IdP block with real client id/secret), not a rewrite. **Alternative
considered:** broker runs its own provider Authorization Code flow — explicitly
rejected by Q2-B (broker never runs its own provider OAuth; it consumes
Keycloak-brokered grants).

### 2. Resolve the realm-to-realm URL split with explicit IdP endpoint URLs

Keycloak runs with `KC_HOSTNAME=http://localhost:8180` and
`KC_HOSTNAME_BACKCHANNEL_DYNAMIC=false`, so every issuer is `localhost:8180`, but
the container actually listens on `keycloak:8080`. When the `prokura` realm
brokers to the `acme` realm, the **browser** must be redirected to the acme
*authorization* endpoint at `http://localhost:8180/...` while the **server-side**
token / JWKS / userinfo calls must go to `http://keycloak:8080/...` (inside the
container `localhost:8180` resolves to nothing). Decision: configure the `acme`
IdP in `realm-export.json` with **explicit per-endpoint URLs** rather than OIDC
discovery — `authorizationUrl` on `localhost:8180`, `tokenUrl` / `jwksUrl` /
`userInfoUrl` / `issuer` on `keycloak:8080` — because discovery returns a single
issuer host and cannot express the split. This is the same class of issue as the
M0 CIBA callback hostname. **The spike proves the exact working URL set before
the broker is built.** **Alternative considered:** discovery + relying on
`KC_HOSTNAME_BACKCHANNEL_DYNAMIC=true` — rejected because it makes issuers vary
by request host and would break the `localhost:8180` issuer that tokens are
validated against elsewhere.

### 3. Broker retrieves the stored token via Keycloak's broker token endpoint, then imports to OpenBao

After `idp_link:acme` completes, the stored acme tokens live in Keycloak. The
broker calls `GET /realms/prokura/broker/acme/token` presenting an access token
that carries the `broker` read-token permission, parses the stored
`refresh_token` (+ granted scopes), and writes it to OpenBao at
`secret/data/grants/{user}/{provider}` via **hvac**, recording a grant row in
Postgres. From that point the broker owns the grant. **Why hvac over raw HTTP:**
the proposal pins it, and it gives typed KV v2 access; the broker wraps each
OpenBao call in an OTel span so Bao becomes trace-visible (it has no native OTLP
export). **Open detail the spike resolves:** whether the read-token call uses the
user's session access token (with the `broker` client scope) or the broker
service account — the spike will confirm which principal Keycloak accepts.

### 4. Broker service: FastAPI mirroring `services/console/`, with a thin module split

Single service under `services/token-broker/` (`Dockerfile` from
`python:3.12-slim`, `requirements.txt`, `build:` in compose, port 8110,
env-based config). Because the validation chain is substantial, split `app.py`
into small modules rather than one file: `app.py` (routes), `validation.py`
(JWKS + audience + scope checks, PyJWT with JWKS caching mirroring the SDK), 
`grants.py` (OpenBao via hvac + Postgres grant rows), `consent.py` (OpenFGA
check + sole-writer tuple writes), `providers.py` (the provider manifest),
`audit.py` (structured audit emit), `telemetry.py` (OTel setup — the reusable
pattern). Endpoints:

- `POST /v1/tokens/{provider}` — the hand-out validation chain.
- `POST /v1/grants/{provider}/import` — called after linking; imports the stored
  credential. (Also drives the consent screen's "link first" step.)
- `GET /consent` + `POST /consent` — the per-agent consent screen (see §6).
- `POST /v1/grants/{provider}/revoke` and `POST /v1/consent/revoke` — revocation.
- `GET /healthz` — `{"ok": true}` like the console.

### 5. Provider tokens are refreshed against the provider on demand; hand-out capped at 900s

On `POST /v1/tokens/{provider}`, after the validation chain passes, the broker
pulls the refresh credential from OpenBao and refreshes against the acme realm
token endpoint (client `prokura-broker-idp`, backchannel `keycloak:8080`),
returning the fresh acme access token with `expires_in = min(actual, 900)`. This
exercises the real `supports_refresh` loop. The response **never** contains a
refresh token. The provider manifest declares acme as `supports_refresh: true`,
`supports_scope_narrowing: false` — so a narrowing request within granted scopes
returns the token with its *actual* scopes and reports them honestly (never
fake-narrows). The threat-model TTL table records acme (mock), plus documented
GitHub App (~8h) and Google (~1h) residual validity.

### 6. Consent screen served by the broker, behind a prokura-realm session; broker is sole tuple writer

Because the broker is the only component allowed to write `can_use` tuples, the
consent screen is **served by the broker** (bundled static page via
`FileResponse`, mirroring the console) and its `POST /consent` handler is the
only tuple-writer. The page is gated by a valid `prokura`-realm OIDC session so
the acting user is authenticated. On approval the handler (1) resolves the
grant's `owner` and the agent's `operator` from OpenFGA, (2) **refuses the write
unless `operator == owner`** (the F1-A / Q3-B invariant lifted from the FGA model
into broker code) and logs any refusal, (3) writes exactly the one
`agent:{id} can_use grant:{user}/{provider}` tuple. **Why broker-served over a
console page:** keeps the sole-writer invariant inside one trust boundary and
avoids a second service needing FGA write creds. **Alternative considered:** a
Keycloak "required action" consent — rejected as heavier than demo-grade and it
can't express per-agent tuples.

### 7. OpenFGA access via `openfga-sdk`; store discovered by name

The broker uses `openfga-sdk` (new dep) for the `can_use` check and tuple
writes/deletes, discovering the `prokura` store id by name at startup (the smoke
harness already does this over raw HTTP). **Why the SDK over raw HTTP:** the
broker does both checks and writes with operator lookups; the typed client keeps
that readable. The check is `agent:{azp} can_use grant:{user}/{provider}`.

### 8. Telemetry: broker establishes the Python OTel pattern (observability DoD)

The broker adds OpenTelemetry (`opentelemetry-distro`,
`opentelemetry-exporter-otlp`, `opentelemetry-instrumentation-fastapi`,
`opentelemetry-instrumentation-httpx`), exporting OTLP to `http://lgtm:4317`,
**fire-and-forget** (no `depends_on: lgtm`; exporter drops on failure so the
smoke suite stays green with lgtm stopped). W3C `traceparent` is the join key;
the correlation id rides as span attribute `prokura.correlation_id` and as a
field in each structured audit log line. Every issuance and every denial emits an
audit event to the log pipeline in realtime (Loki-queryable within seconds) with
the same correlation id as the persisted Postgres audit row. OpenBao and OpenFGA
calls are wrapped in client-side spans so they appear in the trace. The
`prokura-delegation` Grafana dashboard gets a broker row (dashboard-as-code).

### 9. Broker Postgres tables created idempotently at startup

The broker owns two tables — `grants` (`user_id`, `provider`, `granted_scopes`,
`created_at`) and `audit` (`correlation_id`, `user_id`, `agent`, `provider`,
`scopes`, `ttl`, `decision`, `ts`). They live in the existing `postgres` service
(new logical schema, not a new container) and are created with `CREATE TABLE IF
NOT EXISTS` on broker startup — no migration framework for v0 (matches the
project's demo-grade, clean-slate `down -v && up` discipline). Refresh
credentials are **never** stored in Postgres — only in OpenBao.

## Risks / Trade-offs

- **[Realm-to-realm brokering URL split may not work with explicit URLs as
  hypothesized]** → The spike opens the milestone and proves the exact URL set
  end-to-end before any broker code is written; if explicit URLs fail, fall back
  to a `/etc/hosts` alias or `KC_HOSTNAME_BACKCHANNEL_DYNAMIC` experiment,
  documented in the design's "Resolved at implementation time" section.
- **[Stored-token retrieval principal ambiguous]** (user session token vs broker
  service account) → resolved empirically in the spike; the broker code uses
  whichever Keycloak actually accepts.
- **[Broker becomes a high-value trusted component — sole tuple writer + holds
  all refresh creds]** → least-privilege OpenBao token (already scoped to
  `grants/*`), operator==owner enforced at write time and logged, and the threat
  model explicitly names the broker in the trusted computing base. Negative tests
  assert cross-user writes are refused.
- **[Provider token could leak into logs/audit/responses]** → refresh creds live
  only in OpenBao and broker memory transiently; a `test_no_provider_token_in_logs`
  test (mirroring M1's `test_no_token_in_logs`) asserts no secret hits logs or
  response bodies, including error paths.
- **[First OTel wiring could break the fire-and-forget rule and couple the broker
  to lgtm]** → exporter configured to drop silently; a test asserts the broker
  stays healthy and the smoke suite green with lgtm stopped.
- **[Static per-provider scopes surprise users expecting incremental consent]** →
  documented explicitly in the grant-acquisition spec and README; scope change
  requires re-linking.

## Migration Plan

Purely additive; no data migration (dev-only, clean-slate).

1. Add the `acme` `identityProvider` block (with `storeToken=true` and the split
   URLs proven by the spike) to `deploy/keycloak/realm-export.json`.
2. Add the `token-broker` service to `docker-compose.yml` (`build:
   ./services/token-broker`, port 8110, env for Keycloak/OpenBao/OpenFGA/Postgres,
   OTLP to lgtm, **no `depends_on: lgtm`**).
3. Broker creates its Postgres tables and discovers the FGA store on startup.
4. Add the broker row to the `prokura-delegation` dashboard.
5. Rollback: remove the compose service and revert the realm block; `down -v &&
   up` returns to the M1 baseline. No promoted-spec changes to unwind beyond the
   grant-acquisition delta.

Definition of done (M1 closing discipline): full smoke suite green; the
link → consent → brokered-token flow appears as a **single linked trace** in the
Console with a live audit event in Loki; clean-slate `down -v && up` reproduces
it from scratch.

## Open Questions

- **Exact working URL set for the acme IdP** (authorization vs token/jwks hosts)
  — resolved by the spike, recorded in "Resolved at implementation time".
- **Which principal retrieves the stored token** (user access token carrying the
  `broker` read-token scope, vs broker service account) — resolved by the spike.
- **Does the acme realm issue refresh tokens to `prokura-broker-idp` by default**
  or must "Store Tokens" + offline/refresh be explicitly enabled on both sides —
  confirm in the spike; if acme won't issue a refresh token, import the access
  token itself (spec allows "the provider token itself where no refresh token
  exists") and document acme as `supports_refresh: false`.
- **Consent-screen session mechanism** — full OIDC redirect login on the broker
  vs accepting a bearer session token; lean to the simplest that keeps the page
  authenticated, decided during implementation.

## Resolved at implementation time

Verified against the running Keycloak 26.7.1 image by the Phase-1 spike
(`spike/idp-link/link_spike.py`), which passes end-to-end from a clean-slate
`down -v && up` with no admin-API tweaks — everything below is baked into
`deploy/keycloak/realm-export.json`.

- **The realm-to-realm URL split works exactly as hypothesized (§2).** The
  `acme` IdP with `authorizationUrl` on `http://localhost:8180` and
  `tokenUrl`/`jwksUrl`/`userInfoUrl`/`issuer` on `http://keycloak:8080` links
  successfully: the browser is redirected to acme on `localhost:8180`, the
  backchannel code→token exchange runs on `keycloak:8080`, and the flow returns
  `kc_action_status=success`. No `/etc/hosts` alias or dynamic-backchannel
  fallback was needed.
- **`kc_action=idp_link:<alias>` requires two things a bare realm export omits.**
  (1) The authenticated user must hold the `manage-account` (or
  `manage-account-links`) role — Keycloak's `performAccountLinking` refuses with
  `FEDERATED_IDENTITY_LINK_ERROR / not_allowed` otherwise. Fixed by giving
  `alice` `default-roles-prokura` (which composites `manage-account`). (2) The
  request needs `prompt=login`; linking is a sensitive action and Keycloak
  refuses it on a pure-SSO session. Keycloak 26 also inserts a **confirmation
  page** ("Do you want to link your account with ACME?") whose form is accepted
  with the `continue` button.
- **Stored-token retrieval principal = the user's own access token, and it must
  carry `resource_access.broker.roles:[read-token]`.** `getTokenV1` checks
  exactly this claim (confirmed against Keycloak source). Two facts fell out:
  (a) `addReadTokenRoleOnCreate=true` only grants the `broker read-token` role
  when a *brokered user is created* — it does **not** fire when linking to a
  *pre-existing* account, so `alice` is granted `broker:read-token` explicitly in
  the realm export; (b) this realm omits Keycloak's built-in `roles` client
  scope, so the role never reaches the token — added a minimal `broker-read-token`
  client scope (a `oidc-usermodel-client-role-mapper` restricted to the `broker`
  client) and made it a default scope on `smoke-cli` (tests) and `token-broker`
  (the broker forwards the user's `aud=token-broker` token, which must be
  `sub=alice`; a service-account token would resolve the wrong federated identity).
- **`acme` issues a refresh token** (`supports_refresh: true`). The stored token
  response contains a `refresh_token` (≈650 chars), imported to OpenBao at
  `secret/data/grants/alice/acme` and read back successfully with the least-
  privilege `prokura-broker-dev-token`.
- **Broker service port: 8110** (unchanged from §4).
- **Consent-screen auth mechanism:** the broker's `POST /consent` validates a
  prokura-realm bearer token (signature/issuer, any audience) and derives the
  grant owner from its `preferred_username`; the served page (demo driver) passes
  that token. operator==owner is then enforced against OpenFGA in broker code.

Additional facts resolved while building the broker (Phases 2-8):

- **The broker re-exchanges the incoming token to retrieve the stored
  credential — the agent never gets read-token.** The agent's `aud=token-broker`
  token is minted in the *agent-app* client context, so it does NOT carry
  `resource_access.broker.roles` (and it must not — that would let any agent read
  stored credentials directly from Keycloak). Instead the broker performs its own
  RFC 8693 exchange as the confidential `token-broker` client (which holds the
  `broker-read-token` scope) with **no `audience` param** (self-audience is
  rejected as "not available"); the resulting `azp=token-broker` token carries
  `resource_access.broker.roles=[read-token]` and is what the broker presents to
  `/broker/{alias}/token`. Required enabling `standard.token.exchange.enabled` on
  the `token-broker` client.
- **The mock provider's refresh credential is session-bound; the acme realm gets
  30-day session lifespans.** A real provider's refresh token is not tied to a
  Keycloak SSO session, but acme's is — so without long lifespans the stored
  credential expires (~30 min idle) and hand-outs fail with `invalid_grant`.
  `offline_access` was tried first but the acme brokering client rejects it
  (`invalid_scope`) and it broke the backchannel exchange, so the simpler fix is
  generous `ssoSession*`/`clientSession*` lifespans on the acme realm (documented
  as a mock artifact in the threat model). The broker also persists a **rotated**
  refresh token if the provider returns a new one, so rotation never breaks the
  next hand-out.
