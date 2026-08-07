# ADR-0018: The approval trigger lives on the resource server (reactive step-up)

- **Status:** accepted
- **Source of truth:** `openspec/changes/archive/2026-08-07-add-mcp-authorization/`; `services/tools-api/`
- **Relationship:** Refines ADR-0005 and ADR-0008 (M3 agent-initiated → M4 reactive).

## Context

M3 shipped an agent-initiated approval: enforcement was server-side but the *trigger* was agent-influenceable — the agent decided when to ask for approval.

## Decision

Move the **trigger to the resource server** (reactive step-up, RFC 9470-style): a sensitive call without an action token is refused with a `428 approval_required` challenge, and the resource server registers the exact `{action, params}` it observed (recording the hash). The agent then runs client-initiated CIBA for that reference and retries. The approved action is the one the server saw, not one the agent described.

## Alternatives considered

- Keep the M3 agent-initiated trigger: enforcement is still server-side, but the trigger is agent-influenceable.

## Consequences

The un-bypassable trigger is on the server. Evolves ADR-0005/ADR-0008 (hash-binding and single-use are unchanged); only who initiates the ceremony moved. Delivered in M4.

