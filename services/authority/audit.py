"""Realtime authority-console audit — every login / register read / revoke /
link / topic event emitted with the flow correlation id (trace id), so the
console's actions are Loki-queryable and joinable to the trace. The console
holds no persisted store of its own; its record is the audit stream (and the
downstream broker/approval records it triggers)."""

import logging

from telemetry import current_traceparent

_log = logging.getLogger("prokura.audit")


def emit(event: str, *, user=None, agent=None, provider=None, detail=None) -> str:
    correlation_id = current_traceparent() or "no-trace"
    _log.info(
        "authority_audit correlation_id=%s event=%s user=%s agent=%s provider=%s detail=%s",
        correlation_id, event, user, agent, provider, detail,
        extra={"prokura.correlation_id": correlation_id, "prokura.event": event},
    )
    return correlation_id
