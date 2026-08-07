# Tasks: finalize-docs-and-demo (M6, 4th of four)

Runs on `apply` **after** security-review → expand-threat-model → adr-reconciliation
(the architecture doc references their outputs; SPEC.md retires here). Planning-only
now; findings/content are produced when applied.

## 1. Consolidated architecture doc

- [x] 1.1 Write `docs/architecture.md`: components, the four flows (A delegation, B
  brokering, C approval, D RAG) + the MCP authorization surface, the TCB diagram —
  referencing (not duplicating) the threat model, ADRs, and security baseline.
- [x] 1.2 Add the **Roadmap / v1** section, migrating the SPEC.md §10 / SPEC-REVIEW
  forward-looking items (SPIFFE/SPIRE, RAR-in-Keycloak, `act`-chains, real
  Google/GitHub providers end-to-end, TypeScript SDK, XAA/ID-JAG, CIBA push).
- [x] 1.3 Mark `SPEC.md` superseded (banner → `docs/architecture.md`); keep for
  history. Verify no remaining doc treats SPEC.md as the source of truth.

## 2. README quickstart

- [x] 2.1 5-minute quickstart: clone → `docker-compose up` → drive the headline MCP
  demo → watch it in the console, with the non-production framing (Q1) and Nango
  prior-art credit (Q7).

## 3. Demo — show it being used

- [x] 3.1 A **runnable, narrated demo** (`demo/run_demo.py`) that a person launches and
  *watches*: a real MCP client connects (discover/DCR → login → tools) and drives the
  whole chain — consent-gated token (+ no-passthrough proof) → reactive human approval
  → FGA-filtered RAG (alice retrieves the protected doc, bob provably cannot) — printing
  each step and the real values live. This *shows the system being used* rather than
  punting to `pytest`. Wired as the headline of the README quickstart, the front-door,
  and the walkthrough. Verified end to end against the live stack. (An animated gif, if
  wanted, is a screen-recording of this run — an optional cosmetic follow-up.)

## 3b. Walkthrough suite (master + per-flow deep dives, screenshot-rich)

- [x] 3b.1 Capture the screenshots by driving the **live stack** (the flows the smoke
  tests exercise): consent screen, approval UI, Mailpit sink, Grafana dashboard rows
  (incl. the M5 RAG row), a Tempo linked trace (`mcp → … → openfga`), the console
  span→logs jump, and the RAG candidate ranking. Store under `docs/walkthroughs/img/`.
- [x] 3b.2 Write the **master** end-to-end walkthrough (`docs/walkthroughs/`): the
  headline demo as one narrative (discover/DCR → login → consent → brokered token →
  human approval → FGA-filtered RAG via a real MCP client), each stage with its captured
  screenshot + caption, linking out to the per-flow deep dives.
- [x] 3b.3 Write the **per-flow deep dives** — delegation (A), brokering (B), approval
  (C), the MCP surface, RAG (D) — each screenshot-rich, linking **back** to the master
  and **to its matching M0–M5 milestone blog**; blogs = build log, walkthroughs = guided
  tour, no duplication.
- [x] 3b.4 Authored as HTML (blog-style, shared design system) so they render on Pages;
  verify each renders and every screenshot loads in a real browser (screenshot).

## 4. Console trace→logs jump (observability delta)

- [x] 4.1 On the span-detail view, when a span carries a correlation ID (broker audit
  correlation ID / approval reference ID), add a control that queries `/api/loki` for
  that ID and renders the matching audit lines inline. Reuse the existing proxy — no
  backend change.
- [x] 4.2 Graceful "no correlated logs" empty state when a span has no correlation ID;
  never an error or an unfiltered dump. Verify both paths in a real browser (screenshot).

## 5. Organize the GitHub Pages site (main:/docs, .nojekyll)

- [x] 5.1 Add `docs/index.html`: a landing/front-door page with navigation unifying
  the architecture doc, the milestone blog series (`docs/blog/`), the **walkthrough
  suite** (`docs/walkthroughs/`), the threat model, the ADRs, the security-review
  summary, the READMEs, and the quickstart. Consistent header/nav/styling with the
  existing blog pages.
- [x] 5.2 Author the architecture doc's public face as HTML (blog-style); for the
  frequently-edited Markdown (threat model, ADRs, security summary, READMEs) link to
  the GitHub-rendered source rather than duplicating as HTML. No dead links.
- [x] 5.3 Confirm the Pages source (legacy build, `main` → `/docs`, `.nojekyll`) serves
  the organized site; nav reaches every reader-facing artifact from one front door.

## 6. Verify + wrap

- [x] 6.1 Fresh-clone check: `docker-compose up`, follow the README quickstart verbatim,
  confirm the demo runs and the console trace→logs jump works — **by looking**, not by
  asserting APIs alone.
- [ ] 6.2 Load the live Pages site (`patrickdaj.github.io/prokura`) in a real browser:
  landing page renders, nav works, no broken links, blog + architecture reachable —
  verify by looking, not just by checking the deploy status.
- [x] 6.3 Confirm architecture.md is internally consistent with the final threat model,
  ADRs, and security-review findings; SPEC.md superseded. Archive is the next action.
