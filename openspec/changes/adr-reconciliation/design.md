# Design — ADR Reconciliation

## Context

`docs/adr/` is empty, yet Prokura has a rich, mostly-settled decision history living in SPEC-REVIEW.md (F1–F9, Q1–Q7), SPEC.md, the OpenSpec capability specs, and per-change design docs. For a reference-architecture-as-product, the *why* must be as legible as the *what*. This change reconciles the scattered decisions into a navigable ADR corpus, **deriving** ADRs from OpenSpec rather than re-litigating anything. It runs on `apply` after M6, so it captures the final decision set including choices made by the two sibling M6 changes.

## Goals / Non-Goals

**Goals**
- A complete, traceable `docs/adr/` meeting the `decision-records` spec: defined format, one ADR per material decision, each citing its source of truth, plus a navigable index.
- A decision inventory that proves completeness against the known set (F1–F9, Q1–Q7, and locked choices without a numbered ID).
- A reusable ADR template for future decisions.

**Non-Goals**
- Not re-deciding anything. OpenSpec stays the working source of truth; ADRs index and narrate it.
- Not the threat model or the control review (sibling changes).
- No code changes.

## Chosen approach: derive from OpenSpec (decided)

Three approaches were weighed; the user chose **derive**:
- **Derive (chosen)** — extract decisions already made across specs/design/SPEC-REVIEW into standalone ADRs that cite back to those artifacts. OpenSpec remains canonical; ADRs are a readable, stable index. Low duplication risk because each ADR points at its source rather than restating requirements.
- *Standalone-as-source (rejected)* — make ADRs canonical going forward. More conventional but duplicates decision content already in OpenSpec and creates two sources that can drift.
- *Audit-only (rejected)* — just a gap report. Leaves `docs/adr/` empty, failing the M6 deliverable.

Consequence of the choice: ADRs are **narrative + citation**, not a second requirements store. The single source of truth stays in OpenSpec; the ADR's job is context, alternatives, and consequences — the reasoning that specs deliberately omit.

## Method

**1. Build the decision inventory first.** Enumerate every material decision from three sources: SPEC-REVIEW.md (F1–F9 findings, Q1–Q7 decisions — each already has options + resolution, ideal ADR raw material), SPEC.md (§9 hard rules, §10 v1 roadmap items that were decided out, §11 trade-offs), and the OpenSpec specs/design docs (locked choices like broker-sole-writer, broker audience, TTL honesty, GitHub App, ntfy notify-only, Mailpit, Python-v0/TS-v1). Each inventory row: decision → source citation → disposition (`new ADR` | `exclude: not architectural` | `open: never settled`).

**2. Classify, don't over-produce.** Not every statement is an ADR. The inventory's exclusion column keeps the corpus to genuinely architectural, alternatives-existed decisions. Implementation details and settled-by-default choices are excluded with a reason, so completeness is checkable without inflating the corpus.

**3. Author ADRs from the inventory.** One ADR per `new ADR` row, using the template. SPEC-REVIEW findings map almost directly (context = the finding, decision = the resolution, alternatives = the options table, consequences = the trade-off noted). Each ADR cites its source; where the source is an OpenSpec spec, the ADR links the requirement it explains.

**4. Handle conflicts and gaps honestly.** If an ADR's decision would contradict its cited source, or a decision turns out never to have been settled, it is flagged as an open item (not written as `accepted`) — the spec forbids papering over unsettled decisions.

**5. Index.** Generate `docs/adr/README.md` from the corpus; mark superseded decisions (e.g. F1's original invalid FGA construct superseded by direct assignment) with proper status and links.

## Numbering and format

- Sequential four-digit numbers; `0000-template.md` is the template. Numbers are stable once assigned (superseding creates a new ADR that links back, never renumbers).
- Format per the `decision-records` spec: number, title, status, context, decision, alternatives, consequences, source citation. Kept lightweight — MADR-style — because the depth already lives in OpenSpec; the ADR adds reasoning and pointer, not a re-spec.

## Key decisions

- **Inventory before authoring.** Writing ADRs ad hoc would make completeness unprovable. The inventory is the artifact that lets the spec's "every material decision has exactly one ADR" be verified.
- **Cite, don't copy.** Each ADR points at its OpenSpec source, preventing the drift that a standalone-source approach would invite and honoring the "OpenSpec is canonical" choice.
- **Run after M6.** Capturing decisions before the security-review and threat-model changes settle theirs would leave the corpus incomplete; sequencing last makes it final.

## Risks / Trade-offs

- **Drift between ADR and cited source over time.** Mitigated by citation (single source of truth stays OpenSpec) and by status marking; a future decision change supersedes rather than edits.
- **Judgment on "material".** The exclusion column with reasons makes the boundary explicit and reviewable, rather than leaving it implicit.
- **Superseded-decision handling.** Several decisions replaced earlier ones (F1 FGA model, F4 GitHub App vs OAuth app); the corpus must show the supersession chain, not just the final state, or the *why* is lost.

## Rollout

None runtime. On archive, `decision-records` joins `openspec/specs/`; `docs/adr/` becomes the durable decision index, cross-referenced by the expanded threat model (mitigation rationales) and the architecture doc.
