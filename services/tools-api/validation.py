"""Verify a bearer token addressed to this resource server (aud=agent-tools-api).
The M1 audience defense: a token minted for anything else is refused here."""

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
    try:
        key = _jwks_client.get_signing_key_from_jwt(token)
        claims = jwt.decode(token, key.key, algorithms=["RS256"],
                            issuer=config.KEYCLOAK_ISSUER, options={"verify_aud": False})
    except jwt.PyJWTError as e:
        raise TokenInvalid(str(e)) from e
    aud = claims.get("aud", [])
    aud = [aud] if isinstance(aud, str) else (aud or [])
    if config.TOOLS_AUDIENCE not in aud:
        raise WrongAudience(f"aud={aud} does not include {config.TOOLS_AUDIENCE!r}")
    return claims
