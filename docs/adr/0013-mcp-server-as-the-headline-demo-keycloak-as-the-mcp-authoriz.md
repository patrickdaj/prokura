# ADR-0013: MCP server as the headline demo (Keycloak as the MCP authorization server)

- **Status:** accepted
- **Source of truth:** SPEC-REVIEW Q4; `openspec/specs/mcp-authorization/spec.md`; `services/mcp/`
- **Also records the locked choice:** MCP-first vs LangChain (Q4).

## Context

The spec hedged between a LangChain demo and an MCP server; MCP AS mode sat in the v1 roadmap.

## Decision

Ship the **MCP server as the headline**: Keycloak as an MCP authorization server (RFC 8414 metadata, RFC 7591 DCR, RFC 9728 PRM served by the MCP server), the delegation chain driven through MCP tools by a real client. The documented gap: RFC 8707 Resource Indicators are unsupported — audience is bound by a client scope instead.

## Alternatives considered

- A — LangChain-only v0: least risk, least distinctive.
- C — both in v0: severe scope risk in the plan.

## Consequences

'Keycloak as an MCP AS' is the most-searched, least-served piece of this space and is genuinely reachable. Cost: the second provider (Google) and a fuller RAG corpus slipped toward v1.

