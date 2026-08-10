# Proposal: add-authority-console (M8 — Authority console)

## Why

After M7, every party is correct but the *principal's* experience is scattered across
four surfaces: the approval UI (:8120), the consent screen (:8110), ntfy, and nothing at
all for "what agents act for me right now?". Power of attorney is only tolerable if you
can read the register and tear up the grant — and no surface today aggregates, for one
signed-in human, their agents, grants, pending approvals, and activity, or offers
one-click revoke (v1 thesis #1, `docs/architecture.md` §"Beyond parity" and §"v1
delivery plan — M8"). Two v0 gaps also still lack a user-facing entry point: grant
linking (Flow B's last ❌ — no real person is ever routed into `kc_action=idp_link`)
and notification onboarding (nothing tells a user their ntfy topic, deferred from M7).

## What Changes

- **New user-facing service `services/authority/` (port 8160)** — the "my agents"
  panel, behind its own OIDC session (M7's `websession.py` pattern, `authority-ui`
  confidential client): every agent operated by the signed-in principal, each agent's
  consented grants, pending approvals (deep-linking into the M7 approval surface), and
  a live activity feed from the already-correlated Loki audit lines.
- **Per-agent revoke from the console** — consent-tuple removal via the broker (which
  stays the sole `can_use` writer) plus Keycloak session revocation where applicable.
  The console relays the *signed-in user's* authority downstream by RFC 8693 exchange
  of its session token — never a service-account acting for nobody.
- **"Connect a provider" entry** — the console routes the signed-in user into
  Keycloak account linking (`kc_action=idp_link`) and, on return, imports the grant
  via the broker's existing bearer-authenticated import endpoint. Closes the last ❌
  in the correct-party gap table.
- **Notification onboarding** — the console shows the signed-in user their unguessable
  ntfy topic (+ QR / subscribe link); the approval service exposes a user-bound-token
  API for the topic derivation it owns.
- **Broker/approval read+revoke APIs for the console** — narrow, bearer-authenticated
  (exchanged user-bound token) endpoints so the console can aggregate and act without
  becoming a second tuple-writer or duplicating session surfaces.
- Existing operator console (:8095) is untouched; the M7 surfaces stay canonical for
  their ceremonies (approve/deny happens on :8120; the authority console links, never
  re-implements).

## Capabilities

### New Capabilities

- `authority-console`: the principal's aggregated authority register — session-gated
  "my agents" view (agents, grants, scopes, pending approvals, activity feed),
  per-agent consent revoke, provider-linking entry, and notification onboarding.

### Modified Capabilities

- `per-agent-consent`: consent revocation MAY additionally be performed from the
  authority console's authenticated session, relayed to the broker with an exchanged
  user-bound token (aud=token-broker, azp=authority console); the broker remains the
  sole tuple writer and the owner is the verified token subject. (Write path for
  *granting* consent is unchanged — the broker's own screen.)
- `human-approval`: the approval service SHALL expose narrow user-bound-token read
  APIs for the console (pending/decided approvals for the token's subject; the
  subject's notification topic). Decisions remain exclusively on the approval
  surface's own session.
- `grant-acquisition`: the user-facing linking entry point becomes a requirement —
  a real person can reach `kc_action=idp_link` from the console and the resulting
  grant is imported without any admin/demo-driver step.

## Impact

- New: `services/authority/` (FastAPI + websession.py + static panel HTML), compose
  service on 8160, `authority-ui` + `authority-console` realm clients (session +
  exchange) in `deploy/keycloak/realm-export.json`.
- Modified: `services/token-broker/` (bearer path for consent revoke + consent/grant
  listing for the console), `services/approval/` (user-bound read APIs: approvals
  list, ntfy topic), realm export.
- Tests: `tests/smoke/authoritykit.py` (agent-side has no place here — this is a human
  surface, so humankit drives it), console aggregation/revoke/linking smoke tests;
  M7's separation invariant must keep passing (the console holds no user password;
  it holds a session like the other trusted surfaces).
- Docs: architecture gap-table row B-linking closes; M8 blog; walkthrough addition.
- Spike-first (same discipline as M7): the aggregation query (FGA tuples + approval
  rows + Loki lines for one principal) and console-initiated `kc_action=idp_link`
  are proven against the live stack before any service code.
