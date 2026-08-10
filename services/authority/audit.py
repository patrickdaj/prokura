"""Realtime authority-console audit — every login / register read / revoke /
link / topic event emitted with the flow correlation id (trace id), so the
console's actions are Loki-queryable and joinable to the trace. The console
holds no persisted store of its own; its record is the audit stream (and the
downstream broker/approval records it triggers)."""

import logging

from prokura_telemetry import current_trace_id, is_denial, record_decision

_log = logging.getLogger("prokura.audit")


def emit(event: str, *, user=None, agent=None, provider=None, detail=None) -> str:
    trace_id = current_trace_id() or "no-trace"
    # Native trace context joins the line to its trace (Tempo→Loki derived field);
    # no hand-copied correlation id in the text.
    _log.info(
        "authority_audit event=%s user=%s agent=%s provider=%s detail=%s",
        event, user, agent, provider, detail,
        extra={"prokura.event": event},
    )
    record_decision(event, deny=is_denial(event), provider=provider)
    return trace_id
