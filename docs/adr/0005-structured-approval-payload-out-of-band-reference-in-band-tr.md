# ADR-0005: Structured approval payload out-of-band; reference in-band; trusted rendering

- **Status:** accepted
- **Source of truth:** SPEC-REVIEW F5; `openspec/specs/human-approval/spec.md`; `services/approval/app.py`
- **Also records the locked choice:** Approval payload hashing / no free-text binding_message (F5).

## Context

§9 made 'binding_message rendered verbatim' a hard rule, but the message is agent-authored — the very principal the human is checking. A prompt-injected agent can make the human approve attacker text; Keycloak also caps `binding_message` at 50 chars, no spaces.

## Decision

The agent registers `{action, params}` with the approval service; `binding_message` carries only a short reference ID. The **trusted** approval UI fetches and renders the service-held payload (never agent text); the approval service records a payload hash; the resource server verifies the executed action against the approved hash before acting. Reproduces RAR's properties without touching Keycloak internals.

## Alternatives considered

- B — keep free text, document the risk: 'approval theater' undermines the thesis.
- C — implement RAR in Keycloak via extension: standards-faithful, largest effort, deepest internals risk (a v1 topic).

## Consequences

The human approves parameters, not prose. Rewrote the §9 hard rule accordingly. See ADR-0008 (single-use) and ADR-0018 (reactive trigger).

