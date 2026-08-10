"""M9 CAEP / Shared Signals emitter (revocation spec).

On a kill, the broker emits a signed Security Event Token (RFC 8417) carrying a
CAEP `session-revoked` event, so revocation is a signal other systems can consume
— not merely an internal tuple delete. Demo-grade: a single in-memory stream
(subscribers poll `GET /ssf/stream`) and the same event on the realtime audit
stream (Loki-queryable, joinable to the revoke trace). Signing is HS256 with a
broker-held key (a proper multi-receiver RS256/JWKS deployment is out of demo
scope, stated honestly in the residual register)."""

import logging
import secrets
import time

import jwt

import config

_log = logging.getLogger("prokura.audit")

CAEP_SESSION_REVOKED = (
    "https://schemas.openid.net/secevent/caep/event-type/session-revoked"
)

# Demo-grade in-memory stream (bounded). A restart drops the live buffer; the SET
# also lands in the durable audit stream, so the signal is not lost, only the push.
_STREAM: list[dict] = []
_MAX = 200


def _key() -> str:
    return config.SSF_SIGNING_SECRET


def build_set(agent: str, user: str, provider: str, correlation_id: str) -> str:
    now = int(time.time())
    payload = {
        "iss": config.KEYCLOAK_ISSUER,
        "iat": now,
        "jti": secrets.token_hex(12),
        "aud": "prokura-ssf-receivers",
        "sub_id": {"format": "opaque", "id": f"agent:{agent}/user:{user}"},
        "events": {
            CAEP_SESSION_REVOKED: {
                "subject": {"agent": agent, "user": user, "provider": provider},
                "event_timestamp": now * 1000,
                "reason": "revoked",
            }
        },
        "prokura.correlation_id": correlation_id,
    }
    return jwt.encode(payload, _key(), algorithm="HS256")


def emit_revocation(*, agent: str, user: str, provider: str, correlation_id: str) -> str:
    token = build_set(agent, user, provider, correlation_id)
    _STREAM.append({"ts": int(time.time()), "type": "session-revoked",
                    "agent": agent, "user": user, "provider": provider, "set": token})
    if len(_STREAM) > _MAX:
        del _STREAM[: len(_STREAM) - _MAX]
    # Realtime audit line so the signal is watchable + joinable to the trace.
    _log.info(
        "broker_signal correlation_id=%s event=session-revoked agent=%s user=%s provider=%s",
        correlation_id, agent, user, provider,
        extra={"prokura.correlation_id": correlation_id, "prokura.event": "session-revoked"},
    )
    return token


def stream(since: int = 0) -> list[dict]:
    """Events with ts >= since — the demo SSF poll transmitter."""
    return [e for e in _STREAM if e["ts"] >= since]
