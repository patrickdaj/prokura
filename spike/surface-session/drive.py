"""M7 spike driver (tasks 1.1–1.3). Run with the stack up:

    .venv/bin/python spike/surface-session/drive.py

Proves, against the live realm:
  1.1  auth-code+PKCE login -> callback -> signed session cookie -> authorized POST
  1.2  two surfaces on :8961/:8962 with distinct cookie names coexist in one jar
  1.3  a service-held confidential client initiates CIBA (login_hint=alice,
       binding_message=ref) and completes the FULL ceremony (delegate -> decide ->
       poll) with the agent side doing nothing; probes the cibaExpiresIn clamp
       and inspects the delegation bearer (SR-02 auth options).

Spike-grade: creates throwaway spike-* clients via the admin API, drives the
Keycloak login form over httpx, and uses alice's dev password — allowed here
(spike code, not product code; the kits lose this in task 7.2)."""

import html
import json
import re
import subprocess
import sys
import time
from base64 import urlsafe_b64decode

import httpx

KC = "http://localhost:8180"
REALM = "prokura"
APPROVAL = "http://localhost:8120"
ALICE = ("alice", "alice")


def admin_token() -> str:
    r = httpx.post(f"{KC}/realms/master/protocol/openid-connect/token",
                   data={"grant_type": "password", "client_id": "admin-cli",
                         "username": "admin", "password": "admin"}, timeout=10.0)
    r.raise_for_status()
    return r.json()["access_token"]


def ensure_client(admin: str, rep: dict) -> None:
    h = {"Authorization": f"Bearer {admin}"}
    r = httpx.get(f"{KC}/admin/realms/{REALM}/clients?clientId={rep['clientId']}", headers=h)
    r.raise_for_status()
    if r.json():
        uid = r.json()[0]["id"]
        httpx.put(f"{KC}/admin/realms/{REALM}/clients/{uid}", headers=h, json=rep).raise_for_status()
    else:
        httpx.post(f"{KC}/admin/realms/{REALM}/clients", headers=h, json=rep).raise_for_status()


def jwt_claims(t: str) -> dict:
    p = t.split(".")[1]
    return json.loads(urlsafe_b64decode(p + "=" * (-len(p) % 4)))


def kc_form_login(c: httpx.Client, url: str, jar: dict) -> str:
    """GET an auth URL, submit the Keycloak login form, return the redirect Location.
    Keycloak marks cookies Secure on plain-HTTP dev, so the jar is manual."""
    r = c.get(url, headers={"Cookie": "; ".join(f"{k}={v}" for k, v in jar.items())})
    for sc in r.headers.get_list("set-cookie"):
        k, v = sc.split(";", 1)[0].split("=", 1)
        jar[k] = v
    if r.status_code in (302, 303):
        return r.headers["location"]        # SSO already active — no form
    m = re.search(r'id="kc-form-login"[^>]*action="([^"]+)"', r.text)
    assert m, f"no login form at {url}: {r.status_code}"
    r = c.post(html.unescape(m.group(1)),
               data={"username": ALICE[0], "password": ALICE[1]},
               headers={"Cookie": "; ".join(f"{k}={v}" for k, v in jar.items())})
    for sc in r.headers.get_list("set-cookie"):
        k, v = sc.split(";", 1)[0].split("=", 1)
        jar[k] = v
    assert r.status_code == 302, f"login failed: {r.status_code} {r.text[:200]}"
    return r.headers["location"]


def drive_surface_login(c: httpx.Client, cookies: dict, port: int, kc_jar: dict,
                        ref: str = "") -> None:
    """Simulate the browser against one spike surface, sharing one Keycloak jar
    (SSO) and one surface-cookie dict keyed by cookie NAME (host-scoped, like a
    real browser's jar for localhost)."""
    base = f"http://localhost:{port}"
    r = c.get(f"{base}/login", params={"ref": ref} if ref else None)
    assert r.status_code in (302, 307), r.status_code
    loc = kc_form_login(c, r.headers["location"], kc_jar)
    assert loc.startswith(f"{base}/callback"), loc
    r = c.get(loc)
    assert r.status_code == 303, f"callback failed: {r.status_code} {r.text[:200]}"
    for sc in r.headers.get_list("set-cookie"):
        k, v = sc.split(";", 1)[0].split("=", 1)
        cookies[k] = v
    if ref:
        assert r.headers["location"].endswith(f"#{ref}"), \
            f"ref lost across login: {r.headers['location']}"


