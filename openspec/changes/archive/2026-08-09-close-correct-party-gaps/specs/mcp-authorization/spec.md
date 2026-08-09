# mcp-authorization — delta (close-correct-party-gaps / M7)

## MODIFIED Requirements

### Requirement: MCP tools drive the delegation chain

The MCP server SHALL expose tools, reachable only with a valid MCP-audience token,
that exercise the chain: obtaining a brokered third-party provider token (via the
Token Broker, subject to per-agent consent) and performing a sensitive action
that requires human approval. The MCP server SHALL NOT pass an inbound MCP token
through to a downstream service; it SHALL obtain a correctly-audienced token
(RFC 8693 exchange) for each downstream call. When a sensitive tool is called
without an action token, the MCP server SHALL relay the resource server's
`approval_required` challenge containing only `{status, ref, action_token}` and a
message instructing the agent to wait for human approval and retry — it SHALL NOT
instruct or enable the agent to perform any part of the CIBA ceremony (the
ceremony is initiated server-side by the approval service at registration).

#### Scenario: A tool call yields a brokered provider token

- **WHEN** a consented MCP client calls the provider-token tool
- **THEN** the MCP server exchanges for a broker-audience token, the broker
  returns a scoped provider token, and the tool returns it — the inbound MCP token
  is never forwarded downstream

#### Scenario: Sensitive tool challenge involves no agent-side ceremony

- **WHEN** an MCP client calls `send_email` without an action token
- **THEN** the response carries the challenge (`ref`, `action_token`) and a
  wait-and-retry instruction only; after the human approves in their own session,
  the same client's retry with the action token executes the action exactly once,
  with no agent-side Keycloak interaction in between

#### Scenario: Documented RFC 8707 gap

- **WHEN** the mcp-authorization behavior is reviewed
- **THEN** the docs state that Keycloak does not enforce RFC 8707 resource
  indicators and that audience binding is achieved with a client scope instead
