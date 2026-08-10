# Tasks: add-authority-console (M8)

## 1. Spike — aggregation + console-initiated linking (de-risk before service code)

- [ ] 1.1 `spike/authority-agg/`: for one principal, join OpenFGA (`agent operator`
      + `can_use` tuples), approval rows, and Loki audit lines into one register
      view — prove the queries and the per-user Loki filter against the live stack
- [ ] 1.2 Extend the spike: from an `authority-ui`-style confidential client, drive
      `kc_action=idp_link:acme` in a browser session (prompt=login + KC-26 confirm
      hop) and confirm which realm-role/scope grant makes `idp_link` legal for a
      non-`account` client
- [ ] 1.3 Extend the spike: RFC 8693 exchange of a console session token into
      `aud=token-broker` and `aud=approval`, and prove the broker/approval accept
      the exchanged user-bound bearer (subject preserved)
- [ ] 1.4 Record spike findings in the design doc (aggregation queries, idp_link
      client config, exchange audiences/scopes, Loki filter shape)

## 2. Realm fixtures (deploy/keycloak/realm-export.json)

- [ ] 2.1 Add `authority-ui` confidential client (session; exact redirect URI for
      port 8160) and `authority-console` confidential client (token exchange enabled)
- [ ] 2.2 Add `approval-audience` client scope (aud=approval) so the console can
      exchange for the approval read APIs; attach as optional to `authority-console`
- [ ] 2.3 Grant `authority-ui` whatever the spike proved is needed for `idp_link`
      (manage-account reach / client scope); clean-slate `docker compose up` verifies

## 3. Approval service — user-bound read APIs

- [ ] 3.1 `GET /v1/my/approvals` (user-bound bearer, aud=approval): the token
      subject's pending + recent approvals; never another user's; no decision path
- [ ] 3.2 `GET /v1/my/topic` (user-bound bearer): the subject's ntfy topic only;
      wrong-audience/invalid token refused before derivation
- [ ] 3.3 Validation: approval-service audience check added to `validation.py`;
      decisions remain session-only (assert no bearer can decide)

## 4. Broker — console read + bearer revoke

- [ ] 4.1 `GET /v1/consents` (user-bound bearer, aud=token-broker): the subject's
      `can_use` grants with provider + scopes
- [ ] 4.2 `/v1/consent/revoke` accepts a user-bound bearer (owner = verified
      subject) in addition to the M7 surface session; both converge on
      `consent.revoke_consent`; audit records the acting user and azp
- [ ] 4.3 Grant import reachable by the console: confirm `POST /v1/grants/{provider}/import`
      accepts the console's exchanged user-bound token (owner = subject)

## 5. Authority console service (services/authority/, port 8160)

- [ ] 5.1 Scaffold: FastAPI app + `websession.py` (from M7) + OIDC login/callback,
      `authority-ui` client, signed `prokura_authority_session` cookie; compose
      service on 8160; realm client wired
- [ ] 5.2 Aggregation backend: `/api/register` reads FGA tuples + broker `/v1/consents`
      + approval `/v1/my/approvals` (all via exchanged user-bound tokens), assembled
      server-side for the session principal only
- [ ] 5.3 Activity feed: `/api/activity` proxies Loki via Grafana, filtered
      server-side to the session user; cross-user isolation enforced in the backend
- [ ] 5.4 Actions: `POST /api/revoke/{agent}/{provider}` (exchange → broker bearer
      revoke); `GET /api/link/{provider}` (redirect into `kc_action=idp_link`) +
      `/api/link/callback` (exchange → broker import)
- [ ] 5.5 Notification onboarding: `/api/topic` (exchange → approval `/v1/my/topic`);
      render topic + subscribe URL + client-side QR
- [ ] 5.6 The panel (`index.html`): "my agents" register, per-agent revoke buttons,
      pending-approvals inbox deep-linking to :8120, connect-a-provider, topic/QR,
      activity feed — service-held data only, no URL-carried credentials

## 6. Tests

- [ ] 6.1 humankit drives the console: real login on :8160, read the register,
      revoke an agent, connect a provider, see the topic (labeled simulated human)
- [ ] 6.2 Mechanism tests (direct httpx with exchanged tokens): register aggregation
      correctness; console revoke == surface revoke (tuple-gone parity + same audit);
      approval read API refuses decisions and wrong audiences
- [ ] 6.3 Cross-principal isolation: bob's console never returns alice's agents,
      approvals, topic, or activity lines
- [ ] 6.4 Separation invariant still holds: the authority service source contains no
      user password and no decide/CIBA call; extend `test_party_separation.py`
- [ ] 6.5 Re-green the full smoke suite through the new surface

## 7. Verify, document, close

- [ ] 7.1 **Acceptance run:** a signed-in human opens the console, reads their
      register (agents, grants, pending approvals, activity, topic), and revokes an
      agent — verified by looking (screenshots, tuple gone in OpenFGA, audit line in
      Loki, the revoked agent's next hand-out refused)
- [ ] 7.2 Provider-link acceptance: a real person connects a provider from the
      console and the grant appears in the register (no admin API touched)
- [ ] 7.3 Update docs: architecture gap-table row B-linking → closed; M8 blog
      (`docs/blog/m8-authority-console.html`) + walkthrough addition; console README
- [ ] 7.4 New ADR: the authority console as an aggregating trusted surface that
      relays the principal's own authority by token exchange (no new write authority)
