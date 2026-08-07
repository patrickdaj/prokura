# ADR-0015: Mailpit sink for the gated send; Drive-shaped ACLs for RAG

- **Status:** accepted
- **Source of truth:** SPEC-REVIEW Q6; `services/tools-api/` (Mailpit); `deploy/rag/manifest.json`
- **Also records the locked choice:** Mailpit demo sink (Q6).

## Context

'Gated send via Gmail' means the `gmail.send` restricted scope with Google verification friction that every cloner would hit — invisible in the spec.

## Decision

Use **Mailpit** (a local SMTP sink) for the gated `email.send`: zero Google friction, CIBA demos identically, works offline. Give Google a different showcase — the ACL'd RAG corpus is authored **Drive-shaped** (per-doc owner/viewers mirroring a Drive permissions export), so Flow D's tuples mirror real Drive permissions.

## Alternatives considered

- B — Gmail in testing mode: real texture, per-cloner OAuth-consent friction.
- C — a GitHub write action instead of email: only one provider needed, weakens the abstraction milestone.

## Consequences

The whole demo runs offline and reproducibly. Live Google Drive ingestion is a v1 item; the enforcement path is identical.

