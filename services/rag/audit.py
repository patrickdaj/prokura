"""RAG audit — structured, realtime-to-Loki events for every retrieval decision.

The retriever holds no audit DB (the vector store is not an audit trail), so audit
is emit-only: each ``rag_audit`` line carries the correlation id (= active trace id)
in its text so it is Loki-queryable within seconds and joins to the flow's trace and
the mcp/broker audit that share the same traceparent.

Invariant: audit records the DECISION shape (querying user, candidate count, allowed
count, decision) — NEVER document content. Non-leakage is a property of the audit
trail too."""

import logging

from prokura_telemetry import current_trace_id, is_denial, record_decision

_log = logging.getLogger("prokura.audit")


def emit(*, decision: str, user: str | None = None, agent: str | None = None,
         candidates: int | None = None, allowed: int | None = None,
         detail: str | None = None) -> str:
    trace_id = current_trace_id() or "no-trace"
    # Native trace context joins the line to its trace (Tempo→Loki derived field);
    # no hand-copied correlation id in the text.
    _log.info(
        "rag_audit decision=%s user=%s agent=%s candidates=%s allowed=%s detail=%s",
        decision, user, agent, candidates, allowed, detail,
        extra={"prokura.decision": decision},
    )
    record_decision(decision, deny=is_denial(decision),
                    candidates=candidates, allowed=allowed)
    return trace_id
