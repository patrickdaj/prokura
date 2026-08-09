"""Browser session for a trusted surface (M7, D2): Authorization Code + PKCE
against Keycloak with this surface's confidential client; the callback sets a
signed, HttpOnly, SameSite=Lax cookie holding {sub, preferred_username, exp}.

The session is a claim cache, not a credential store — no tokens are kept. The
OAuth ``state`` is HMAC-signed and round-trips an optional approval ref across
the login (the ``#fragment`` never reaches the server; page JS passes it to
/login, D3). Cookie names are per-surface: localhost cookies are host-scoped,
not port-scoped, so two surfaces sharing a name would clobber each other
(spike finding S2).

Proven in spike/surface-session/ before graduating here; the token broker
carries the same module per the repo's per-service-module convention."""

import base64
import hashlib
import hmac
import json
import secrets
import time
from urllib.parse import urlencode

import httpx


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


class WebSession:
    def __init__(self, *, issuer_public: str, issuer_internal: str, client_id: str,
                 client_secret: str, redirect_uri: str, cookie_name: str,
                 secret: str, max_age: int = 1800):
        self.issuer_public = issuer_public        # browser-facing (auth redirect)
        self.issuer_internal = issuer_internal    # service-side (token endpoint)
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.cookie_name = cookie_name
        self.key = secret.encode()
        self.max_age = max_age
        self._pkce: dict[str, str] = {}           # state -> verifier (in-memory)

    # -- signing ---------------------------------------------------------------
    def _sign(self, payload: dict) -> str:
        body = _b64(json.dumps(payload, separators=(",", ":")).encode())
        mac = _b64(hmac.new(self.key, body.encode(), hashlib.sha256).digest())
        return f"{body}.{mac}"

    def _verify(self, blob: str) -> dict | None:
        try:
            body, mac = blob.split(".", 1)
            want = _b64(hmac.new(self.key, body.encode(), hashlib.sha256).digest())
            if not hmac.compare_digest(mac, want):
                return None
            return json.loads(_unb64(body))
        except Exception:
            return None

    # -- login flow ------------------------------------------------------------
    def login_url(self, ref: str = "") -> str:
        verifier = _b64(secrets.token_bytes(32))
        challenge = _b64(hashlib.sha256(verifier.encode()).digest())
        state = self._sign({"n": secrets.token_hex(8), "ref": ref, "t": int(time.time())})
        self._pkce[state] = verifier
        if len(self._pkce) > 1000:                # drop oldest half; demo-grade bound
            for k in list(self._pkce)[:500]:
                self._pkce.pop(k, None)
        return f"{self.issuer_public}/protocol/openid-connect/auth?" + urlencode({
            "client_id": self.client_id, "response_type": "code",
            "redirect_uri": self.redirect_uri, "scope": "openid",
            "state": state, "code_challenge": challenge,
            "code_challenge_method": "S256"})

    def handle_callback(self, code: str, state: str) -> tuple[dict, str] | None:
        """Returns (session_claims, ref) or None. Consumes the PKCE verifier;
        the post-login redirect target is FIXED to the surface's own path by the
        caller — state only ever carries the ref, never a URL."""
        st = self._verify(state)
        verifier = self._pkce.pop(state, None)
        if st is None or verifier is None:
            return None
        r = httpx.post(f"{self.issuer_internal}/protocol/openid-connect/token", data={
            "grant_type": "authorization_code", "client_id": self.client_id,
            "client_secret": self.client_secret, "code": code,
            "redirect_uri": self.redirect_uri, "code_verifier": verifier}, timeout=10.0)
        if r.status_code != 200:
            return None
        at = r.json()["access_token"]
        claims = json.loads(_unb64(at.split(".")[1]))
        sess = {"sub": claims["sub"], "preferred_username": claims.get("preferred_username"),
                "exp": int(time.time()) + self.max_age}
        return sess, st.get("ref", "")

    def cookie_value(self, sess: dict) -> str:
        return self._sign(sess)

    def session_from(self, cookie: str | None) -> dict | None:
        if not cookie:
            return None
        sess = self._verify(cookie)
        if not sess or sess.get("exp", 0) < time.time():
            return None
        return sess
