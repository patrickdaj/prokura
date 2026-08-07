# token-brokering (delta)

Amends the audit requirement: the audit trail becomes watchable live, not only persisted.

## MODIFIED Requirements

### Requirement: Issuance audit log
Every token issuance and every denial SHALL be audit-logged with `{user, agent (azp), provider, scopes, ttl}` and a correlation ID linking related broker, Keycloak, and approval events. In addition to the persisted record, every audit event SHALL be emitted to the telemetry pipeline in realtime as it occurs, carrying the same correlation ID as the persisted record, so the audit trail is watchable live (Loki-queryable) and joinable to the flow's distributed trace.

#### Scenario: Audit on issuance
- **WHEN** a provider token is issued
- **THEN** an audit record exists containing user, agent, provider, scopes, ttl, and a correlation ID

#### Scenario: Audit event emitted in realtime
- **WHEN** a token issuance or denial occurs
- **THEN** an audit event with the same correlation ID as the persisted record is queryable in the log backend within seconds, without waiting for any batch export
