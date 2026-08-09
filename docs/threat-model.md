# Threat model

> Adversary-centric model of the assembled Prokura reference architecture (flows A–D
> + the MCP authorization surface). Companion to the control-centric
> [`security-review.md`](./security-review.md) (are the hard rules enforced?) and the
> decision records in [`adr/`](./adr/) (why each control exists). **Non-production**
> (docker-compose, dev secrets, no mTLS, single-node) throughout — accepted residuals
> are stated as such, not hidden.

## Trusted Computing Base (TCB)

Everything behind the compose network that can mint, broker, or gate credentials
is trusted:

- **Keycloak** — issues user/agent tokens, brokers third-party grants (Store
  Tokens), and is the sole identity authority.
- **Token Broker** — holds every third-party refresh credential (in OpenBao),
  performs provider refresh, and is the **sole writer of OpenFGA `can_use`
  tuples**. It enforces `operator == grant owner` at tuple-write time (the
  invariant is in broker code, not the FGA model — F1-A/Q3-B), and refuses +
  logs any cross-user write. A compromise of the broker compromises all grants;
  it is deliberately minimal and least-privileged (its OpenBao token is scoped to
  `secret/data/grants/*` only).
- **OpenBao** — the only store of long-lived provider credentials. Credentials
  are held in broker memory transiently during a refresh and never appear in any
  API response, log line, or audit record (asserted by
  `test_no_provider_token_in_logs`).
- **OpenFGA** — the per-agent consent authority (`can_use`). With Dynamic Client
  Registration enabled for MCP (M4), any client can register itself; the
  `can_use` tuple is the gate between a registered client and a user's grants.

- **Approval service** (M3) — the CIBA-gated human-approval authority. It holds
  the structured action payload and its hash, renders the human-facing approval
  surface itself (never agent-authored text), relays the human's decision to
  Keycloak's CIBA callback, and is the sole issuer + introspector of the
  single-use action token. It joins the TCB: a compromise could approve actions,
  so decisions are only accepted from an authenticated session and every
  register/delegate/decision/consume event is audited.
- **Tools-API** (M3) — the resource server for the gated `email.send` action. It
  is not fully trusted to *decide*, but it enforces the gate: audience check
  (M1 defense) plus hash-verify + single-use consume against the approval service
  before any action runs.
- **RAG retriever** (M5) — the resource server for FGA-filtered retrieval. It
  validates an `aud=rag-server` token and authorizes candidate chunks **as the end
  user** against OpenFGA; it never authorizes as the agent. Its correctness gates
  data disclosure, so it joins the TCB.

Agents and MCP clients are **outside** the TCB: an agent can obtain a provider
token only by presenting a broker-audience token (RFC 8693, `aud=token-broker`)
for a grant its user owns AND for which the user has consented to that specific
agent. The read-token capability that retrieves a Keycloak-stored credential
stays inside the broker (the broker re-exchanges the incoming token as its own
confidential client), so an agent can never retrieve a stored credential directly
from Keycloak's `/broker/{alias}/token` endpoint. Notification transport (ntfy)
and the tools-API's action-execution surface are outside the TCB.

## Assets

Every asset, where it lives, which TCB component owns it, and what its compromise enables:

| Asset | Store | Owning TCB component | Compromise enables |
|-------|-------|----------------------|--------------------|
| User identity / session | Keycloak (H2) | Keycloak | Full impersonation of the user across all flows |
| Delegated agent tokens (`aud=mcp-server` / `token-broker` / `agent-tools-api` / `rag-server`) | Bearer, agent-held, ≤900 s | Keycloak (mints) | Replay of the user's delegated authority for ≤15 min, within the token's audience only |
| Third-party **refresh** credentials | OpenBao `secret/data/grants/*` | Token Broker (sole reader) | Long-lived provider access (full blast radius of all grants) |
| Provider **access** tokens | Transient; returned to the requesting caller | Token Broker (mints per hand-out) | Provider access until expiry, for that provider/scope only |
| `can_use` consent tuples | OpenFGA | Token Broker (sole writer) | An agent gains standing access to a user's grant |
| Approval payloads + action tokens (`<ref>.<secret>`) | Approval Postgres | Approval service | Execution of a sensitive action the user did not approve |
| RAG corpus + `document` owner/viewer tuples | pgvector + OpenFGA | RAG retriever / broker-analog ingestor | Disclosure of documents to a user who may not see them |
| Audit records | Loki + service Postgres | each service | Repudiation (if forgeable) or loss of the accountability trail |

## Actors and attacker model

**Legitimate actors.** End user (e.g. `alice`, `bob`); the agent principal
(`azp=mcp-server`, inside no trust boundary of its own); a Dynamically-Registered MCP
client (the transport identity, untrusted).

