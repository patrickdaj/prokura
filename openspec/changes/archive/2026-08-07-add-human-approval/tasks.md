# Tasks: add-human-approval (M3)

Verify-first, mirroring M0/M2: the CIBA transport is already proven, but how the
reference ID reaches the issued action token is not — Phase 1 pins that against
the running Keycloak 26.7.1 image before the gated tool is built. Each phase
closes by driving real traffic and looking.

## 1. Verify — how the reference ID reaches the action token

- [x] 1.1 Drive a CIBA request as `agent-app` (`login_hint=alice`,
  `binding_message=apr-test`, an approval scope) against the running image using
  the existing `ciba-spike` as the decision relay; approve it; decode the issued
  access token.
- [x] 1.2 Determine empirically whether the `binding_message` (reference ID)
  surfaces as a claim/scope on the token, or whether a protocol mapper is needed.
  Confirm the 120 s `auth_req_id` expiry behaviour and whether a second Keycloak
  consent screen appears.
- [x] 1.3 **Record findings in design.md "Resolved at implementation time"**: the
  ref-ID surfacing mechanism (built-in vs mapper vs approval-minted token), the
  expiry config, and the exact delegation POST body fields on 26.7.1.

## 2. Approval service — scaffold + CIBA channel

- [x] 2.1 Create `services/approval/` mirroring `services/token-broker/`:
  `Dockerfile` (uvicorn on 8120), `requirements.txt` (fastapi, uvicorn, httpx,
  psycopg, PyJWT, OTel), env config, `GET /healthz`, and `telemetry.py` reusing
  M2's fire-and-forget OTel pattern.
- [x] 2.2 `POST /register`: accept `{action, params}`, compute a canonical
  `sha256` hash, mint a binding-safe reference ID (`^[a-zA-Z0-9-._+/!?#]{1,50}$`),
  store the row, return `{ref}`.
- [x] 2.3 `POST /ciba/delegate`: receive Keycloak's delegation POST (return 201),
  correlate it to the registered payload by `binding_message`, and persist the
  delegation bearer for the callback.
- [x] 2.4 Create approval Postgres tables idempotently on startup.
- [x] 2.5 Add the `approval` service to compose and **repoint the CIBA SPI flag**
  from `ciba-spike` to `approval:8120/ciba/delegate`; move `ciba-spike` behind
  its `spike` profile.

## 3. Trusted approval UI + decision relay

- [x] 3.1 `GET /approvals` + `GET /approval/{ref}`: a bundled UI (FileResponse,
  matching the console/consent style) gated by a prokura-realm OIDC session,
  rendering the **service-held** action, params, agent, and scopes — never any
  agent-supplied string.
- [x] 3.2 `POST /approval/{ref}/decide`: on approve/deny, relay
  `{"status":"SUCCEED"|"UNAUTHORIZED"}` to Keycloak's
  `…/ext/ciba/auth/callback` with the stored delegation bearer; mark the row
  decided. On denial/timeout the action is terminal.
- [x] 3.3 ntfy notify on new pending approval: per-user unguessable topic, ntfy
  ACLs; body carries only a deep link + reference ID (no action params).

## 4. Gated tool + SDK require_approval()

- [x] 4.1 `services/tools-api/`: `POST /tools/email/send` requiring an action
  token (`aud=agent-tools-api`). Extract the reference ID, fetch the approved
  payload+hash from the approval service, **verify** the action+params it is
  about to perform hash to the approved hash, **atomically consume** the ref
  (reject if already consumed), then send via the Mailpit SMTP sink.
- [x] 4.2 SDK `prokura/approval.py` + `require_approval(action, params, *,
  scopes)`: register payload → initiate CIBA (`binding_message=ref`) → poll →
  return the action token. Typed errors `ApprovalDenied` / `ApprovalTimeout`;
  never logs the token. Export from `prokura/__init__.py`.
- [x] 4.3 Realm: add the action-token scope/mapper proven in Phase 1;
  confirm the 120 s CIBA expiry is pinned.

## 5. Tests (drive the live stack)

- [x] 5.1 `test_human_approval.py` happy path: register → CIBA → approve in the
  UI (or via the decide endpoint) → `email.send` executes once and the mail lands
  in Mailpit; the action token's ref matches.
- [x] 5.2 Single-use + hash: re-presenting the consumed token is refused
  (replay); calling the tool with params differing from the approved payload is
  refused (hash mismatch) — neither sends mail.
- [x] 5.3 Denial and timeout: a denied action returns an error to the poll and
  never executes; a request left 120 s expires and aborts cleanly.
- [x] 5.4 Notification safety: a fabricated publish to the topic changes no state
  and the genuine action is still only decidable in the UI; no approval
  notification contains action params.
- [x] 5.5 `test_no_action_token_in_logs.py`: no action token or CIBA credential
  in logs or response bodies, including error paths.

## 6. Verify + wrap

- [x] 6.1 Add an approval row to the Grafana delegation dashboard; confirm it
  renders (screenshot).
- [x] 6.2 Drive the full flow and **look**: register → notify (ntfy) → approve in
  the UI → hash-verified single-use `email.send` → mail in Mailpit; the flow is
  one linked trace with a live audit event in Loki. Browser screenshots of the
  approval UI.
- [x] 6.3 Update `docs/threat-model.md`: approval service in the TCB; the
  spoofed-notification and replay defenses; ntfy topic/ACL model.
- [x] 6.4 Clean-slate `down -v && up`; whole smoke suite green, including with
  lgtm stopped (fire-and-forget holds).
