"""Issuance/denial audit. Every event is BOTH persisted (Postgres broker_audit)
AND emitted to the telemetry pipeline in realtime with the same correlation id,
so the trail is Loki-queryable within seconds and joinable to the flow's trace
(token-brokering spec: 'Issuance audit log')."""

import logging

import db
from telemetry import current_traceparent

_log = logging.getLogger("prokura.audit")


def emit(
    *,
    decision: str,
    user: str | None = None,
    agent: str | None = None,
    provider: str | None = None,
    scopes: str | None = None,
    ttl: int | None = None,
    detail: str | None = None,
) -> str:
    """Record an audit event; returns the correlation id (the active trace id)."""
    correlation_id = current_traceparent() or "no-trace"
    db.insert_audit(
        correlation_id=correlation_id, user_id=user, agent=agent, provider=provider,
        scopes=scopes, ttl=ttl, decision=decision, detail=detail,
    )
    # Realtime emit — the correlation id (= trace id) is in the line text so it is
    # Loki-queryable and joins to the persisted row AND the flow trace. Trace
    # context is also attached automatically by the OTel logging handler.
    _log.info(
        "broker_audit correlation_id=%s decision=%s user=%s agent=%s "
        "provider=%s scopes=%s ttl=%s detail=%s",
        correlation_id, decision, user, agent, provider, scopes, ttl, detail,
        extra={
            "prokura.correlation_id": correlation_id,
            "prokura.decision": decision,
            "prokura.provider": provider,
        },
    )
    return correlation_id
