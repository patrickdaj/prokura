# M7 spike — surface session + server-initiated CIBA

De-risks `close-correct-party-gaps` before any service change. Run with the
stack up:

```bash
.venv/bin/python spike/surface-session/drive.py
```

Proves (findings recorded in the change's `design.md` §"Spike findings"):

1. Authorization Code + PKCE login → signed HttpOnly session cookie →
   authorized POST, with the `#ref` fragment surviving the login round-trip
   inside the signed OAuth `state` (`websession.py` — the module that graduates
   into `services/approval/` and `services/token-broker/`).
2. Two surfaces on different localhost ports with distinct cookie names coexist
   in one browser jar (and share one Keycloak SSO session).
3. A **service-held** confidential client initiates CIBA and completes the full
   ceremony (delegate → decide → poll) with the agent side doing nothing —
   plus: the delegation POST is authenticated by a realm-signed JWT (SR-02
   mechanism), and the realm's `cibaExpiresIn` governs `expires_in` outright.

Creates throwaway `spike-*` clients via the admin API and uses alice's dev
password to drive the Keycloak form — allowed in spike code only (the smoke
kits lose all user credentials in task 7.2).
