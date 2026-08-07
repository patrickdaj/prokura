# per-agent-consent

## Purpose

Per-agent grant authorization via OpenFGA (decisions F1-A, Q3-B). This is a security gate, not a convenience: with dynamic client registration enabled for MCP, any client can register itself — the consent tuple is what stands between a registered client and the user's grants.

## Requirements

### Requirement: Valid direct-assignment FGA model
The OpenFGA authorization model SHALL define grant usage as a direct assignment (`define can_use: [agent]`) with no self-referential or cross-object-join constructs. The model MUST load successfully in OpenFGA. (Replaces the invalid `[agent] and operator from can_use` construct — F1.)

#### Scenario: Model loads
- **WHEN** `model.fga` is written to the OpenFGA store at stack startup
- **THEN** OpenFGA accepts the model and check queries against it succeed

### Requirement: Consent screen writes the tuple
An agent SHALL gain access to a grant only after the user approves it on a per-agent consent screen ("Allow <agent> to use your <provider> grant — [scopes]"), rendered in an authenticated session. Approval writes the `agent:{id} can_use grant:{user}/{provider}` tuple; nothing else creates consent.

#### Scenario: Approval grants exactly one agent
- **WHEN** the user approves agent `summarizer` for their GitHub grant
- **THEN** `summarizer` passes the broker's FGA check for that grant and every other agent still fails it

#### Scenario: No implicit consent
- **WHEN** a grant is created and no consent has been given to any agent
- **THEN** no agent passes the FGA check for that grant

### Requirement: Broker is the sole tuple writer with a write-time invariant
Only the Token Broker SHALL write `can_use` tuples, and it MUST refuse any write where the agent's `operator` is not the grant's `owner`. This moves the operator==owner property from the FGA model into broker code; the threat model MUST document the broker as a trusted tuple writer.

#### Scenario: Cross-user write refused
- **WHEN** a tuple write is attempted authorizing an agent operated by user A on a grant owned by user B
- **THEN** the broker refuses the write and logs it

### Requirement: Consent revocation
The user SHALL be able to revoke a single agent's access to a grant without revoking the grant itself. Revocation deletes the tuple and takes effect on the next broker request.

#### Scenario: Revoked agent loses access
- **WHEN** the user revokes agent `summarizer`'s consent for their GitHub grant and `summarizer` then requests a token
- **THEN** the broker responds 403 while other consented agents remain unaffected
