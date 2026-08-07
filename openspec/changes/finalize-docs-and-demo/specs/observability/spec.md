## ADDED Requirements

### Requirement: Trace-to-logs correlation jump in the console

The bespoke console SHALL let a user move from a selected trace or span to its
**correlated audit log lines** without leaving the console. When a trace/span carrying
a domain correlation identifier (the token-brokering audit correlation ID or the
human-approval reference ID, per the existing propagation requirement) is selected,
the console SHALL query Loki for that identifier (via the existing same-origin
`/api/loki` proxy) and render the matching audit lines alongside the span detail. This
closes the loop from "what happened" (the trace) to "the audit record of it" (the
logs). Log lines MUST NOT expose secrets or request parameters beyond what the audit
events already contain.

#### Scenario: Jump from a span to its audit logs
- **WHEN** a user selects a span that carries a correlation ID (e.g. a broker issuance
  or an approval decision) in the console
- **THEN** the console fetches and displays the Loki audit lines matching that
  correlation ID, so the trace and its audit record are visible together

#### Scenario: Absent correlation is handled gracefully
- **WHEN** a selected span carries no correlation identifier
- **THEN** the console shows a clear "no correlated logs" state rather than an error
  or an unfiltered log dump
