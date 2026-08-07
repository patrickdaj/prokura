# SPEC Review — Findings, Options, and How Auth0 Resolved Each

**Reviews:** `SPEC.md` (AgentGate Draft v0.1)
**Reference product:** Auth0 for AI Agents (GA November 19, 2025) — User Authentication, Token Vault, Async Authorization (CIBA + RAR + Guardian push), FGA for RAG. Auth for MCP went GA May 2026; Cross App Access is in Early Access. All Auth0 and Keycloak capability claims in this document were verified against official docs, source, and release notes in August 2026.

Each item below states the problem, how Auth0 resolved it (or why they sidestepped it), the realistic options for AgentGate, and a recommendation. Findings F1–F9 are defects or unimplementable claims in the current draft; questions Q1–Q7 are open design decisions that reshape the spec.

## Summary

| # | Item | Severity | Recommended resolution |
|---|---|---|---|
| F1 | `can_use` FGA relation is invalid | Blocker (model won't load) | Direct-assignment relation + write-time invariant in broker |
| F2 | Flow A/B token audience mismatch | Blocker (confused deputy) | Broker gets its own audience |
| F3 | 15-min TTL rule unenforceable for third-party tokens | Spec accuracy | Restate as hand-out interval; per-provider TTL table |
| F4 | GitHub refresh loop doesn't exist for OAuth apps | Design error | Use a GitHub App; provider manifest declares refresh capability |
| F5 | `binding_message` is agent-authored → approval theater | Security thesis | Structured payload + reference ID; trusted UI renders |
| F6 | Custom Java SPI may be unnecessary | Effort/risk | Spike Keycloak's built-in CIBA HTTP channel in M0 |
| F7 | ntfy topics are open capabilities | Security gap | ntfy = notify-only; decisions only via authenticated UI |
| F8 | "Single-use action token" asserted, not implemented | Spec gap | Action-ID claim + resource-side replay check |
| F9 | Keycloak already stores external IdP tokens | Architecture overlap | Resolve via Q2 |
| Q1 | What is this project *for*? | Strategic | Reference implementation, production-honest docs |
| Q2 | Where do grants come from? | Architectural fork | Keycloak account linking as acquisition; broker owns lifecycle |
| Q3 | Who writes `can_use` tuples / consent granularity? | Design gap | Per-agent consent screen (differentiator vs Auth0) |
| Q4 | LangChain demo vs MCP-first | Strategic | MCP server as headline demo |
| Q5 | Python-only SDK? | Scope | Python v0, TypeScript v1 — explicit ADR |
| Q6 | How does the demo send email? | Practical | Mailpit SMTP sink; Google showcased elsewhere |
| Q7 | Prior art (Nango) + name collision | Positioning | Build minimal, credit prior art, verify name |

---

## Part 1 — Findings

### F1. The OpenFGA `can_use` relation is broken

**Problem.** §5 defines:

```
define can_use: [agent] and operator from can_use
```

This is self-referential — the tupleset `can_use` appears inside its own definition — and OpenFGA will reject the model. Even if it loaded, the intersection is unsatisfiable: the direct branch (`[agent]`) yields agent subjects while `operator from can_use` yields user subjects, so no single subject can satisfy both sides. The intent — *"an agent may use a grant only if the agent's operator owns that grant"* — is a cross-object join that OpenFGA's modeling language cannot express.

**How Auth0 resolved it.** They went a different route entirely: Token Vault access is not gated by ReBAC. Authorization to exchange is bound to the OAuth client (the app must have the Token Vault grant type enabled for the connection) plus possession of the user's Auth0 refresh/access token. No relationship graph is consulted for vault access; FGA is reserved for document/RAG authorization.

**Options.**

- **A (recommended). Direct assignment + write-time invariant.** Model becomes `define can_use: [agent]`. The broker is the only writer of `can_use` tuples and enforces "agent's operator == grant owner" at tuple-write time. Moves a security property from the model into broker code — the threat model must cover the broker as a trusted tuple writer.
- **B. Two checks in broker code.** No `can_use` relation; broker checks `grant owner == token sub` and `agent operator == token sub` as two separate FGA checks per request. No consent granularity (any of the user's agents can use any of the user's grants).
- **C. Auth0-style: no FGA gate on grants.** Possession of a valid exchanged token (`sub` = user, `azp` = agent) plus the grant belonging to `sub` is sufficient. Simplest; matches the commercial product; but forfeits per-agent consent, which is one of AgentGate's differentiators (see Q3).

**Recommendation:** A. It keeps the per-agent consent story (Q3) and is honest about where enforcement lives.

### F2. Flow A / Flow B audience mismatch

**Problem.** Flow A exchanges the user token to `audience = agent-tools-api`. Flow B then has the agent present *that same token* to the Token Broker. The broker would be accepting a token addressed to a different resource — precisely the confused-deputy shape §11 says user-context FGA checks exist to prevent. Any holder of an `agent-tools-api` token could mint third-party tokens.

**How Auth0 resolved it.** The problem doesn't arise in their architecture: Token Vault *is part of the authorization server*. The agent calls Auth0's own token endpoint with the custom grant `urn:auth0:params:oauth:grant-type:token-exchange:federated-connection-access-token`, presenting an Auth0 refresh token *or* access token as the `subject_token` (two documented variants with distinct `subject_token_type` URNs); the AS validates its own client and its own token. There is no third-party resource server accepting someone else's audience.

**Options.**

- **A (recommended). Broker is its own audience.** Agents perform token exchange with `audience = token-broker` (in addition to, or instead of, `agent-tools-api`), and the broker rejects any token whose `aud` isn't itself. Two exchanges per flow, but each token is honest about its addressee.
- **B. Multi-audience token.** One exchange requesting both audiences. Fewer round trips; slightly wider blast radius per token; Keycloak supports multiple audience mappers.
- **C. Fold the broker into Keycloak as a custom grant (Auth0's shape).** Architecturally purest and closest to Token Vault, but means a substantial Java extension — the cost §11 already rejected when choosing not to build an AS.

**Recommendation:** A for v0; note C as the "what Auth0 actually does" comparison in `docs/architecture.md`.

### F3. The 15-minute TTL hard rule is unenforceable for third-party tokens

**Problem.** §9: "All agent-held tokens ≤ 15 min TTL." The broker does not control upstream token lifetimes: Google access tokens live ~1 hour; classic GitHub OAuth-app tokens don't expire at all. Returning `expires_in: 900` doesn't make a leaked provider token stop working at 15 minutes — the rule as written is false advertising, and it's the first thing a security reviewer will ding.

**How Auth0 resolved it.** They don't claim it. Auth0's Token Vault blog states federated access tokens' lifetime *depends on the upstream provider*, with Token Vault refreshing as needed; the docs pages make no lifetime promise at all — responses simply carry the provider's `expires_in`. Auth0 imposes no 15-minute bound anywhere (its own access tokens default to 24 hours); the ≤15-min figure is this spec's own design rule, not an Auth0 property.

**Options.**

- **A (recommended). Restate honestly.** Keycloak-issued tokens ≤ 15 min (enforceable). For provider tokens: "hand-out validity is provider-controlled; the broker's *re-issuance interval* is ≤ 15 min; residual exposure per provider is documented in the threat model," with a per-provider TTL table (Google ~1h; GitHub App ~8h user tokens; GitHub OAuth app: non-expiring — see F4).
- **B. Only support providers with short/configurable token lifetimes.** Keeps the rule true but shrinks the connector story to near zero.
- **C. Drop the rule for provider tokens entirely.** Loses a real (if bounded) defensive property for Keycloak tokens too — don't.

**Recommendation:** A.

### F4. The GitHub "refresh loop" doesn't exist for OAuth apps

**Problem.** Flow B assumes every provider hands out a `refresh_token`. Classic GitHub **OAuth apps** issue non-expiring access tokens with **no refresh token**; refresh tokens only exist for **GitHub Apps** with user-token expiration enabled. Related: "scope-down enforced" (Flow B acceptance) is only cryptographically real where the provider supports narrowing — Google allows requesting a scope subset on refresh; GitHub does not, so for GitHub the broker can only *decline* over-broad requests, never mint a narrower token.

**How Auth0 resolved it.** Pre-integrated connections abstract this: GitHub is a documented Token Vault provider, and neither exchange flow accepts a scope parameter — scopes are fixed at the connection/consent step, never narrowed per exchange. (How the vault internally handles GitHub's non-expiring OAuth-app tokens is not documented; Auth0's GitHub guide even punts scope configuration to the GitHub side — "scopes are not supported for GitHub yet.")

**Options.**

- **A (recommended). Use a GitHub App** with expiring user access tokens. Gives the demo a genuine refresh loop and 8-hour bounded tokens, matching the spec's security story. Slightly more setup for users running the demo (App creation vs OAuth app).
- **B. Keep the OAuth app, adapt the spec.** Store the non-expiring token in OpenBao, hand out the same token each time, and document that GitHub tokens are long-lived. Simpler setup; visibly weakens the headline claims.
- **C. Provider manifest declares capabilities.** Whichever GitHub flavor ships, add `supports_refresh` / `supports_scope_narrowing` fields to the provider abstraction (pulls the §10 "connector abstraction" question partially into v0) and make Flow B acceptance criteria per-capability: cryptographic enforcement where supported, policy enforcement (reject) where not.

**Recommendation:** A + C. The manifest honesty is cheap and makes the second provider (Google) prove the abstraction, as M2 already intends.

### F5. Free-text `binding_message` is the vulnerability, not the control

**Problem.** §9 makes "binding_message rendered verbatim" a hard rule — but the message is *authored by the agent*, i.e., by the LLM, the very principal the human is being asked to check. A prompt-injected agent can request `email:send` to an attacker while the binding message reads "Send your weekly summary to yourself?". The human approves text written by the adversary. Additionally, Keycloak validates `binding_message` against `^[a-zA-Z0-9-._+/!?#]{1,50}$` — max 50 characters, no spaces — so rich descriptive messages will be rejected at the protocol layer anyway.

**How Auth0 resolved it.** Rich Authorization Requests (RAR): the agent submits a structured `authorization_details` payload (action type, recipient, amount, …); the **trusted** Guardian push UI renders it; and the resource server independently validates that the executed action matches the approved payload. The agent never controls the rendering, and the approval is bound to parameters, not prose. (The spec punts RAR to v1 — but Keycloak doesn't support RAR today, so v1 would hit the same wall.)

**Options.**

- **A (recommended). Structured payload out-of-band, reference in-band.** Agent registers `{action, params}` with the approval service; `binding_message` carries only a short reference ID (fits Keycloak's limits). The approval UI fetches the payload from the approval service and renders it itself (trusted rendering). The approval service records a hash of the payload; the demo tool API verifies the executed action against the approved hash before acting. This reproduces RAR's security properties without touching Keycloak internals.
- **B. Keep free text, document the risk.** Acceptable only if AgentGate is explicitly a demo (Q1) — but "approval theater" undermines the project's whole thesis, and §9 currently enshrines the vulnerability as a hard rule.
- **C. Implement RAR in Keycloak via extension.** Standards-faithful, largest effort, deepest Keycloak-internals risk. Reasonable v1 ADR topic, not v0.

**Recommendation:** A in v0. Rewrite the §9 hard rule as: "the approval UI renders the action payload from the approval service — never agent-authored text — and the resource server validates the executed action against the approved payload."

### F6. The custom Java SPI may be unnecessary

**Problem.** M3 (the riskiest milestone) budgets a custom Keycloak `AuthenticationChannelProvider` SPI in Java (`extensions/keycloak-ciba-ntfy/`).

**How Auth0 resolved it.** Not applicable — their CIBA channel is their own Guardian infrastructure. But Keycloak itself ships a built-in **HTTP authentication channel provider** for CIBA, configured via `--spi-ciba-auth-channel--ciba-http-auth-channel--http-authentication-channel-uri` (double-dash separators on Keycloak 26+; older single-dash spelling is deprecated): Keycloak POSTs the backchannel auth request (including `binding_message`) to an external HTTP endpoint, and the decision comes back on Keycloak's standard callback endpoint at `/realms/{realm}/protocol/openid-connect/ext/ciba/auth/callback`, authorized by the bearer token Keycloak included in the delegation request.

**Options.**

- **A (recommended). Spike the built-in HTTP channel in M0.** Point it at a FastAPI endpoint (which pushes to ntfy and exposes the approval UI's decision path). If it works, the Java SPI is deleted from the plan and M3 shrinks to Python + configuration. It's lightly documented, so verify early — this is a week-one spike, not a week-three discovery.
- **B. Keep the Java SPI.** Full control, upstream-contribution potential, but Java toolchain + Keycloak SPI churn across versions is real maintenance drag for a mostly-Python project.
- **C. Skip Keycloak CIBA; implement approval purely in the broker.** Simplest, but abandons the standards story (CIBA) that justifies choosing Keycloak at all — Auth0 deliberately built on CIBA and markets that.

**Recommendation:** A, with B as fallback if the built-in channel proves unusable.

### F7. ntfy topics are open capabilities

**Problem.** Public ntfy topics are bearer capabilities: anyone who guesses the topic name can **subscribe** (leaking pending-action details) and **publish** (spoofing approval notifications). The spec also never states how the approve/deny callback authenticates the decision-maker.

**How Auth0 resolved it.** Guardian push: an enrolled, cryptographically bound device (RSA keypair generated at enrollment; responses signed with the device's private key). Auth0's CIBA offers exactly two channels — Guardian push (default) and email — and its docs recommend push because email "can be vulnerable to phishing attacks." (SMS is not a CIBA channel at Auth0.)

**Options.**

- **A (recommended). ntfy is notify-only; decisions only through the authenticated UI.** Hard rule for §9: the notification carries no approval capability and minimal detail (a deep link + reference ID); approve/deny happens exclusively in the approval UI behind a Keycloak session, and the callback to Keycloak is made by the approval service, not the user's device. Per-user random (unguessable) topic names as defense-in-depth.
- **B. Self-hosted ntfy with ACLs.** ntfy supports auth in self-hosted mode; adds config surface, keeps the same architecture. Good docker-compose default.
- **C. Web Push instead of ntfy.** Per-user push subscriptions, no shared topics — but VAPID/service-worker plumbing is a meaningful chunk of demo-UI work.

**Recommendation:** A + B together (self-hosted ntfy in compose, notify-only semantics regardless).

### F8. "Single-use action token" is asserted but not implemented

**Problem.** Flow C's acceptance says the CIBA-issued token is "single-use scope." CIBA returns an ordinary access token for the requested scope; nothing in Keycloak makes it single-use. Single-use requires replay tracking at the resource server — which appears in no component's scope.

**How Auth0 resolved it.** They don't claim single-use. Their bound is RAR: the token authorizes a *specific parameterized action* — per their docs, "your resource server is responsible for the granular validation of the content within `authorization_details`" — which makes replay mostly moot, since replaying the token can only re-authorize the same already-executed action. (The only short TTL Auth0 documents in this flow is the authorization request's `auth_req_id` expiry, default 300 s; there is no special access-token lifetime.)

**Options.**

- **A (recommended). Action-ID claim + resource-side replay check.** Combined with F5-A, the approval reference ID ends up associated with the token (scope like `action:{id}` or a claim via mapper); the demo tool API records consumed action IDs and rejects re-execution. Cheap (one table/set in the demo API) and makes the acceptance criterion testable.
- **B. Soften the claim.** "Short-TTL (≤2 min), single-action-scoped" — honest, less strong.
- **C. JTI-based replay cache** at the resource server for these tokens specifically. Equivalent to A with more moving parts if F5-A exists anyway.

**Recommendation:** A (it falls out of F5-A nearly for free).

### F9. Keycloak already stores external IdP tokens

**Problem.** With "Store Tokens" enabled on an identity provider, Keycloak keeps upstream tokens and exposes them at `GET /realms/{realm}/broker/{alias}/token` (requires the `broker.read-token` role). The spec's broker duplicates the *acquisition* half of this without acknowledging the overlap. And since Keycloak 26.4 (Sept 2025), retrieval also auto-refreshes the stored external token when a valid refresh token exists — so the refresh half overlaps too. What the broker still uniquely adds: leases, per-request scope-down policy, per-agent gating, and audit.

**How Auth0 resolved it.** Full unification: signing in with (or linking) a connection *is* the vault-seeding act; there is no second consent flow the IdP doesn't know about.

**Resolution:** This is the same fork as Q2 — see below. At minimum, `docs/architecture.md` needs an ADR explaining why grant acquisition lives where it lives relative to Keycloak's native capability.

---

## Part 2 — Open Decisions

### Q1. What is AgentGate *for*?

The spec oscillates: "reference implementation" in the one-liner, production-grade hard rules in §9, docker-compose-only in §2. The answer decides where polish goes.

- **A (recommended). Reference architecture** — the docs, ADRs, threat model, and demo *are* the product; §9 rules are stated as "what production would require," and the compose stack is explicitly non-production. Cheapest path to credibility; matches §2's non-goals.
- **B. Runnable platform** people actually deploy — then SDK ergonomics, upgrade paths, secret rotation, and eventually HA belong in the roadmap, and the 6-week milestone plan is not credible.
- **C. Portfolio/credibility piece** — then demo video + README polish outrank breadth, and one provider might be enough.

*Auth0's position:* commercial SaaS — they made choice B with a company attached. A is the honest OSS counterpoint.

### Q2. Where do grants come from — broker-owned OAuth flows, or Keycloak identity brokering?

The biggest architectural fork in the doc. Flow B runs a standalone Authorization Code flow the IdP never sees, splitting the identity story (and the spec never says how the broker authenticates the user during grant setup).

**How Auth0 resolved it.** Unified with login: sign in with Google → tokens vaulted; additional providers attach via the Connected Accounts flow (My Account API: `/me/v1/connected-accounts/connect` → provider consent → callback) under the same identity. First-provider consent, identity, and vault-seeding are one motion; extra providers are a second motion, but always through the provider's own consent screen. (Connected Accounts' GA status is murky — community threads still called it Early Access in spring 2026.)

- **A. Broker-owned flows (as specced).** Max flexibility (incremental/per-request scopes), least Keycloak coupling; but two consent surfaces, and grant identity is only correlated to Keycloak by the broker's own bookkeeping. If chosen: require the setup flow to start from an authenticated Keycloak session (broker validates a user token before `POST /v1/grants/{provider}/start`).
- **B (recommended). Keycloak account linking as acquisition; broker owns lifecycle.** Use Keycloak identity providers with *Store Tokens* enabled and **client-initiated account linking** for connecting Google/GitHub to an existing account (this is Keycloak's analog of Auth0's connect-account flow; on current Keycloak, invoke it via the application-initiated action `kc_action=idp_link:<alias>` — the older `/broker/{provider}/link` endpoint is deprecated). The broker pulls the stored token via `/broker/{alias}/token`, imports the refresh token into OpenBao, and owns refresh/lease/scope-down from there. One identity, one consent surface, less OAuth code to write; closest to Auth0's shape while the broker still earns its place (F9). Trade-off: scopes are configured statically per IdP in the realm, not incrementally per request.
- **C. Hybrid.** Login provider (Google) seeds via B; extra providers via A. Two code paths in v0 — probably not worth it yet; a defensible v1 evolution.

### Q3. Who writes `can_use` tuples, and what does the user consent to?

Currently the Flow B FGA gate checks tuples with no defined provisioning path. Options assume F1-A (direct-assignment `can_use`).

**How Auth0 resolved it.** Consent is app-scoped: the user consents to scopes for a *connection* used by an *application*; any agent running inside that application shares the grant. There is no per-agent consent.

- **A. Implicit: grant setup authorizes all the user's agents.** One tuple-write loop at grant creation. Simple; coarse.
- **B (recommended). Per-agent consent screen.** Grant setup (or first use) shows "Allow *summarizer-agent* to use your GitHub grant — [scopes]"; approval writes the tuple. This is *more* granular than Auth0 offers and is exactly the kind of differentiator an OSS reference implementation should demonstrate — and it gives the FGA grant model (F1-A) a reason to exist.
- **C. Admin-provisioned.** Tuples written by realm admin tooling. Fine for enterprise narratives, wrong for the demo's self-service story.

### Q4. LangChain demo or MCP-first?

The spec hedges ("LangChain or MCP server"; DCR sits in the architecture diagram; MCP AS mode is v1 roadmap).

**How Auth0 resolved it.** They ship both framework SDK integrations (LangGraph, Vercel AI, LlamaIndex, Genkit — plus a Cloudflare Agents starter) *and* a named "Auth for MCP" product, GA since May 2026 — securing MCP servers with Auth0 as AS is one of their loudest 2025–26 stories.

- **A. LangChain-only v0** (as mostly specced). Least risk; least distinctive.
- **B (recommended). MCP server as the headline demo.** "Keycloak as an MCP authorization server" is arguably the most-searched-for, least-well-served piece of this whole space, and it's genuinely reachable: Keycloak 26.4 shipped explicit MCP AS support (RFC 8414 metadata, DCR per RFC 7591, an official MCP guide). Per RFC 9728, protected-resource metadata is published by the MCP server itself, pointing at Keycloak; the real remaining gap is RFC 8707 Resource Indicators (unsupported — scopes are the documented workaround), so MCP spec 2025-06-18+ is only partially covered. The gated-action and brokered-token flows demo identically through MCP tools. Cost: something falls out — the most likely candidate is the second provider (Google) slipping to v1, or the RAG corpus shrinking.
- **C. Both in v0.** Scope risk in a 6-week plan is severe; only viable if Q1 = portfolio piece and depth is sacrificed elsewhere.

### Q5. Is Python-only the right SDK bet?

**How Auth0 resolved it.** JS-first (`auth0-ai-js`, with Vercel AI/LangGraph integrations), Python second — because agent *app* developers concentrate in TypeScript.

- **A (recommended). Python v0, TypeScript v1 — as an explicit ADR.** The backend stack is already Python; MCP servers in Python are idiomatic; just make it a decision, not a default.
- **B. TypeScript-first.** Better audience match, but splits the implementation stack in half for a solo 6-week build.
- **C. Both.** Not in 6 weeks.

### Q6. How does the demo send email?

"Drafts email + gated send" via Gmail means `gmail.send` — a Google **restricted** scope with verification requirements (fine in testing mode with allowlisted users, but that constraint is invisible in the spec).

**How Auth0 resolved it.** They didn't, really. Their quickstarts do use Gmail/Calendar — but customers must create their *own* Google OAuth client and clear Google's verification for sensitive scopes themselves (Auth0's docs warn of the 100-login cap until the consent screen is verified). Auth0's "integrations" are pre-configured connection templates, not pre-verified Google clients — the Google friction is identical for AgentGate.

- **A (recommended). Mailpit (local SMTP sink) for the gated send.** Zero Google friction, CIBA demos identically, works offline. Then give Google a different showcase: Calendar ("create event" as a second gated action) or Drive as the ACL'd RAG corpus (which would make Flow D's tuples mirror real Drive permissions — a strong demo).
- **B. Gmail in testing mode.** Real-world texture; every person who clones the repo must configure an OAuth consent screen and allowlist themselves — meaningful quickstart friction.
- **C. Replace email with a GitHub write action** (post a comment / close an issue) as the gated action. Only one provider needed end-to-end; weakens the "second provider proves the abstraction" milestone.

### Q7. Prior art and naming

- **Nango** is an established OSS third-party OAuth token broker (grant lifecycle, refresh, large provider catalog). AgentGate's broker is a from-scratch subset of it.
  - **A (recommended). Build minimal, credit prior art.** The value proposition is the *assembly* — delegation + CIBA + FGA + brokering under one identity model — not the broker in isolation. Say so in the README; add a comparison row.
  - **B. Embed Nango.** Less code, but a heavyweight dependency, and check its current license terms before assuming it's embeddable in an Apache-2.0 project.
- **Name check:** "AgentGate" is likely collision-prone. Search GitHub/npm/PyPI and trademarks before the README ships.
- **Roadmap addition:** Okta/Auth0 are pushing **Cross App Access (XAA)** — implementing the IETF draft `draft-ietf-oauth-identity-assertion-authz-grant` (its token is the ID-JAG, Identity Assertion JWT Authorization Grant) — for app-to-app agent access in enterprises. At Auth0 it's in Early Access via Enterprise Connections (not GA). Worth a §10 bullet so the roadmap tracks where the commercial ecosystem is heading.

---

## Suggested priority order

1. **F1, F2, F3** — fix before any code; they're in the spec's normative sections.
2. **Q1, Q2, Q4** — the three decisions everything else hangs off.
3. **F5 + F8** — adopt the structured-approval design in v0; it protects the project's central thesis.
4. **F6 spike** in M0 — could delete the riskiest deliverable.
5. **F4, F7, Q3, Q5, Q6, Q7** — resolve as M1–M3 approach.
