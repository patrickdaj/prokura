# Proposal: add-human-approval (M3)

## Why

M2 lets an agent obtain a scoped provider token, but only gates it on *prior*
consent. High-risk actions — sending an email, moving money — need a human in
the loop **at action time**, in a trusted surface, with a credential that can be
used exactly once for exactly the approved action. M3 makes SPEC.md's Flow C
real: a sensitive action pauses on CIBA, a human approves in an authenticated UI
that renders a service-held payload (never agent prose), and only then is a
single-use, hash-bound action token issued. The **approval service joins the
trusted computing base**.

The M0 spike already proved the hard part — Keycloak's built-in CIBA HTTP
authentication channel round-trips (delegation POST in, decision on the callback
endpoint) — so M3 is **Python + configuration, no Java SPI**. This milestone
turns that spike into product.

## What Changes

- **Approval service (new, `services/approval/`):** a FastAPI service that
  (1) accepts out-of-band **payload registration** from an agent and returns a
  reference ID + records a payload hash; (2) receives Keycloak's CIBA
  **delegation POST** (replacing the M0 spike as the channel target); (3) serves
  a **trusted approval UI** behind a Keycloak session that renders the
  service-held payload by reference ID; (4) relays the decision to Keycloak's
  **CIBA callback**; (5) emits **ntfy** notifications carrying only a deep link +
  reference ID. Born instrumented (traceparent + correlation IDs — observability
  DoD), and it joins the trusted computing base in the threat model.
- **Keycloak (config):** repoint the built-in CIBA HTTP auth-channel SPI flag
  from `ciba-spike` to the approval service; retire the spike to a profile.
  Issue **action tokens** carrying the approval reference ID (scope/claim);
  `agent-app` already has CIBA (poll) enabled from M0.
- **Gated tool (resource server):** a concrete sensitive action to protect —
  `email.send` via the Mailpit SMTP sink. Before executing, the tool endpoint
  **verifies the action matches the approved payload hash** and **rejects any
  reference ID already consumed** (single-use), making F8-A testable.
- **SDK `require_approval()`:** register the payload, initiate CIBA, poll, and
  return the action token — the M3 addition to the `agent-sdk` contract.
- **ntfy:** per-user unguessable topics with ACLs; notify-only, no capability.

## Capabilities

### Modified Capabilities

- `agent-sdk`: a delta ADDING the `require_approval()` helper to the SDK contract
  (the M1 spec already foreshadows it as an M3 addition).

(No new capabilities. M3 *implements* the existing `human-approval` spec's six
requirements. If implementation reveals a genuine gap, a `human-approval` delta
will be added during design; the default expectation is no change.)

## Impact

- **New:** `services/approval/` (FastAPI + trusted approval UI + ntfy client +
  Postgres approval tables), a gated `email.send` tool endpoint that enforces
  hash + single-use, SDK `require_approval()`, realm action-token scope/claim,
  `deploy/ntfy/` ACL + per-user topic config, integration tests.
- **Modified:** `docker-compose.yml` (approval service; **repoint the CIBA SPI
  flag** from `ciba-spike` to the approval service; ntfy ACLs), the Grafana
  delegation dashboard (approval row), `docs/threat-model.md` (approval service
  in the TCB; the spoofed-notification and replay defenses).
- **No new spike:** the M0 CIBA spike already de-risked the transport; M3 builds
  directly on its proven delegation-POST / callback round-trip.
- **Verification (definition of done):** registration → CIBA → approve →
  hash-verified single-use execution appears as one linked trace; denial and the
  120 s timeout abort cleanly; replay and parameter-mismatch are refused; a
  spoofed ntfy message is inert and leaks nothing. Clean-slate `down -v && up`.
