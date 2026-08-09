"""M7 spike (tasks 1.1/1.2): per-surface OIDC session module — the pattern that
graduates into services/approval/websession.py and services/token-broker/websession.py.

Authorization Code + PKCE against Keycloak with a confidential client; the
callback sets a signed, HttpOnly, SameSite=Lax cookie holding
{sub, preferred_username, exp}. The cookie NAME is per-surface (localhost
cookies are host-scoped, not port-scoped — two surfaces on :8961/:8962 would
clobber each other with a shared name). The OAuth `state` is HMAC-signed and
carries an optional fragment ref across the login round-trip (D3).

Stdlib-only signing (HMAC-SHA256) — no session framework; the session is a
claim cache, not a credential store (no tokens are kept)."""

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
        self.issuer_public = issuer_public        # browser-facing (redirects)
        self.issuer_internal = issuer_internal    # service-side (token endpoint)
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.cookie_name = cookie_name
        self.key = secret.encode()
        self.max_age = max_age
        self._pkce: dict[str, str] = {}           # state -> verifier (in-memory, demo-grade)

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
        return f"{self.issuer_public}/protocol/openid-connect/auth?" + urlencode({
            "client_id": self.client_id, "response_type": "code",
            "redirect_uri": self.redirect_uri, "scope": "openid",
            "state": state, "code_challenge": challenge,
            "code_challenge_method": "S256"})

    def handle_callback(self, code: str, state: str) -> tuple[dict, str] | None:
        """Returns (session_claims, ref) or None. Consumes the PKCE verifier."""
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
        p = at.split(".")[1]
        claims = json.loads(_unb64(p))
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
