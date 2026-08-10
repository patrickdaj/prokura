# Design: add-authority-console (M8)

## Context

M7 made every party correct in place; M8 aggregates. The principal's authority is
readable today only by visiting four surfaces and a log store. Everything the console
needs already exists somewhere: `agent → operator` and `can_use` tuples in OpenFGA,
approval rows in the approval service, correlated audit lines in Loki, grants in the
broker, linking in Keycloak (`kc_action=idp_link`, proven in M2), the topic derivation
in the approval service. The console's job is one authenticated view over those
sources plus two actions (revoke consent, start a provider link) and one onboarding
step (show your ntfy topic) — **aggregation and onboarding, not new authority
mechanics** (`docs/architecture.md` §"Correct-party gaps", closing note).

Constraints carried from M7: no URL-carried credentials anywhere; the broker stays the
sole `can_use` writer with `operator == owner` enforced at write time (F1-A/Q3-B);
decisions stay on the approval surface's own session; humankit remains the only
simulated human; demo-grade session bar (no Redis, SameSite + signed state).

## Goals / Non-Goals

**Goals:**

- One signed-in page where a principal reads their register: agents (with operator
  proof), per-agent consented grants + scopes, pending/recent approvals, live
  activity, notification topic.
- One-click per-agent consent revoke from that page, with the write still performed
  by the broker under the same owner invariant.
- A real person reaches provider linking from the page and the grant lands imported.
- The M7 surfaces are linked, not duplicated: approvals deep-link to `:8120`,
  consent *granting* stays on `:8110`.
- Exit: a human reads the register and tears up a grant, on camera.

**Non-Goals:**

- Instant/propagating revocation and CIBA push (M9) — revoke here is the existing
  consent-tuple removal + Keycloak session revocation, honest about latency.
- Risk tiers, standing approvals, budgets (M11); real providers (M12).
- Replacing the operator console (:8095) or Grafana.
- Multi-user administration; the console shows only the signed-in principal's world.

## Decisions

### D1 — A new trusted surface: `services/authority/` (port 8160), session-first

