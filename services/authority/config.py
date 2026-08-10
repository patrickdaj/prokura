"""Authority console configuration (compose supplies all defaults)."""

import os

KEYCLOAK_INTERNAL = os.environ.get("KEYCLOAK_URL", "http://keycloak:8080")
KEYCLOAK_ISSUER = os.environ.get(
    "KEYCLOAK_ISSUER", "http://localhost:8180/realms/prokura"
)
REALM = os.environ.get("PROKURA_REALM", "prokura")

# M8 (D1): browser session on the authority console surface. authority-ui is the
# confidential login client (exact redirect URI); the signed HttpOnly cookie
# carries only {sid, sub, username, exp} — the user's tokens stay server-side.
AUTHORITY_PUBLIC_URL = os.environ.get("AUTHORITY_PUBLIC_URL", "http://localhost:8160")
UI_CLIENT_ID = os.environ.get("UI_CLIENT_ID", "authority-ui")
UI_CLIENT_SECRET = os.environ.get("UI_CLIENT_SECRET", "authority-ui-dev-secret")
SESSION_SECRET = os.environ.get("SESSION_SECRET", "authority-session-dev-secret")
SESSION_COOKIE = "prokura_authority_session"
SESSION_MAX_AGE = int(os.environ.get("SESSION_MAX_AGE", "1800"))

# M8 (D2): the backend exchange client. The console exchanges (RFC 8693) the
# signed-in user's stored token into downstream audiences — never a service
# account acting for nobody. Subject is preserved, so downstream sees the owner.
EXCHANGE_CLIENT_ID = os.environ.get("EXCHANGE_CLIENT_ID", "authority-console")
EXCHANGE_CLIENT_SECRET = os.environ.get("EXCHANGE_CLIENT_SECRET", "authority-console-dev-secret")

# Downstream surfaces (internal hosts) + their audiences.
BROKER_URL = os.environ.get("BROKER_URL", "http://token-broker:8110")
BROKER_AUDIENCE = os.environ.get("BROKER_AUDIENCE", "token-broker")
APPROVAL_URL = os.environ.get("APPROVAL_URL", "http://approval:8120")
APPROVAL_AUDIENCE = os.environ.get("APPROVAL_AUDIENCE", "approval")
# Browser-facing approval surface, for deep links into the M7 approval ceremony.
APPROVAL_PUBLIC_URL = os.environ.get("APPROVAL_PUBLIC_URL", "http://localhost:8120")

# Activity feed: Loki through Grafana's datasource proxy (same as services/console).
GRAFANA_URL = os.environ.get("GRAFANA_URL", "http://lgtm:3000")

# FGA read (operator relation) — the console's own read position (D3), same as
# the RAG reader; writes stay broker-only.
OPENFGA_URL = os.environ.get("OPENFGA_URL", "http://openfga:8080")
FGA_STORE_NAME = os.environ.get("FGA_STORE_NAME", "prokura")

OTLP_ENDPOINT = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://lgtm:4317")
SERVICE_NAME = os.environ.get("OTEL_SERVICE_NAME", "authority")
