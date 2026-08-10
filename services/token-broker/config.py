"""Broker configuration from environment (compose supplies all defaults)."""

import os

KEYCLOAK_INTERNAL = os.environ.get("KEYCLOAK_URL", "http://keycloak:8080")
# Issuer as it appears in tokens (browser-facing host). Tokens minted by
# Keycloak carry iss=http://localhost:8180/realms/prokura even in-network,
# because KC_HOSTNAME is pinned. JWKS is fetched over the internal host.
KEYCLOAK_ISSUER = os.environ.get(
    "KEYCLOAK_ISSUER", "http://localhost:8180/realms/prokura"
)
REALM = os.environ.get("PROKURA_REALM", "prokura")

BROKER_AUDIENCE = os.environ.get("BROKER_AUDIENCE", "token-broker")
# The broker's own confidential client — used to exchange (RFC 8693) the incoming
# token into a read-token-scoped token so the broker (not the agent) can retrieve
# the Keycloak-stored provider credential.
BROKER_CLIENT_ID = os.environ.get("BROKER_CLIENT_ID", "token-broker")
BROKER_CLIENT_SECRET = os.environ.get("BROKER_CLIENT_SECRET", "token-broker-dev-secret")

OPENBAO_URL = os.environ.get("OPENBAO_URL", "http://openbao:8200")
OPENBAO_TOKEN = os.environ.get("BROKER_BAO_TOKEN", "prokura-broker-dev-token")

OPENFGA_URL = os.environ.get("OPENFGA_URL", "http://openfga:8080")
FGA_STORE_NAME = os.environ.get("FGA_STORE_NAME", "prokura")

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://prokura:prokura-dev@postgres:5432/prokura",
)

OTLP_ENDPOINT = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://lgtm:4317")
SERVICE_NAME = os.environ.get("OTEL_SERVICE_NAME", "token-broker")

# Hand-out interval cap (TTL honesty — token-brokering spec). M9 lowers this to a
# small, legible floor so the post-revocation in-flight residual (a provider token
# already issued, which Prokura cannot un-issue at the mock provider) is small and
# reported honestly rather than a full 15 minutes. Configurable per deployment.
MAX_TTL_SECONDS = int(os.environ.get("BROKER_MAX_TTL_SECONDS", "120"))

# M7 (D2): browser session on the consent surface.
BROKER_PUBLIC_URL = os.environ.get("BROKER_PUBLIC_URL", "http://localhost:8110")
UI_CLIENT_ID = os.environ.get("UI_CLIENT_ID", "broker-ui")
UI_CLIENT_SECRET = os.environ.get("UI_CLIENT_SECRET", "broker-ui-dev-secret")
SESSION_SECRET = os.environ.get("SESSION_SECRET", "broker-session-dev-secret")
SESSION_COOKIE = "prokura_consent_session"
SESSION_MAX_AGE = int(os.environ.get("SESSION_MAX_AGE", "1800"))

# M9: HS256 signing key for the demo CAEP/SSF Security Event Tokens (single stream,
# demo-grade — a multi-receiver RS256/JWKS transmitter is out of scope).
SSF_SIGNING_SECRET = os.environ.get("SSF_SIGNING_SECRET", "prokura-ssf-dev-secret")
