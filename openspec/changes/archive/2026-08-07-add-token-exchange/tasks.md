# Tasks: add-token-exchange (M1)

## 1. Keycloak exchange config (verify against 26.7.1)

- [x] 1.1 Confirm the standard token-exchange config for `agent-app` on the pinned image; determine whether audience `aud` claims require attaching `broker-audience`/`tools-audience` scopes and/or fine-grained exchange permissions
- [x] 1.2 Update `deploy/keycloak/realm-export.json`: per-(client, audience) exchange permissions for `agent-app` → {`agent-tools-api`, `token-broker`}, no wildcards; re-import and verify

## 2. SDK exchange()

- [x] 2.1 `sdk/prokura-py/` package skeleton (`pyproject.toml`, `prokura/__init__.py`, `prokura/exchange.py`)
- [x] 2.2 Implement `exchange(subject_token, audience, scopes, *, base_url, client_id, client_secret)` via httpx; return access token; no disk/log persistence
- [x] 2.3 Raise `ExchangeDenied` naming the audience on Keycloak permission refusal; distinct from transport errors

## 3. Tests (drive it)

- [x] 3.1 Integration test: login (reuse `drive_login`) → `exchange(...,"agent-tools-api",["tools:read"])`; assert `sub`=user, `azp`=agent-app, `aud` has agent-tools-api, scopes == requested
- [x] 3.2 Integration test: exchange to `token-broker`; assert `aud` has token-broker
- [x] 3.3 Negative test: exchange to an un-permitted audience raises `ExchangeDenied`
- [x] 3.4 Assert no token value in captured logs

## 4. Verify + wrap

- [x] 4.1 Full smoke + M1 tests green from the running stack
- [x] 4.2 Confirm the delegated exchange appears as a linked trace in the Console (observability DoD)
- [x] 4.3 Clean-slate `down -v && up`; whole suite green