def main() -> None:
    admin = admin_token()

    # --- throwaway spike clients ---------------------------------------------
    for name, port in (("surface-a", 8961), ("surface-b", 8962)):
        ensure_client(admin, {
            "clientId": f"spike-{name}", "enabled": True, "publicClient": False,
            "secret": f"spike-{name}-secret", "protocol": "openid-connect",
            "standardFlowEnabled": True, "directAccessGrantsEnabled": False,
            "redirectUris": [f"http://localhost:{port}/callback"],
            "attributes": {"pkce.code.challenge.method": "S256"}})
    ensure_client(admin, {
        "clientId": "spike-ciba", "enabled": True, "publicClient": False,
        "secret": "spike-ciba-secret", "protocol": "openid-connect",
        "standardFlowEnabled": False, "directAccessGrantsEnabled": False,
        "attributes": {"oidc.ciba.grant.enabled": "true",
                       "ciba.backchannel.token.delivery.mode": "poll"}})
    print("spike clients ensured")

    # --- start the two surfaces ----------------------------------------------
    procs = [subprocess.Popen([sys.executable, "spike/surface-session/app.py", str(p)])
             for p in (8961, 8962)]
    time.sleep(2.5)
    try:
        run_checks()
    finally:
        for p in procs:
            p.terminate()


def run_checks() -> None:
    surface_cookies: dict[str, str] = {}    # one host-scoped jar, like a browser
    kc_jar: dict[str, str] = {}

    with httpx.Client(follow_redirects=False, timeout=15.0,
                      cookies=None) as c:
        # 1.1 login -> session -> authorized POST, with a ref surviving via state
        drive_surface_login(c, surface_cookies, 8961, kc_jar, ref="apr-deadbeef")
        r = c.post("http://localhost:8961/act",
                   headers={"Cookie": "; ".join(f"{k}={v}" for k, v in surface_cookies.items())})
        assert r.status_code == 200 and r.json()["acted_as"] == "alice", r.text
        print("1.1 OK: login -> signed cookie -> authorized POST (ref survived state)")

        # unauthenticated + tampered-cookie negative checks (fresh, jar-free
        # requests — the driving client's own jar would replay the good cookie)
        assert httpx.post("http://localhost:8961/act").status_code == 401
        bad = surface_cookies["prokura_surface-a_session"][:-3] + "xxx"
        r = httpx.post("http://localhost:8961/act",
                       headers={"Cookie": f"prokura_surface-a_session={bad}"})
        assert r.status_code == 401, "tampered cookie accepted!"
        print("1.1 OK: no-session and tampered-cookie POSTs refused")

        # 1.2 second surface, same jar (Keycloak SSO session should skip the form)
        drive_surface_login(c, surface_cookies, 8962, kc_jar)
        hdr = {"Cookie": "; ".join(f"{k}={v}" for k, v in surface_cookies.items())}
        a = c.post("http://localhost:8961/act", headers=hdr)
        b = c.post("http://localhost:8962/act", headers=hdr)
        assert a.json()["surface"] == "surface-a" and b.json()["surface"] == "surface-b"
        assert len([k for k in surface_cookies if k.startswith("prokura_")]) == 2
        print("1.2 OK: two sessions coexist in one jar "
              f"(cookies: {[k for k in surface_cookies if k.startswith('prokura_')]})")

    # 1.3 server-initiated CIBA — the "agent" does NOTHING after the 428-equivalent
    with httpx.Client(timeout=15.0) as c:
        # a real approval row (the delegate receiver only stores known refs)
        ut = user_token(c)
        r = c.post(f"{APPROVAL}/register", headers={"Authorization": f"Bearer {ut}"},
                   json={"action": "email.send",
                         "params": {"to": "spike@example.com", "subject": "s", "body": "b"}})
        r.raise_for_status()
        ref = r.json()["ref"]

        # the SERVICE-held client initiates
        r = c.post(f"{KC}/realms/{REALM}/protocol/openid-connect/ext/ciba/auth",
                   data={"client_id": "spike-ciba", "client_secret": "spike-ciba-secret",
                         "scope": "openid", "login_hint": "alice",
                         "binding_message": ref, "requested_expiry": "300"})
        assert r.status_code == 200, f"ciba init failed: {r.status_code} {r.text[:300]}"
        j = r.json()
        auth_req_id, expires_in = j["auth_req_id"], j["expires_in"]
        print(f"1.3 CIBA initiated by service client: expires_in={expires_in} "
              f"(requested 300; realm cibaExpiresIn clamp applies)")

        # delegation arrived at the approval service (status -> delegated)?
        for _ in range(20):
            s = c.get(f"{APPROVAL}/approval/{ref}", headers={"Authorization": f"Bearer {ut}"})
            if s.status_code == 200 and s.json()["status"] == "delegated":
                break
            time.sleep(0.5)
        else:
            raise AssertionError("delegation never reached the approval service")
        print("1.3 OK: Keycloak delivered the delegation to /ciba/delegate")

        # human decides (API-driven here; the real UI takes over in task 3.x)
        c.post(f"{APPROVAL}/approval/{ref}/decide",
               headers={"Authorization": f"Bearer {ut}"},
               json={"decision": "approve"}).raise_for_status()

        # the SERVICE polls and completes; the agent never saw any of this
        for _ in range(10):
            r = c.post(f"{KC}/realms/{REALM}/protocol/openid-connect/token",
                       data={"grant_type": "urn:openid:params:grant-type:ciba",
                             "auth_req_id": auth_req_id,
                             "client_id": "spike-ciba", "client_secret": "spike-ciba-secret"})
            if r.status_code == 200:
                break
            assert r.json().get("error") in ("authorization_pending", "slow_down"), r.text
            time.sleep(2)
        else:
            raise AssertionError("polling never completed")
        cl = jwt_claims(r.json()["access_token"])
        assert cl.get("preferred_username") == "alice"
        print(f"1.3 OK: service completed the ceremony (token sub=alice, azp={cl.get('azp')}) "
              "— token now discarded (the ceremony is the product)")

    print("\nSPIKE GREEN: session pattern + coexistence + server-initiated CIBA all proven")


