## Why

The docs site (`docs/`, 20 static HTML pages) has no shared navigation — every
page hand-embeds its own rail, and they have already drifted into three
unrelated systems that disagree with each other. The blog milestone stepper is
truncated at M4 on the four oldest posts (`m1`–`m4` show only `M0…M4`; `m5`–`m9`
show the full `M0…M9`), blog pages offer no way back to the walkthroughs or
GitHub except the wordmark, and the same nav slot reads "GitHub" on the landing
page but "Architecture" on the walkthrough index. Because the markup is
copy-pasted per page, each new milestone (M10–M12 are on the roadmap) will
re-introduce the same drift.

## What Changes

- Add a single source of truth for site navigation: `docs/site-nav.js`, holding
  the section list, the milestone list (M0–M9, extended once when a milestone
  lands), and the flow list as data arrays, and injecting the rail into every
  page. Current-page detection and correct relative paths are derived from
  `location.pathname` so the one file works from the root, `blog/`, and
  `walkthroughs/`.
- Unify the **global rail** to be identical on every page: the `PROKURA`
  wordmark (home) on the left; `Walkthrough · Blog · Architecture · GitHub` on
  the right, with the current section marked.
- Render a **section strip** from the shared lists: the full M0–M9 stepper on
  every blog page (fixing the `m1`–`m4` truncation), and a matching flow strip
  on the walkthrough pages; keep the walkthrough→origin-blog cross-link.
- Add a `<noscript>` fallback (home + GitHub) so the page is not nav-dead
  without JavaScript.
- Replace the hand-embedded `.rail` markup in all 20 pages with the shared
  include; **BREAKING** to the per-page rail markup only (no runtime service or
  spec-level behavior of any product capability changes).

## Capabilities

### New Capabilities
- `docs-site-navigation`: what the docs site's navigation must guarantee —
  one source of truth, a global rail identical across every page, a
  section strip generated from shared lists (complete milestone stepper, flow
  strip), current-page marking, and a no-JavaScript fallback.

### Modified Capabilities

(none — no runtime capability's requirements change; `docs-landing-page`'s
specced requirements are untouched, since the rail is not among its
requirements.)

## Impact

- `docs/site-nav.js` (new) and the `<div class="rail">…</div>` block in all 20
  `docs/**/*.html` pages (landing, `blog/index` + `m1`–`m9`, `walkthroughs/index`
  + the flow/surface pages). Small nav-related additions to
  `docs/walkthroughs/walkthrough.css` if the strip needs styling hooks.
- No changes to services, the demo, README, blog/walkthrough article bodies, or
  any product capability. Verification is visual per the repo's discipline:
  browser screenshots of each page type, light and dark, plus a no-JS check.
