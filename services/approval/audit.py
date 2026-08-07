"""Realtime approval audit — every register / delegate / decision / consume event
emitted with the flow correlation id (trace id), Loki-queryable and joinable to
the trace. The approvals table is the persisted record."""

import logging

from telemetry import current_traceparent

_log = logging.getLogger("prokura.audit")


def emit(event: str, *, ref=None, user=None, agent=None, action=None, detail=None) -> str:
    correlation_id = current_traceparent() or "no-trace"
    _log.info(
        "approval_audit correlation_id=%s event=%s ref=%s user=%s agent=%s action=%s detail=%s",
        correlation_id, event, ref, user, agent, action, detail,
        extra={"prokura.correlation_id": correlation_id, "prokura.event": event},
    )
    return correlation_id
