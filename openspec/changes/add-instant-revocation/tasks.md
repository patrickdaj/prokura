# Tasks: add-instant-revocation (M9 — The kill switch)

## 1. Spike — measure the three revocation paths + residual (de-risk before build)

- [ ] 1.1 `spike/kill-switch/`: against the live stack, measure path (a) — consent tuple
      delete → time to the first denied broker hand-out
- [ ] 1.2 Extend the spike: path (b) — revoke the agent client's Keycloak sessions/offline
      tokens for one user and prove a re-exchange as that agent for that user then fails;
      determine the exact Keycloak API + the **minimal** admin role, and that the human's
      own sessions are untouched
- [ ] 1.3 Extend the spike: path (c) — a broker deny-list entry → time to a refused
      hand-out; and the in-flight residual — issue a provider token, revoke everything,
      confirm it still works at the mock provider until its (bounded) TTL
- [ ] 1.4 Record spike findings in the design doc (measured latencies, the Keycloak
      revocation API/role, the honest TTL floor, the SET signing-key choice)

## 2. Realm fixtures (deploy/keycloak/realm-export.json)

- [ ] 2.1 Add a confidential admin-capable broker client (or grant the existing
      `token-broker` service account) exactly the minimal role the spike proved for
      targeted agent-client session/offline revocation — never `realm-admin`
- [ ] 2.2 Confirm `offline_access` is exercisable by the agent (so the spike's "re-acquire"
      path is real) and that revocation drops it; clean `docker compose up` re-imports

## 3. Broker — deny-list + continuous evaluation

- [ ] 3.1 `broker_denylist(agent, user_id, provider NULL, reason, azp, created_at)` table
      (idempotent DDL at startup) + db accessors (add/remove/match)
- [ ] 3.2 Hand-out chain: add step (5) deny-list check after the `can_use` check, before the
      provider is contacted; a null-provider entry denies all of the agent's grants
- [ ] 3.3 Lower the provider-token TTL cap to the spike's honest floor (config-driven,
      demo default 120s); `expires_in` reflects it

## 4. Broker — the kill fan-out

- [ ] 4.1 `services/token-broker/revocation.py` `kill(agent, user, provider, *, azp)`:
      tuple delete + deny-list write + Keycloak agent-client session/offline revocation for
      the user + timing; scoped to the agent, never the human's sessions
- [ ] 4.2 Wire both revoke paths (M7 consent-surface session + M8 console exchanged bearer)
      to `kill()`; re-granting consent clears the matching deny entry
- [ ] 4.3 Measure `stop_ms` (new-authority-denied latency) and compute the in-flight
      residual; return them from the revoke response and emit the metric with the trace id

## 5. CAEP / SSF signal

- [ ] 5.1 On `kill()`, build a signed Security Event Token (CAEP `session-revoked`, subject =
      agent-for-user + grant context) and log it to the audit stream (Loki-queryable)
- [ ] 5.2 `GET /ssf/stream` demo transmitter: in-memory subscribers receive the SET; a
      subscriber can read the revocation event

## 6. Console + dashboard surfacing

- [ ] 6.1 Authority console: `/api/revoke` returns the measured time-to-stop + residual, and
      the panel shows "denied in X ms; already-issued token expires within ≤ N s" (replacing
      the M8 next-hand-out note)
- [ ] 6.2 Operator dashboard (LGTM + `services/console`): a time-to-stop panel fed by
      `prokura.revocation.stop_ms`, joinable to the revoke trace/audit line

## 7. Tests

- [ ] 7.1 `tests/smoke/test_revocation.py`: kill-time measured; a revoked agent's offline
      token cannot re-mint/re-exchange (path b); the deny-list refuses re-issuance even with a
      stale tuple (path c); agent-wide (null-provider) kill refuses all grants
- [ ] 7.2 In-flight residual is honest: a token issued just before revoke still works until
      its bounded TTL, and the reported stop discloses it (no false "instant provider revoke")
- [ ] 7.3 The CAEP SET is emitted and a subscriber receives it; the event is in the audit
      stream with the revoke correlation id
- [ ] 7.4 Parity + isolation still hold: console revoke == surface revoke (now including the
      fan-out); revocation is scoped to the agent (human sessions untouched); M8 separation
      invariant unchanged
- [ ] 7.5 Re-green the full smoke suite through the new hand-out step and revoke path

## 8. Verify, document, close

- [ ] 8.1 **Acceptance run:** a signed-in human revokes an agent from the console — verified
      by looking (screenshots of the measured kill time + residual), the tuple gone, the
      deny entry present, the Keycloak re-exchange refused, the CAEP SET in Loki, and the
      dashboard time-to-stop panel showing the number
- [ ] 8.2 Update docs: architecture "kill switch" row / M9 marked delivered; the threat
      model TTL/residual note; broker + revocation READMEs
- [ ] 8.3 **M9 blog** (`docs/blog/m9-instant-revocation.html`) + blog index + landing card
- [ ] 8.4 **Walkthrough** (`docs/walkthroughs/revocation.html`) with live screenshots
      (register → revoke → measured stop + residual → dashboard panel) + index flowcard
- [ ] 8.5 New ADR: the kill fan-out (tuple + Keycloak session/offline + deny-list), the
      propagation-free deny-list, and the honest in-flight residual
