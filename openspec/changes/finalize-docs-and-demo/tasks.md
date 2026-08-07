# Tasks: finalize-docs-and-demo (M6, 4th of four)

Runs on `apply` **after** security-review → expand-threat-model → adr-reconciliation
(the architecture doc references their outputs; SPEC.md retires here). Planning-only
now; findings/content are produced when applied.

## 1. Consolidated architecture doc

- [ ] 1.1 Write `docs/architecture.md`: components, the four flows (A delegation, B
  brokering, C approval, D RAG) + the MCP authorization surface, the TCB diagram —
  referencing (not duplicating) the threat model, ADRs, and security baseline.
- [ ] 1.2 Add the **Roadmap / v1** section, migrating the SPEC.md §10 / SPEC-REVIEW
  forward-looking items (SPIFFE/SPIRE, RAR-in-Keycloak, `act`-chains, real
  Google/GitHub providers end-to-end, TypeScript SDK, XAA/ID-JAG, CIBA push).
- [ ] 1.3 Mark `SPEC.md` superseded (banner → `docs/architecture.md`); keep for
  history. Verify no remaining doc treats SPEC.md as the source of truth.

## 2. README quickstart

- [ ] 2.1 5-minute quickstart: clone → `docker-compose up` → drive the headline MCP
  demo → watch it in the console, with the non-production framing (Q1) and Nango
  prior-art credit (Q7).

## 3. Demo capture

- [ ] 3.1 Record the headline MCP flow (discover/DCR → login → consent → brokered
  token → reactive approval → FGA-filtered RAG) as a gif/video, driven by the scripted
  flow the smoke tests use; embed it (README/docs). Verify it plays and matches the
  live flow.

## 4. Console trace→logs jump (observability delta)

- [ ] 4.1 On the span-detail view, when a span carries a correlation ID (broker audit
  correlation ID / approval reference ID), add a control that queries `/api/loki` for
  that ID and renders the matching audit lines inline. Reuse the existing proxy — no
  backend change.
- [ ] 4.2 Graceful "no correlated logs" empty state when a span has no correlation ID;
  never an error or an unfiltered dump. Verify both paths in a real browser (screenshot).

## 5. Verify + wrap

- [ ] 5.1 Fresh-clone check: `docker-compose up`, follow the README quickstart verbatim,
  confirm the demo runs and the console trace→logs jump works — **by looking**, not by
  asserting APIs alone.
- [ ] 5.2 Confirm architecture.md is internally consistent with the final threat model,
  ADRs, and security-review findings; SPEC.md superseded. Archive is the next action.
