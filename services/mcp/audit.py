"""MCP audit — structured, realtime-to-Loki events for every tool decision.

The MCP server holds no state (no DB), so audit is emit-only: each line carries
the correlation id (= active trace id) in its text so it is Loki-queryable within
seconds and joins to the flow's trace and the broker/approval audit rows that
share the same traceparent."""

import logging

from prokura_telemetry import current_trace_id, is_denial, record_decision

_log = logging.getLogger("prokura.audit")


def emit(*, decision: str, user: str | None = None, agent: str | None = None,
         tool: str | None = None, detail: str | None = None) -> str:
    trace_id = current_trace_id() or "no-trace"
    # Native trace context joins the line to its trace (Tempo→Loki derived field);
    # no hand-copied correlation id in the text.
    _log.info(
        "mcp_audit decision=%s user=%s agent=%s tool=%s detail=%s",
        decision, user, agent, tool, detail,
        extra={"prokura.decision": decision, "prokura.tool": tool},
    )
    record_decision(decision, deny=is_denial(decision), tool=tool)
    return trace_id
