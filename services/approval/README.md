# Prokura Approval Service (M3)

CIBA-gated **human approval** for sensitive actions (human-approval spec). It joins the
**trusted computing base**: it renders the action from server-held storage — never from
anything the agent wrote — and issues a **single-use, hash-bound** token so an approved
action runs exactly once.

## Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `GET`  | `/healthz` | liveness |
| `POST` | `/register` | agent registers `{action, params}` → `{ref, action_token}` |
| `POST` | `/ciba/delegate` | Keycloak's CIBA HTTP auth-channel receiver (returns `201`) |
| `GET`  | `/approvals` | the trusted approval UI (authenticated) |
| `GET`  | `/approval/{ref}` | JSON payload for the UI — **service-held**, never agent text |
| `GET`  | `/my/approvals` | the caller's pending approvals |
| `POST` | `/approval/{ref}/decide` | approve / deny → relay the decision to Keycloak's CIBA callback |
| `POST` | `/consume` | the gated tool verifies the hash + single-use, then atomically consumes |

## The ceremony

1. A tool refuses a sensitive call and **registers** the exact `{action, params}` here,
   getting back a `ref` and an `action_token` (`<ref>.<secret>`). The action token is
   issued now but is **invalid until the ref reaches `approved`**.
2. The agent drives **CIBA** at Keycloak with `binding_message=ref`; Keycloak calls
   `POST /ciba/delegate`, which records the delegation and sends a **notify-only** ntfy
   deep link (capability-free — just the link + ref) to the user.
3. The human opens `/approvals?ref=…`, sees the **server-stored** payload, and decides.
   `POST /approval/{ref}/decide` relays the decision to Keycloak's CIBA callback — the
   decision travels only through the authenticated surface, never the notification (ADR-0007).
4. The tool retries with the `action_token`; `POST /consume` checks the CIBA token's subject
   owns the approval, the **action hash matches** the stored payload, and **atomically
   consumes** the ref. A replay is refused `409` (ADR-0008).

## Why it's in the TCB

- **Trusted rendering** — the UI shows `{action, params}` from service-held storage; the
  agent cannot influence what the human approves, closing the substitution gap (ADR-0007).
- **Single-use, hash-bound** — one approval authorizes exactly one execution of exactly one
  payload (ADR-0008). CIBA runs on Keycloak's built-in HTTP channel, no custom Java SPI (ADR-0006).

## Configuration

Key env (see `config.py`): `KEYCLOAK_URL`, `PROKURA_REALM`, `DATABASE_URL`, `NTFY_URL` +
`NTFY_USER`/`NTFY_APPROVAL_PASSWORD` + `NTFY_TOPIC_SALT`, `APPROVAL_PUBLIC_URL`.

Port **8120**. Born instrumented — traceparent join key + `prokura.correlation_id`, realtime
audit to Loki (see the Flow C / postmortem walkthroughs).