The console is a FastAPI service following the per-service-module convention
(`websession.py` copied from M7's proven pattern, `audit.py`, `telemetry.py`), with
its own confidential `authority-ui` realm client (exact redirect URI), signed HttpOnly
session cookie (`prokura_authority_session`). It joins the TCB as a trusted *surface*
— it renders service-held data and relays the user's own authority; it never holds a
user password and never writes authorization state itself.

*Alternative — extend `services/console`:* rejected; that service is an unauthenticated
operator dashboard proxying Grafana. Mixing an authenticated principal surface into it
would blur the TCB boundary and the demo story.

### D2 — Downstream authority via RFC 8693 exchange of the session's token

The console's OIDC callback keeps the user's access+refresh token **server-side in the
session store** (encrypted-at-rest is out of demo scope; the cookie still carries only
signed claims). For every downstream read/action the console exchanges the user token
(its `authority-console` confidential client, standard token exchange enabled) into
the target audience: `token-broker` for consent listing/revoke and grant import,
`approval` reads via a new `approval-audience` scope. The downstream service then
authorizes exactly as it would for any bearer: verified signature + audience + the
token's own subject as the acting user. No service-account-acting-for-nobody, no
second session system, and the M7 write-guard survives unchanged: the broker sees
`owner = verified token subject`.

*Alternative — service credential + asserted username:* rejected; it would make the
console a trusted asserter of identity (a confused-deputy shape M6's threat model
exists to kill). *Alternative — reuse each surface's session via iframes:* rejected;
cookies are per-surface by design (S2) and the UX would be four logins.

### D3 — Broker and approval grow narrow bearer APIs; ceremonies stay put

- Broker: `GET /v1/consents` (list `can_use` for the token subject's grants),
  `POST /v1/consent/revoke` accepts EITHER its own surface session (M7 path, kept for
  the consent screen) OR a bearer whose verified `aud=token-broker` and whose subject
  is the owner — `azp` is audited. Consent *granting* remains session-only on the
  broker's screen (the explicit-approval moment is a ceremony; revocation is the
  owner destroying their own delegation — lower bar, same owner invariant).
- Approval service: `GET /v1/my/approvals` and `GET /v1/my/topic` authenticated by a
  user-bound bearer (new `approval-audience` client scope so exchange can mint
  `aud=approval`); decisions remain session-only on `:8120`.
- FGA: the console reads `agent operator` and `can_use` tuples directly (read-only,
  same trust position as the RAG reader); writes stay broker-only.
- Activity feed: the console proxies Loki through Grafana exactly like the operator
  console does, but filters to the session user (`|= "user=<username>"` over the
  audit streams) server-side, so one principal cannot read another's activity.

### D4 — Provider linking from the console (closing Flow B's last gap)

"Connect a provider" sends the user's browser to the Keycloak auth endpoint with
`kc_action=idp_link:acme` on the `authority-ui` client (`prompt=login` and the
Keycloak-26 confirm hop as proven in M2; the client needs `manage-account` reach —
spike task validates which realm-role/scope grant makes `idp_link` legal for a
non-`account` client). Callback returns to the console; the console then exchanges
the session token for `aud=token-broker` and calls the broker's existing
`POST /v1/grants/{provider}/import`. The user sees the grant appear in their register
without any admin API or demo driver.

### D5 — Notification onboarding stays derivable only by the approval service

The topic salt never leaves the approval service. The console calls
`GET /v1/my/topic` (user-bound bearer) and renders the topic, the ntfy web URL, and a
QR code (client-side JS, no external service). ADR-0007 unchanged: the topic is
notify-only; knowing it grants no capability.

### D6 — Tests: the console is a human surface, so humankit drives it

New smoke tests use humankit (real login on `:8160`, real clicks for revoke/link);
mechanism tests hit the new bearer APIs with exchanged tokens directly. The M7
separation invariant extends: the authority service source must contain no user
password and no CIBA/decide call; revocation from the console must appear in the
audit stream with the acting user. `authoritykit.py` exists only if agent-side
mechanics need sharing; expectation is humankit + direct httpx suffice.

## Risks / Trade-offs

- [Keycloak may refuse `kc_action=idp_link` for a non-`account` client or demand
  consented `manage-account`] → spike validates the exact client config against the
  live realm before service code; fallback is a console-rendered link into the
  Keycloak account console's linking page (uglier, still user-present).
- [Storing user tokens server-side in the console session] → demo-grade in-memory
  store, 30-min cap mirroring SSO idle timeout, tokens never serialized into the
  cookie; stated in threat-model residuals.
- [A second revoke path could drift from the consent screen's semantics] → both paths
  converge on the same broker code (`consent.revoke_consent`) and the same audit
  event; a smoke test asserts tuple-gone parity between paths.
- [Loki feed could leak cross-user activity] → server-side filter on the session
  user + a smoke test proving bob's console never returns alice's audit lines.
- [Scope creep toward M9 (instant revocation)] → the console reports what revoke
  does today (tuple removal + session revocation), links the M9 thesis, measures
  nothing.

## Migration Plan

Realm changes land first (authority-ui/authority-console clients, approval-audience
scope) — clean `docker compose up` re-imports; additive service APIs next (broker,
approval), console service last. Nothing existing breaks: all M7 paths remain; the
only contract addition is new endpoints and one alternative (bearer) authentication
on consent revoke. Rollback = git revert + clean compose up.

## Open Questions

- Does `kc_action=idp_link` require the `manage-account` client role on the *user*
  or an explicit client scope for `authority-ui`? (Spike resolves; M2 finding covers
  the account-client path only.)
- Should the activity feed show tool *outcomes* (sent/denied/consumed) only, or also
  reads (rag_retrieved)? Default: everything carrying `user=<principal>` in the
  audit streams, newest first — it is their register.
