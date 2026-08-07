"""Verify an inbound access token addressed to this resource server
(aud=rag-server) — the F2 confused-deputy defense on the RAG boundary.

A token minted for anything else (e.g. an mcp-server token, or a broker-audience
token) is refused here: the retriever authorizes as the end user only when it holds
a token of its OWN audience, never a caller-supplied identity. The end-user FGA
subject is derived from ``preferred_username`` (the stable realm username the broker
and the whole OpenFGA model key on — the token ``sub`` is an opaque UUID; see the
M5 spike finding in design.md)."""

import jwt
from jwt import PyJWKClient

import config

_JWKS_URL = f"{config.KEYCLOAK_INTERNAL}/realms/{config.REALM}/protocol/openid-connect/certs"
_jwks_client = PyJWKClient(_JWKS_URL, cache_keys=True)


class TokenInvalid(Exception):
    pass


class WrongAudience(Exception):
    pass


def verify_bearer(token: str) -> dict:
    """Return the token claims iff the signature, issuer, and audience all check.
    Raises WrongAudience for a foreign-audience token (the F2 defense)."""
    try:
        key = _jwks_client.get_signing_key_from_jwt(token)
        claims = jwt.decode(token, key.key, algorithms=["RS256"],
                            issuer=config.KEYCLOAK_ISSUER, options={"verify_aud": False})
    except jwt.PyJWTError as e:
        raise TokenInvalid(str(e)) from e
    aud = claims.get("aud", [])
    aud = [aud] if isinstance(aud, str) else (aud or [])
    if config.RAG_AUDIENCE not in aud:
        raise WrongAudience(f"aud={aud} does not include {config.RAG_AUDIENCE!r}")
    return claims


def end_user(claims: dict) -> str | None:
    """The FGA subject identity (username), or None if the token carries no user
    (e.g. a service-account / agent-only token — Flow D refuses these)."""
    return claims.get("preferred_username")
