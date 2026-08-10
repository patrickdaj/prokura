"""Realtime approval audit — every register / delegate / decision / consume event
emitted with the flow correlation id (trace id), Loki-queryable and joinable to
the trace. The approvals table is the persisted record."""

import logging

from prokura_telemetry import current_trace_id, is_denial, record_decision

_log = logging.getLogger("prokura.audit")


def emit(event: str, *, ref=None, user=None, agent=None, action=None, detail=None) -> str:
    trace_id = current_trace_id() or "no-trace"
    # Native trace context joins the line to its trace (Tempo→Loki derived field);
    # no hand-copied correlation id in the text.
    _log.info(
        "approval_audit event=%s ref=%s user=%s agent=%s action=%s detail=%s",
        event, ref, user, agent, action, detail,
        extra={"prokura.event": event},
    )
    # On the CIBA background leg the request span is gone; record_decision then
    # no-ops (non-recording span) — §3.4 gives those emits a linked span instead.
    record_decision(event, deny=is_denial(event), ref=ref, action=action)
    return trace_id
