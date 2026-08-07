# ADR-0007: ntfy is notify-only; decisions only through the authenticated UI

- **Status:** accepted
- **Source of truth:** SPEC-REVIEW F7; `openspec/specs/human-approval/spec.md`; `deploy/ntfy/`
- **Also records the locked choice:** ntfy notify-only (F7).

## Context

Public ntfy topics are bearer capabilities: anyone guessing the topic can subscribe (leaking pending-action detail) or publish (spoofing notifications). The spec never said how the decision callback authenticates the decider.

## Decision

ntfy is **notify-only**: the notification carries no approval capability — only a deep link + reference ID. Approve/deny happens exclusively in the approval UI behind a Keycloak session; the callback to Keycloak is made by the approval service. Self-hosted **deny-all** ntfy in compose, per-user unguessable topic names as defense-in-depth.

## Alternatives considered

- B — self-hosted ntfy with ACLs (adopted together).
- C — Web Push instead of ntfy: no shared topics, but VAPID/service-worker plumbing.

## Consequences

A spoofed publish is inert and changes no approval state. See the F7 STRIDE-C entry.

