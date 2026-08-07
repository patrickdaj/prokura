"""Provider capability manifest (token-brokering spec). Each provider declares
whether it supports refresh and cryptographic scope narrowing; enforcement is
per-capability. ``acme`` is the offline mock (a second Keycloak realm, proven by
the M2 spike). GitHub/Google are documented bring-your-own-credentials entries."""

# residual_ttl_note feeds the threat model's TTL-honesty table. The broker caps
# its own hand-out at MAX_TTL_SECONDS regardless; these are the provider-side
# residual lifetimes.
MANIFEST = {
    "acme": {
        "supports_refresh": True,
        "supports_scope_narrowing": False,
        # Backchannel host (keycloak:8080) — the spike proved the URL split.
        "token_url": "http://keycloak:8080/realms/acme/protocol/openid-connect/token",
        "client_id": "prokura-broker-idp",
        "client_secret": "acme-idp-dev-secret",
        "residual_ttl_note": "mock realm; acme access-token lifespan 3600s",
    },
    # --- Bring-your-own-credentials (documented, not wired in v0) ---
    "github": {
        "supports_refresh": True,
        "supports_scope_narrowing": False,
        "byo": True,
        "residual_ttl_note": "GitHub App user token ~8h residual",
    },
    "google": {
        "supports_refresh": True,
        "supports_scope_narrowing": False,
        "byo": True,
        "residual_ttl_note": "Google access token ~1h residual",
    },
}


def get(provider: str) -> dict | None:
    return MANIFEST.get(provider)


def is_available(provider: str) -> bool:
    """A provider is usable in v0 only if it is wired (has a token_url), i.e. not
    a byo-only documented entry."""
    p = MANIFEST.get(provider)
    return bool(p and p.get("token_url"))
