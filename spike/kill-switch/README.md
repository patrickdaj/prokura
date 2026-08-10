# spike/kill-switch — M9 de-risk (the kill switch)

Proves, against the live compose stack, the three revocation paths and the residual the
M9 design turns on, before any service code:

1. **(a) tuple delete → denied hand-out latency** — how fast the existing per-hand-out
   consent check denies once the `can_use` tuple is gone (~36 ms; already instant).
2. **(b) Keycloak revocation** — the load-bearing "can't re-acquire" move: which API +
   minimal reach revokes an *agent client's* sessions/refresh for one user (so a refresh
   then fails `400 invalid_grant`) **without** logging the human out. Finding:
   `DELETE /admin/realms/{realm}/users/{id}/consents/{agent-client}` (204), realm-management
   `manage-users`; kills online + offline refresh; human sessions untouched.
3. **(c) in-flight residual** — a provider token issued just before revoke stays valid at
   the mock provider until its TTL (no provider revocation endpoint); M9 bounds the TTL and
   reports the residual honestly.

## Run

    .venv/bin/python spike/kill-switch/kill_spike.py

`RESULT`/`SPIKE DONE` lines on success. Findings are recorded in the change's `design.md`.
Path (b) is destructive (revokes the agent's consent for alice); humankit re-consents on
the next test run.
