"""Provider-token hand-out (M2).

`get_provider_token()` presents a broker-audience token (obtained via
`exchange(..., "token-broker")`) to the Token Broker and returns a short-lived
third-party provider access token. The broker enforces the full chain — audience,
grant, scope subset, per-agent consent — and never returns a refresh token.

Tokens are in-memory, short-lived values: nothing here writes them to disk or
logs them, and transport errors never leak the request body (agent-sdk spec).
"""

from __future__ import annotations

from collections.abc import Iterable

import httpx


class ProviderTokenError(Exception):
    """Hand-out failed for a transport or protocol reason."""


class ConsentDenied(ProviderTokenError):
    """The agent lacks consent (or a grant) for this provider — broker returned 403."""

    def __init__(self, provider: str, detail: str) -> None:
        self.provider = provider
        super().__init__(f"broker denied provider {provider!r}: {detail}")


class ScopeExceeded(ProviderTokenError):
    """Requested scopes exceed the grant's granted scopes — broker returned 403."""

    def __init__(self, provider: str, detail: str) -> None:
        self.provider = provider
        super().__init__(f"requested scopes exceed grant for {provider!r}: {detail}")


def get_provider_token(
    broker_token: str,
    provider: str,
    scopes: Iterable[str] = (),
    *,
    base_url: str,
    http: httpx.Client | None = None,
) -> dict:
    """Return a provider access token for `provider`.

    `broker_token` must be a token whose audience is the broker
    (`exchange(user_token, "token-broker", ...)`). `base_url` is the broker
    service root (e.g. ``http://localhost:8110``).

    Returns ``{"access_token", "token_type", "expires_in", "scope", "provider"}``.
    Raises ScopeExceeded / ConsentDenied on the broker's 403 refusals and
    ProviderTokenError on other failures.
    """
    url = f"{base_url}/v1/tokens/{provider}"
    body = {"scopes": list(scopes)}

    owns_client = http is None
    client = http or httpx.Client(timeout=15.0)
    try:
        resp = client.post(
            url,
            json=body,
            headers={"Authorization": f"Bearer {broker_token}"},
        )
    except httpx.HTTPError as e:  # transport failure — never leak the request
        raise ProviderTokenError(f"broker unreachable: {e}") from e
    finally:
        if owns_client:
            client.close()

    if resp.status_code == 200:
        return resp.json()

    detail = ""
    try:
        detail = resp.json().get("error", "")
    except ValueError:
        detail = resp.text[:200]
    if resp.status_code == 403:
        if "scope" in detail.lower():
            raise ScopeExceeded(provider, detail)
        raise ConsentDenied(provider, detail)
    raise ProviderTokenError(f"hand-out failed ({resp.status_code}): {detail}")
