#!/usr/bin/env python3
"""Flow A capture — Delegation.

Drives a REAL authorization-code + PKCE login with an explicit consent screen,
screenshots each step into docs/walkthroughs/img/, then decodes the delegated
token to prove it is single-audience and short-lived.

Run:  .venv/bin/python demo/capture/flow_a.py
"""
import base64
import hashlib
import http.server
import json
import os
import secrets
import threading
import urllib.parse

import httpx
from playwright.sync_api import sync_playwright

KC = "http://localhost:8180"
REALM = "prokura"
MCP = "http://localhost:8140"
REDIRECT = "http://127.0.0.1:9876/callback"
IMG = os.path.join(os.path.dirname(__file__), "..", "..", "docs", "walkthroughs", "img")
IMG = os.path.abspath(IMG)
SCOPE_NAME = "act-on-your-behalf"
CONSENT_TEXT = "Act on your behalf — call tools and read documents you are authorized to see"

GRANTED_HTML = """<!doctype html><meta charset=utf-8><title>Signed in</title>
<style>body{margin:0;min-height:100vh;display:grid;place-items:center;background:#0b0d10;
color:#e7ebf0;font-family:-apple-system,Segoe UI,Roboto,sans-serif}.c{text-align:center}
.m{letter-spacing:.5em;color:#cfd6de;font-size:14px;margin-bottom:26px}.ok{font-size:44px;color:#4ade80}
h1{font-weight:600;font-size:20px;margin:14px 0 6px}p{color:#93a0ad;font-size:14px;max-width:40ch;
margin:0 auto;line-height:1.55}code{color:#d8a24a;font-family:ui-monospace,monospace}</style>
<div class=c><div class=m>PROKURA</div><div class=ok>&#10003;</div>
<h1>Delegation granted</h1><p>Alice authorized the agent. An authorization code was returned
to the agent's redirect (<code>?code=&hellip;</code>) — the agent now exchanges it for a
scoped, single-audience token.</p></div>"""


def b64(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def start_callback_server(caught):
    """A real listener on :9876 so the agent's redirect resolves cleanly and we
    capture the authorization code from a genuine HTTP response."""
    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            p = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            caught["code"] = p.get("code", [None])[0]
            caught["error"] = p.get("error", [None])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(GRANTED_HTML.encode())

    srv = http.server.HTTPServer(("127.0.0.1", 9876), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def admin_token(c):
    r = c.post(f"{KC}/realms/master/protocol/openid-connect/token",
               data={"grant_type": "password", "client_id": "admin-cli",
                     "username": "admin", "password": "admin"})
    r.raise_for_status()
    return r.json()["access_token"]


def configure_consent(c):
    """Idempotent: a consent-screen scope + a fresh client that requires it."""
    at = admin_token(c)
    A = {"Authorization": f"Bearer {at}"}
    scopes = c.get(f"{KC}/admin/realms/{REALM}/client-scopes", headers=A).json()
    scope = next((s for s in scopes if s["name"] == SCOPE_NAME), None)
    if not scope:
        c.post(f"{KC}/admin/realms/{REALM}/client-scopes", headers=A, json={
            "name": SCOPE_NAME, "protocol": "openid-connect",
            "description": "Delegated authority granted to the agent",
            "attributes": {"display.on.consent.screen": "true",
                           "consent.screen.text": CONSENT_TEXT,
                           "include.in.token.scope": "false"}}).raise_for_status()
        scopes = c.get(f"{KC}/admin/realms/{REALM}/client-scopes", headers=A).json()
        scope = next(s for s in scopes if s["name"] == SCOPE_NAME)
    reg = c.post(f"{KC}/realms/{REALM}/clients-registrations/openid-connect",
                 headers={"Content-Type": "application/json"},
                 json={"client_name": "Claude (MCP client)", "redirect_uris": [REDIRECT],
                       "token_endpoint_auth_method": "none",
                       "grant_types": ["authorization_code", "refresh_token"],
                       "response_types": ["code"]}).json()
    client_id = reg["client_id"]
    found = c.get(f"{KC}/admin/realms/{REALM}/clients", headers=A,
                  params={"clientId": client_id}).json()
    rep = found[0]
    rep["consentRequired"] = True
    c.put(f"{KC}/admin/realms/{REALM}/clients/{rep['id']}", headers=A, json=rep).raise_for_status()
    # attach the consent-screen scope to THIS client only (not realm-wide, which
    # would force a consent screen on every DCR client and break scripted logins).
    c.put(f"{KC}/admin/realms/{REALM}/clients/{rep['id']}/default-client-scopes/{scope['id']}",
          headers=A).raise_for_status()
    return client_id


def decode(seg):
    p = seg + "=" * (-len(seg) % 4)
    return json.loads(base64.urlsafe_b64decode(p))


def main():
    os.makedirs(IMG, exist_ok=True)
    c = httpx.Client(timeout=20.0)
    client_id = configure_consent(c)

    verifier = b64(secrets.token_bytes(32))
    challenge = b64(hashlib.sha256(verifier.encode()).digest())
    params = {"client_id": client_id, "response_type": "code", "redirect_uri": REDIRECT,
              "scope": "openid", "state": secrets.token_urlsafe(8),
              "code_challenge": challenge, "code_challenge_method": "S256",
              "resource": f"{MCP}/mcp"}
    auth_url = f"{KC}/realms/{REALM}/protocol/openid-connect/auth?" + str(httpx.QueryParams(params))

    caught = {}
    srv = start_callback_server(caught)
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1400, "height": 880}, device_scale_factor=2)

        # 1 — the real login page (the agent's delegation request)
        page.goto(auth_url, wait_until="networkidle")
        page.screenshot(path=os.path.join(IMG, "flowA-01-login.png"))

        # 2 — sign in as alice → the explicit consent screen
        page.fill("#username", "alice")
        page.fill("#password", "alice")
        page.click("#kc-login")
        page.wait_for_selector("text=Grant Access", timeout=10000)
        page.screenshot(path=os.path.join(IMG, "flowA-02-consent.png"))

        # 3 — grant → redirect intercepted → clean confirmation
        page.click("#kc-login")  # the "Yes" accept button on the consent form
        page.wait_for_selector("text=Delegation granted", timeout=10000)
        page.screenshot(path=os.path.join(IMG, "flowA-03-granted.png"))
        browser.close()
    srv.shutdown()

    assert caught.get("code"), f"no code caught: {caught}"

    # 4 — exchange the code (PKCE) and decode the delegated token
    tok = c.post(f"{KC}/realms/{REALM}/protocol/openid-connect/token", data={
        "grant_type": "authorization_code", "client_id": client_id, "code": caught["code"],
        "redirect_uri": REDIRECT, "code_verifier": verifier, "resource": f"{MCP}/mcp"}).json()
    claims = decode(tok["access_token"].split(".")[1])
    life = claims["exp"] - claims["iat"]
    result = {"sub": claims.get("preferred_username"), "azp": claims.get("azp"),
              "aud": claims.get("aud"), "scope": claims.get("scope"),
              "lifetime_s": life, "expires_in": tok.get("expires_in"),
              "client_id": client_id, "claims": claims}
    json.dump(result, open(os.path.join(os.path.dirname(__file__), "flow_a.result.json"), "w"), indent=2)
    print(json.dumps({k: result[k] for k in
          ("sub", "azp", "aud", "scope", "lifetime_s")}, indent=2))
    print("screenshots →", IMG)


if __name__ == "__main__":
    main()
