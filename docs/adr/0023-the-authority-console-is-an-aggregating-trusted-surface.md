# ADR-0023: The authority console is an aggregating trusted surface, not a new authority

- **Status:** accepted
- **Source of truth:** `openspec/changes/archive/*-add-authority-console/`; `services/authority/`
- **Relationship:** Builds on ADR-0022 (server-initiated ceremony) and the M7 surface-session pattern (`websession.py`); reuses the RFC 8693 exchange position of ADR-0002 (each resource server is its own audience) and the sole-writer invariant of ADR-0012/ADR-0001. Closes correct-party gap **B (grant linking)** and the notification-onboarding tail of gap C.

## Context

After M7 every party is correct, but the *principal's* view of their own delegated authority
is scattered: `agent operator` and `can_use` tuples in OpenFGA, approval rows in the approval
service, the notification topic derivable only inside that service, grants in the broker,
activity in Loki. There was no single place for a signed-in person to read "what acts for me"
and revoke it, and no user-facing entry into `kc_action=idp_link` (gap B — a real person was
never routed into linking; only a headless spike drove it). Power of attorney is only tolerable
if you can read the register and tear up the grant.

The risk in building that page is that a new aggregating surface becomes a **confused deputy** —
a service that asserts *who the user is* out of band, or holds a service credential that acts on
authorization state, or becomes a second writer of `can_use` tuples. Any of those would re-open
exactly the impersonation class M6/M7 exist to kill.

## Decision

Add `services/authority` (port 8160) as a trusted **surface**, not a new authority:

- **Its own session, no password, tokens server-side.** Authorization Code + PKCE via a
  confidential `authority-ui` client (the M7 `websession.py` pattern); the signed HttpOnly
  cookie carries only `{sid, sub, preferred_username, exp}`. The user's access/refresh tokens
  are held server-side keyed by `sid` and never enter the cookie.
- **Downstream is the user's own authority, by RFC 8693 exchange.** For every read/action the
  console exchanges the user's token — as the confidential `authority-console` client — into the
  target audience: `aud=token-broker` (list/revoke consents, import grants) and `aud=approval`
  (read approvals, read topic). The exchange **preserves the subject**, so downstream authorizes
  exactly as for any bearer: verified signature + audience + the token's own subject as the owner.
  The `authority-ui` token carries `aud=authority-console` (a realm mapper) so the backend client
  is permitted to exchange it — the same mechanism the MCP server relies on.
- **Not a second writer.** The broker stays the sole `can_use` writer. Revoke from the console is
  relayed as a user-bound bearer to the broker's `/v1/consent/revoke`, which converges on the same
  code path and audit event as the M7 consent screen; because revoke only deletes a tuple under
  `grant:{subject}/…`, a foreign subject can never revoke another user's delegation.
- **Narrow, bearer-only read APIs; ceremonies stay put.** The broker grows `GET /v1/consents` and a
  bearer path on revoke; the approval service grows `GET /v1/my/approvals` and `GET /v1/my/topic`
  (new `approval` audience client + `approval-audience` scope). Decisions remain session-only on
  `:8120`; consent *granting* remains session-only on `:8110`. The console links those ceremonies,
  it never re-implements them. The activity feed filters Loki server-side to the session username.
- **Linking from the console.** "Connect a provider" routes the user into `kc_action=idp_link` in
  their own browser (no `prompt=login`: forcing a re-auth on the broker return leg loops when an
  SSO session already exists); on return the console imports the grant with the user's exchanged
  token — closing gap B with no admin API or demo driver.

## Alternatives considered

- **Extend the operator console (`:8095`).** Rejected: it is an unauthenticated Grafana-proxy
  dashboard; mixing an authenticated principal surface into it blurs the TCB boundary.
- **Service credential + asserted username.** Rejected: it makes the console a trusted asserter of
  identity — the confused-deputy shape the threat model exists to kill. Token exchange keeps the
  subject verified end to end.
- **Reuse each surface's session via iframes.** Rejected: cookies are per-surface by design (spike
  S2), and the UX would be four logins.
- **A second, console-owned revoke implementation.** Rejected: two revoke paths would drift; both
  converge on `consent.revoke_consent` and one audit event instead.

## Consequences

Every correct-party gap is now closed in place. The console adds a surface and a handful of narrow,
user-bound read/revoke endpoints, but **no new write authority and no new session system** — the
broker still writes every tuple, the approval service still owns the topic salt and every decision,
and the console carries only the user's own exchanged bearer. The M7 separation invariant extends to
it: the authority service source holds no user password and no CIBA/decision call (grep-enforced in
`test_party_separation.py`), and a console revoke appears in the audit stream with the acting user
and `azp=authority-console`. Instant/propagating revocation remains M9; the console is honest that
revoke takes effect on the agent's next hand-out. Server-side token storage is demo-grade
(in-memory, bounded, dropped on restart → re-login). Delivered in M8.
