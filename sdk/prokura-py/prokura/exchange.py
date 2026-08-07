"""RFC 8693 delegated token exchange.

`exchange()` turns a user's token into a token addressed to a specific audience,
attributable to user-via-agent (sub=user, azp=agent). Two audiences matter in
Prokura: `agent-tools-api` (tool calls) and `token-broker` (F2-A — the broker
rejects any other aud). Keycloak surfaces an audience only when the matching
audience client scope is requested, so the SDK maps audience → that scope.

Tokens are in-memory, short-lived values: nothing here writes them to disk or
logs them (agent-sdk spec, "never persists tokens").
"""

from __future__ import annotations

from collections.abc import Iterable

import httpx

_GRANT = "urn:ietf:params:oauth:grant-type:token-exchange"
_ACCESS = "urn:ietf:params:oauth:token-type:access_token"

# audience -> the realm client scope whose audience mapper adds that aud
_AUDIENCE_SCOPE = {
    "token-broker": "broker-audience",
    "agent-tools-api": "tools-audience",
}


class ExchangeError(Exception):
    """Token exchange failed for a transport or protocol reason."""


class ExchangeDenied(ExchangeError):
    """Keycloak refused the exchange for the requested audience (no permission)."""

    def __init__(self, audience: str, detail: str) -> None:
        self.audience = audience
        super().__init__(f"exchange denied for audience {audience!r}: {detail}")


def exchange(
    subject_token: str,
    audience: str,
    scopes: Iterable[str] = (),
    *,
    base_url: str,
    realm: str,
    client_id: str,
    client_secret: str,
    http: httpx.Client | None = None,
) -> str:
    """Exchange `subject_token` for an access token addressed to `audience`.

    Returns the raw access token string. Raises ExchangeDenied if the client
    is not permitted for the audience, ExchangeError on other failures.
    """
    requested = list(scopes)
    aud_scope = _AUDIENCE_SCOPE.get(audience)
    if aud_scope:
        requested.append(aud_scope)

    data = {
        "grant_type": _GRANT,
        "client_id": client_id,
        "client_secret": client_secret,
        "subject_token": subject_token,
        "subject_token_type": _ACCESS,
        "audience": audience,
    }
    if requested:
        data["scope"] = " ".join(requested)
    url = f"{base_url}/realms/{realm}/protocol/openid-connect/token"

    owns_client = http is None
    client = http or httpx.Client(timeout=15.0)
    try:
        resp = client.post(url, data=data)
    except httpx.HTTPError as e:  # transport failure — never leak `data`
        raise ExchangeError(f"token endpoint unreachable: {e}") from e
    finally:
        if owns_client:
            client.close()

    if resp.status_code == 200:
        return resp.json()["access_token"]

    detail = ""
    try:
        detail = resp.json().get("error_description") or resp.json().get("error", "")
    except ValueError:
        detail = resp.text[:200]
    # KC denies un-permitted audiences with access_denied / "audience not available"
    if resp.status_code in (400, 403) and (
        "audience" in detail.lower() or resp.status_code == 403
    ):
        raise ExchangeDenied(audience, detail)
    raise ExchangeError(f"exchange failed ({resp.status_code}): {detail}")
