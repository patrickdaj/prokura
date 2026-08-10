# spike/authority-agg — M8 de-risk (authority console)

Proves, against the live compose stack, the three mechanisms the authority
console depends on, before any service code:

1. **Aggregation** — join OpenFGA (`agent operator` + `can_use`), approval rows,
   and Loki audit lines into one register view for a single principal, and the
   per-user Loki filter (`|= "user=<username>"`).
2. **RFC 8693 exchange** — from the confidential `authority-console` client,
   exchange the signed-in user's `authority-ui` token into `aud=token-broker`
   and `aud=approval`, subject preserved, and prove the broker's audience gate
   accepts it.
3. **`idp_link`** — drive `kc_action=idp_link:acme` from the confidential
   (non-`account`) `authority-ui` client and confirm it is legal.

## Run

    .venv/bin/python spike/authority-agg/agg_spike.py

Exit 0 + `RESULT`/`SPIKE PASSED` on success. Passwords live here (spike-quarantine,
not an agent kit). Findings are recorded in the change's `design.md`.
