"""M9 kill switch — the revoke fan-out (revocation spec).

A single owner-authenticated revoke stops an agent on every path, under the same
owner invariant, and returns a measured time-to-stop:

  1. delete the `can_use` consent tuple            (denies the next hand-out, ~instant)
  2. write a broker deny-list entry                (propagation-free "stop now")
  3. revoke the agent client's Keycloak sessions/  (so it can't re-acquire authority:
     offline+online refresh for THIS user only      DELETE users/{id}/consents/{agent},
                                                     the human's sessions untouched — M9 spike b)
  4. emit a CAEP/SSF revocation signal             (consumable by other systems)

The only thing Prokura cannot shorten is a provider access token already handed
out: the mock provider has no revocation endpoint, so it stays valid until its
bounded TTL (`config.MAX_TTL_SECONDS`). That residual is reported, not hidden."""

import time

import httpx

import config
import consent
import db
import signals
import telemetry
from telemetry import current_traceparent, tracer

_broker_admin_token: tuple[float, str] | None = None


class RevokeError(Exception):
    pass


def _admin_token() -> str:
    """The broker's own client-credentials token (carries realm-management
    manage-users — M9 realm fixture). Cached until near expiry."""
    global _broker_admin_token
    now = time.monotonic()
    if _broker_admin_token and _broker_admin_token[0] > now:
        return _broker_admin_token[1]
    r = httpx.post(
        f"{config.KEYCLOAK_INTERNAL}/realms/{config.REALM}/protocol/openid-connect/token",
        data={"grant_type": "client_credentials", "client_id": config.BROKER_CLIENT_ID,
              "client_secret": config.BROKER_CLIENT_SECRET}, timeout=10.0)
    if r.status_code != 200:
        raise RevokeError(f"broker admin token failed: {r.status_code}")
    body = r.json()
    _broker_admin_token = (now + body.get("expires_in", 60) - 15, body["access_token"])
    return _broker_admin_token[1]


def _user_id(username: str, admin: str) -> str | None:
    r = httpx.get(f"{config.KEYCLOAK_INTERNAL}/admin/realms/{config.REALM}/users",
                  params={"username": username, "exact": "true"},
                  headers={"Authorization": f"Bearer {admin}"}, timeout=10.0)
    if r.status_code != 200 or not r.json():
        return None
    return r.json()[0]["id"]


def _revoke_agent_sessions(agent: str, user: str) -> str:
    """Revoke the agent client's refresh/offline for this user by deleting the
    user's consent for that client. 204 = revoked; 404 = nothing to revoke (the
    agent isn't a consented KC client) — both are a clean stop. The human's own
    sessions are never touched (we do not call users/{id}/logout)."""
    try:
        admin = _admin_token()
        uid = _user_id(user, admin)
        if not uid:
            return "no_user"
        r = httpx.delete(
            f"{config.KEYCLOAK_INTERNAL}/admin/realms/{config.REALM}/users/{uid}/consents/{agent}",
            headers={"Authorization": f"Bearer {admin}"}, timeout=10.0)
        if r.status_code in (204, 404):
            return "revoked" if r.status_code == 204 else "no_consent"
        return f"error_{r.status_code}"
    except (httpx.HTTPError, RevokeError) as e:
        return f"error_{e}"


def kill(agent: str, user: str, provider: str, *, azp: str) -> dict:
    """Per-grant revoke fan-out: delete the `can_use` tuple, write a deny-list
    entry for this grant, and emit the signal. Instant and scoped — the agent's
    delegation (its Keycloak session, its other grants) is untouched. Re-acquiring
    THIS grant is blocked even with a fresh user token, because the deny-list
    denies it before the provider is contacted. Returns timing + honest residual.

    (An agent-wide *kill* that also revokes the agent's Keycloak sessions/offline
    tokens is `kill_agent` — the broader "stop this agent entirely" action, which
    de-delegates it; per-grant revoke deliberately does not, so revoking one grant
    never disturbs the agent's other consented grants.)"""
    with tracer().start_as_current_span("revocation.kill") as span:
        span.set_attribute("prokura.revoke.agent", agent)
        t0 = time.monotonic()
        consent.revoke_consent(agent, user, provider)          # durable consent state
        db.add_deny(agent, user, provider, reason="revoked", azp=azp)  # propagation-free stop
        stop_ms = int((time.monotonic() - t0) * 1000)
        span.set_attribute("prokura.revocation.stop_ms", stop_ms)
        telemetry.record_stop_ms(stop_ms, agent=agent)
        correlation_id = current_traceparent() or "no-trace"
        signals.emit_revocation(agent=agent, user=user, provider=provider,
                                correlation_id=correlation_id)
    return {"stop_ms": stop_ms, "residual_seconds": config.MAX_TTL_SECONDS}


def kill_agent(agent: str, user: str, *, azp: str) -> dict:
    """Agent-wide kill — stop this agent entirely for this user: an agent-wide
    deny entry (all providers), delete every `can_use` tuple the agent holds on
    the user's grants, and revoke the agent client's Keycloak sessions/offline
    tokens for this user (so it cannot re-acquire ANY authority — M9 spike b).
    This de-delegates the agent; the human's own sessions are never touched."""
    with tracer().start_as_current_span("revocation.kill_agent") as span:
        span.set_attribute("prokura.revoke.agent", agent)
        t0 = time.monotonic()
        db.add_deny(agent, user, None, reason="killed", azp=azp)   # agent-wide deny
        for g in db.list_grants(user):                             # drop every tuple it holds
            consent.revoke_consent(agent, user, g["provider"])
        kc = _revoke_agent_sessions(agent, user)                   # can't re-acquire (offline)
        stop_ms = int((time.monotonic() - t0) * 1000)
        span.set_attribute("prokura.revocation.stop_ms", stop_ms)
        telemetry.record_stop_ms(stop_ms, agent=agent)
        correlation_id = current_traceparent() or "no-trace"
        signals.emit_revocation(agent=agent, user=user, provider="*",
                                correlation_id=correlation_id)
    return {"stop_ms": stop_ms, "residual_seconds": config.MAX_TTL_SECONDS, "keycloak": kc}


def unkill(agent: str, user: str, provider: str) -> None:
    """Clear deny entries (e.g. on re-consent), so the grant is usable again —
    both the per-grant entry and any agent-wide (null-provider) kill entry."""
    db.remove_deny(agent, user, provider)
    db.remove_deny(agent, user, None)
