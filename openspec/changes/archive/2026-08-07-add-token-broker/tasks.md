# Tasks: add-token-broker (M2)

Spike-first, mirroring M0. Do not build the broker service until Phase 1 proves
the realm-to-realm brokering + stored-token import works against the running
Keycloak 26.7.1 image. Each phase closes by driving real traffic and looking.

## 1. Spike — account linking → importable refresh token (de-risk the milestone) ✅ PASSED

Spike script: `spike/idp-link/link_spike.py`. Passes end-to-end from a clean
`down -v && up` with no admin-API tweaks; all findings baked into
`realm-export.json` and recorded in design.md "Resolved at implementation time".

- [x] 1.1 Added the `acme` OIDC `identityProvider` block to `realm-export.json`
  with `storeToken=true`, `addReadTokenRoleOnCreate=true`, and the explicit
  browser/backchannel endpoint URL split. (Also fixed the pre-existing
  `acme-realm.json` `comment` field that broke import.)
- [x] 1.2 Drove `kc_action=idp_link:acme&prompt=login` for `alice` → acme login
  → back to prokura: `kc_action_status=success`. The URL split works; browser
  auth on `localhost:8180`, backchannel token exchange on `keycloak:8080`.
  Required: `alice` holds `manage-account` (via `default-roles-prokura`) and the
  Keycloak-26 confirmation page is accepted via the `continue` button.
- [x] 1.3 Retrieved the stored token via `GET /realms/prokura/broker/acme/token`.
  Principal = the user's own access token carrying
  `resource_access.broker.roles:[read-token]` (needs the `broker read-token` role
  — granted explicitly in the export, NOT auto-granted on linking a pre-existing
  account — plus the new `broker-read-token` client-role mapper scope). acme
  **does** issue a `refresh_token` (`supports_refresh: true`).
- [x] 1.4 Imported the refresh credential into OpenBao at
  `secret/data/grants/alice/acme` with `prokura-broker-dev-token`; read back OK.
- [x] 1.5 Findings written into design.md. Spike code lives under `spike/idp-link/`.

## 2. Token Broker service — scaffold + telemetry pattern

- [x] 2.1 Create `services/token-broker/` mirroring `services/console/`:
  `Dockerfile` (`python:3.12-slim`, uvicorn on port 8110), `requirements.txt`
  (`fastapi`, `uvicorn`, `httpx`, `hvac`, `openfga-sdk`, `PyJWT`, `psycopg[binary]`,
  `opentelemetry-distro`, `opentelemetry-exporter-otlp`,
  `opentelemetry-instrumentation-fastapi`, `opentelemetry-instrumentation-httpx`),
  env-based config, `GET /healthz` → `{"ok": true}`.
- [x] 2.2 `telemetry.py`: OTel setup exporting OTLP to `http://lgtm:4317`,
  **fire-and-forget** (exporter drops on failure; no `depends_on: lgtm`). W3C
  traceparent as join key; `prokura.correlation_id` span attribute + structured
  log field. FastAPI + httpx auto-instrumentation on. This is the reusable Python
  instrumentation pattern (observability DoD).
- [x] 2.3 Create broker Postgres tables idempotently on startup (`CREATE TABLE IF
  NOT EXISTS`): `grants` and `audit` (design §9). Discover the OpenFGA `prokura`
  store id by name on startup.
- [x] 2.4 Add the `token-broker` service to `docker-compose.yml` (`build:
  ./services/token-broker`, port 8110, env for Keycloak/OpenBao/OpenFGA/Postgres +
  OTLP, **no `depends_on: lgtm`**).

## 3. Grant acquisition (grant-acquisition spec)

- [x] 3.1 `providers.py`: provider manifest declaring per-provider `supports_refresh`,
  `supports_scope_narrowing`, and endpoint URLs. `acme` entry uses the spike's
  proven values.
- [x] 3.2 `grants.py` + `POST /v1/grants/{provider}/import`: after linking, pull
  the stored token from the Keycloak broker endpoint (principal from spike),
  import the refresh credential to `secret/data/grants/{user}/{provider}` via
  **hvac** wrapped in an OTel span, and record the grant row (provider + granted
  scopes). No response or log line contains the credential.
- [x] 3.3 `POST /v1/grants/{provider}/revoke`: revoke at the provider where
  supported, delete from OpenBao, remove the grant row, and delete all `can_use`
  tuples referencing the grant.

