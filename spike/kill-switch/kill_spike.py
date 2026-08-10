"""M9 spike — de-risk the kill switch before any service code.

Measures, against the live compose stack, the three revocation paths and the
residual the design turns on:

  (a) consent tuple delete  → time to the first denied broker hand-out
  (b) Keycloak revocation   → which API + minimal reach revokes an AGENT's
      sessions/refresh for one user (so a re-mint/refresh then fails) WITHOUT
      logging the human out — the load-bearing "can't re-acquire" move
  (c) in-flight residual    → a provider token issued just before revoke stays
      valid at the (mock) provider until its bounded TTL — reported, not hidden

Spike-quarantine: reuses the smoke kits (they drive the real login via humankit);
admin creds here PROVE the API, task 2.1 then wires the minimal role.

Usage:  .venv/bin/python spike/kill-switch/kill_spike.py
"""

import base64
import json
import sys
import time

sys.path.insert(0, "tests/smoke")

import httpx  # noqa: E402

import brokerkit  # noqa: E402
import humankit  # noqa: E402
from conftest import (  # noqa: E402
    DEMO_USER,
    KEYCLOAK_URL,
    REALM,
    admin_token,
    device_bootstrap,
    link_acme,
)

BROKER = "http://localhost:8110"
ADMIN = None


def claims(t: str) -> dict:
    p = t.split(".")[1]
    p += "=" * (-len(p) % 4)
    return json.loads(base64.urlsafe_b64decode(p))


def _admin() -> str:
    global ADMIN
    if ADMIN is None:
        ADMIN = admin_token()
    return ADMIN


def _user_id(username: str) -> str:
    r = httpx.get(f"{KEYCLOAK_URL}/admin/realms/{REALM}/users?username={username}",
                  headers={"Authorization": f"Bearer {_admin()}"}, timeout=10)
    r.raise_for_status()
    return r.json()[0]["id"]


def _sessions(uid: str) -> list:
    r = httpx.get(f"{KEYCLOAK_URL}/admin/realms/{REALM}/users/{uid}/sessions",
                  headers={"Authorization": f"Bearer {_admin()}"}, timeout=10)
    return r.json() if r.status_code == 200 else []


def _refresh(refresh_token: str) -> httpx.Response:
    return httpx.post(f"{KEYCLOAK_URL}/realms/{REALM}/protocol/openid-connect/token",
                      data={"grant_type": "refresh_token", "client_id": "agent-app",
                            "client_secret": "agent-app-dev-secret",
                            "refresh_token": refresh_token}, timeout=15)


def setup():
    link_acme(KEYCLOAK_URL)
    brokerkit.import_grant(brokerkit.broker_token(), "acme")
    brokerkit.seed_operator("agent-app", DEMO_USER)
    humankit.drive_consent("agent-app", "acme")


def path_a_tuple_delete():
    print("\n== (a) consent tuple delete → denied hand-out latency ==")
    bt = brokerkit.broker_token()
    r = httpx.post(f"{BROKER}/v1/tokens/acme", json={"scopes": []},
                   headers={"Authorization": f"Bearer {bt}"}, timeout=15)
    print(f"RESULT before delete: hand-out = {r.status_code}")
    t0 = time.monotonic()
    brokerkit.fga_write([{"user": "agent:agent-app", "relation": "can_use",
                          "object": f"grant:{DEMO_USER}/acme"}], delete=True)
    denied_ms = None
    for _ in range(50):
        r = httpx.post(f"{BROKER}/v1/tokens/acme", json={"scopes": []},
                       headers={"Authorization": f"Bearer {bt}"}, timeout=15)
        if r.status_code == 403:
            denied_ms = (time.monotonic() - t0) * 1000
            break
        time.sleep(0.02)
    print(f"RESULT (a) tuple-delete → first denied hand-out: {denied_ms:.0f} ms "
          f"(err={r.json().get('error')})")
    humankit.drive_consent("agent-app", "acme")  # restore


