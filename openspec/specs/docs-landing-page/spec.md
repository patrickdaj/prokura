# docs-landing-page

## Purpose

The public landing page (`docs/index.html`) presents Prokura scene-first: the
credential-sharing problem lands in plain second person before any mechanism
vocabulary, a live fail-closed demonstration anchors the hero, and four
governance questions build tension (today) before resolving (prokura). The
depth below "Why this exists" — Start here, the M1–M9 control cards, in-depth
docs, the flow tour, and footer — is unchanged.

## Requirements

### Requirement: Problem lands before solution vocabulary
The landing page hero SHALL state the problem in plain second person —
handing an agent your credentials makes it indistinguishable from you —
before any solution or mechanism vocabulary (token exchange, CIBA, FGA,
audience, broker, MCP) appears. The what-Prokura-does sentence SHALL use
plain language (scoped, consent-gated per agent, human-approved, revocable);
the stack/credibility sentence (Keycloak, OpenFGA, OpenBao, MCP, "Auth0 for
AI Agents") SHALL come last in the lede.

#### Scenario: Newcomer reads only the first two sentences
- **WHEN** a reader with no OAuth/MCP background reads the hero's first two
  sentences
- **THEN** they encounter the credential-sharing problem stated in second
  person ("you"), with no identity-standards jargon

#### Scenario: Jargon placement
- **WHEN** the hero lede is scanned top to bottom
- **THEN** no mechanism term appears before the problem statement, and stack
  names appear only in the lede's final sentence

### Requirement: Fail-closed demonstration in the hero
The hero SHALL include one terminal-styled panel, in the site's existing
`screen`/`term` visual language, showing a sensitive action failing closed:
a `send_email` attempt refused with the literal status
`428 approval_required`, a human deny on the trusted approval UI, and the
kill-switch outcome. The panel SHALL depict only behavior the stack actually
exhibits, and SHALL be captioned as running live in the demo.

#### Scenario: Panel content is real
- **WHEN** each line of the panel is compared against stack behavior
- **THEN** every depicted behavior maps to an implemented control: the 428
  refusal and payload registration (tools-api approval gate, ADR-0018),
  decisions only on the authenticated approval UI (ADR-0007), and instant
  revocation with measured time-to-stop (ADR-0024)

#### Scenario: Panel stays compact
- **WHEN** the hero renders on a laptop viewport
- **THEN** the panel is roughly seven lines plus a one-line caption and the
  hero remains within the first screenful-and-a-bit

### Requirement: Four questions create tension before resolving
The four governance Q-cards SHALL each present, in order: a plain-language
*today →* line stating why the question is unanswerable with shared
credentials, then a plain-language *prokura →* line stating how it becomes
answerable, with the mechanism reduced to a short mono tag (`RFC 8693`,
`broker + FGA`, `CIBA step-up`, `kill switch`).

#### Scenario: Card reading order
- **WHEN** a Q-card is read
- **THEN** the pain (today) precedes the resolution (prokura), and no
  mechanism jargon appears outside the tag

#### Scenario: Claims stay honest
- **WHEN** the prokura→ lines make quantitative claims
- **THEN** each is backed by an enforced or measured property (≤15-minute
  token TTL; measured time-to-stop)

### Requirement: Depth sections unchanged
The change SHALL leave everything below the "Why this exists" section
unchanged — Start here, the M1–M9 control cards, the in-depth docs links,
the flow tour, and the footer — and styling additions SHALL be confined to
the page's inline `<style>` block (no edits to `walkthrough.css`).

#### Scenario: Diff scope
- **WHEN** the change's diff is inspected
- **THEN** only `docs/index.html` is modified, and within it only the hero,
  the "Why this exists" section, and the inline style block
