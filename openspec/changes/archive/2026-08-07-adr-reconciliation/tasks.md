# Tasks — ADR Reconciliation

> Executed on `apply`, **after M6** (captures the final decision set, including the
> two sibling M6 changes). Derives ADRs from OpenSpec; changes no decisions.

## 1. Template and skeleton

- [x] 1.1 Write `docs/adr/0000-template.md` with the fields required by the `decision-records` spec (number, title, status, context, decision, alternatives, consequences, source citation)
- [x] 1.2 Create `docs/adr/README.md` skeleton (index table: number, title, status)

## 2. Decision inventory

- [x] 2.1 Extract decisions from SPEC-REVIEW.md: F1–F9 findings and Q1–Q7 decisions, each with its options and resolution
- [x] 2.2 Extract decisions from SPEC.md: §9 hard rules, §10 items decided out for v1, §11 acknowledged trade-offs
- [x] 2.3 Extract locked choices from OpenSpec specs/design not tied to a numbered finding (broker-sole-writer + operator==owner, broker token audience, TTL honesty/re-issuance interval, GitHub App vs OAuth app, grant via Keycloak brokering vs broker-run OAuth, ntfy notify-only, Mailpit demo sink, Python-v0/TS-v1, MCP-first vs LangChain)
- [x] 2.4 Add decisions settled by the sibling M6 changes (security-baseline invariants, threat-model residual acceptances)
- [x] 2.5 Build the inventory table: decision → source citation → disposition (`new ADR` | `exclude: not architectural` | `open: never settled`); give a reason for every exclusion

## 3. Author ADRs

- [x] 3.1 For each `new ADR` row, write one ADR from the template; for SPEC-REVIEW rows map context=finding, decision=resolution, alternatives=options table, consequences=trade-off
- [x] 3.2 Add a resolving source citation to each ADR (SPEC-REVIEW ID or `openspec/specs|changes/...` path); where the source is a spec, link the requirement the ADR explains
- [x] 3.3 Assign stable sequential numbers; do not split one decision across ADRs or merge unrelated decisions

## 4. Supersession and conflicts

- [x] 4.1 Model supersession chains (e.g. F1 original invalid FGA construct → direct assignment; F4 OAuth app → GitHub App) as superseded ADRs linking to their replacements, not a single final-state note
- [x] 4.2 Flag any ADR whose decision would contradict its cited source as an open item; do NOT mark it `accepted`
- [x] 4.3 Flag any inventoried decision that was never actually settled as `open` for resolution in its proper venue; create no `accepted` ADR for it

## 5. Index and verify

- [x] 5.1 Populate `docs/adr/README.md` from the corpus (every ADR with current status; superseded visibly marked)
- [x] 5.2 Verify completeness against the `decision-records` spec: every F1–F9, Q1–Q7, and listed locked choice maps to exactly one accepted ADR or a reasoned exclusion
- [x] 5.3 Verify traceability: every ADR citation resolves to an existing source; no dangling references
- [x] 5.4 Cross-link: threat-model mitigation rationales → their ADRs; note ADRs the future architecture doc should reference
