"""M2 spike — prove account linking (kc_action=idp_link:acme) works with the
realm-to-realm URL split, then retrieve the stored token and confirm it is
importable into OpenBao.

Runs headlessly against the live compose stack (no browser). Drives the full
ceremony: prokura login (fresh, prompt=login) -> idp_link required action ->
acme login -> broker callback (backchannel token exchange keycloak:8080) ->
link complete. Then retrieves the stored token via the Keycloak broker endpoint
and writes it to OpenBao.

Cookies are handled manually and keyed by realm path, because Keycloak marks
cookies Secure even on plain-HTTP dev and a shared jar both drops them and
collides on same-named per-realm cookies (AUTH_SESSION_ID etc).

Usage:  python link_spike.py
Exit 0 and prints RESULT lines on success.
"""

import base64
import hashlib
import html as html_mod
import os
import re
import secrets
import sys

import httpx

KC = os.environ.get("PROKURA_KEYCLOAK_URL", "http://localhost:8180")
BAO = os.environ.get("PROKURA_OPENBAO_URL", "http://localhost:8200")
BAO_TOKEN = os.environ.get("BROKER_BAO_TOKEN", "prokura-broker-dev-token")
USER, PW = "alice", "alice"
CLIENT_ID = "smoke-cli"
REDIRECT = "http://127.0.0.1/cb"
ALIAS = "acme"

_b64 = lambda b: base64.urlsafe_b64encode(b).rstrip(b"=").decode()  # noqa: E731


def _realm_of(url: str) -> str:
    m = re.search(r"/realms/([^/]+)/", url)
    return m.group(1) if m else "prokura"


def _merge_cookies(store: dict, url: str, resp: httpx.Response) -> None:
    realm = _realm_of(url)
    jar = store.setdefault(realm, {})
    for sc in resp.headers.get_list("set-cookie"):
        name, val = sc.split(";", 1)[0].split("=", 1)
        jar[name] = val


def _cookie_header(store: dict, url: str) -> str:
    jar = store.get(_realm_of(url), {})
    return "; ".join(f"{k}={v}" for k, v in jar.items())


def _form_action(html_text: str) -> str | None:
    m = re.search(r'id="kc-form-login"[^>]*action="([^"]+)"', html_text)
    return html_mod.unescape(m.group(1)) if m else None


