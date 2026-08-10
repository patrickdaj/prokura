# services/authority — Authority Console (M8)

The principal's aggregated authority register. A trusted **surface** (not a new
authority mechanism): behind its own OIDC session it renders, for the signed-in
user only, the agents that act for them, the grants those agents can use, their
pending/recent approvals, their notification topic, and a live activity feed —
and offers two actions: revoke an agent's consent and connect a provider.

Port **8160**. Session cookie `prokura_authority_session` (signed, HttpOnly).

## How it stays correct-by-construction

- **Own session, no password.** Authorization Code + PKCE via the confidential
  `authority-ui` client (M7 `websession.py` pattern). The cookie holds only
  `{sid, sub, preferred_username, exp}`; the user's access/refresh tokens live
  **server-side** keyed by `sid` (D2) — never in the cookie.
- **Downstream is the user's own authority.** For every read/action the console
  exchanges (RFC 8693) the signed-in user's token — as the `authority-console`
  client — into the target audience (`token-broker`, `approval`), subject
  preserved. Downstream sees `owner = verified token subject`; there is no
  service account acting for nobody and no out-of-band username assertion.
- **Not a second writer.** The broker stays the sole `can_use` writer. Revoke
  relays a user-bound bearer to the broker's `/v1/consent/revoke`; the console
  writes no authorization state itself.
- **Ceremonies stay put.** Approvals deep-link to the approval surface (:8120);
  consent *granting* stays on the broker's consent screen (:8110).

## Endpoints

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/login`, `/callback` | — | OIDC session for the surface |
| GET | `/whoami` | session | who is signed in (401 → `/login`) |
| GET | `/` | — | the panel (`index.html`) |
| GET | `/api/register` | session | agents + consents + grants + approvals |
| GET | `/api/activity` | session | Loki feed, filtered server-side to the user |
| GET | `/api/topic` | session | the user's ntfy topic + subscribe URL + QR |
| POST | `/api/revoke/{agent}/{provider}` | session | per-agent consent revoke (→ broker bearer) |
| GET | `/api/link/{provider}` | session | start `kc_action=idp_link` in the user's browser |
| GET | `/api/link/callback` | session | on return, import the grant (→ broker) |

## Modules

- `app.py` — endpoints + server-side token store + session.
- `websession.py` — OIDC login (M7 pattern) returning the token bundle so the app
  can keep tokens server-side.
- `exchange.py` — RFC 8693 exchange into `token-broker` / `approval`.
- `fga.py` — reads the `operator` relation (the console's own read position).
- `activity.py` — Loki via Grafana proxy, `|= "user=<username>"`, username
  validated before it enters the LogQL string.
- `audit.py` / `telemetry.py` — the shared per-service instrumentation pattern.

## Realm wiring

`authority-ui` (session; carries `aud=authority-console`), `authority-console`
(exchange; optional scopes `broker-audience`, `approval-audience`), the `approval`
resource client, and the `approval-audience` client scope — all in
`deploy/keycloak/realm-export.json`. The `idp_link` flow needs no extra grant on
`authority-ui` (M8 spike finding).
