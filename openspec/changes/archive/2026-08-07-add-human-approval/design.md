## Context

M2 gates provider tokens on *prior* consent. Flow C (`human-approval`) adds a
human in the loop **at action time** for sensitive actions, with a credential
usable exactly once for exactly the approved action. The `human-approval` spec is
fully written (six requirements, decisions F5/F6/F7/F8); M3 implements it.

Current state, verified against the repo:

- **The CIBA transport is already proven (M0).** `spike/ciba-http-channel/`
  showed Keycloak's built-in HTTP auth channel round-trips: Keycloak POSTs an
  authentication-delegation request (JSON with `binding_message`, `login_hint`,
  `scope`; `Authorization: Bearer <delegation token>`) to a channel URI and
  expects **201**; the decision is returned by POSTing
  `{"status":"SUCCEED"|"UNAUTHORIZED"|"CANCELLED"}` to
  `…/realms/prokura/protocol/openid-connect/ext/ciba/auth/callback` with that
  same bearer. The SPI flag is
  `--spi-ciba-auth-channel--ciba-http-auth-channel--http-authentication-channel-uri`,
  currently pointed at `ciba-spike:8000/ciba/delegate`. **No Java SPI is needed.**
- **The realm is CIBA-ready.** `agent-app` has `oidc.ciba.grant.enabled` with
  `ciba.backchannel.token.delivery.mode: poll` (M0). The prokura realm has CIBA
  attributes set (poll delivery).
- **Infra to reuse:** ntfy (per-user topics + ACLs), Mailpit (SMTP sink for the
  demo action), Postgres, and the OTel pattern the broker established in M2.

Structural template: `services/token-broker/` (FastAPI, flat modules, env config,
`build:` in compose, OTLP fire-and-forget). House style: the archived M1/M2
changes.

## Goals / Non-Goals

**Goals:**

- An **approval service** that receives Keycloak's CIBA delegation, holds the
  structured payload (registered out-of-band by the agent, keyed by a reference
  ID, with a recorded hash), serves a **trusted approval UI** that renders the
  service-held payload behind a Keycloak session, and relays the decision to
  Keycloak's CIBA callback. It joins the trusted computing base.
- **Reference-ID-only binding messages** (Keycloak regex
  `^[a-zA-Z0-9-._+/!?#]{1,50}$`); agent-authored prose never reaches the human.
- A **single-use, hash-bound action token**: on approval the agent's CIBA poll
  yields a token carrying the reference ID; a gated tool verifies the action it
  is about to perform against the approved payload hash and rejects any reference
  ID already consumed.
- A concrete gated action — **`email.send` via Mailpit** — to make the guarantees
  demonstrable and testable.
- **SDK `require_approval()`** — register payload, initiate CIBA, poll, return the
  action token.
- **ntfy** notify-only (deep link + reference ID; per-user unguessable topic).
- Born instrumented; the whole flow appears as one linked trace.

**Non-Goals:**

- A real mobile push app or device-side approval — decisions happen only in the
  Keycloak-session-gated UI; ntfy carries no capability.
- Rich policy on *which* actions require approval — a static per-tool marker
  (already modelled in OpenFGA as `tool.requires_approval`) is enough for v0.
- Production hardening (HA, mTLS). docker-compose, non-production.
- Replacing the M0 spike's role wholesale in one shot — the spike stays
  profile-gated as a reference; the SPI flag repoints to the approval service.

## Decisions

### 1. Built-in HTTP channel, approval service as the channel target (no Java SPI)

Repoint the CIBA SPI flag from `ciba-spike` to the approval service
(`approval:8120/ciba/delegate`). The approval service reproduces the spike's
proven contract — accept the delegation POST (return 201), relay the decision to
the callback — but as product code: authenticated UI, persisted state, hash,
audit. **Why over a Java SPI:** M0 already proved the built-in channel works; a
SPI is permitted by the spec only as a documented fallback, and we don't need it.

### 2. Out-of-band payload registration; binding message is the reference ID only