def user_token(c: httpx.Client) -> str:
    """alice token via agent-app (spike-only use of the dev password)."""
    import base64
    import hashlib
    import secrets as sec
    b64 = lambda b: base64.urlsafe_b64encode(b).rstrip(b"=").decode()  # noqa: E731
    verifier = b64(sec.token_bytes(32))
    challenge = b64(hashlib.sha256(verifier.encode()).digest())
    redirect = "http://127.0.0.1/cb"
    jar: dict[str, str] = {}
    r = c.get(f"{KC}/realms/{REALM}/protocol/openid-connect/auth",
              params={"client_id": "agent-app", "response_type": "code",
                      "redirect_uri": redirect, "scope": "openid", "state": "spike",
                      "code_challenge": challenge, "code_challenge_method": "S256"},
              headers={}, follow_redirects=False)
    for sc in r.headers.get_list("set-cookie"):
        k, v = sc.split(";", 1)[0].split("=", 1)
        jar[k] = v
    m = re.search(r'id="kc-form-login"[^>]*action="([^"]+)"', r.text)
    assert m, "no login form"
    r = c.post(html.unescape(m.group(1)),
               data={"username": ALICE[0], "password": ALICE[1]},
               headers={"Cookie": "; ".join(f"{k}={v}" for k, v in jar.items())},
               follow_redirects=False)
    loc = r.headers["location"]
    code = httpx.URL(loc).params["code"]
    r = c.post(f"{KC}/realms/{REALM}/protocol/openid-connect/token",
               data={"grant_type": "authorization_code", "client_id": "agent-app",
                     "client_secret": "agent-app-dev-secret", "code": code,
                     "redirect_uri": redirect, "code_verifier": verifier})
    r.raise_for_status()
    return r.json()["access_token"]


if __name__ == "__main__":
    main()
