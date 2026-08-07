# Proposal: finalize-docs-and-demo (M6, 4th of four)

## Why

M6 "Polish" has three lens-specific follow-ups — `security-review` (control-centric),
`expand-threat-model` (adversary-centric), `adr-reconciliation` (decision-centric).
But the **reader-facing** deliverables that make a newcomer understand the system in
one sitting are owned by none of them: the consolidated `docs/architecture.md` (into
which SPEC.md retires), the README 5-minute quickstart, and the demo gif/video. One
deferred console feature — jumping from a trace/span to its correlated Loki audit
logs — is likewise homeless (the `/api/loki` proxy is built but unused). For a project
whose product *is* its documentation and demo, these are not optional. This change is
the closing capstone: it gives those deliverables an OpenSpec contract, and it becomes
the **permanent home for the v1 roadmap** when SPEC.md is superseded.

## What Changes

- **New `docs/architecture.md` (SPEC.md retires into it).** The single consolidated
  architecture doc — components, the four flows (A delegation, B brokering, C
  approval, D RAG) plus the MCP authorization surface, the TCB diagram, and the
  locked decisions by reference to the ADRs. On completion, SPEC.md is marked
  **superseded** (kept for history, no longer the source of truth). This is
  sequenced **last** among the M6 changes because it references the threat model,
  the ADRs, and the security-review findings the other three produce.
- **v1 roadmap gets a permanent home.** The forward-looking items currently in
  SPEC.md §10 and SPEC-REVIEW (SPIFFE/SPIRE attestation, RAR-in-Keycloak, multi-agent
  `act`-chain delegation, real Google/GitHub providers end-to-end, the TypeScript
  SDK, Cross-App-Access / ID-JAG, CIBA push mode) migrate into an
  `architecture.md` **Roadmap / v1** section — the durable in-repo home once SPEC.md
  retires. No decisions change; this is relocation, not re-decision.
- **README 5-minute quickstart.** Clone → `docker-compose up` → drive the headline
  MCP demo → watch it in the console, with the honest non-production framing (Q1) and
  the Nango prior-art credit (Q7) in place.
- **Demo gif/video.** The headline MCP flow captured end to end: DCR/login → per-agent
  consent → brokered provider token → human-approved action → FGA-filtered RAG, all
  through a real MCP client, with the live trace/console alongside.
- **Organized GitHub Pages site.** The repo already publishes to GitHub Pages (legacy
  build, `main` → `/docs`, live at `patrickdaj.github.io/prokura`) but has **no
  landing page** (only `docs/blog/index.html` exists) and the docs are scattered
  files. Organize `/docs` into a coherent published site: a `docs/index.html` front
  door with navigation unifying the architecture doc, the milestone blog series, the
  threat model, the ADRs, the security-review summary, the READMEs, and the
  quickstart — every reader-facing artifact reachable from one place. Resolve how
  Markdown renders under `.nojekyll` (GitHub Pages does **not** auto-convert `.md`
  there, so long-form docs need an HTML rendering or an explicit link to the
  GitHub-rendered source).
- **Console → Loki logs jump.** From a selected trace/span in the bespoke console,
  jump to its **correlated Loki audit logs** (query by correlation ID via the existing
  `/api/loki` proxy), closing the trace↔logs loop the observability story implies. An
  `observability` capability delta.

## Capabilities

### New Capabilities

<!-- None. The docs/demo deliverables are documentation tasks, not a capability. -->

### Modified Capabilities

- `observability`: a delta adding the trace→correlated-logs jump — selecting a trace
  or span in the console surfaces its correlated audit log lines from Loki (by
  correlation ID), so an operator moves from "what happened" (trace) to "the audit
  record of it" (logs) without leaving the console.

## Impact

- **New:** `docs/architecture.md` (incl. the v1 Roadmap section), a `docs/index.html`
  Pages landing/nav page, a demo asset under `docs/` (gif/video), and the
  `observability` delta spec.
- **Modified:** `README.md` (quickstart), the `docs/` site organization (Pages served
  from `main:/docs`, `.nojekyll`; existing `docs/blog/` folded under the new landing
  nav), `services/console/` (wire the trace→logs jump onto the span-detail view; the
  `/api/loki` proxy already exists), and `SPEC.md` (mark superseded, pointing at
  `docs/architecture.md`).
- **Ordering:** runs on `apply` **after** the other three M6 changes
  (security-review → expand-threat-model → adr-reconciliation → **this**), because the
  architecture doc is the capstone that references their outputs and is where SPEC.md
  finally retires.
- **No new runtime behavior beyond the console jump, no production hardening.** The
  compose stack stays explicitly non-production; residuals are stated, not fixed.
