# Tasks: establish-v02-baseline (M0 skeleton + CIBA spike)

## 1. Repository scaffold

- [x] 1.1 Create repo layout per SPEC.md §7 adjusted for decisions: drop `extensions/keycloak-ciba-ntfy/` (pending spike verdict), add `services/approval/` placeholder, name everything Prokura
- [x] 1.2 Write root `README.md` stub: Prokura positioning line ("registered power of attorney for AI agents"), non-production disclaimer, Nango prior-art credit with comparison row placeholder
- [x] 1.3 Add `.env.example` and confirm no secrets in compose or repo (SPEC.md §9)

## 2. Compose stack

- [x] 2.1 `docker-compose.yml` with pinned images: Keycloak 26.4+, OpenFGA, OpenBao (dev mode), Postgres, self-hosted ntfy (auth enabled), Mailpit
- [x] 2.2 Keycloak realm export `deploy/keycloak/realm-export.json`: realm `prokura`, demo user, agent client(s) with explicit per-(client, audience) token-exchange permissions, token lifetime ≤ 15 min, CIBA enabled
- [x] 2.3 OpenFGA model `deploy/openfga/model.fga` with the corrected direct-assignment `can_use` relation (F1-A) and types user/agent/grant/document/tool; loaded automatically at startup
- [x] 2.4 OpenBao init script `deploy/openbao/init.sh`: KV v2 mount, broker policy, dev-token documented as non-production
- [x] 2.5 ntfy config: ACLs on, per-user topic scheme documented, anonymous publish/subscribe disabled

## 3. Smoke tests

- [x] 3.1 Test harness (pytest) that waits for stack health and runs against compose
- [x] 3.2 Smoke: OIDC login via Authorization Code + PKCE returns a user token with realm issuer
- [x] 3.3 Smoke: OpenFGA model loaded — write a `can_use` tuple and a check query answers true; invalid-model regression guard (model file must load cleanly)
- [x] 3.4 Smoke: OpenBao KV write/read via broker policy token succeeds; root token not used
- [x] 3.5 Smoke: Mailpit receives SMTP; ntfy rejects anonymous publish

## 4. CIBA HTTP-channel spike (F6-A — decides M3 shape)

- [x] 4.1 Configure `--spi-ciba-auth-channel--ciba-http-auth-channel--http-authentication-channel-uri` pointing at a minimal FastAPI endpoint
- [x] 4.2 Initiate a backchannel auth request (`/ext/ciba/auth`) with a conformant reference-ID `binding_message`; verify the FastAPI endpoint receives the delegation POST including the binding message and bearer token
- [x] 4.3 Return SUCCEED via Keycloak's CIBA callback endpoint using the delegation bearer token; verify the agent's token poll completes; repeat for UNAUTHORIZED (denial) and timeout
- [x] 4.4 Record the spike verdict in `design.md` Open Questions (works → delete Java SPI from plan; fails → document failure mode and scope the SPI fallback)

## 5. Wrap-up

- [x] 5.1 All smoke tests green from a clean `docker-compose up` on a fresh clone
- [x] 5.2 Update `design.md` with the pinned Keycloak image and spike verdict; note any spec deltas the spike forces
- [x] 5.3 Demoable artifact check: one command brings up the stack; README quickstart section describes it