Before initiating CIBA the agent calls `POST /register` on the approval service
with `{action, params}`. The service stores the payload, computes a hash
(`sha256` of a canonical JSON encoding), and returns a **reference ID** that fits
the Keycloak binding-message regex (e.g. `apr-<22 url-safe chars>`, ≤50, no
disallowed characters). The agent then initiates CIBA with
`binding_message=<ref id>`. **Why:** keeps agent-authored text out of the
human-facing surface entirely (F5-A) and gives the UI and the tool a stable key.

### 3. Trusted rendering: the UI renders the service-held payload, never agent text

The approval UI (served by the approval service, behind a prokura-realm OIDC
session) fetches the payload by reference ID from the service and renders the
action, params, requesting agent, and scopes from **stored** data. No
agent-supplied string is ever rendered. The recorded hash is the anchor the tool
later checks against. **Why:** the whole point of Flow C is that the human
approves what will actually happen, not what an agent claims will happen (F7).

### 4. Decisions only in the authenticated UI; ntfy is inert notify-only

Approval/denial happen exclusively in the UI behind a Keycloak session; the
**approval service** (not any device) relays the decision to Keycloak's callback.
ntfy notifications carry only a deep link + reference ID, published to a
**per-user unguessable topic** with ntfy ACLs. A spoofed message changes no
state; a genuine pending action is still only decidable in the UI. **Why:** F7-A/B
— notifications must not be a capability and must leak nothing.

### 5. The action token carries the reference ID; the tool enforces hash + single-use

On approval the agent's CIBA poll returns an access token. The reference ID must
ride on it (scope or claim) so the gated tool can look up the approved payload.
**Exact surfacing is verified against the running image first** (see Phase 1 /
Open Questions) — candidates: a protocol mapper exposing the CIBA
`binding_message` as a claim, or an approval-scoped token the service mints.
Before executing, the gated tool (a resource server) (a) recomputes the hash of
the action+params it is about to perform and checks it equals the approved hash,
and (b) **atomically consumes** the reference ID in Postgres (`UPDATE … SET
consumed_at=now() WHERE ref=? AND consumed_at IS NULL`), refusing if already
consumed. **Why:** makes F8-A ("single-use action token") and the
parameter-mismatch refusal directly testable, and the atomic consume closes the
concurrent-replay race.

### 6. The gated tool is a small resource server; the action is `email.send` via Mailpit

A minimal `services/tools-api/` (FastAPI) exposes `POST /tools/email/send`. It
requires an action token audienced to `agent-tools-api` (M1's audience), verifies
hash + single-use against the approval service, and on success sends through the
Mailpit SMTP sink. **Why a separate service:** the resource server is a distinct
trust role from the broker and the approval service; keeping it separate keeps
the "who executes" boundary honest and mirrors the compose-per-service pattern.

### 7. Approval state in Postgres; born instrumented

Tables created idempotently at startup: `approvals` (`ref`, `agent`, `user`,
`action`, `params_json`, `hash`, `scopes`, `status`, `created_at`, `decided_at`,
`consumed_at`). The service reuses M2's OTel `telemetry.py` pattern (OTLP
fire-and-forget, traceparent join key, correlation IDs), and every
register/delegate/decision/consume event is audit-logged in realtime.

## Risks / Trade-offs

