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
