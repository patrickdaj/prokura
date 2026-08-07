# Design: finalize-docs-and-demo (M6, 4th of four)

## Context

The three M6 lens changes produce a threat model, an ADR corpus, and a security-review
findings register. What remains is the reader's front door: a single architecture doc
that ties them together (and retires SPEC.md), a quickstart, a demo capture, and one
small console feature (trace→logs jump) whose backend (`/api/loki` proxy in
`services/console/app.py`) already exists but is unused. The console already renders a
span-detail accordion (commit `d5dfece`), so the jump has a natural anchor. This change
is deliberately light on new code and heavy on consolidation.

## Goals / Non-Goals

**Goals:**
- One consolidated `docs/architecture.md` that a newcomer can read start-to-finish;
  SPEC.md superseded and pointing at it.
- A durable in-repo home for the v1 roadmap (an `architecture.md` Roadmap section).
- A README quickstart and a demo gif/video of the headline MCP flow.
- Close the trace↔logs loop in the console using the existing proxy.

**Non-Goals:**
- Re-deciding anything: the roadmap items and architecture decisions are relocated /
  referenced, not changed (decisions live in the ADRs from `adr-reconciliation`).
- Production hardening or new services.
- A docs site / static-site generator — plain Markdown in-repo, consistent with the
  rest of the project.

## Decisions

### 1. architecture.md is the capstone; SPEC.md is superseded, not deleted

`docs/architecture.md` references (does not duplicate) the ADRs, threat model, and
security baseline the other three changes produce — which is why this change is
sequenced last. SPEC.md is kept for history with a "superseded by
docs/architecture.md" banner, so external links and git archaeology still resolve.

### 2. The v1 roadmap moves to an architecture.md section, verbatim-then-curated

The §10 / SPEC-REVIEW forward-looking items are lifted into an `architecture.md`
**Roadmap / v1** section as the single durable home. Until this change is applied, the
canonical copy remains SPEC.md §10 (no interim second copy, to avoid drift).

### 3. Console trace→logs jump reuses the existing proxy

The `/api/loki` proxy already exists; the work is front-end: on the span-detail view,
when the span carries a correlation ID (broker audit correlation ID / approval
reference ID — the same IDs the observability propagation requirement already attaches
to spans), add a control that queries `/api/loki` for that ID and renders the audit
lines inline. No backend change, no new dependency. A "no correlated logs" empty state
mirrors the graceful-state discipline used on the approval screen.

### 4. GitHub Pages: a curated HTML front door; markdown stays GitHub-rendered

Pages is a **legacy build from `main:/docs` with `.nojekyll`** — so `.md` files are
served as raw text, not HTML (which is why the blog is authored as bespoke HTML). The
decision: publish a `docs/index.html` landing page + consistent nav that unifies the
already-HTML blog series with the other reader-facing artifacts, author the
**architecture doc's public face as HTML** (matching the blog's style), and for the
frequently-edited Markdown (threat model, ADRs, security-review summary, READMEs)
**link to their GitHub-rendered source** rather than maintain parallel HTML copies —
keeping a single source of truth. *Alternatives:* (a) drop `.nojekyll` and adopt
Jekyll to auto-render Markdown — rejected: it fights the bespoke blog HTML and adds
config for little gain; (b) a client-side Markdown renderer in the site — viable but
more moving parts than linking out. The exact HTML-vs-link split per doc is settled at
apply time, once the final docs exist. The nav must degrade gracefully (no dead links
to docs a given reader's build hasn't produced yet).

### 5. Demo capture is a scripted, reproducible flow

The gif/video records the same scripted MCP flow the smoke tests drive (discover/DCR →
login → consent → brokered token → reactive approval → FGA-filtered RAG), so the demo
is reproducible and stays honest with the tests, not a one-off screen recording.

## Risks / Trade-offs

- **architecture.md drifts from the ADRs/threat model** → it *references* them rather
  than restating, and is authored last so the referenced artifacts are final.
- **v1 roadmap copied in two places during the gap** → explicitly keep SPEC.md §10 as
  the sole copy until this change is applied; the move is atomic with SPEC's retirement.
- **Console jump surfaces sensitive log content** → it queries only existing audit
  lines (which already exclude secrets/params) by correlation ID; no new log content
  is created.

## Migration Plan

Additive and doc-centric. Apply after the other three M6 changes. Steps: author
`docs/architecture.md` (folding SPEC.md content + the v1 roadmap), add the README
quickstart, capture the demo asset, wire the console jump, then flip SPEC.md to
superseded. Rollback is trivial (docs + one front-end feature); nothing depends on it.

## Open Questions

- Demo asset format (animated gif vs short mp4) and where it embeds (README top vs a
  docs/demo page) — settle at apply time.
- Whether architecture.md carries its own condensed diagrams or embeds the existing
  ones — decide against the final threat-model/ADR diagrams.
