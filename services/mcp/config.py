"""MCP server configuration from environment (compose supplies all defaults)."""

import os

KEYCLOAK_INTERNAL = os.environ.get("KEYCLOAK_URL", "http://keycloak:8080")
# Issuer as it appears in tokens (browser-facing host), matching the other
# resource servers — tokens carry iss=http://localhost:8180/realms/prokura even
# in-network because KC_HOSTNAME is pinned; JWKS is fetched over the internal host.
KEYCLOAK_ISSUER = os.environ.get(
    "KEYCLOAK_ISSUER", "http://localhost:8180/realms/prokura"
)
REALM = os.environ.get("PROKURA_REALM", "prokura")

# The audience this resource server requires on inbound MCP access tokens (the M1
# defense). Bound by the mcp-audience client scope (RFC 8707 workaround).
MCP_AUDIENCE = os.environ.get("MCP_AUDIENCE", "mcp-server")

# Public origin used to build RFC 9728 metadata URLs; must match how clients reach
# the server (the token's issuer host family), so the canonical resource URI and
# the resource_metadata pointer are the ones a real MCP client can fetch.
MCP_PUBLIC_URL = os.environ.get("MCP_PUBLIC_URL", "http://localhost:8140")
# The canonical protected-resource URI (RFC 9728 `resource`). Clients also send it
# as the OAuth `resource` parameter (RFC 8707) — we don't rely on it for binding.
MCP_RESOURCE = os.environ.get("MCP_RESOURCE", f"{MCP_PUBLIC_URL}/mcp")

# The MCP server's own confidential client — the subject of the RFC 8693 exchange
# that turns an inbound MCP token into a broker-/tools-audience token. azp of the
# exchanged token is this client, so it is also the consent "agent" identity.
MCP_CLIENT_ID = os.environ.get("MCP_CLIENT_ID", "mcp-server")
MCP_CLIENT_SECRET = os.environ.get("MCP_CLIENT_SECRET", "mcp-server-dev-secret")

# Downstream services the tools drive (internal compose hosts).
BROKER_URL = os.environ.get("BROKER_URL", "http://token-broker:8110")
BROKER_AUDIENCE = os.environ.get("BROKER_AUDIENCE", "token-broker")
TOOLS_URL = os.environ.get("TOOLS_URL", "http://tools-api:8130")
TOOLS_AUDIENCE = os.environ.get("TOOLS_AUDIENCE", "agent-tools-api")
RAG_URL = os.environ.get("RAG_URL", "http://rag:8150")
RAG_AUDIENCE = os.environ.get("RAG_AUDIENCE", "rag-server")

OTLP_ENDPOINT = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://lgtm:4317")
SERVICE_NAME = os.environ.get("OTEL_SERVICE_NAME", "mcp")

# MCP protocol revision this server implements (verified in the M4 spike).
MCP_PROTOCOL_VERSION = "2025-06-18"
