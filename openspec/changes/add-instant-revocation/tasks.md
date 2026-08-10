# Tasks: add-instant-revocation (M9 — The kill switch)

## 1. Spike — measure the three revocation paths + residual (de-risk before build)

- [x] 1.1 `spike/kill-switch/`: against the live stack, measure path (a) — consent tuple
      delete → time to the first denied broker hand-out (~36 ms; already instant)
- [x] 1.2 Extend the spike: path (b) — CONFIRMED `DELETE users/{id}/consents/{agent-client}`
      (204) → agent refresh `400 invalid_grant`, human sessions untouched; minimal role =
      realm-management `manage-users` (kills online + offline refresh alike)
- [x] 1.3 Extend the spike: in-flight residual — a provider token issued before revoke stays
      valid at mock acme (no revocation endpoint) until its TTL; M9 bounds TTL (120 s) and
      reports it. (Deny-list latency is an in-process DB check — sub-ms, built in Phase 3.)
- [x] 1.4 Record spike findings in the design doc (measured latencies, the Keycloak
      revocation API/role, the honest TTL floor; SET signing-key deferred to build)

## 2. Realm fixtures (deploy/keycloak/realm-export.json)

- [x] 2.1 Granted the existing `token-broker` service account realm-management
      `manage-users` (service-account-token-broker user in realm-export); verified the
      broker's own client-credentials token is accepted by the admin API and can call
      `DELETE users/{id}/consents/{agent-client}` (404 when no consent = a clean no-op)
- [x] 2.2 The agent's refresh token (online; agent-app is not granted `offline_access`) is
      revoked by the consent-delete — spike (b) proved refresh → `400 invalid_grant` after,
      so the "re-acquire" path is real and closed. Clean `docker compose up` re-imports.

## 3. Broker — deny-list + continuous evaluation

- [x] 3.1 `broker_denylist(agent, user_id, provider NULL, reason, azp, created_at)` table
      (idempotent DDL at startup) + db accessors (add/remove/match)
- [x] 3.2 Hand-out chain: add step (5) deny-list check after the `can_use` check, before the
      provider is contacted; a null-provider entry denies all of the agent's grants
- [x] 3.3 Lower the provider-token TTL cap to the spike's honest floor (config-driven,
      demo default 120s); `expires_in` reflects it

## 4. Broker — the kill fan-out

- [x] 4.1 `services/token-broker/revocation.py` `kill(agent, user, provider, *, azp)`:
      tuple delete + deny-list write + Keycloak agent-client session/offline revocation for
      the user + timing; scoped to the agent, never the human's sessions
- [x] 4.2 Wire both revoke paths (M7 consent-surface session + M8 console exchanged bearer)
      to `kill()`; re-granting consent clears the matching deny entry
- [x] 4.3 Measure `stop_ms` (new-authority-denied latency) and compute the in-flight
      residual; return them from the revoke response and emit the metric with the trace id

## 5. CAEP / SSF signal

- [x] 5.1 On `kill()`, build a signed Security Event Token (CAEP `session-revoked`, subject =
      agent-for-user + grant context) and log it to the audit stream (Loki-queryable)
- [x] 5.2 `GET /ssf/stream` demo transmitter: in-memory subscribers receive the SET; a
      subscriber can read the revocation event

## 6. Console + dashboard surfacing

- [x] 6.1 Authority console: `/api/revoke` returns the measured time-to-stop + residual, and
      the panel shows "denied in X ms; already-issued token expires within ≤ N s" (replacing
      the M8 next-hand-out note)
- [x] 6.2 Operator dashboard (LGTM + `services/console`): a time-to-stop panel fed by
      `prokura.revocation.stop_ms`, joinable to the revoke trace/audit line

## 7. Tests

- [x] 7.1 `tests/smoke/test_revocation.py`: kill-time measured; the revoked grant cannot be
      re-acquired with a fresh token (deny-list blocks it); the deny-list refuses even with a
      stale tuple; agent-wide (null-provider) deny refuses all grants. (Path-b Keycloak
      session/offline revocation is the agent-wide kill — proven in `spike/kill-switch`.)
- [x] 7.2 In-flight residual is honest: a token issued just before revoke still works until
      its bounded TTL, and the reported stop discloses it (no false "instant provider revoke")
- [x] 7.3 The CAEP SET is emitted and readable on `/ssf/stream`; the signed token carries the
      `session-revoked` event + subject, with the revoke correlation id in the audit stream
- [x] 7.4 Parity + isolation still hold: M8 console revoke == surface revoke (now the kill),
      per-grant revoke is scoped (session + other grants untouched); M8 separation invariant
      unchanged (both verified by the green M8 suite)
- [x] 7.5 Re-green the full smoke suite through the new hand-out step and revoke path
      (88 passed)

## 8. Verify, document, close

- [x] 8.1 **Acceptance run:** a signed-in human revokes an agent from the console — verified
      by looking (screenshots of the measured kill time + residual), the tuple gone, the
      deny entry present, the Keycloak re-exchange refused, the CAEP SET in Loki, and the
      dashboard time-to-stop panel showing the number
- [x] 8.2 Update docs: architecture "kill switch" row / M9 marked delivered; the threat
      model TTL/residual note; broker + revocation READMEs
- [x] 8.3 **M9 blog** (`docs/blog/m9-instant-revocation.html`) + blog index + landing card
- [x] 8.4 **Walkthrough** (`docs/walkthroughs/revocation.html`) with live screenshots
      (register → revoke → measured stop + residual → dashboard panel) + index flowcard
- [x] 8.5 New ADR: the kill fan-out (tuple + Keycloak session/offline + deny-list), the
      propagation-free deny-list, and the honest in-flight residual