**Adversary classes.** Every threat below names at least one of these; no threat
assumes an undefined attacker. Common boundary for **all**: none can forge Keycloak's
RS256 signatures, read OpenBao without the broker's scoped token, or write an OpenFGA
tuple except through broker code.

| # | Adversary | Assumed capabilities | Boundaries |
|---|-----------|----------------------|------------|
| A1 | **Compromised / malicious agent** | Holds a *valid* user-delegated `aud=mcp-server` token; can call any MCP tool; knows its own approval `ref`s (returned at `/register`) | Cannot mint tokens for other audiences it lacks the scope for; cannot approve its own actions |
| A2 | **Malicious MCP client (DCR)** | Can self-register (RFC 7591) and run OAuth 2.1 as a *consenting* user | Registration confers **no** trust; reaches user grants only after a `can_use` tuple exists |
| A3 | **On-network attacker** | Can send arbitrary requests to any service port on the compose network (no mTLS) | Cannot forge JWTs; cannot guess 96-bit `ref`s / topics; sees no secret in transit that isn't already gated |
| A4 | **Malicious grant-linking user** | A real user linking *their own* provider account and consenting *their own* agents | Confined to their own grants/tuples (`operator == owner` at write time) |
| A5 | **Curious / malicious insider** | Holds some legitimate access (a user session, a service on the network) | Bounded by the same authz as any user; cannot exceed the delegating user's reach |

## TTL honesty table

The broker caps every hand-out at **900 s** (`expires_in ≤ 900`), regardless of
the underlying provider token's real lifetime. Residual validity *beyond* the
hand-out interval is provider-controlled and is stated here honestly — the broker
never claims a provider token expires at 15 minutes.

