"""Approval service configuration (compose supplies all defaults)."""

import os

KEYCLOAK_INTERNAL = os.environ.get("KEYCLOAK_URL", "http://keycloak:8080")
KEYCLOAK_ISSUER = os.environ.get(
    "KEYCLOAK_ISSUER", "http://localhost:8180/realms/prokura"
)
REALM = os.environ.get("PROKURA_REALM", "prokura")

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://prokura:prokura-dev@postgres:5432/prokura"
)

NTFY_URL = os.environ.get("NTFY_URL", "http://ntfy")
# The approval service is the only principal allowed to publish (deny-all server).
NTFY_USER = os.environ.get("NTFY_USER", "prokura-approval")
NTFY_PASSWORD = os.environ.get("NTFY_APPROVAL_PASSWORD", "prokura-approval-dev")
# Salt for deriving each user's unguessable notification topic.
NTFY_TOPIC_SALT = os.environ.get("NTFY_TOPIC_SALT", "prokura-approval-dev-salt")
# Where the deep link in a notification points (browser-facing).
APPROVAL_PUBLIC_URL = os.environ.get("APPROVAL_PUBLIC_URL", "http://localhost:8120")

OTLP_ENDPOINT = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://lgtm:4317")
SERVICE_NAME = os.environ.get("OTEL_SERVICE_NAME", "approval")

CIBA_CALLBACK = (
    f"{KEYCLOAK_INTERNAL}/realms/{REALM}/protocol/openid-connect/ext/ciba/auth/callback"
)

# M7 (ADR-0022): the approval service owns CIBA ceremony initiation — the only
# client with the CIBA grant. Poll delivery; the issued token is discarded.
CIBA_CLIENT_ID = os.environ.get("CIBA_CLIENT_ID", "approval-service")
CIBA_CLIENT_SECRET = os.environ.get("CIBA_CLIENT_SECRET", "approval-service-dev-secret")
CIBA_AUTH_URL = f"{KEYCLOAK_INTERNAL}/realms/{REALM}/protocol/openid-connect/ext/ciba/auth"
TOKEN_URL = f"{KEYCLOAK_INTERNAL}/realms/{REALM}/protocol/openid-connect/token"

# M7 (D2): browser session on the trusted surface.
UI_CLIENT_ID = os.environ.get("UI_CLIENT_ID", "approval-ui")
UI_CLIENT_SECRET = os.environ.get("UI_CLIENT_SECRET", "approval-ui-dev-secret")
SESSION_SECRET = os.environ.get("SESSION_SECRET", "approval-session-dev-secret")
SESSION_COOKIE = "prokura_approval_session"
# Session lifetime mirrors the SSO session (D2) — the 15-min honesty rule is
# about delegated tokens, not first-party browser sessions.
SESSION_MAX_AGE = int(os.environ.get("SESSION_MAX_AGE", "1800"))

# SR-02: cap on the /ciba/delegate request body (Keycloak's payload is ~1 KB).
DELEGATE_BODY_CAP = 16 * 1024

# An undecided approval expires with the backchannel window (mirrors the realm's
# cibaExpiresIn). Enforced HERE since M7: the agent-side CIBA poll that used to
# surface expiry no longer exists (ADR-0022), so the ceremony owner enforces it.
APPROVAL_TTL_SECONDS = int(os.environ.get("APPROVAL_TTL_SECONDS", "600"))
