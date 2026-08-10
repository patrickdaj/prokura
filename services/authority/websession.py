"""Browser session for the authority console (M8, D1/D2) — the M7 trusted-surface
pattern (spike/surface-session), with one addition: the OIDC callback also returns
the token response so the app can keep the user's access+refresh token
SERVER-SIDE (D2). The signed HttpOnly cookie carries only {sid, sub,
preferred_username, exp}; tokens are NEVER serialized into it.

Authorization Code + PKCE against Keycloak with the confidential ``authority-ui``
client. The OAuth ``state`` is HMAC-signed and round-trips an optional target
(e.g. a provider to link) across the login. Cookie name is per-surface
(``prokura_authority_session``): localhost cookies are host-scoped, not
port-scoped, so a shared name would clobber the other surfaces (spike S2)."""

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

    # signed state helper (used for the provider-link CSRF token too)
    def sign_state(self, payload: dict) -> str:
        return self._sign({**payload, "n": secrets.token_hex(8), "t": int(time.time())})

    def verify_state(self, blob: str) -> dict | None:
        return self._verify(blob)

    # -- login flow ------------------------------------------------------------
    def login_url(self, ref: str = "", *, redirect_uri: str | None = None,
                  extra: dict | None = None) -> str:
        """Build the Keycloak auth URL. ``redirect_uri`` overrides the default
        (used for the /api/link/callback leg); ``extra`` adds parameters such as
        ``kc_action``/``prompt`` for account linking."""
        verifier = _b64(secrets.token_bytes(32))
        challenge = _b64(hashlib.sha256(verifier.encode()).digest())
        state = self.sign_state({"ref": ref})
        self._pkce[state] = verifier
        if len(self._pkce) > 1000:                # drop oldest half; demo-grade bound
            for k in list(self._pkce)[:500]:
                self._pkce.pop(k, None)
        params = {
            "client_id": self.client_id, "response_type": "code",
            "redirect_uri": redirect_uri or self.redirect_uri, "scope": "openid",
            "state": state, "code_challenge": challenge, "code_challenge_method": "S256"}
        if extra:
            params.update(extra)
        return f"{self.issuer_public}/protocol/openid-connect/auth?" + urlencode(params)

    def handle_callback(self, code: str, state: str, *,
                        redirect_uri: str | None = None) -> tuple[dict, str, dict] | None:
        """Returns (session_claims, ref, token_response) or None. Consumes the
        PKCE verifier. token_response holds the user's access/refresh tokens for
        the app to store server-side (D2) — they never enter the cookie."""
        st = self._verify(state)
        verifier = self._pkce.pop(state, None)
        if st is None or verifier is None:
            return None
        r = httpx.post(f"{self.issuer_internal}/protocol/openid-connect/token", data={
            "grant_type": "authorization_code", "client_id": self.client_id,
            "client_secret": self.client_secret, "code": code,
            "redirect_uri": redirect_uri or self.redirect_uri,
            "code_verifier": verifier}, timeout=10.0)
        if r.status_code != 200:
            return None
        tok = r.json()
        claims = json.loads(_unb64(tok["access_token"].split(".")[1]))
        sess = {"sub": claims["sub"], "preferred_username": claims.get("preferred_username")}
        return sess, st.get("ref", ""), tok

    def cookie_value(self, sess: dict) -> str:
        # sess already carries {sid, sub, preferred_username, exp}.
        return self._sign(sess)

    def session_from(self, cookie: str | None) -> dict | None:
        if not cookie:
            return None
        sess = self._verify(cookie)
        if not sess or sess.get("exp", 0) < time.time():
            return None
        return sess
