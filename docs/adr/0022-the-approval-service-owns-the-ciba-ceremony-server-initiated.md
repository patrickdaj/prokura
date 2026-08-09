# ADR-0022: The approval service owns the CIBA ceremony (server-initiated)

- **Status:** accepted
- **Source of truth:** `openspec/changes/archive/*-close-correct-party-gaps/`; `services/approval/`
- **Relationship:** Supersedes the client-initiated portion of ADR-0018's flow description (the reactive trigger of ADR-0018 is unchanged); completes the F5-A/F8-A chain of custody.

## Context

ADR-0018 moved the approval *trigger* onto the resource server, but ceremony *initiation*
stayed client-side: the agent drove Keycloak's CIBA grant with the in-repo `agent-app`
confidential client. Discovered live (2026-08-08): an agent driving the stack completed a
CIBA approval **itself** with those dev credentials — the exact self-authorization Prokura
exists to prevent. A real external agent could not legitimately initiate at all (anonymous
DCR clients have no CIBA grant), so the only working path was the wrong party.

## Decision

The **approval service initiates and completes the whole ceremony**. On `POST /register`
(called by the tools-API when it fires the 428), the approval service calls Keycloak's
CIBA endpoint with its own confidential client (`approval-service`, the realm's **only**
CIBA-grant client), `login_hint` = the registered user from *verified* claims,
`binding_message` = the ref. It stores `auth_req_id`, receives the delegation on
`/ciba/delegate` (authenticated: the delegation bearer is a realm-signed JWT whose `azp`
must be `approval-service` — SR-02), relays the human's session-authenticated decision to
Keycloak's callback, polls the token endpoint to complete the ceremony, and **discards
the issued token** — the ceremony record is the product; the token has no consumer.
`agent-app` loses the CIBA grant (breaking `approvalkit.ciba_init`, deliberately). The
agent's whole role in a sensitive action: receive `428 {ref, action_token}` → wait →
retry with the action token. `/consume` proves the presenting user with the caller's
validated user-bound token instead of the now-nonexistent agent-held CIBA token.

## Alternatives considered

- **MCP server initiates on the 428** — duplicates ceremony ownership across two
  services, leaves non-MCP callers of the tools-API stuck, and puts CIBA credentials
  outside the approval service's trust position; the approval service already owns every
  other leg.
- **Provision per-DCR-client CIBA grants** — hands the ceremony to the least-trusted
  party (the root cause), and anonymous DCR clients are public anyway (no client auth
  for the backchannel grant).
- **Use the CIBA-issued token as the consume credential** — tighter binding, more moving
  parts; revisit when push mode replaces polling (M9). Default: discard.

## Consequences

No agent client can reach the CIBA grant, so agent participation in the ceremony is not
just discouraged but *impossible* — the correct-party property is enforced by the realm,
not by convention. The MCP server's 428 relay needed zero changes. The realm's
`cibaExpiresIn` is 600 s (human latency, not agent latency). Delivered in M7.