- **[How the reference ID reaches the issued action token is unproven on 26.7.1]**
  → Phase 1 verifies it against the running image before the tool is built
  (mirrors M2's read-token discovery); if no built-in mapper surfaces the binding
  message, fall back to an approval-service-minted, ref-scoped token and document
  it in "Resolved at implementation time".
- **[Approval service joins the TCB — it can approve actions]** → decisions only
  from the authenticated UI; the service authenticates the UI session and holds
  the hash; threat model names it and states the trust. ntfy carries no
  capability.
- **[Single-use race — two executions of one ref]** → atomic conditional UPDATE
  in Postgres is the consume; a test drives a second execution and asserts refusal.
- **[Spoofed / leaky notifications]** → per-user unguessable topic + ntfy ACLs;
  payloads carry only a deep link + ref ID; tests assert a fabricated publish is
  inert and that no params appear in any notification.
- **[CIBA timeout handling]** → the 120 s expiry is Keycloak's; the SDK poll
  surfaces the token-endpoint error and the service marks the action terminal.

## Migration Plan

Additive. (1) Add `services/approval/` and `services/tools-api/` to compose.
(2) **Repoint** the Keycloak CIBA SPI flag to the approval service; move
`ciba-spike` behind its existing `spike` profile. (3) Add the action-token scope
and any mapper to `realm-export.json`. (4) Add ntfy per-user topic ACLs.
(5) Approval/tool tables created on startup. Rollback: revert the compose SPI
flag to the spike and remove the services; `down -v && up` returns to the M2
baseline. Definition of done: register → CIBA → approve → hash-verified single-use
execution is one linked trace; denial, 120 s timeout, replay, and
parameter-mismatch are refused; a spoofed ntfy message is inert; clean-slate
`down -v && up` reproduces it.

## Open Questions

- **Exact action-token ref-ID surfacing** (Keycloak binding-message claim mapper
  vs an approval-minted ref-scoped token) — resolved in Phase 1 against 26.7.1.
- **Does Keycloak enforce the 120 s CIBA `auth_req_id` expiry by default**, or
  must `attributes` set it — confirm and pin in the realm.
- **Consent-vs-approval interplay:** the CIBA request may itself prompt consent;
  confirm the poll flow returns cleanly with `is_consent_required` handled by the
  approval decision, not a second Keycloak consent screen.

## Resolved at implementation time

Verified against the running Keycloak 26.7.1 image (Phase 1,
`spike/idp-link/`-style probe over the M0 CIBA channel):

- **CIBA round-trips exactly as M0 proved.** Backchannel auth at
  `…/ext/ciba/auth` returns `{auth_req_id, expires_in: 120, interval: 5}`;
  Keycloak POSTs the delegation to the channel URI; the decision is relayed to
  `…/ext/ciba/auth/callback`; the agent's `urn:openid:params:grant-type:ciba`
  poll then yields the token. The **120 s expiry is the default** (no realm
  attribute needed) and **`is_consent_required` is false** — no second Keycloak
  consent screen appears.
- **The delegation POST body** carries `binding_message` (our reference ID),
  `login_hint`, `scope`, and `is_consent_required` — so the approval service
  correlates the delegation to the registered payload by `binding_message`. The
  delegation **bearer** carries only `sub`/`azp`/`jti`/`iss`/`aud` (no session id,
  no `auth_req_id`).
- **The reference ID does NOT surface on the Keycloak-issued action token**, and
  there is no built-in protocol mapper for the CIBA binding message (a claim
  mapper would need a Java SPI, which the spec forbids as anything but a
  fallback). **Decision (supersedes design §5's "candidates"):** the **approval
  service is the action-token authority**. At `POST /register` it returns a
  compact single-use action token `<ref>.<secret>` that is INVALID until the ref
  reaches APPROVED via the CIBA ceremony. The gated tool introspects it at the
  approval service (`POST /consume`), which verifies the presented CIBA token's
  `sub` matches the ref's owner, the action+params hash equals the approved hash,
  and the ref is unconsumed — then **atomically consumes** it. This keeps the ref
  on the credential the tool sees (spec: "carry the reference ID"), keeps the
  single-use authority in one trusted service, and needs no Keycloak extension.
  The Keycloak CIBA token remains the proof-of-approval-ceremony that authorizes
  consumption.
- **Approval service port: 8120; tools-api port: 8130.**
- **CIBA window pinned to 30 s** (`cibaExpiresIn`) for a snappy demo and a fast
  timeout test — `requested_expiry` is clamped to the realm value, so it can't be
  shortened per-request. The spec's "120 s" is the OIDC-suggested ceiling; the
  demo pins 30 s.
- **ntfy is deny-all**, so notifications required provisioning: an `ntfy-init`
  container creates a single `prokura-approval` publisher with `rw` on
  `prokura-approvals-*`, and the approval service authenticates (Basic) to
  publish. Topics are per-user and unguessable (sha256 of salt+user). Verified: a
  delivered notification carries only the reference ID + deep link — no action
  params — and anonymous publish to a topic is refused (403).
