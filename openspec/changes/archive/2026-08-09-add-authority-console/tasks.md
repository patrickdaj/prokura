# Tasks: add-authority-console (M8)

## 1. Spike — aggregation + console-initiated linking (de-risk before service code)

- [x] 1.1 `spike/authority-agg/`: for one principal, join OpenFGA (`agent operator`
      + `can_use` tuples), approval rows, and Loki audit lines into one register
      view — prove the queries and the per-user Loki filter against the live stack
- [x] 1.2 Extend the spike: from an `authority-ui`-style confidential client, drive
      `kc_action=idp_link:acme` in a browser session (prompt=login + KC-26 confirm
      hop) and confirm which realm-role/scope grant makes `idp_link` legal for a
      non-`account` client
- [x] 1.3 Extend the spike: RFC 8693 exchange of a console session token into
      `aud=token-broker` and `aud=approval`, and prove the broker/approval accept
      the exchanged user-bound bearer (subject preserved)
- [x] 1.4 Record spike findings in the design doc (aggregation queries, idp_link
      client config, exchange audiences/scopes, Loki filter shape)

## 2. Realm fixtures (deploy/keycloak/realm-export.json)

- [x] 2.1 Add `authority-ui` confidential client (session; exact redirect URI for
      port 8160) and `authority-console` confidential client (token exchange enabled)
- [x] 2.2 Add `approval-audience` client scope (aud=approval) so the console can
      exchange for the approval read APIs; attach as optional to `authority-console`
      — plus the `approval` resource client the exchange audience resolves against,
      and an `aud=authority-console` mapper on `authority-ui` so its token is
      exchangeable (spike finding)
- [x] 2.3 `idp_link` needs no extra grant for `authority-ui` (spike 1.2 proved a
      plain confidential non-`account` client works); realm re-imports cleanly on
      `docker compose up --force-recreate keycloak`

## 3. Approval service — user-bound read APIs

- [x] 3.1 `GET /v1/my/approvals` (user-bound bearer, aud=approval): the token
      subject's pending + recent approvals; never another user's; no decision path
- [x] 3.2 `GET /v1/my/topic` (user-bound bearer): the subject's ntfy topic only;
      wrong-audience/invalid token refused before derivation
- [x] 3.3 Validation: approval-service audience check added to `validation.py`
      (`verify_bearer` + `WrongAudience`); decisions remain session-only

## 4. Broker — console read + bearer revoke

- [x] 4.1 `GET /v1/consents` (user-bound bearer, aud=token-broker): the subject's
      `can_use` grants with provider + scopes
- [x] 4.2 `/v1/consent/revoke` accepts a user-bound bearer (owner = verified
      subject) in addition to the M7 surface session; both converge on
      `consent.revoke_consent`; audit records the acting user and azp; revoke of a
      missing tuple is idempotent (200, not 500)
- [x] 4.3 Grant import reachable by the console: `POST /v1/grants/{provider}/import`
      already verifies `aud=token-broker` + owner=subject; the console's exchanged
      token satisfies it (confirmed in the link acceptance run, task 7.2)

## 5. Authority console service (services/authority/, port 8160)

- [x] 5.1 Scaffold: FastAPI app + `websession.py` (from M7, token-storing variant) +
      OIDC login/callback, `authority-ui` client, signed `prokura_authority_session`
      cookie (server-side token store keyed by sid); compose service on 8160
- [x] 5.2 Aggregation backend: `/api/register` reads FGA `operator` tuples + broker
      `/v1/consents` + approval `/v1/my/approvals` (broker/approval via exchanged
      user-bound tokens), assembled server-side for the session principal only
- [x] 5.3 Activity feed: `/api/activity` proxies Loki via Grafana, filtered
      server-side to the session user (username validated before entering LogQL)
- [x] 5.4 Actions: `POST /api/revoke/{agent}/{provider}` (exchange → broker bearer
      revoke); `GET /api/link/{provider}` (redirect into `kc_action=idp_link`) +
      `/api/link/callback` (exchange → broker import)
- [x] 5.5 Notification onboarding: `/api/topic` (exchange → approval `/v1/my/topic`);
      render topic + subscribe URL + QR (segno, server-side SVG — no external service)
- [x] 5.6 The panel (`index.html`): "my agents" register, per-agent revoke buttons,
      pending-approvals inbox deep-linking to :8120, connect-a-provider, topic/QR,
      activity feed — service-held data only, no URL-carried credentials

## 6. Tests

- [x] 6.1 humankit drives the console: real login on :8160, read the register,
      revoke an agent (button click), connect a provider (full idp_link ceremony),
      see the topic — the sanctioned simulated human, `test_authority_console.py`
- [x] 6.2 Mechanism tests (real session + exchanged/plain tokens): register
      aggregation correctness; console revoke == surface revoke (tuple-gone parity);
      the read APIs refuse decisions and the wrong audience
- [x] 6.3 Cross-principal isolation: bob's console never returns alice's agents,
      approvals, topic, or activity lines
- [x] 6.4 Separation invariant still holds: the authority service source contains no
      user password and no decide/CIBA call; `test_party_separation.py` extended
- [x] 6.5 Re-green the full smoke suite through the new surface (82 passed)

## 7. Verify, document, close

- [x] 7.1 **Acceptance run:** a signed-in human opened the console, read their
      register (agents, grants, approvals, activity, topic), and revoked agent-app
      via the UI — verified by looking (before/after screenshots), tuple gone in
      OpenFGA, `consent_revoked … azp=authority-console` line in Loki, and the
      revoked agent's next hand-out refused `403 not_consented`
- [x] 7.2 Provider-link acceptance: bob connected acme from the console (real
      browser idp_link ceremony) and the grant landed in his register — no admin API
      touched during the ceremony (`test_connect_provider_end_to_end`)
- [x] 7.3 Docs updated: architecture gap-table rows B-linking + topic-onboarding →
      closed (all 4 gaps closed) and M8 marked delivered; M8 blog
      (`docs/blog/m8-authority-console.html`) + blog index + landing cards (M7+M8) +
      walkthrough flowcard; `services/authority/README.md`
- [x] 7.4 New ADR-0023: the authority console as an aggregating trusted surface that
      relays the principal's own authority by token exchange (no new write authority);
      indexed in `docs/adr/README.md`