def path_b_keycloak_revocation():
    print("\n== (b) Keycloak revocation: kill the agent's refresh for one user ==")
    tok = device_bootstrap("agent-app", "agent-app-dev-secret",
                           scope="openid offline_access broker-audience")
    rt = tok.get("refresh_token")
    c = claims(tok["access_token"])
    print(f"RESULT agent-app token: sub={c.get('preferred_username')} "
          f"scope={tok.get('scope')} has_refresh={bool(rt)}")

    r = _refresh(rt)
    print(f"RESULT refresh BEFORE revoke: {r.status_code} "
          f"(new_access={'access_token' in r.json()})")
    rt = r.json().get("refresh_token", rt)  # rotation

    uid = _user_id(DEMO_USER)
    sess_before = len(_sessions(uid))

    # Candidate 1: revoke the user's consent for the agent client (targeted).
    d = httpx.delete(
        f"{KEYCLOAK_URL}/admin/realms/{REALM}/users/{uid}/consents/agent-app",
        headers={"Authorization": f"Bearer {_admin()}"}, timeout=10)
    print(f"RESULT DELETE users/{{id}}/consents/agent-app → {d.status_code}")

    r2 = _refresh(rt)
    err = r2.json().get("error", "") if r2.headers.get("content-type", "").startswith("application/json") else r2.text[:60]
    print(f"RESULT refresh AFTER consent-delete: {r2.status_code} err={err!r}  "
          f"→ {'STOPPED ✓' if r2.status_code != 200 else 'still works ✗'}")

    sess_after = len(_sessions(uid))
    print(f"RESULT human interactive sessions: before={sess_before} after={sess_after} "
          f"(logoutUserSessions NOT called — targeted at the agent client)")

    # If consent-delete didn't stop it, try the offline-session logout fallback.
    if r2.status_code == 200:
        lo = httpx.post(f"{KEYCLOAK_URL}/admin/realms/{REALM}/users/{uid}/logout",
                        headers={"Authorization": f"Bearer {_admin()}"}, timeout=10)
        print(f"RESULT fallback POST users/{{id}}/logout → {lo.status_code} "
              f"(broader; kills all sessions — note as trade-off)")
        r3 = _refresh(rt)
        print(f"RESULT refresh after logout: {r3.status_code}")


def path_c_residual():
    print("\n== (c) in-flight residual: issued provider token outlives revoke ==")
    humankit.drive_consent("agent-app", "acme")
    bt = brokerkit.broker_token()
    r = httpx.post(f"{BROKER}/v1/tokens/acme", json={"scopes": []},
                   headers={"Authorization": f"Bearer {bt}"}, timeout=15)
    if r.status_code != 200:
        print(f"RESULT could not obtain provider token: {r.status_code} {r.text[:100]}")
        return
    acme_at, ttl = r.json()["access_token"], r.json()["expires_in"]
    ui = httpx.get(f"{KEYCLOAK_URL}/realms/acme/protocol/openid-connect/userinfo",
                   headers={"Authorization": f"Bearer {acme_at}"}, timeout=10)
    print(f"RESULT provider token valid at acme BEFORE revoke: userinfo={ui.status_code} "
          f"(broker expires_in={ttl}s)")
    # revoke consent (tuple delete) — the broker path
    brokerkit.fga_write([{"user": "agent:agent-app", "relation": "can_use",
                          "object": f"grant:{DEMO_USER}/acme"}], delete=True)
    ui2 = httpx.get(f"{KEYCLOAK_URL}/realms/acme/protocol/openid-connect/userinfo",
                    headers={"Authorization": f"Bearer {acme_at}"}, timeout=10)
    print(f"RESULT same token AFTER revoke: userinfo={ui2.status_code}  "
          f"→ residual = the already-issued token stays valid until its ≤{ttl}s TTL "
          f"(mock acme has no revocation endpoint — reported honestly, not hidden)")
    humankit.drive_consent("agent-app", "acme")  # restore


def main() -> int:
    setup()
    path_a_tuple_delete()
    path_c_residual()          # residual first — uses a live session
    path_b_keycloak_revocation()  # destructive (revokes the agent's consent) — run last
    print("\nSPIKE DONE — record findings in design.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
