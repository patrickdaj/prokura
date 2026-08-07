"""Human approval via CIBA (M3).

`require_approval()` gates a sensitive action on a human decision: it registers
the structured `{action, params}` payload with the approval service, initiates a
CIBA request whose binding message is the returned reference ID, polls to
completion, and returns the tokens the gated tool needs — the CIBA access token
(proof the ceremony completed) and the single-use action token that carries the
reference ID. Agent-authored prose never reaches the binding message or the human.

Tokens are in-memory, short-lived values: nothing here writes them to disk or
logs them, and transport errors never leak the request body (agent-sdk spec).
"""

from __future__ import annotations

import base64
import json
import time
from collections.abc import Iterable

import httpx

_CIBA_GRANT = "urn:openid:params:grant-type:ciba"


class ApprovalError(Exception):
    """Approval failed for a transport or protocol reason."""


class ApprovalDenied(ApprovalError):
    """The human denied the action."""


class ApprovalTimeout(ApprovalError):
    """The CIBA request expired with no decision."""


def _preferred_username(token: str) -> str:
    seg = token.split(".")[1]
    seg += "=" * (-len(seg) % 4)
    return json.loads(base64.urlsafe_b64decode(seg)).get("preferred_username", "")


def _poll_ciba(c: httpx.Client, token_url: str, auth_req_id: str, interval: int,
               client_id: str, client_secret: str, action: str) -> str:
    """Poll the CIBA token endpoint to completion; return the CIBA access token or
    raise ApprovalDenied / ApprovalTimeout / ApprovalError."""
    while True:  # Keycloak's expiry surfaces as an expired_token error
        tr = c.post(token_url, data={"grant_type": _CIBA_GRANT, "auth_req_id": auth_req_id,
                    "client_id": client_id, "client_secret": client_secret})
        if tr.status_code == 200:
            return tr.json()["access_token"]
        try:
            err = tr.json().get("error", "")
        except ValueError:
            err = tr.text[:120]
        if err in ("authorization_pending", "slow_down"):
            time.sleep(interval)
            continue
        if err == "access_denied":
            raise ApprovalDenied(f"action {action!r} denied")
        if err in ("expired_token", "invalid_grant"):
            raise ApprovalTimeout(f"approval for {action!r} expired")
        raise ApprovalError(f"ciba poll failed: {err}")


def drive_ciba_approval(
    ref: str,
    *,
    base_url: str,
    realm: str,
    client_id: str,
    client_secret: str,
    login_hint: str,
    scopes: Iterable[str] = (),
    requested_expiry: int | None = None,
    action: str = "action",
    http: httpx.Client | None = None,
) -> str:
    """Reactive-approval counterpart of ``require_approval`` (M4).

    When a resource server refuses a sensitive call with an ``approval_required``
    challenge, it has ALREADY registered the real action and returned a reference
    id. The agent does not register anything — it simply drives the
    (client-initiated) CIBA ceremony for that ``ref`` (as the binding message),
    waits for the human's decision, and then retries the action with the
    challenge's action token. Returns the CIBA access token on approval; raises
    ApprovalDenied / ApprovalTimeout / ApprovalError otherwise."""
    owns = http is None
    c = http or httpx.Client(timeout=20.0)
    try:
        scope = " ".join(["openid", "tools-audience", *scopes])
        data = {"client_id": client_id, "client_secret": client_secret,
                "scope": scope, "login_hint": login_hint, "binding_message": ref}
        if requested_expiry:
            data["requested_expiry"] = str(requested_expiry)
        auth = c.post(f"{base_url}/realms/{realm}/protocol/openid-connect/ext/ciba/auth",
                      data=data)
        if auth.status_code != 200:
            raise ApprovalError(f"ciba initiation failed ({auth.status_code})")
        aj = auth.json()
        return _poll_ciba(c, f"{base_url}/realms/{realm}/protocol/openid-connect/token",
                          aj["auth_req_id"], aj.get("interval", 5),
                          client_id, client_secret, action)
    except httpx.HTTPError as e:
        raise ApprovalError(f"approval endpoint unreachable: {e}") from e
    finally:
        if owns:
            c.close()


def require_approval(
    subject_token: str,
    action: str,
    params: dict,
    *,
    scopes: Iterable[str] = (),
    base_url: str,
    realm: str,
    client_id: str,
    client_secret: str,
    approval_url: str,
    login_hint: str | None = None,
    requested_expiry: int | None = None,
    http: httpx.Client | None = None,
) -> dict:
    """Gate `action` on human approval. Returns
    ``{"action_token", "ciba_token"}`` on approval; raises ApprovalDenied /
    ApprovalTimeout / ApprovalError otherwise."""
    login_hint = login_hint or _preferred_username(subject_token)
    owns = http is None
    c = http or httpx.Client(timeout=20.0)
    try:
        # 1. register the structured payload -> reference ID + action token
        reg = c.post(f"{approval_url}/register",
                     headers={"Authorization": f"Bearer {subject_token}"},
                     json={"action": action, "params": params,
                           "scopes": " ".join(scopes)})
        if reg.status_code != 200:
            raise ApprovalError(f"registration failed ({reg.status_code})")
        ref = reg.json()["ref"]
        action_token = reg.json()["action_token"]

        # 2. initiate CIBA with the reference ID as the binding message
        scope = " ".join(["openid", "tools-audience", *scopes])
        data = {"client_id": client_id, "client_secret": client_secret,
                "scope": scope, "login_hint": login_hint, "binding_message": ref}
        if requested_expiry:
            data["requested_expiry"] = str(requested_expiry)
        auth = c.post(f"{base_url}/realms/{realm}/protocol/openid-connect/ext/ciba/auth",
                      data=data)
        if auth.status_code != 200:
            raise ApprovalError(f"ciba initiation failed ({auth.status_code})")
        aj = auth.json()
        auth_req_id, interval = aj["auth_req_id"], aj.get("interval", 5)

        # 3. poll the token endpoint until a decision
        token_url = f"{base_url}/realms/{realm}/protocol/openid-connect/token"
        while True:  # Keycloak's expiry surfaces as an expired_token error
            tr = c.post(token_url, data={"grant_type": _CIBA_GRANT,
                        "auth_req_id": auth_req_id,
                        "client_id": client_id, "client_secret": client_secret})
            if tr.status_code == 200:
                return {"action_token": action_token,
                        "ciba_token": tr.json()["access_token"], "ref": ref}
            err = ""
            try:
                err = tr.json().get("error", "")
            except ValueError:
                err = tr.text[:120]
            if err in ("authorization_pending", "slow_down"):
                time.sleep(interval)
                continue
            if err == "access_denied":
                raise ApprovalDenied(f"action {action!r} denied")
            if err in ("expired_token", "invalid_grant"):
                raise ApprovalTimeout(f"approval for {action!r} expired")
            raise ApprovalError(f"ciba poll failed: {err}")
    except httpx.HTTPError as e:
        raise ApprovalError(f"approval endpoint unreachable: {e}") from e
    finally:
        if owns:
            c.close()
