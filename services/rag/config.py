"""RAG retriever configuration from environment (compose supplies all defaults)."""

import os

KEYCLOAK_INTERNAL = os.environ.get("KEYCLOAK_URL", "http://keycloak:8080")
# Issuer as it appears in tokens (browser-facing host), matching the other resource
# servers — tokens carry iss=http://localhost:8180/realms/prokura even in-network
# because KC_HOSTNAME is pinned; JWKS is fetched over the internal host.
KEYCLOAK_ISSUER = os.environ.get(
    "KEYCLOAK_ISSUER", "http://localhost:8180/realms/prokura"
)
REALM = os.environ.get("PROKURA_REALM", "prokura")

# The audience this resource server requires on inbound tokens (the F2 defense):
# a token minted for anything else (e.g. an mcp-server token) is refused here.
RAG_AUDIENCE = os.environ.get("RAG_AUDIENCE", "rag-server")

OPENFGA_URL = os.environ.get("OPENFGA_URL", "http://openfga:8080")
FGA_STORE_NAME = os.environ.get("FGA_STORE_NAME", "prokura")

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://prokura:prokura-dev@postgres:5432/prokura",
)

# Seeded corpus (Drive-shaped) mounted read-only into the container.
CORPUS_DIR = os.environ.get("RAG_CORPUS_DIR", "/deploy/rag/corpus")
MANIFEST_PATH = os.environ.get("RAG_MANIFEST_PATH", "/deploy/rag/manifest.json")

# Retrieval fan-out: how many nearest chunks to authorize before answering.
TOP_K = int(os.environ.get("RAG_TOP_K", "5"))

OTLP_ENDPOINT = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://lgtm:4317")
SERVICE_NAME = os.environ.get("OTEL_SERVICE_NAME", "rag")
