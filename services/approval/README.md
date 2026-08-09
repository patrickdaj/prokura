# Prokura Approval Service (M3, re-wired M7)

CIBA-gated **human approval** for sensitive actions (human-approval spec). It joins the
**trusted computing base**: it renders the action from server-held storage — never from
anything the agent wrote — and issues a **single-use, hash-bound** token so an approved
action runs exactly once. Since M7 it owns the **whole ceremony** (ADR-0022): it
initiates CIBA itself, receives the delegation, relays the decision, completes the
ceremony by polling, and discards the issued token. No agent client can even reach the
CIBA grant.

## Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `GET`  | `/healthz` | liveness |
| `POST` | `/register` | the tools-API registers `{action, params}` → `{ref, action_token}`; initiates CIBA server-side |
| `POST` | `/ciba/delegate` | Keycloak's CIBA HTTP auth-channel receiver — **authenticated** (realm-signed delegation JWT, `azp=approval-service`, body cap; SR-02) |
| `GET`  | `/login` · `/callback` | OIDC session for the trusted surface (auth-code + PKCE, `approval-ui` client, signed cookie) |
| `GET`  | `/approvals` | the trusted approval UI (session-gated rendering) |
| `GET`  | `/whoami` | session probe for the page (401 → login redirect) |
| `GET`  | `/approval/{ref}` | JSON payload for the UI — **service-held**, never agent text (session) |
| `GET`  | `/my/approvals` | the session user's approvals |
| `POST` | `/approval/{ref}/decide` | approve / deny **in the session** → relay to Keycloak's CIBA callback + complete the ceremony |
| `POST` | `/consume` | the gated tool verifies the user, hash + single-use, then atomically consumes |

## The ceremony (M7: server-initiated)

1. A tool refuses a sensitive call and **registers** the exact `{action, params}` here,
   getting back a `ref` and an `action_token` (`<ref>.<secret>`). The action token is
   issued now but is **invalid until the ref reaches `approved`**. Registration itself
   initiates CIBA with this service's own confidential client (`login_hint` from the
   *verified* caller claims, `binding_message=ref`) — the agent's role ends at the 428.
2. Keycloak delivers the delegation to `POST /ciba/delegate` (authenticated), which
   records it and sends a **notify-only** ntfy deep link (capability-free — just
   `/approvals#ref`) to the user.
3. The human follows the deep link, signs in (OIDC; the `#ref` survives the login
   round-trip inside the signed OAuth `state`), sees the **server-stored** payload, and
   decides. Decisions exist only in that session — no bearer path (ADR-0007, M7).
4. The service relays the decision to Keycloak's callback and completes the ceremony by
   polling the token endpoint; the issued token is **discarded** (the ceremony is the
   product — ADR-0022).
5. The tool retries with the `action_token`; `POST /consume` checks the caller's
   user-bound token subject owns the approval, the **action hash matches** the stored
   payload, and **atomically consumes** the ref. A replay is refused `409` (ADR-0008).

## Why it's in the TCB

- **Trusted rendering** — the UI shows `{action, params}` from service-held storage; the
  agent cannot influence what the human approves, closing the substitution gap (ADR-0007).
- **Single-use, hash-bound** — one approval authorizes exactly one execution of exactly one
  payload (ADR-0008). CIBA runs on Keycloak's built-in HTTP channel, no custom Java SPI (ADR-0006).
- **Sole ceremony owner** — the only realm client with the CIBA grant; initiation,
  delegation receipt, decision relay, and completion all happen in this trust position
  (ADR-0022). Errors leave as stable machine codes only (SR-01).

## Configuration

Key env (see `config.py`): `KEYCLOAK_URL`, `PROKURA_REALM`, `DATABASE_URL`, `NTFY_URL` +
`NTFY_USER`/`NTFY_APPROVAL_PASSWORD` + `NTFY_TOPIC_SALT`, `APPROVAL_PUBLIC_URL`,
`UI_CLIENT_ID`/`UI_CLIENT_SECRET` + `SESSION_SECRET` (surface session),
`CIBA_CLIENT_ID`/`CIBA_CLIENT_SECRET` (ceremony initiator).

Port **8120**. Born instrumented — traceparent join key + `prokura.correlation_id`, realtime
audit to Loki (see the Flow C / postmortem walkthroughs).
