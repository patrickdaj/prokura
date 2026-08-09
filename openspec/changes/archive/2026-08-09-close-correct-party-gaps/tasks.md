# Tasks: close-correct-party-gaps (M7)

## 1. Spike — surface session + server-initiated CIBA (de-risk before any service change)

- [x] 1.1 `spike/surface-session/`: minimal FastAPI page with Keycloak Authorization
      Code + PKCE login and signed session cookie; prove login → callback → session →
      authorized POST against the live realm
- [x] 1.2 Extend the spike: two services on different localhost ports with distinct
      cookie names — prove both sessions coexist in one browser
- [x] 1.3 Extend the spike: initiate CIBA from a service-held confidential client
      (`login_hint=alice`, `binding_message=ref`) and complete the full ceremony
      (delegate callback → decide relay → poll) with the agent side doing nothing;
      confirm/raise the 30 s `cibaExpiresIn` realm clamp for human-latency decisions
- [x] 1.4 Record spike findings in the design doc (session pattern, cookie scoping,
      CIBA client config, clamp value)

## 2. Realm fixtures (deploy/keycloak/realm-export.json)

- [x] 2.1 Add `approval-ui` and `broker-ui` confidential clients (exact redirect URIs
      for ports 8120/8110) and an `approval-service` CIBA client (poll delivery);
      remove the CIBA grant from `agent-app`
- [x] 2.2 Configure the CIBA HTTP channel shared-secret header for the delegation
      receiver (SR-02) and set the agreed `cibaExpiresIn`
- [x] 2.3 Persist the `act-on-your-behalf` consent-screen scope + `consentRequired`
      per-client (agent-app; verify DCR-client interaction with the anonymous-DCR
      consent policy); delete the live-config path from `demo/capture/flow_a.py`
- [x] 2.4 Enable Device Authorization Grant on the realm and `agent-app`
- [x] 2.5 Clean-slate `docker compose up`: consent screen appears on first login with
      no out-of-band mutation (identity-delegation "cold start" scenario)

## 3. Approval service — session, server-initiated CIBA, SR-02

- [x] 3.1 Add `websession.py` (from spike) + OIDC login/callback routes; serve
      `/approvals` behind the session; `approval.html` drops `?token=`, stashes the
      `#ref` across the login round-trip via signed `state` (ref validated
      `^apr-[0-9a-f]+$`)
- [x] 3.2 `/approval/{ref}` and `/decide` authorize from the session (subject must be
      the approval's target user); URL-carried tokens ignored everywhere
- [x] 3.3 Initiate CIBA at `/register` (store `auth_req_id`, poll after decision,
      discard issued token); remove any expectation that a client drives the ceremony
- [x] 3.4 Authenticate + bound `/ciba/delegate` (shared-secret header, body-size cap,
      401 before parse)
- [x] 3.5 SR-01 sweep on approval + tools-api + broker + mcp error paths: stable error
      codes out, upstream detail to audit logs only

## 4. Broker — consent session

- [x] 4.1 Add `websession.py` + OIDC login/callback; serve `/consent` behind the
      session; `consent.html` drops `?token=`
- [x] 4.2 `POST /consent` and `/v1/consent/revoke` take the owner from the session
      subject; operator==owner write-guard now checks against the session identity

## 5. MCP server — challenge contract

- [x] 5.1 Update the 428 relay: response carries `{status, ref, action_token}` + a
      wait-and-retry message only; remove "complete CIBA" instructions from tool
      descriptions and README
- [x] 5.2 Verify no MCP path requires (or permits) agent-side ceremony participation

## 6. RAG — tuple reconciliation

- [x] 6.1 Decouple tuple-sync from the pgvector seed guard in `services/rag/ingest.py`;
      idempotent manifest→FGA reconciliation on startup
- [x] 6.2 Smoke test: reset the OpenFGA store, restart rag, previously-authorized query
      returns documents again without vector re-ingestion

## 7. Test-kit quarantine

- [x] 7.1 New `tests/smoke/humankit.py` (Playwright): real login + drive `/approvals`,
      `/consent`, and device-code verification as the labeled simulated human
- [x] 7.2 Strip `approvalkit`/`brokerkit`/`mcpkit` of `decide()`, `consent()`,
      `ciba_init()`, and all `DEMO_PASSWORD` use; agent-side bootstrap moves to the
      device flow
- [x] 7.3 Separation-invariant test: agent-side kits contain no user credential, no
      CIBA initiation, no decide/consent calls (grep-able assertion)
- [x] 7.4 Re-green the full smoke suite through the new party boundaries (reactive
      approval, single-use, hash-mismatch, consent grant/revoke, MCP chain)

## 8. Verify, document, close

- [x] 8.1 **The acceptance run:** from a real external MCP client (Claude Code), drive
      get_provider_token → send_email → 428 → human approves from the ntfy deep link
      in their own browser session → retry executes; zero in-repo credentials touched
      by the agent; verified by looking (Mailpit, Tempo trace, Loki audit,
      screenshots)
- [x] 8.2 Device-flow acceptance: headless smoke bootstrap with the human approving
      the user code in a browser session (humankit)
- [x] 8.3 Update docs: architecture gap table → closure checkmarks; threat-model Flow C
      agent-influenceable-trigger note resolves; security-review SR-01/SR-02 marked
      fixed; M7 blog (`docs/blog/m7-correct-parties.html`) + walkthrough refresh where
      the ceremony changed
- [x] 8.4 New ADR: server-initiated CIBA ceremony ownership (supersedes the
      client-initiated portion of ADR-0018's flow description)
