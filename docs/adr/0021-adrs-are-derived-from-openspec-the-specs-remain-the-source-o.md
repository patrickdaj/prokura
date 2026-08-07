# ADR-0021: ADRs are derived from OpenSpec; the specs remain the source of truth

- **Status:** accepted
- **Source of truth:** `openspec/changes/archive/2026-08-07-adr-reconciliation/` (this change); `openspec/specs/decision-records/spec.md`

## Context

Decisions lived inside OpenSpec proposals/design and SPEC-REVIEW; `docs/adr/` was empty. Duplicating decisions risks two sources of truth that drift.

## Decision

Author ADRs as a **readable, stable index derived from OpenSpec**, not a parallel authority. Each ADR cites where its decision actually lives (a SPEC-REVIEW ID or an OpenSpec artifact). This reconciliation makes no decisions; an apparently-unsettled decision is flagged `open`, not fabricated as `accepted`.

## Alternatives considered

- ADRs as the primary decision record: would compete with OpenSpec and drift.
- No ADRs, decisions stay only in specs: readers can't see 'why' without spelunking.

## Consequences

Readers get the 'why' at a glance; the working source of truth stays in OpenSpec. This ADR records the reconciliation method itself.

