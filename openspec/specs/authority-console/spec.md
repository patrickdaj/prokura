# authority-console

## Purpose

The principal's aggregated authority register (v1 thesis #1, M8). One session-gated
"my agents" view over authority that already exists across OpenFGA, the approval
service, the broker, and Loki — plus per-agent consent revoke, provider-linking
entry, and notification onboarding. It is a trusted *surface*, not a new authority
mechanism: it renders service-held data and relays the signed-in principal's own
authority downstream by RFC 8693 token exchange (subject preserved), the broker
stays the sole `can_use` writer, and it holds no user password and no ceremony call.

## Requirements

### Requirement: Session-gated authority register
The authority console SHALL be a trusted surface with its own OIDC Authorization
Code + PKCE login (confidential client, exact redirect URI, signed HttpOnly
session cookie) that renders, for the signed-in principal only: every agent whose
`operator` is the principal, each agent's consented grants (`can_use` tuples) with
provider and scopes, the principal's pending and recent approvals, and the
principal's notification topic. No console surface SHALL accept a URL-carried
credential, and no data belonging to another principal SHALL be reachable through
any console endpoint.

#### Scenario: Signed-in principal reads their register
- **WHEN** a user signs in on the console and their agents, consents, and
  approvals exist
- **THEN** the page lists their agents with per-agent consented grants, their
  pending approvals, and their notification topic — all derived from
  service-held state, none from client-supplied identity

#### Scenario: No session, no register
- **WHEN** the console is opened without a session
- **THEN** the user is redirected through Keycloak login before any register data
  is rendered

#### Scenario: Cross-principal isolation
- **WHEN** user B signs in on the console while user A has agents, approvals, and
  audit activity
- **THEN** none of A's agents, consents, approvals, activity lines, or topic
  appear in any response to B's session

### Requirement: Downstream authority is the principal's own, via token exchange
For every downstream read or action, the console SHALL present a user-bound token
obtained by RFC 8693 exchange of the signed-in session's token into the target
audience. The console SHALL NOT assert a username out-of-band, SHALL NOT use a
service account to act on authorization state, and SHALL NOT write `can_use`
tuples itself — the broker remains the sole writer.

#### Scenario: Revoke carries the owner's identity
- **WHEN** the principal clicks revoke for one agent
- **THEN** the broker receives a bearer whose verified subject is that principal
  (audience `token-broker`), performs the tuple delete itself, and the audit
  event records the principal as the acting user

#### Scenario: Console cannot act for an absent user
- **WHEN** any console-initiated downstream call is inspected
- **THEN** its credential is a user-bound exchanged token, never a bare service
  credential asserting a user

### Requirement: Per-agent revoke from the console
The console SHALL offer per-agent consent revocation for the signed-in principal.
Revocation from the console SHALL converge on the same broker code path and audit
event as revocation from the consent surface, and SHALL invoke the M9 per-grant kill
(tuple delete + deny-list + revocation signal) — so effect is within seconds, not only
on the next hand-out, and re-acquiring the grant is blocked even with a fresh token. The
console SHALL report the measured time-to-stop and the honest in-flight residual to the
principal.

#### Scenario: One-click revoke tears up the delegation
- **WHEN** the principal revokes agent X's consent for provider P from the console
- **THEN** the `can_use` tuple is deleted, X's next provider-token request is
  refused 403, other agents are unaffected, and the register reflects the removal

#### Scenario: The revoke reports a measured kill time
- **WHEN** the principal revokes an agent from the console
- **THEN** the result states the measured new-authority-denied latency and the in-flight
  residual (the window in which an already-issued token remains valid), rather than a bare
  "effect on next hand-out" note

### Requirement: Provider linking entry from the console
The console SHALL route the signed-in principal into Keycloak account linking
(`kc_action=idp_link:<alias>`) in the principal's own browser session and, on
return, SHALL trigger the broker's grant import with an exchanged user-bound
token, so a linked grant appears in the register with no admin API or demo-driver
involvement.

#### Scenario: A real person links a provider end-to-end
- **WHEN** the principal clicks "connect <provider>", completes the provider login
  in their browser, and returns to the console
- **THEN** the grant is imported (refresh credential to OpenBao, tuples per spec)
  and the register shows the provider grant as available

### Requirement: Notification onboarding
The console SHALL show the signed-in principal their ntfy notification topic and a
subscribe affordance (URL and QR), obtained from the approval service via a
user-bound token. The topic remains notify-only; possession grants no approval
capability.

#### Scenario: Principal learns their topic
- **WHEN** the principal opens the console's notification section
- **THEN** it shows the same topic the approval service notifies for that user,
  with a subscribe link/QR — and publishing to that topic still changes no
  approval state

### Requirement: Live activity feed scoped to the principal
The console SHALL render an activity feed from the correlated audit log streams,
filtered server-side to events whose acting user is the session principal, newest
first. The filter SHALL be applied before any data leaves the console backend.

#### Scenario: Feed shows the principal's events only
- **WHEN** alice's agents produce audit events and bob opens his console feed
- **THEN** bob's feed contains bob's events and none of alice's
