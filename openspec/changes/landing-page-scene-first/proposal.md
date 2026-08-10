## Why

The landing page (`docs/index.html`) fronts every audience the project has —
AI/agent developers, security engineers, hiring managers, OSS evaluators — but
it opens with a category label ("Agentic identity, assembled") and a ~90-word
lede that reaches solution jargon (delegated/scoped/CIBA/FGA/MCP) before the
problem has landed. A newcomer leaves without feeling the thing the project
exists to fix: an agent holding your credentials **is** you, unaccountably.
The strongest material on the page (the four governance questions) defuses its
own tension by answering each question in mechanism jargon immediately.

## What Changes

- Rewrite the hero: problem-first H1 ("Your agent shouldn't *be* you."), a
  lede that spends two second-person sentences on the pain before any
  solution vocabulary, then one plain-language sentence on what Prokura does
  and one stack-credibility sentence (Keycloak/OpenFGA/OpenBao, MCP,
  OSS answer to "Auth0 for AI Agents").
- Add one terminal panel under the hero chips (existing `screen`/`term`
  aesthetic) showing a prompt-injected `send_email` failing closed: the real
  `428 approval_required` refusal, deny on the trusted approval UI, and the
  kill switch. Caption: "Fail closed, not fail open — this runs live in the
  demo below." The panel depicts only real stack behavior.
- Rework the four "Why this exists" Q-cards into *today →* / *prokura →*
  plain-language pairs, with the mechanism reduced to a small mono tag
  (`RFC 8693`, `broker + FGA`, `CIBA step-up`, `kill switch`).
- Everything below "Why this exists" (Start here, M1–M9 control cards,
  in-depth docs, flow tour, footer) is unchanged.

## Capabilities

### New Capabilities
- `docs-landing-page`: what the landing page must communicate and in what
  order — problem felt before solution vocabulary, fail-closed demonstration
  grounded in real stack behavior, layered depth for expert audiences.

### Modified Capabilities

(none — no runtime capability's requirements change; this is the docs
surface only)

## Impact

- `docs/index.html` only (copy + small additions to its inline `<style>`
  block). No changes to `docs/walkthroughs/walkthrough.css`, the
  walkthroughs, blog posts, README, or any service.
- Verification is visual per the repo's discipline: browser screenshot of
  the rendered page, light and dark.
