"""Grant lifecycle: import the Keycloak-brokered refresh credential into OpenBao,
refresh against the provider on hand-out, and revoke. Long-lived credentials
exist ONLY in OpenBao (grant-acquisition + token-brokering specs); they are held
in broker memory only transiently during a refresh and never returned or logged.
"""

import hvac
import httpx

import config
import db
import providers
from prokura_telemetry import tracer

_bao = hvac.Client(url=config.OPENBAO_URL, token=config.OPENBAO_TOKEN)
_MOUNT = "secret"


class GrantError(Exception):
    pass


_TOKEN_EXCHANGE = "urn:ietf:params:oauth:grant-type:token-exchange"


def _bao_path(user: str, provider: str) -> str:
    return f"grants/{user}/{provider}"


def _exchange_for_read_token(subject_token: str) -> str:
    """Exchange the incoming token (as the confidential token-broker client) into
    a token whose ``azp`` is the broker, so token-broker's ``broker-read-token``
    scope applies and the result carries resource_access.broker.roles=[read-token].
    This keeps the stored-token read capability inside the broker's trust boundary
    — the agent never gets it."""
    with tracer().start_as_current_span("keycloak.broker_exchange"):
        r = httpx.post(
            f"{config.KEYCLOAK_INTERNAL}/realms/{config.REALM}/protocol/openid-connect/token",
            data={
                "grant_type": _TOKEN_EXCHANGE,
                "client_id": config.BROKER_CLIENT_ID,
                "client_secret": config.BROKER_CLIENT_SECRET,
                "subject_token": subject_token,
                "subject_token_type": "urn:ietf:params:oauth:token-type:access_token",
                # No audience: issues a token for the broker client itself, so
                # azp=token-broker and its broker-read-token scope applies.
            },
            timeout=15.0,
        )
    if r.status_code != 200:
        raise GrantError(f"broker read-token exchange failed: {r.status_code} {r.text[:200]}")
    return r.json()["access_token"]


def import_grant(access_token: str, user: str, provider: str) -> dict:
    """Retrieve the stored provider token from Keycloak's broker endpoint and
    import the long-lived credential into OpenBao. The broker first exchanges the
    incoming token for a read-token-scoped token (see _exchange_for_read_token)."""
    if not providers.is_available(provider):
        raise GrantError(f"provider {provider!r} is not wired in this deployment")

    read_token = _exchange_for_read_token(access_token)
    with tracer().start_as_current_span("keycloak.broker.retrieve_token") as span:
        span.set_attribute("prokura.provider", provider)
        r = httpx.get(
            f"{config.KEYCLOAK_INTERNAL}/realms/{config.REALM}/broker/{provider}/token",
            headers={"Authorization": f"Bearer {read_token}"},
            timeout=15.0,
        )
    if r.status_code != 200:
        raise GrantError(f"stored-token retrieval failed: {r.status_code} {r.text[:200]}")
    stored = r.json()
    refresh = stored.get("refresh_token")
    credential = refresh or stored.get("access_token")
    if not credential:
        raise GrantError("no importable credential in stored token")
    scopes = stored.get("scope", "")

    with tracer().start_as_current_span("openbao.write_grant") as span:
        span.set_attribute("prokura.bao.path", _bao_path(user, provider))
        _bao.secrets.kv.v2.create_or_update_secret(
            path=_bao_path(user, provider),
            secret={
                "credential": credential,
                "kind": "refresh_token" if refresh else "access_token",
                "scopes": scopes,
            },
            mount_point=_MOUNT,
        )
    db.record_grant(user, provider, scopes)
    return {"provider": provider, "scopes": scopes, "has_refresh": bool(refresh)}


def _read_credential(user: str, provider: str) -> dict:
    with tracer().start_as_current_span("openbao.read_grant") as span:
        span.set_attribute("prokura.bao.path", _bao_path(user, provider))
        resp = _bao.secrets.kv.v2.read_secret_version(
            path=_bao_path(user, provider), mount_point=_MOUNT, raise_on_deleted_version=False
        )
    return resp["data"]["data"]


def issue_provider_token(user: str, provider: str) -> dict:
    """Refresh against the provider and return a fresh access token, capped at
    MAX_TTL_SECONDS. Never returns a refresh token."""
    manifest = providers.get(provider)
    if not manifest or not manifest.get("token_url"):
        raise GrantError(f"provider {provider!r} not available")
    cred = _read_credential(user, provider)
    if cred["kind"] != "refresh_token":
        # No refresh available; hand out the stored access token as-is (capped).
        return {"access_token": cred["credential"], "expires_in": config.MAX_TTL_SECONDS,
                "scope": cred.get("scopes", "")}

    with tracer().start_as_current_span("provider.refresh") as span:
        span.set_attribute("prokura.provider", provider)
        r = httpx.post(manifest["token_url"], data={
            "grant_type": "refresh_token",
            "refresh_token": cred["credential"],
            "client_id": manifest["client_id"],
            "client_secret": manifest["client_secret"],
        }, timeout=15.0)
    if r.status_code != 200:
        raise GrantError(f"provider refresh failed: {r.status_code} {r.text[:120]}")
    body = r.json()

    # Persist a rotated refresh token if the provider returned a new one, so the
    # next hand-out doesn't fail (Keycloak rotates refresh tokens on refresh).
    rotated = body.get("refresh_token")
    if rotated and rotated != cred["credential"]:
        with tracer().start_as_current_span("openbao.rotate_grant") as span:
            span.set_attribute("prokura.bao.path", _bao_path(user, provider))
            _bao.secrets.kv.v2.create_or_update_secret(
                path=_bao_path(user, provider),
                secret={"credential": rotated, "kind": "refresh_token",
                        "scopes": cred.get("scopes", "")},
                mount_point=_MOUNT,
            )

    ttl = min(int(body.get("expires_in", config.MAX_TTL_SECONDS)), config.MAX_TTL_SECONDS)
    return {
        "access_token": body["access_token"],
        "expires_in": ttl,
        # Honest scope reporting (non-narrowing provider): report actual scopes.
        "scope": body.get("scope", cred.get("scopes", "")),
    }


def revoke_grant(user: str, provider: str) -> None:
    with tracer().start_as_current_span("openbao.delete_grant"):
        _bao.secrets.kv.v2.delete_metadata_and_all_versions(
            path=_bao_path(user, provider), mount_point=_MOUNT
        )
    db.delete_grant(user, provider)


def grant_exists(user: str, provider: str) -> bool:
    return db.get_grant(user, provider) is not None
