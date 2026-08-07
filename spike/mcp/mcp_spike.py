"""M4 spike: prove a dynamically-registered MCP client can complete the OAuth 2.1
+ PKCE handshake against Keycloak and inspect how the RFC 8707 `resource` param
maps to the token audience."""
import base64, hashlib, html, re, secrets, json, sys, httpx

KC = "http://localhost:8180"
REALM = "prokura"
MCP_RESOURCE = "http://localhost:8140/mcp"   # planned MCP server canonical URI
REDIRECT = "http://127.0.0.1:9876/callback"
b64 = lambda x: base64.urlsafe_b64encode(x).rstrip(b"=").decode()

def claims(t):
    p = t.split(".")[1]; p += "=" * (-len(p) % 4)
    return json.loads(base64.urlsafe_b64decode(p))

with httpx.Client(follow_redirects=False, timeout=20.0) as c:
    # 1. Dynamic Client Registration (RFC 7591), anonymous
    reg = c.post(f"{KC}/realms/{REALM}/clients-registrations/openid-connect",
        headers={"Content-Type": "application/json"},
        json={"client_name": "mcp-spike-client", "redirect_uris": [REDIRECT],
              "token_endpoint_auth_method": "none",
              "grant_types": ["authorization_code", "refresh_token"], "response_types": ["code"]})
    print("DCR ->", reg.status_code)
    if reg.status_code != 201:
        print(reg.text[:300]); sys.exit(1)
    client_id = reg.json()["client_id"]
    print("  dynamic client_id:", client_id)

    # 2. OAuth 2.1 authorization code + PKCE, with RFC 8707 resource param
    verifier = b64(secrets.token_bytes(32)); challenge = b64(hashlib.sha256(verifier.encode()).digest())
    auth = c.get(f"{KC}/realms/{REALM}/protocol/openid-connect/auth", params={
        "client_id": client_id, "response_type": "code", "redirect_uri": REDIRECT,
        "scope": "openid", "state": "s", "code_challenge": challenge,
        "code_challenge_method": "S256", "resource": MCP_RESOURCE})
    cookies = dict(sc.split(";",1)[0].split("=",1) for sc in auth.headers.get_list("set-cookie"))
    m = re.search(r'id="kc-form-login"[^>]*action="([^"]+)"', auth.text)
    print("  auth page:", auth.status_code, "login form:", bool(m))
    r = c.post(html.unescape(m.group(1)), data={"username": "alice", "password": "alice"},
               headers={"Cookie": "; ".join(f"{k}={v}" for k,v in cookies.items())})
    loc = r.headers.get("location", "")
    print("  login ->", r.status_code, "redirects to callback:", loc.startswith(REDIRECT))
    code = httpx.URL(loc).params.get("code")

    # 3. token request (with resource param)
    tok = c.post(f"{KC}/realms/{REALM}/protocol/openid-connect/token", data={
        "grant_type": "authorization_code", "client_id": client_id, "code": code,
        "redirect_uri": REDIRECT, "code_verifier": verifier, "resource": MCP_RESOURCE})
    print("  token ->", tok.status_code)
    if tok.status_code != 200:
        print(tok.text[:300]); sys.exit(2)
    at = tok.json()["access_token"]
    cl = claims(at)
    print("\n=== access token claims ===")
    print("  azp:", cl.get("azp"))
    print("  aud:", cl.get("aud"))
    print("  scope:", cl.get("scope"))
    print(f"\nRFC 8707 check — resource {MCP_RESOURCE!r} reflected in aud: "
          f"{MCP_RESOURCE in (cl.get('aud') if isinstance(cl.get('aud'),list) else [cl.get('aud')])}")
print("\nMCP SPIKE: DCR + OAuth 2.1 + PKCE handshake complete")
