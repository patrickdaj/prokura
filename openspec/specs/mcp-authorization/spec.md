# mcp-authorization

## Purpose

Keycloak as an MCP authorization server, and the Prokura MCP server as an OAuth
2.1 resource server, per MCP Authorization (2025-06-18). Lets any standard MCP
client discover, register, authenticate, and call protected tools that drive the
delegation chain. (SPEC.md Flow: MCP AS mode; decision Q4-B.)

## Requirements

### Requirement: MCP server publishes RFC 9728 protected-resource metadata

The MCP server SHALL implement OAuth 2.0 Protected Resource Metadata (RFC 9728),
serving a metadata document at `/.well-known/oauth-protected-resource` whose
`authorization_servers` field names the Keycloak realm authorization server. An
unauthenticated protected request SHALL receive `401 Unauthorized` with a
`WWW-Authenticate: Bearer resource_metadata="<url>"` header pointing at that
document.

#### Scenario: Discovery from a 401 challenge

- **WHEN** an MCP client makes a protected request with no access token
- **THEN** the server responds `401` with a `WWW-Authenticate` header carrying the
  `resource_metadata` URL, and that URL returns metadata listing the Keycloak
  authorization server

### Requirement: Authorization-server metadata and dynamic client registration

The Keycloak realm SHALL expose OAuth 2.0 Authorization Server Metadata (RFC
8414) and SHALL permit OAuth 2.0 Dynamic Client Registration (RFC 7591) so an MCP
client can obtain a client id without manual configuration. Registration policy
MUST permit anonymous registration for clients whose redirect URIs are localhost
(the OAuth 2.1 requirement), and the trade-off — any client may register — MUST be
documented, with per-agent consent as the gate on a registered client's access.

#### Scenario: A client registers dynamically

- **WHEN** an MCP client POSTs client metadata (localhost redirect URI, public /
  PKCE) to the realm's registration endpoint
- **THEN** it receives a client id and a registration access token, with no
  operator involvement

#### Scenario: AS metadata is discoverable

- **WHEN** a client fetches `.../.well-known/oauth-authorization-server`
- **THEN** it receives the authorization and token endpoints, the registration
  endpoint, and `S256` PKCE support

### Requirement: OAuth 2.1 + PKCE with audience-bound tokens

A registered client SHALL obtain tokens via OAuth 2.1 authorization code with
PKCE (`S256`) and SHALL send the RFC 8707 `resource` parameter. Because the
authorization server does not bind the token audience from `resource` (a
documented gap), the deployment SHALL bind audience with a client scope so tokens
issued to MCP clients carry `aud` identifying the MCP server. The MCP server SHALL
validate that presented access tokens include it in the audience and reject those
that do not.

#### Scenario: Token carries the MCP audience

- **WHEN** a registered MCP client completes the OAuth 2.1 + PKCE flow
- **THEN** the issued access token's `aud` includes the MCP server, and the MCP
  server accepts it

#### Scenario: Wrong-audience token refused

- **WHEN** a token not issued for the MCP server (e.g. a broker-audience token) is
  presented to the MCP server
- **THEN** the MCP server responds `401` and performs no tool action

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
