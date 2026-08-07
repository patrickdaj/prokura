"""Bearer-token validation for the hand-out chain (token-brokering spec, steps
1-3): JWKS signature, ``aud = token-broker``, and requested-scope subset. Step 4
(the OpenFGA ``can_use`` check) lives in consent.py."""

import jwt
from jwt import PyJWKClient

import config

# JWKS fetched over the internal host; PyJWKClient caches keys.
_JWKS_URL = f"{config.KEYCLOAK_INTERNAL}/realms/{config.REALM}/protocol/openid-connect/certs"
_jwks_client = PyJWKClient(_JWKS_URL, cache_keys=True)


class TokenInvalid(Exception):
    """Signature/issuer/expiry failure — 401."""


class WrongAudience(Exception):
    """Token is valid but not minted for the broker — 403."""


def verify_signature(token: str) -> dict:
    """Validate signature + issuer + expiry only. Returns claims. Raises
    TokenInvalid (401). Used for the consent endpoint (an authenticated user
    session, any audience)."""
    try:
        signing_key = _jwks_client.get_signing_key_from_jwt(token)
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=config.KEYCLOAK_ISSUER,
            options={"verify_aud": False},
        )
    except jwt.PyJWTError as e:
        raise TokenInvalid(str(e)) from e


def verify_bearer(token: str) -> dict:
    """Validate signature + issuer + expiry + audience. Returns claims.

    Raises TokenInvalid (401) on signature/issuer/expiry problems and
    WrongAudience (403) when ``aud`` does not include the broker audience.
    """
    claims = verify_signature(token)
    aud = claims.get("aud", [])
    aud = [aud] if isinstance(aud, str) else (aud or [])
    if config.BROKER_AUDIENCE not in aud:
        raise WrongAudience(f"aud={aud} does not include {config.BROKER_AUDIENCE!r}")
    return claims


def scopes_subset(requested: list[str], granted: str) -> bool:
    """True iff every requested scope is within the grant's granted scopes.
    An empty request means 'all granted scopes'."""
    if not requested:
        return True
    granted_set = set(granted.split())
    return set(requested).issubset(granted_set)
