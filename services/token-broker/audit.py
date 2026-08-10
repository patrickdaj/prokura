"""Issuance/denial audit. Every event is BOTH persisted (Postgres broker_audit)
AND emitted to the telemetry pipeline in realtime with the same correlation id,
so the trail is Loki-queryable within seconds and joinable to the flow's trace
(token-brokering spec: 'Issuance audit log')."""

import logging

import db
from prokura_telemetry import current_trace_id, is_denial, record_decision

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
    """Record an audit event; returns the active trace id (persisted as the row's
    join key). Trace↔log correlation is the native trace context, not a copied id."""
    trace_id = current_trace_id() or "no-trace"
    db.insert_audit(
        correlation_id=trace_id, user_id=user, agent=agent, provider=provider,
        scopes=scopes, ttl=ttl, decision=decision, detail=detail,
    )
    # Realtime emit — the native trace_id/span_id is attached to the record by the
    # OTel logging handler and is the Tempo→Loki join key (derived field), so the
    # line needs no hand-copied correlation id.
    _log.info(
        "broker_audit decision=%s user=%s agent=%s provider=%s scopes=%s ttl=%s detail=%s",
        decision, user, agent, provider, scopes, ttl, detail,
        extra={"prokura.decision": decision, "prokura.provider": provider},
    )
    # Narrate the trace: the same decision as a span event, red on a deny path.
    record_decision(decision, deny=is_denial(decision), provider=provider)
    return trace_id