## 4. Per-agent consent (per-agent-consent spec)

- [x] 4.1 `consent.py` + bundled consent screen served by the broker
  (`FileResponse`, mirroring the console), gated by a valid `prokura`-realm OIDC
  session. Renders "Allow &lt;agent&gt; to use your &lt;provider&gt; grant — [scopes]".
- [x] 4.2 `POST /consent`: the **sole** `can_use` tuple writer. Resolve grant
  `owner` and agent `operator` from OpenFGA; **refuse and log** any write where
  `operator != owner` (F1-A / Q3-B invariant in broker code); on success write
  exactly the one `agent:{id} can_use grant:{user}/{provider}` tuple.
- [x] 4.3 `POST /v1/consent/revoke`: delete a single agent's tuple without
  touching the grant; effective on the next broker request.

## 5. Token hand-out (token-brokering spec)

- [x] 5.1 `validation.py` + `POST /v1/tokens/{provider}`: run the validation chain
  in order — (1) JWKS signature (PyJWT + JWKS caching mirroring the SDK), (2)
  `aud = token-broker`, (3) requested scopes ⊆ grant's granted scopes, (4) OpenFGA
  `agent:{azp} can_use grant:{user}/{provider}`. Any failure → 403 without
  contacting the provider.
- [x] 5.2 On success: pull the refresh credential from OpenBao, refresh against
  the acme token endpoint (backchannel `keycloak:8080`), return the provider
  access token with `expires_in = min(actual, 900)` and **never** a refresh
  token. Non-narrowing provider reports actual scopes honestly (no fake-narrow).
- [x] 5.3 `audit.py`: every issuance and every denial writes a persisted `audit`
  row `{user, agent, provider, scopes, ttl, decision, correlation_id}` **and**
  emits a matching realtime audit event (same correlation id) to the log pipeline,
  Loki-queryable within seconds.

## 6. SDK — get_provider_token()

- [x] 6.1 Add `prokura/provider_token.py` mirroring `exchange.py`: keyword-only
  connection args, injectable `http: httpx.Client`, typed exceptions
  (`ProviderTokenError` / `ConsentDenied` / `ScopeExceeded`), never logs the
  token or POST body. POSTs the `aud=token-broker` bearer to
  `POST /v1/tokens/{provider}`; returns the provider access token + expiry.
- [x] 6.2 Export `get_provider_token` and the exceptions from `prokura/__init__.py`;
  update the roadmap docstring (M2 now done).

## 7. Tests (drive the live stack)

- [x] 7.1 `test_grant_acquisition.py`: link `acme` for `alice` → import → assert the
  credential is in OpenBao at `secret/data/grants/alice/acme` and a grant row
  exists; assert no credential appeared in any response.
- [x] 7.2 `test_consent.py`: approve agent `smoke-agent` → it passes the FGA check
  and every other agent still fails (no implicit consent); cross-user write is
  refused and logged; revocation drops access on the next request.
- [x] 7.3 `test_token_brokering.py`: happy path via SDK `get_provider_token()`
  returns a provider token + expiry ≤900 and **never** a refresh token; the three
  refusals — over-broad scope (403, provider not contacted), missing consent (403,
  logged), and refresh loop on the refresh-capable provider — each asserted.
- [x] 7.4 `test_no_provider_token_in_logs.py`: mirror M1's `test_no_token_in_logs`
  with `caplog` — no refresh credential in logs, audit records, or response bodies
  including error paths.
- [x] 7.5 `test_broker_audit.py`: after an issuance, the audit event is
  Loki-queryable within seconds with the same correlation id as the persisted
  row; skip if lgtm is absent (telemetry is fire-and-forget).

## 8. Verify + wrap

- [x] 8.1 Add the broker row to `deploy/lgtm/dashboards/prokura-delegation.json`
  (dashboard-as-code); confirm it renders (screenshot, not the API).
- [x] 8.2 Drive the full flow and **look**: link → consent → brokered token; the
  three steps appear as one linked trace in the Console and a live audit event in
  Loki. Take browser screenshots.
- [x] 8.3 Update the threat model TTL table (acme mock; documented GitHub App ~8h,
  Google ~1h) and name the broker in the trusted computing base + as sole tuple
  writer.
- [x] 8.4 Clean-slate `down -v && up`; whole smoke suite green from scratch,
  including with lgtm stopped (fire-and-forget holds).
