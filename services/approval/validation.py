"""Verify a prokura-realm bearer token (signature + issuer + expiry). Used to
authenticate the human in the approval UI and to check the CIBA token's subject
at consume time."""

import jwt
from jwt import PyJWKClient

import config

_JWKS_URL = f"{config.KEYCLOAK_INTERNAL}/realms/{config.REALM}/protocol/openid-connect/certs"
_jwks_client = PyJWKClient(_JWKS_URL, cache_keys=True)


class TokenInvalid(Exception):
    pass


def verify_signature(token: str) -> dict:
    try:
        key = _jwks_client.get_signing_key_from_jwt(token)
        return jwt.decode(token, key.key, algorithms=["RS256"],
                          issuer=config.KEYCLOAK_ISSUER, options={"verify_aud": False})
    except jwt.PyJWTError as e:
        raise TokenInvalid(str(e)) from e
