"""RFC 8693 token exchange from inside the console's trust boundary (M8, D2).

The console never forwards the user's session token downstream. It exchanges
that token — as the confidential ``authority-console`` client — into a fresh
token addressed to a specific downstream audience (``token-broker`` or
``approval``). The user's ``authority-ui`` token names ``authority-console`` in
its ``aud`` (mapper in the realm), which is what permits ``authority-console`` to
exchange it.

The exchanged token preserves the acting user (``sub``/``preferred_username`` from
the subject) with ``azp=authority-console``, so downstream the OWNER is the
verified token subject — never a service account acting for nobody, and never an
out-of-band username assertion. Tokens are transient and never logged."""

import httpx

import config
from telemetry import tracer

_GRANT = "urn:ietf:params:oauth:grant-type:token-exchange"
_ACCESS = "urn:ietf:params:oauth:token-type:access_token"

# downstream audience -> the realm client scope whose audience mapper adds it
_AUDIENCE_SCOPE = {
    config.BROKER_AUDIENCE: "broker-audience",
    config.APPROVAL_AUDIENCE: "approval-audience",
}


class ExchangeError(Exception):
    pass


def exchange_for(subject_token: str, audience: str) -> str:
    """Exchange the signed-in user's token for one addressed to ``audience``.
    Returns the raw access token string."""
    data = {
        "grant_type": _GRANT,
        "client_id": config.EXCHANGE_CLIENT_ID,
        "client_secret": config.EXCHANGE_CLIENT_SECRET,
        "subject_token": subject_token,
        "subject_token_type": _ACCESS,
        "audience": audience,
    }
    scope = _AUDIENCE_SCOPE.get(audience)
    if scope:
        data["scope"] = scope
    with tracer().start_as_current_span("keycloak.authority_exchange") as span:
        span.set_attribute("prokura.exchange.audience", audience)
        r = httpx.post(
            f"{config.KEYCLOAK_INTERNAL}/realms/{config.REALM}/protocol/openid-connect/token",
            data=data, timeout=15.0,
        )
    if r.status_code != 200:
        raise ExchangeError(f"exchange for aud={audience} failed: {r.status_code} {r.text[:200]}")
    return r.json()["access_token"]