def main() -> int:
    verifier = _b64(secrets.token_bytes(32))
    challenge = _b64(hashlib.sha256(verifier.encode()).digest())
    cookies: dict[str, dict] = {}

    with httpx.Client(follow_redirects=False, timeout=20.0) as c:
        # 1. Auth request with the idp_link application-initiated action.
        auth_url = f"{KC}/realms/prokura/protocol/openid-connect/auth"
        params = {
            "client_id": CLIENT_ID,
            "response_type": "code",
            "redirect_uri": REDIRECT,
            "scope": "openid",
            "state": "spike",
            "kc_action": f"idp_link:{ALIAS}",
            "prompt": "login",  # linking is sensitive -> force fresh auth
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
        r = c.get(auth_url, params=params)
        _merge_cookies(cookies, auth_url, r)
        assert r.status_code == 200, f"auth GET {r.status_code}: {r.text[:300]}"
        action = _form_action(r.text)
        assert action, "no prokura login form"
        print("HOP 1  prokura login page rendered")

        # 2. Submit prokura credentials -> should 302 toward the acme IdP.
        r = c.post(
            action,
            data={"username": USER, "password": PW},
            headers={"Cookie": _cookie_header(cookies, action)},
        )
        _merge_cookies(cookies, action, r)
        assert r.status_code in (302,303,307), f"prokura login {r.status_code}: {r.text[:300]}"
        loc = r.headers["location"]
        print(f"HOP 2  prokura login -> 302 {loc[:90]}")

        # 3..N. Follow redirects within Keycloak, filling the acme login form
        #        when we reach it, until we land back on the client redirect.
        acme_login_done = False
        for hop in range(3, 12):
            if loc.startswith(REDIRECT) or loc.startswith("http://127.0.0.1"):
                break
            url = loc if loc.startswith("http") else KC + loc
            r = c.get(url, headers={"Cookie": _cookie_header(cookies, url)})
            _merge_cookies(cookies, url, r)
            if r.status_code in (301, 302, 303, 307):
                loc = r.headers["location"]
                print(f"HOP {hop}  302 -> {loc[:90]}")
                continue
            if r.status_code == 200 and "login-actions/required-action" in url \
                    and 'name="continue"' in r.text:
                # Keycloak 26 idp_link confirmation: "Do you want to link ...?"
                action = re.search(r'<form[^>]*action="([^"]+)"', r.text)
                assert action, "no confirm form action"
                action = html_mod.unescape(action.group(1))
                print(f"HOP {hop}  link-confirmation page -> accepting (continue)")
                r = c.post(action, data={"continue": ""},
                           headers={"Cookie": _cookie_header(cookies, action)})
                _merge_cookies(cookies, action, r)
                assert r.status_code in (302,303,307), f"confirm {r.status_code}: {r.text[:300]}"
                loc = r.headers["location"]
                print(f"HOP {hop}  confirm -> 302 {loc[:90]}")
                continue
            if r.status_code == 200 and "/realms/acme/" in url and not acme_login_done:
                action = _form_action(r.text)
                assert action, f"no acme login form at {url}: {r.text[:200]}"
                print(f"HOP {hop}  acme login page rendered")
                r = c.post(
                    action,
                    data={"username": USER, "password": PW},
                    headers={"Cookie": _cookie_header(cookies, action)},
                )
                _merge_cookies(cookies, action, r)
                acme_login_done = True
                assert r.status_code in (302,303,307), f"acme login {r.status_code}: {r.text[:300]}"
                loc = r.headers["location"]
                print(f"HOP {hop}  acme login -> 302 {loc[:90]}")
                continue
            # Unexpected interstitial (e.g. review-profile). Surface it.
            print(f"HOP {hop}  UNEXPECTED {r.status_code} at {url}")
            import pathlib
            pathlib.Path("/tmp/interstitial.html").write_text(r.text)
            forms = re.findall(r'<form[^>]*action="([^"]+)"[^>]*>', r.text)
            print("  forms:", [html_mod.unescape(f) for f in forms])
            print("  links:", re.findall(r'href="([^"]*(?:broker|link|idp)[^"]*)"', r.text)[:5])
            print("  meta-refresh:", re.findall(r'http-equiv="refresh"[^>]*content="([^"]+)"', r.text))
            return 2

        assert loc.startswith("http://127.0.0.1"), f"did not land on client redirect: {loc}"
        final = httpx.URL(loc)
        status = final.params.get("kc_action_status")
        print(f"FINAL  {loc[:120]}")
        print(f"RESULT link kc_action_status = {status}")
        if status != "success":
            return 3

    # Link succeeded. Now prove stored-token retrieval + OpenBao import.
    return retrieve_and_import()


def retrieve_and_import() -> int:
    """Log in as alice (agent-app is confidential; use smoke-cli public) to get a
    user access token carrying the broker read-token role, call the broker token
    endpoint, and import the credential into OpenBao."""
    # Fresh login (no kc_action) to get a normal user token.
    verifier = _b64(secrets.token_bytes(32))
    challenge = _b64(hashlib.sha256(verifier.encode()).digest())
    cookies: dict[str, dict] = {}
    with httpx.Client(follow_redirects=False, timeout=20.0) as c:
        auth_url = f"{KC}/realms/prokura/protocol/openid-connect/auth"
        r = c.get(auth_url, params={
            "client_id": CLIENT_ID, "response_type": "code", "redirect_uri": REDIRECT,
            "scope": "openid", "state": "tok", "code_challenge": challenge,
            "code_challenge_method": "S256",
        })
        _merge_cookies(cookies, auth_url, r)
        if r.status_code == 302:  # already have SSO session from the link flow
            loc = r.headers["location"]
        else:
            action = _form_action(r.text)
            assert action, "no login form for token retrieval"
            r = c.post(action, data={"username": USER, "password": PW},
                       headers={"Cookie": _cookie_header(cookies, action)})
            assert r.status_code in (302,303,307), f"login {r.status_code}: {r.text[:300]}"
            loc = r.headers["location"]
        code = httpx.URL(loc).params["code"]
        tok = c.post(f"{KC}/realms/prokura/protocol/openid-connect/token", data={
            "grant_type": "authorization_code", "client_id": CLIENT_ID,
            "code": code, "redirect_uri": REDIRECT, "code_verifier": verifier,
        })
        assert tok.status_code == 200, tok.text
        access = tok.json()["access_token"]
        print("RESULT got prokura user access token")

        # Retrieve the stored acme token via the Keycloak broker endpoint.
        br = c.get(f"{KC}/realms/prokura/broker/{ALIAS}/token",
                   headers={"Authorization": f"Bearer {access}"})
        print(f"RESULT broker/{ALIAS}/token -> {br.status_code}")
        if br.status_code != 200:
            print("  body:", br.text[:400])
            return 4
        stored = br.json()
        has_refresh = "refresh_token" in stored and bool(stored["refresh_token"])
        print(f"RESULT stored token keys = {sorted(stored.keys())}")
        print(f"RESULT has_refresh_token = {has_refresh}")
        cred = stored.get("refresh_token") or stored.get("access_token")
        assert cred, f"no importable credential in {stored.keys()}"

        # Import into OpenBao at the grant path.
        path = f"{BAO}/v1/secret/data/grants/{USER}/{ALIAS}"
        payload = {"data": {
            "credential": cred,
            "kind": "refresh_token" if has_refresh else "access_token",
            "scopes": stored.get("scope", ""),
        }}
        w = c.post(path, json=payload, headers={"X-Vault-Token": BAO_TOKEN})
        print(f"RESULT openbao write -> {w.status_code}")
        assert w.status_code in (200, 204), w.text
        rb = c.get(path, headers={"X-Vault-Token": BAO_TOKEN})
        assert rb.status_code == 200, rb.text
        got = rb.json()["data"]["data"]
        print(f"RESULT openbao read back kind = {got.get('kind')}, "
              f"credential_len = {len(got.get('credential',''))}")
    print("\nSPIKE PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
