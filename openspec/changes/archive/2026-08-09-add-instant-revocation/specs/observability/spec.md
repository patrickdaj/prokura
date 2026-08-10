# observability — delta (add-instant-revocation / M9)

## ADDED Requirements

### Requirement: Revocation time-to-stop is measured and surfaced
Each revocation SHALL record a `prokura.revocation.stop_ms` measurement — the latency until
the revoked agent can no longer be issued or re-acquire authority — emitted with the revoke's
correlation id so it joins the revoke's trace and audit line. The operator dashboard SHALL
surface a time-to-stop panel, and the emitted CAEP Security Event Token SHALL appear in the
realtime audit stream (Loki-queryable) alongside the metric.

#### Scenario: Time-to-stop appears on the dashboard
- **WHEN** an agent is revoked
- **THEN** a `prokura.revocation.stop_ms` measurement is recorded and shown on the dashboard's
  time-to-stop panel, correlated to the revoke's trace

#### Scenario: The revocation signal is watchable
- **WHEN** a revocation emits its CAEP Security Event Token
- **THEN** the event is present in the realtime audit stream with the revoke's correlation id,
  joinable to the metric and the trace
