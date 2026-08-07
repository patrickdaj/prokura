import base64, hashlib, secrets, httpx
from playwright.sync_api import sync_playwright
import flow_a  # reuse config + auth url build

c = httpx.Client(timeout=20.0)
client_id = flow_a.configure_consent(c)
v = flow_a.b64(secrets.token_bytes(32))
ch = flow_a.b64(hashlib.sha256(v.encode()).digest())
params = {"client_id": client_id, "response_type": "code", "redirect_uri": flow_a.REDIRECT,
          "scope": "openid", "state": secrets.token_urlsafe(8), "code_challenge": ch,
          "code_challenge_method": "S256", "resource": f"{flow_a.MCP}/mcp"}
auth_url = f"{flow_a.KC}/realms/{flow_a.REALM}/protocol/openid-connect/auth?" + str(httpx.QueryParams(params))

import re
with sync_playwright() as pw:
    b = pw.chromium.launch(); p = b.new_page()
    p.on("framenavigated", lambda f: print("NAV →", f.url[:90]) if f == p.main_frame else None)
    def on_route(route):
        print("ROUTE FIRED →", route.request.url[:90])
        route.fulfill(status=200, content_type="text/html", body="<h1>Delegation granted</h1>")
    p.route(re.compile(r"127\.0\.0\.1:9876/callback"), on_route)
    p.goto(auth_url, wait_until="networkidle")
    p.fill("#username", "alice"); p.fill("#password", "alice"); p.click("#kc-login")
    p.wait_for_selector("text=Grant Access", timeout=10000)
    print("--- clicking accept ---")
    p.click("#kc-login")
    p.wait_for_timeout(3000)
    print("FINAL URL:", p.url[:100])
    print("CONTENT HEAD:", re.sub(r"\s+", " ", p.content())[:300])
    b.close()
