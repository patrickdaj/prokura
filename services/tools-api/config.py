"""Tools-API (resource server) configuration."""

import os

KEYCLOAK_INTERNAL = os.environ.get("KEYCLOAK_URL", "http://keycloak:8080")
KEYCLOAK_ISSUER = os.environ.get("KEYCLOAK_ISSUER", "http://localhost:8180/realms/prokura")
REALM = os.environ.get("PROKURA_REALM", "prokura")
TOOLS_AUDIENCE = os.environ.get("TOOLS_AUDIENCE", "agent-tools-api")

APPROVAL_URL = os.environ.get("APPROVAL_URL", "http://approval:8120")

MAILPIT_HOST = os.environ.get("MAILPIT_HOST", "mailpit")
MAILPIT_PORT = int(os.environ.get("MAILPIT_PORT", "1025"))
MAIL_FROM = os.environ.get("MAIL_FROM", "agent@prokura.local")

OTLP_ENDPOINT = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://lgtm:4317")
SERVICE_NAME = os.environ.get("OTEL_SERVICE_NAME", "tools-api")
