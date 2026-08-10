## Context

`docs/` is a build-free static site of 20 hand-authored HTML pages served over
GitHub Pages. Styling is already shared (every page links
`walkthroughs/walkthrough.css`), but navigation is not: each page embeds its own
`<div class="rail">…</div>`. Auditing all 20 pages (2026-08-10) found three
divergent rails:

- **Landing** (`index.html`): `.nav` = Walkthrough · Blog · **GitHub**.
- **Walkthrough index**: `.nav` = Walkthrough(cur) · Blog · **Architecture** (no
  GitHub). Individual flow pages: `← Walkthrough` + one contextual link (the
  originating `M# blog`, or Architecture for `claude-code`/`postmortem`).
- **Blog**: a milestone `.steps` stepper only (no Walkthrough/Blog/GitHub), and
  the stepper is **truncated at M4** on `m1`–`m4` (frozen when only M1–M4
  existed) while `m5`–`m9` carry the full `M0…M9`.

The drift is structural: copy-pasted markup with no source of truth, so each new
milestone (M10–M12 planned) reproduces the truncation bug.

## Goals / Non-Goals

**Goals:**
- Exactly one place to edit navigation; adding a milestone or flow is a one-line
  data edit, not a 20-file sweep.
- A global rail that is byte-identical across all pages (same items, same order,
  same slot meanings), with the current section marked.
- The blog stepper shows the complete M0–M9 on every post; the walkthrough pages
  show the full flow list; both are generated from the shared lists.
- Preserve the useful walkthrough→origin-blog cross-link.
- Degrade gracefully without JavaScript (home + GitHub reachable).

**Non-Goals:**
- No build step or toolchain — the site stays `docker compose up`-free static
  HTML.
- No redesign of the rail's visual language; reuse existing `.rail`/`.nav`/
  `.steps` CSS classes and tokens.
- No changes to article bodies, services, README, or any product capability.
- No routing/framework; plain DOM injection.

## Decisions

**D1 — One shared `docs/site-nav.js`, injected at runtime, over a build-time
generator or re-synced static markup.** Alternatives: (a) re-sync the embedded
HTML to be identical by hand — zero machinery but drift returns at M10;
(b) a generator script run at commit — most robust but introduces the build step
the site has deliberately avoided. Chosen: a ~50-line vanilla JS include that
mirrors how `walkthrough.css` is already shared. One `<script>` tag per page,
one file to edit for M10–M12.

**D2 — Data lives in three arrays at the top of `site-nav.js`.**
`SECTIONS` (label → href + match rule for the global rail: Walkthrough, Blog,
Architecture, GitHub), `MILESTONES` (`M0…M9`, each `{id, href, label}`), and
`FLOWS` (the walkthrough flow/surface pages, each `{label, href, blog?}`).
Adding M10 is appending one `MILESTONES` entry.

**D3 — Path/section resolution from `location.pathname`.** The script computes a
`prefix` (`''` at root, `'../'` under `blog/` or `walkthroughs/`) so a single
href table resolves correctly from any depth, and derives the current section
and current milestone/flow by matching the pathname. This removes the
per-directory hand-editing that caused the drift.

**D4 — Two tiers. Global rail on every page; section strip only within its
section.** Tier 1 (global rail) is identical everywhere: `PROKURA` home + the
four `SECTIONS`, current marked with the existing `.cur` class. Tier 2 renders
under it: on blog pages the full `MILESTONES` stepper with the current id as a
non-link `.cur`; on walkthrough pages the `FLOWS` strip plus the current flow's
`blog` cross-link. The landing page has Tier 1 only.

**D5 — Progressive enhancement.** Each page keeps a minimal static
`<noscript>`-friendly anchor set (wordmark → home, plus a GitHub link) so the
page is never nav-dead; `site-nav.js` replaces/augments the rail on load. The
injected rail is written into a known container element the script owns.

**D6 — `site-nav.js` carries its own styles (revised during implementation).**
The three page families do not share one stylesheet: `index.html` and the
walkthroughs link `walkthrough.css` (which defines `.rail`/`.nav` but not
`.steps`), while the blog pages are fully self-contained with their own inline
`<style>` (which defines `.steps` but not `.nav`). Putting nav CSS in
`walkthrough.css` would therefore never reach the blog pages. So the module
injects its own `<style>` block (appended to `document.head`, using the shared
CSS custom properties `--ink`/`--accent`/`--faint`/`--hair`/… that every page
already defines) alongside the markup. This makes navigation a single
self-contained source of truth for both structure and appearance, and reuses
the existing `.rail`/`.mark`/`.nav`/`.cur` class names so the look is unchanged.

## Risks / Trade-offs

- [JS-injected nav is invisible to no-JS clients and crawlers] → `<noscript>`
  fallback (D5) keeps home + GitHub reachable; this is a demo/docs microsite, so
  full crawlability of the rail is not a requirement.
- [A single script touching all pages could break every page at once] → the
  script is defensive (feature-detects its container, no throw if absent), and
  verification renders every page type in a browser before shipping.
- [Relative-path resolution across three directory depths is the classic
  static-site footgun] → centralize path logic in one `prefix` computation (D3)
  and verify links from root, `blog/`, and `walkthroughs/` during the visual
  pass.
- [Milestone list still needs a manual edit at M10] → unavoidable without a
  build step; the win is one edit in one file versus 10+ pages, and the spec
  names the list as the single home for it.
