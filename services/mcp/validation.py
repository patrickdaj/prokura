"""Verify an inbound MCP access token addressed to this resource server
(aud=mcp-server). The M1 audience defense, now on the MCP boundary: a token
minted for anything else (e.g. a broker-audience token) is refused here.

The audience is bound by the mcp-audience client scope, not the RFC 8707
`resource` parameter, which Keycloak does not reflect into `aud` (the documented
gap — see the mcp-authorization spec)."""

import jwt
from jwt import PyJWKClient

import config

_JWKS_URL = f"{config.KEYCLOAK_INTERNAL}/realms/{config.REALM}/protocol/openid-connect/certs"
_jwks_client = PyJWKClient(_JWKS_URL, cache_keys=True)


class TokenInvalid(Exception):
    pass


class WrongAudience(Exception):
    pass


class InsufficientScope(Exception):
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
    if config.MCP_AUDIENCE not in aud:
        raise WrongAudience(f"aud={aud} does not include {config.MCP_AUDIENCE!r}")
    # Scope gate on top of the audience check: aud=mcp-server says the token was
    # minted for this resource; mcp:access says the grant authorizes MCP use.
    if config.MCP_SCOPE not in claims.get("scope", "").split():
        raise InsufficientScope(f"token scope lacks {config.MCP_SCOPE!r}")
    return claims
