# Security Review — Prokura reference architecture

**Lens:** control-centric — *does the assembled system enforce its own hard rules?*
(The adversary-centric view is [`threat-model.md`](./threat-model.md); the decisions
behind the controls are in [`adr/`](./adr/).)

**Scope / posture.** End-to-end review of the docker-compose stack (Keycloak, token
broker, approval service, tools-api, console, OpenFGA, OpenBao, telemetry) against the
`security-baseline` capability spec. The deployment is **explicitly non-production**
(single-node, dev-mode secrets, no mTLS, no HA); the success criterion is *accurate
disclosure of residual risk*, not zero findings. An `accepted-residual` disposition is
a first-class outcome.

**Reviewed against commit** `f0750bd` (post-M5 working tree). Evidence is one of:
**T** test citation (`tests/smoke/`), **C** config/code assertion (`file:line`), or
**P** a documented live probe. Cited locations were re-confirmed against the current
tree.

---

## Findings register

| id | invariant | severity | disposition | evidence |
|----|-----------|----------|-------------|----------|
| SR-01 | External surfaces leak nothing on error | Low | **fixed (M7)** | P — a malformed/garbage bearer surfaces the underlying `jwt`/codec exception text in the 401 body (`"invalid token: Invalid header string: 'utf-8' codec can't decode byte 0x9e…"`). Leaks library/impl detail (no secret). Same `f"invalid token: {e}"` pattern in broker/approval/rag/tools validation. Fix: return a generic `invalid token` without the exception string. |
| SR-02 | Every state-changing inter-service call is authenticated | Low | **fixed (M7)** | P+C — `services/approval/app.py:88` `/ciba/delegate` does not authenticate that the caller is Keycloak. For a known (unguessable, 96-bit) `ref` in `pending`, an unauthenticated caller can win the once-only `pending→delegated` transition (`db.py:81`) with a caller-supplied `delegation_token` later replayed to Keycloak's callback. **Impact bounded to DoS** of that one approval — not spoofing: the decision still requires the real user's authenticated `/decide`, and Keycloak validates the delegation token on the callback. Fix: verify the inbound channel bearer is Keycloak-signed. Handed to threat model (F7). |
| SR-03 | External surfaces validate/bound input | Low | **accepted-residual** | P — no explicit request-size cap on `/rag/search` `query` (200 KB accepted and embedded). Bounded by the offline embedder's linear cost; non-production. v1: add a size bound. |

No High or Medium findings. All other baseline invariants **pass** with the evidence
below. The two `fix` findings logged here (SR-01, SR-02) were **closed in M7**
(`close-correct-party-gaps`); SR-03 remains an accepted residual.

---

## Coverage matrix — every `security-baseline` requirement has a disposition

| # | baseline requirement | disposition | evidence |
|---|----------------------|-------------|----------|
| 1 | **TCB explicit & minimal** — Keycloak, broker, approval, OpenFGA, OpenBao in; agents, MCP/DCR clients, ntfy, tools-api execution surface out | **pass** | C — TCB matches `security-baseline`; T — a DCR'd MCP client gains no grant without a `can_use` tuple (`test_mcp_chain.py`, `test_consent.py`); registration ≠ trust |
| 2 | **Every state-changing inter-service call authenticated** | **pass** | P — broker no-auth→401, wrong-aud→403, garbage→401; tools-api no-token→401; rag no-token→401. C — bearer+JWKS+`aud` check in each service's `validation.py`. `/ciba/delegate` authenticated since M7 (SR-02 fixed). |
| 3 | **Secrets never appear outside their store** | **pass** | T — `test_no_provider_token_in_logs.py`, `test_no_action_token_in_logs.py`; C — refresh creds only in OpenBao (`grants.py`), broker returns access token only (`app.py:108`, no refresh_token); P — no secret in probed success/error bodies |
| 4 | **Repo contains no committed secret** | **pass** | P — `.env` untracked (git); only documented non-production dev values in `docker-compose.yml` / realm export; `.env.example` is the template |
| 5 | **Agent-held tokens ≤ 15 min** | **pass** | C — realm `accessTokenLifespan=900`; broker `MAX_TTL_SECONDS=900`; P — issued mcp/rag tokens `exp−iat = 900s`; broker hand-out `expires_in ≤ 900` |
| 6 | **Residual provider validity stated honestly** | **pass** | C — TTL-honesty table in `threat-model.md` (mock `acme` 30-day session stated, not claimed as 15 min) |
| 7 | **Token exchange never wildcarded** | **pass** | P — `mcp-server`→unlisted audience → 400; C — audience only appears when the matching audience client-scope (assigned per client) is requested; no client can mint an arbitrary `aud` |
| 8 | **Agent cannot reach provider read-token audience** | **pass** | C — `broker-read-token` scope + broker re-exchange as its confidential client; agents lack the scope; P — broker refuses a wrong-audience token |
| 9 | **Data-access authz evaluated as the end user** | **pass** | T — `test_rag_authorization.py` (M5): FGA `batch_check` subject is `user:{end-user}`; adversarial top-hit filtered for a non-viewer; agent identity insufficient |
| 10 | **Every credential/approval decision audit-logged w/ correlation** | **pass** | T — `test_broker_audit.py`, `test_telemetry.py`; C — `audit.py` in broker/approval/mcp/rag emits `{user,agent,action/provider,scopes,ttl/outcome}` + correlation id; one linked trace verified in M4/M5 |
| 11 | **External surfaces validate input & leak nothing on error** | **pass** (+ SR-03) | P — rag missing-field→400 generic; broker error body carries no stack trace/secret; stable machine codes everywhere since M7 (SR-01 fixed). SR-03 (size cap) remains logged |
| 12 | **Non-production posture & residual risk stated honestly** | **pass** | C — posture documented in README/threat-model; residual register below; trusted-code assumptions named |

