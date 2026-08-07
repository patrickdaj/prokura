# Progress blog

A running, visual build log — one page per milestone, written for an outsider:
what we built, how it works, the decisions and gotchas, how it was verified, and
a "Run it yourself" section. Each page is a self-contained, theme-aware static
HTML file in Prokura's own visual language, with no external assets.

## Pages

| Page | File |
|------|------|
| **Start here** — Foundation & Roadmap (M0) | [`index.html`](index.html) |
| **M1** — Delegated Token Exchange | [`m1-token-exchange.html`](m1-token-exchange.html) |
| **M2** — The Token Broker | [`m2-token-broker.html`](m2-token-broker.html) |
| **M3** — Human Approval | [`m3-human-approval.html`](m3-human-approval.html) |
| **M4** — MCP Authorization | [`m4-mcp-authorization.html`](m4-mcp-authorization.html) |

Open any file directly in a browser. The pages cross-link with relative paths
(the `PROKURA` wordmark returns to the M0 hub), so they work unchanged as a
static site.

## Hosting (GitHub Pages)

This directory is a self-contained static site with `index.html` as the front
door. Publish it by pointing GitHub Pages at the branch and folder that contains
it (Settings → Pages → *Deploy from a branch*), then browse to
`…/docs/blog/`. A `.nojekyll` file lives in `docs/` so the HTML is served as-is
without Jekyll processing.

## Conventions

- One page per milestone; M0 (`index.html`) doubles as the series front door and
  the M0→M6 roadmap.
- Each new milestone slots into the M0 roadmap and gets its own page here.
- A full end-to-end **walkthrough** is deliberately deferred to a capstone
  (M6 / demo) rather than duplicated across every page.
- **Every milestone page carries a flow diagram** (the norm). Each page includes
  a small self-contained `renderSeq(el, actors, steps, caption)` component that
  draws a theme-aware SVG **sequence diagram** of the milestone's flow — numbered
  steps, solid arrows for requests and dashed for returns, actor lifelines. The
  CSS lives under `/* sequence-diagram component */` and the data is a per-page
  `actors`/`steps` array. New pages copy the component and describe their flow the
  same way, so the diagrams read as one system.
