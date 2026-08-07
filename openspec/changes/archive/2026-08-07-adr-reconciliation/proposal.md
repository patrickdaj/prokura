## Why

Prokura has made many hard, non-obvious architectural decisions — the SPEC-REVIEW grilling alone produced nine findings (F1–F9) and seven open decisions (Q1–Q7), plus locked choices like broker-brokered grants over broker-run OAuth, the broker's own token audience, TTL honesty, GitHub App over OAuth app, and Python-v0/TypeScript-v1. These decisions and their rationale currently live inside OpenSpec proposals, design docs, and SPEC-REVIEW.md; `docs/adr/` exists but is **empty**. For a project whose product *is* its documentation, that gap means a reader can see *what* was built but must reverse-engineer *why*. This change delivers M6's ADR deliverable: reconcile every material decision into `docs/adr/`.

This is the third of three M6 ("Polish") follow-ups. Its lens is **decision-centric** (is every locked decision recorded, with context and consequences?), complementary to `security-review` (control-centric) and `expand-threat-model` (adversary-centric).

## What Changes

- **New `decision-records` capability spec** stating what the ADR corpus MUST satisfy: a defined ADR format, one ADR per material decision, each ADR traceable to its source (SPEC-REVIEW finding/decision ID or the OpenSpec artifact that made it), and a completeness rule — every locked decision has exactly one accepted ADR.
- **ADRs derived from OpenSpec, not re-decided.** Per the chosen approach, OpenSpec specs/design docs remain the working source of truth; ADRs are the readable, stable index of decisions extracted from them and from SPEC-REVIEW.md. Each ADR cites where the decision actually lives.
- **A decision inventory** mapping every material decision (F1–F9, Q1–Q7, and locked choices not captured as a finding/question) to either a new ADR or an explicit "not an architectural decision" exclusion, so nothing is silently missed.
- **An ADR template and index** (`docs/adr/0000-template.md`, `docs/adr/README.md`) establishing format and navigation for future decisions.
- **No decisions are changed.** This is documentation reconciliation; if the inventory surfaces a decision that was never actually settled, it is flagged for a real decision elsewhere, not resolved here.

## Capabilities

### New Capabilities
- `decision-records`: The required format, coverage, and traceability of the `docs/adr/` corpus — ADR structure, one-ADR-per-decision completeness against the known decision set, and a citation back to the OpenSpec artifact or SPEC-REVIEW ID that is the decision's source of truth.

### Modified Capabilities
<!-- None. This change reads the other specs to extract decisions; it does not change
     their requirements. The decision source of truth stays in OpenSpec; ADRs index it. -->

## Impact

- **Docs**: populates `docs/adr/` — template, index/README, and one ADR per material decision.
- **Specs**: adds `openspec/specs/decision-records/` on archive.
- **Inputs consumed**: SPEC-REVIEW.md (F1–F9, Q1–Q7), SPEC.md, every `openspec/specs/*/spec.md`, archived and active change `design.md`/`proposal.md` files, and the two sibling M6 changes' design rationale.
- **No code changes.**
- **Sequencing**: authored now (planning); the extraction (`apply`) runs after M6 so it captures the full, final decision set — including decisions made by `security-review` and `expand-threat-model`.
