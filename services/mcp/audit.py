"""MCP audit — structured, realtime-to-Loki events for every tool decision.

The MCP server holds no state (no DB), so audit is emit-only: each line carries
the correlation id (= active trace id) in its text so it is Loki-queryable within
seconds and joins to the flow's trace and the broker/approval audit rows that
share the same traceparent."""

import logging

from telemetry import current_traceparent

_log = logging.getLogger("prokura.audit")


def emit(*, decision: str, user: str | None = None, agent: str | None = None,
         tool: str | None = None, detail: str | None = None) -> str:
    correlation_id = current_traceparent() or "no-trace"
    _log.info(
        "mcp_audit correlation_id=%s decision=%s user=%s agent=%s tool=%s detail=%s",
        correlation_id, decision, user, agent, tool, detail,
        extra={
            "prokura.correlation_id": correlation_id,
            "prokura.decision": decision,
            "prokura.tool": tool,
        },
    )
    return correlation_id