| Provider | Wired in v0 | Hand-out cap | Provider-side residual validity | Refresh |
|----------|-------------|--------------|---------------------------------|---------|
| `acme` (mock realm) | yes | 900 s | access token 3600 s; refresh credential lives with the acme SSO session (set to 30 days in the mock realm so the demo grant stays usable — a real provider's refresh token is not Keycloak-session-bound) | yes (`supports_refresh: true`) |
| GitHub (GitHub App) | BYO extension | 900 s | user access token ~8 h | yes |
| Google | BYO extension | 900 s | access token ~1 h | yes |

**Scope narrowing:** `acme` declares `supports_scope_narrowing: false`. A
narrowing request within granted scopes returns the token with its *actual*
scopes and reports them honestly — the broker never fakes narrowing and never
silently widens.

## Trust boundaries

Every crossing where data or credentials pass between a less-trusted and a
more-trusted component, with the direction of trust and how the crossing is guarded:

| Crossing | Direction | Guard |
|----------|-----------|-------|
| agent/MCP-client → **MCP server** | untrusted → TCB | `aud=mcp-server` validated (JWKS/RS256); 401 challenge otherwise |
| MCP server → **Keycloak** (RFC 8693 exchange) | TCB → TCB | confidential-client auth; exchange permitted only per assigned audience client-scope |
| MCP server → **Token Broker** | TCB → TCB | `aud=token-broker` validated; inbound token never forwarded (re-exchanged) |
| MCP server → **tools-API** / **RAG** | TCB → TCB | `aud=agent-tools-api` / `aud=rag-server` validated; no passthrough |
| Token Broker → **OpenBao** | TCB → TCB | broker token scoped to `secret/data/grants/*` |
| Token Broker → **provider** (`acme`) | TCB → external | broker re-exchanges as its confidential client for the read-token |
| Token Broker → **OpenFGA** (write `can_use`) | TCB → TCB | broker is sole writer; `operator == owner` enforced in code |
| Keycloak CIBA channel → **Approval** `/ciba/delegate` | TCB → TCB | authenticated (M7): delegation bearer verified as a realm-signed JWT with `azp=approval-service`, body-size cap, 401 before parse — **SR-02 fixed** |
| Approval → **Keycloak** CIBA callback | TCB → TCB | bearer = Keycloak-issued delegation token; Keycloak validates |
| user browser → **Approval UI** `/decide` | user → TCB | authenticated Keycloak session; `row.user_id == sub` |
| RAG → **OpenFGA** (`batch_check`) | TCB → TCB | subject is `user:{end-user}`, never the agent |

## STRIDE per flow

Each cell is a concrete threat + its mitigation, or an explicit reasoned N/A. Adversary
classes in brackets.

### Flow A — delegated token exchange

| | Threat → mitigation |
|---|---|
| **S**poofing | Forged/replayed delegated token [A1/A3] → RS256 JWKS signature check + issuer + `aud` validation at every resource server; ≤900 s TTL bounds replay |
| **T**ampering | Token claim tampering [A1] → signature covers claims; any edit invalidates it |
| **R**epudiation | Agent denies an exchange it made → Keycloak realm events + broker audit carry `azp` + correlation id |
| **I**nfo disclosure | Token leak in transit/logs [A3] → no secret logged (`test_no_*_in_logs`); transient in memory; residual: no mTLS (accepted) |
| **D**oS | Token endpoint flooding [A3] → N/A for non-production (no rate-limit); accepted residual |
| **E**levation | Exchange for an audience the client isn't permitted [A1/A2] → audience appears only via an assigned audience client-scope; unlisted audience refused (probed) |

### Flow B — token brokering

| | Threat → mitigation |
|---|---|
| **S**poofing | Agent presents another user's/agent's token → `aud=token-broker` + signature; grant lookup keyed to token `sub` |
| **T**ampering | Requested scopes widened beyond grant [A1] → broker checks `requested ⊆ granted`; never widens, never fakes narrowing |
| **R**epudiation | Denies a brokered issuance → every issuance/denial audited with `{user,agent,provider,scopes,ttl}` + correlation id |
| **I**nfo disclosure | Agent reads a stored refresh credential [A1] → read-token stays in the broker (re-exchange as confidential client); OpenBao token scoped to `grants/*`; refresh never returned |
| **D**oS | Provider-refresh storm → N/A non-production; accepted residual |
| **E**levation | Agent uses a grant it isn't consented for [A1/A4] → `can_use` tuple gate; `operator == owner` at write time bars cross-user consent |

### Flow C — human approval

| | Threat → mitigation |
|---|---|
| **S**poofing | Forged approval decision / spoofed notification [A1/A3] → `/decide` requires an authenticated session with `sub == row.user_id`; ntfy is deny-all, per-user unguessable topics, notification carries only ref + deep link. `/ciba/delegate` authenticates its caller (realm-signed delegation JWT, `azp` = the approval service's own CIBA client — **SR-02 fixed, M7**) |
| **T**ampering | Agent alters the action after approval [A1] → tools-API hash-verifies `{action,params}` against the approved hash; mismatch refused (409) |
| **R**epudiation | User denies approving → every register/delegate/decide/consume audited with `ref` + correlation |
| **I**nfo disclosure | Agent-authored prose reaches the human, or params leak in the notification [A1] → UI renders service-held payload only; `binding_message` is a hex-only ref (`^apr-[0-9a-f]{24}$`); notification carries no params |
| **D**oS | Approval spam [A1] → the ceremony is initiated by the approval service on server-side registration (M7, ADR-0022); an agent can only spam the gated tool it is already authorized to call (audited); the 600 s CIBA window expires undecided ceremonies cleanly |
| **E**levation | Replay an approved action [A1] → approval service atomically consumes the ref (single-use); replay refused (409) |

### Flow D — FGA-filtered RAG

| | Threat → mitigation |
|---|---|
| **S**poofing | Caller-supplied user id to widen reach [A1] → identity derived only from a validated `aud=rag-server` token; no caller-supplied subject accepted |
| **T**ampering | Manipulate ranking to surface a protected doc [A1] → ranking is pre-authorization; the `batch_check` as the end user filters regardless of rank (adversarial test) |
| **R**epudiation | Deny a retrieval → `rag_audit` records `{user,candidates,allowed}` + correlation; never logs content |
| **I**nfo disclosure | Agent retrieves a doc the user can't see [A1] — **the confused-deputy** → FGA `batch_check` subject is the end user, not the agent; unauthorized top-hit never reaches the answer (attack tree 4) |
| **D**oS | Oversized query [A3] → **SR-03**: no size cap (accepted residual, offline linear-cost embedder) |
| **E**levation | Agent identity used to exceed user reach [A1] → agent-only / foreign-audience token returns **no chunks** |

### MCP authorization surface

| | Threat → mitigation |
|---|---|
| **S**poofing | Self-registered client impersonates a trusted one [A2] → DCR confers no trust; only an `aud=mcp-server` token results; grants still gated by `can_use` |
| **T**ampering | Tamper with PRM / AS metadata [A3] → served by the MCP server / Keycloak over the same origin as the token issuer; a tampered metadata host yields a token of the wrong `aud`, refused |
| **R**epudiation | Client denies a tool call → `mcp_audit` records tool + `azp=mcp-server` + correlation |
| **I**nfo disclosure | Inbound MCP token forwarded downstream [A1] → never forwarded; each tool re-exchanges (asserted for broker/tools/rag) |
| **D**oS | DCR registration spam [A2] → N/A non-production (localhost redirect policy); accepted residual |
| **E**levation | Registration → grant access without consent [A2] → **the** gate: registration alone reaches no grant; `can_use` required. Documented RFC 8707 gap: `resource` not reflected into `aud`, so audience is bound by the `mcp-audience` client scope instead |

## Attack trees for high-value targets

### 1. Token-broker compromise
**Goal:** exfiltrate all provider access. **Path:** RCE/creds on the broker container → use the in-process OpenBao token → read `secret/data/grants/*` → every user's refresh credential.
**Blast radius:** *all* grants + the broker is the sole `can_use` writer, so the attacker can also forge consent. **Bounding controls:** OpenBao token scoped to `grants/*` only (no root); broker holds no other user's session; refresh creds never leave OpenBao except transiently. **Residual:** broker is a concentrated point of trust — accepted for a single-node reference; production = isolation / per-tenant brokers / HSM-backed store. *Trusted-code assumption.*

### 2. `can_use` tuple forgery / cross-user write
**Goal:** grant an attacker's agent access to a victim's grant. **Paths:** (a) write the tuple directly in OpenFGA — blocked: **only broker code writes `can_use`**, and the model uses `can_use: [agent]` **direct assignment** (no relation chaining to forge through); (b) drive the broker's consent endpoint as the victim — blocked: broker enforces `operator == owner` (the consenting session must own the grant) and audits/refuses cross-user writes. **Breaking control:** sole-writer + `operator == owner` (code). **Residual:** broker compromise (tree 1) defeats it — a *trusted-code* assumption handed forward.

### 3. Approval spoofing / replay
**Goal:** execute a sensitive action without genuine approval. **Paths:**
- Forge a decision → blocked: `/decide` needs an authenticated session with `sub == row.user_id`.
- Spoof the notification → blocked: ntfy deny-all, unguessable per-user topic, no params in the payload; a fabricated publish changes no state.
- **Forge `/ciba/delegate`** → **closed (M7, SR-02 fixed):** the receiver verifies the delegation bearer as a realm-signed JWT whose `azp` is the approval service's own CIBA client before parsing anything; an unauthenticated or foreign-initiator call gets 401/403 and changes no state. (Historical impact was bounded to DoS of one approval; now it is nothing.)
- Replay an approved action → blocked: atomic single-use consume (409).

**Fixed (M7):** the `/ciba/delegate` caller is authenticated (realm-signed delegation JWT, `azp=approval-service`).

### 4. RAG confused-deputy over-sharing
**Goal:** make the agent surface a document the user may not see. **Path:** craft a query so a protected doc is the top embedding hit → the agent (high-privilege) retrieves it → hand it to the model. **Breaking control:** authorization is evaluated **as the end user** (`batch_check` subject `user:{sub}`) *after* ranking; the top hit is filtered when the user holds no `viewer` tuple — proven by `test_protected_doc_is_the_top_hit_but_never_leaks` (`allowed < candidates`). **Residual:** §11 acknowledges the demo-grade embedder and the seeded (vs live-Drive) corpus; neither weakens the enforcement path.

## Threat → disposition mapping

Every threat above resolves to a **mitigating control** (cited: a `security-baseline`
requirement / test / config) or an **accepted residual**. No orphan threats.

- Signature/audience/consent/hash/single-use/end-user-authz threats → mitigated,
  each with a `tests/smoke/` citation in [`security-review.md`](./security-review.md)
  (coverage matrix rows 2, 5, 7–11).
- **SR-01** (error-text leak), **SR-02** (`/ciba/delegate` auth), **SR-03** (no size
  cap) → open findings; SR-01/SR-02 recommended `fix` (v1), SR-03 accepted residual.
- DoS / no-mTLS / dev-secrets / broker concentration / stretched mock session → the
  residual register below.

## Residual-risk register (non-production posture)

| Residual | Why accepted | Production alternative |
|----------|--------------|------------------------|
| No mTLS between services | single-host compose, trusted loopback | mTLS / service mesh |
| Dev-mode secrets | documented, `.env`-confined, not committed | real secret store + rotation |
| Single-node, no HA | reference/demo | HA Keycloak / OpenFGA / OpenBao |
| Broker = concentrated point of trust | least-privilege (scoped token, `operator==owner`) bounds it; can't remove concentration single-node | isolation, per-tenant brokers, HSM |
| No rate-limiting (token/DCR/approval flooding) | non-production; not exposed to the internet | gateway rate limits |
| Mock `acme` session stretched to 30 days | demo convenience; stated in TTL table | real provider refresh/rotation |
| **SR-02** `/ciba/delegate` unauthenticated | **fixed (M7)** — caller verified via realm-signed delegation JWT + `azp` check + body cap | — |
| **SR-03** no `/rag/search` size cap | offline linear-cost embedder | explicit input bounds |

Code-enforced (not model/config) invariants named as **trusted-code assumptions**:
broker sole-writer + `operator == owner`; approval hash-binding + single-use. Their
compromise is reasoned about in attack trees 1–3.