---

## Flow coverage (A delegation · B brokering · C approval · D RAG · MCP surface)

- **A delegation / B brokering** — broker enforces JWKS signature + `aud=token-broker`, grant existence, scope subset, per-agent `can_use` consent, before contacting the provider (`services/token-broker/app.py:61`). Sole OpenBao reader; token scoped to `secret/data/grants/*`.
- **C approval** — `binding_message` is `apr-`+`token_hex(12)` (`^apr-[0-9a-f]{24}$`, hex-only, injection-safe); UI renders **service-held** payload only (`app.py:114`); `consume` verifies action-token, `status==approved`, CIBA-token subject == owner, payload hash, and atomic single-use (`app.py:146`). T — `test_human_approval.py`, `test_reactive_approval.py`. SR-02 fixed in M7.
- **D RAG** — authorizes as `user:{sub}` from a validated `aud=rag-server` token; inbound MCP token never forwarded. T — `test_rag_authorization.py`, `test_rag_mcp.py`.
- **MCP surface** — DCR self-registration confers no trust; `aud=mcp-server` validated; each tool re-exchanges (no passthrough). T — `test_mcp_authorization.py`, `test_mcp_chain.py`.

---

## Trusted-code assumptions (enforced in service code, not a declarative model)

- **Broker is the sole `can_use` tuple writer and enforces `operator == owner`** at write time (`services/token-broker/consent.py`, `fga.py`). The FGA model uses `can_use: [agent]` **direct assignment** (`deploy/openfga/model.fga:13`) — no cross-object joins — so the *only* path to a `can_use` tuple is broker code. Broker compromise ⇒ tuple forgery. → threat model attack tree.
- **Approval single-use / hash-binding** is enforced in `consume` (code), not a model. → threat model.

## Accepted residual risks (non-production posture)

| residual | why accepted (non-prod) | production alternative |
|----------|-------------------------|------------------------|
| No mTLS between services | single-host compose, trusted loopback network | mTLS / service mesh |
| Dev-mode secrets (`*-dev-secret`, dev root token) | documented, `.env`-confined, not committed | real secret store, rotation |
| Single-node, no HA | reference/demo | HA Keycloak/OpenFGA/OpenBao |
| Broker = concentrated point of trust (all grants + sole tuple writer) | least-privilege posture (scoped OpenBao token, operator==owner) bounds it; cannot eliminate concentration single-node | isolation, per-tenant brokers, HSM-backed store |
| Mock `acme` provider session stretched to 30 days | demo convenience; stated in TTL table, not misrepresented | real provider refresh/rotation |
| SR-03 no request-size cap on `/rag/search` | offline embedder, linear cost, non-prod | explicit input bounds |

---

## Test-coverage gaps (`test-gap`)

- **SR-02** — **fixed (M7):** `/ciba/delegate` verifies the delegation bearer (realm-signed JWT, `azp=approval-service`) before parsing, with a body cap; covered by the M7 verification (unauthenticated/garbage/oversized → 401 before parse).
- **SR-01** — **fixed (M7):** every service maps errors to stable machine codes (`{"error": "invalid_token"}` etc.); library/upstream detail goes to audit logs only. Probed across approval/tools-api/broker in the M7 verification.

## Disposition summary

12/12 baseline requirements have a recorded disposition; **all pass**, with **3 Low
findings** (SR-01, SR-02 → **fixed in M7**; SR-03 → `accepted-residual`) and the
residual-risk register above. Control weaknesses (the trusted-code assumptions) are handed to
[`threat-model.md`](./threat-model.md) as attack paths; the decisions behind the
controls (F1 sole-writer, F2 audience, F5/F7/F8 approval, §11 confused-deputy) are
handed to [`adr/`](./adr/).
