"""Prokura Authority Console (M8) — the principal's aggregated authority
register. A trusted *surface* (D1): its own OIDC session (``authority-ui``
confidential client, signed HttpOnly cookie), it renders service-held data and
relays the signed-in user's OWN authority downstream by RFC 8693 exchange (D2).
It holds no user password, writes no authorization state, and is not a second
tuple-writer — the broker stays the sole ``can_use`` writer.

For the signed-in principal only, the console shows: agents they operate (FGA
``operator``), each agent's consented grants (broker ``/v1/consents``), pending
and recent approvals (approval ``/v1/my/approvals``, deep-linking into :8120 for
any decision), their notification topic (approval ``/v1/my/topic``), and a live
activity feed (Loki, filtered server-side to the session user). Two actions:
per-agent consent revoke (→ broker bearer revoke) and provider linking
(``kc_action=idp_link`` → broker grant import). Everything downstream carries the
user's exchanged, user-bound token — never a service account acting for nobody.

Endpoints:
  GET  /healthz
  GET  /login, /callback              OIDC session for the surface
  GET  /whoami                        who is signed in (401 -> /login)
  GET  /                              the panel (index.html)
  GET  /api/register                  aggregated register (session principal only)
  GET  /api/activity                  Loki activity feed, filtered to the user
  GET  /api/topic                     the user's ntfy topic (via approval)
  POST /api/revoke/{agent}/{provider} per-agent consent revoke (via broker bearer)
  GET  /api/link/{provider}           start account linking (kc_action=idp_link)
  GET  /api/link/callback             on return, import the grant (via broker)
"""

import io
import os
import re
import secrets
import time

import httpx
import segno
from fastapi import FastAPI, Header, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse

import activity
import audit
import config
import exchange
import fga
from prokura_telemetry import setup, stamp_flow, tracer
from websession import WebSession

HERE = os.path.dirname(__file__)
app = FastAPI(title="prokura-authority")
setup(app, config.SERVICE_NAME)

_NAME_RE = re.compile(r"^[a-zA-Z0-9._:-]{1,64}$")
LINK_REDIRECT = f"{config.AUTHORITY_PUBLIC_URL}/api/link/callback"

ws = WebSession(
    issuer_public=config.KEYCLOAK_ISSUER,
    issuer_internal=f"{config.KEYCLOAK_INTERNAL}/realms/{config.REALM}",
    client_id=config.UI_CLIENT_ID,
    client_secret=config.UI_CLIENT_SECRET,
    redirect_uri=f"{config.AUTHORITY_PUBLIC_URL}/callback",
    cookie_name=config.SESSION_COOKIE,
    secret=config.SESSION_SECRET,
    max_age=config.SESSION_MAX_AGE,
)

# Server-side token store (D2): sid -> {access_token, refresh_token, exp}. The
# user's tokens live ONLY here, never in the cookie. Demo-grade in-memory, bounded;
# a restart drops sessions (the cookie then fails the token lookup -> re-login).
_TOKENS: dict[str, dict] = {}


class _Http(Exception):
    def __init__(self, status: int, code: str):
        self.status, self.code = status, code


@app.exception_handler(_Http)
async def _h(_: Request, e: _Http) -> JSONResponse:
    return JSONResponse({"error": e.code}, status_code=e.status)


# --- session + server-side tokens ---------------------------------------------

def _store_tokens(sid: str, tok: dict) -> None:
    _TOKENS[sid] = {
        "access_token": tok["access_token"],
        "refresh_token": tok.get("refresh_token"),
        "exp": time.time() + int(tok.get("expires_in", 300)),
    }
    if len(_TOKENS) > 500:                     # demo-grade bound; drop oldest half
        for k in list(_TOKENS)[:250]:
            _TOKENS.pop(k, None)


def _session(request: Request) -> dict:
    sess = ws.session_from(request.cookies.get(config.SESSION_COOKIE))
    if not sess or sess.get("sid") not in _TOKENS:
        raise _Http(401, "session_required")
    return sess


def _fresh_access_token(sid: str) -> str:
    """The user's current access token, refreshed if near expiry. Raises 401 if
    the server-side token is gone (restart) or refresh fails."""
    rec = _TOKENS.get(sid)
    if not rec:
        raise _Http(401, "session_required")
    if rec["exp"] - time.time() > 30:
        return rec["access_token"]
    if rec.get("refresh_token"):
        r = httpx.post(
            f"{config.KEYCLOAK_INTERNAL}/realms/{config.REALM}/protocol/openid-connect/token",
            data={"grant_type": "refresh_token", "client_id": config.UI_CLIENT_ID,
                  "client_secret": config.UI_CLIENT_SECRET,
                  "refresh_token": rec["refresh_token"]}, timeout=10.0)
        if r.status_code == 200:
            _store_tokens(sid, r.json())
            return _TOKENS[sid]["access_token"]
    raise _Http(401, "session_expired")


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True}


@app.get("/login")
def login() -> RedirectResponse:
    return RedirectResponse(ws.login_url())


@app.get("/callback", response_model=None)
def callback(code: str = "", state: str = "") -> JSONResponse | RedirectResponse:
    out = ws.handle_callback(code, state) if code and state else None
    if out is None:
        return JSONResponse({"error": "login_failed"}, status_code=400)
    sess, _ref, tok = out
    sid = secrets.token_urlsafe(18)
    _store_tokens(sid, tok)
    cookie_claims = {"sid": sid, "sub": sess["sub"],
                     "preferred_username": sess["preferred_username"],
                     "exp": int(time.time()) + config.SESSION_MAX_AGE}
    resp = RedirectResponse("/", status_code=303)
    resp.set_cookie(config.SESSION_COOKIE, ws.cookie_value(cookie_claims),
                    httponly=True, samesite="lax", max_age=config.SESSION_MAX_AGE)
    audit.emit("surface_login", user=sess["preferred_username"])
    return resp


@app.get("/whoami")
def whoami(request: Request) -> JSONResponse:
    sess = _session(request)
    return JSONResponse({"user": sess["preferred_username"]})


@app.get("/")
def index() -> FileResponse:
    return FileResponse(os.path.join(HERE, "index.html"))


# --- aggregated register (D2) -------------------------------------------------

@app.get("/api/register")
def register(request: Request) -> JSONResponse:
    sess = _session(request)
    user = sess["preferred_username"]
    # The principal's control surface — tag the trace so `{ prokura.flow =
    # "authority-console" }` finds the human's own "who acts for me" reads/actions.
    stamp_flow("authority-console", user=user)
    at = _fresh_access_token(sess["sid"])
    broker_tok = exchange.exchange_for(at, config.BROKER_AUDIENCE)
    approval_tok = exchange.exchange_for(at, config.APPROVAL_AUDIENCE)

    # agents this principal operates (FGA operator, read directly).
    agents = fga.agents_operated_by(user)
    # per-agent consents + linked grants (broker, user-bound bearer).
    cr = httpx.get(f"{config.BROKER_URL}/v1/consents",
                   headers={"Authorization": f"Bearer {broker_tok}"}, timeout=15.0)
    cr.raise_for_status()
    cbody = cr.json()
    consents, grants = cbody.get("consents", []), cbody.get("grants", [])
    # approvals (approval, user-bound bearer).
    ar = httpx.get(f"{config.APPROVAL_URL}/v1/my/approvals",
                   headers={"Authorization": f"Bearer {approval_tok}"}, timeout=15.0)
    ar.raise_for_status()
    approvals = ar.json().get("approvals", [])

    by_agent: dict[str, list] = {}
    for c in consents:
        by_agent.setdefault(c["agent"], []).append(
            {"provider": c["provider"], "scopes": c["scopes"]})
    # union so no consent is orphaned even if an operator tuple is missing.
    agent_ids = sorted(set(agents) | set(by_agent))
    agents_view = [{"agent": a, "consents": by_agent.get(a, [])} for a in agent_ids]

    audit.emit("register_read", user=user)
    return JSONResponse({
        "user": user,
        "agents": agents_view,
        "grants": grants,
        "approvals": approvals,
        "approval_base": config.APPROVAL_PUBLIC_URL,
    })


@app.get("/api/activity")
def api_activity(request: Request) -> JSONResponse:
    sess = _session(request)
    return JSONResponse({"activity": activity.for_user(sess["preferred_username"])})


@app.get("/api/topic")
def api_topic(request: Request) -> JSONResponse:
    sess = _session(request)
    at = _fresh_access_token(sess["sid"])
    approval_tok = exchange.exchange_for(at, config.APPROVAL_AUDIENCE)
    r = httpx.get(f"{config.APPROVAL_URL}/v1/my/topic",
                  headers={"Authorization": f"Bearer {approval_tok}"}, timeout=15.0)
    if r.status_code != 200:
        raise _Http(502, "topic_unavailable")
    body = r.json()
    # QR for the subscribe URL, rendered server-side (segno, pure-Python — no
    # external service, D5) into an inline SVG the panel drops straight in.
    sub = body.get("subscribe_url", "")
    if sub:
        buf = io.BytesIO()
        segno.make(sub, error="m").save(buf, kind="svg", scale=1, border=2,
                                         dark="#0b0d10", light="#ffffff", xmldecl=False)
        body["qr_svg"] = buf.getvalue().decode()
    return JSONResponse(body)


# --- action: per-agent consent revoke (D3) ------------------------------------

@app.post("/api/revoke/{agent}/{provider}")
def api_revoke(agent: str, provider: str, request: Request) -> JSONResponse:
    sess = _session(request)
    if not _NAME_RE.match(agent) or not _NAME_RE.match(provider):
        raise _Http(400, "bad_request")
    stamp_flow("authority-console", user=sess["preferred_username"], agent=agent)
    at = _fresh_access_token(sess["sid"])
    broker_tok = exchange.exchange_for(at, config.BROKER_AUDIENCE)
    with tracer().start_as_current_span("console.revoke") as span:
        span.set_attribute("prokura.revoke.agent", agent)
        r = httpx.post(f"{config.BROKER_URL}/v1/consent/revoke",
                       headers={"Authorization": f"Bearer {broker_tok}"},
                       json={"agent": agent, "provider": provider}, timeout=15.0)
    if r.status_code != 200:
        audit.emit("revoke_failed", user=sess["preferred_username"], agent=agent,
                   provider=provider, detail=f"{r.status_code}")
        raise _Http(502, "revoke_failed")
    # M9: the broker's kill switch returns a measured time-to-stop + the honest
    # in-flight residual; relay them to the principal instead of a latency caveat.
    body = r.json()
    stop_ms = body.get("stop_ms")
    residual = body.get("residual_seconds")
    audit.emit("revoked", user=sess["preferred_username"], agent=agent, provider=provider,
               detail=f"stop_ms={stop_ms}")
    return JSONResponse({"revoked": True, "agent": agent, "provider": provider,
                         "stop_ms": stop_ms, "residual_seconds": residual})


# --- action: provider linking (D4) --------------------------------------------
# NOTE: the specific /api/link/callback route MUST be declared before the
# /api/link/{provider} catch-all, or FastAPI matches "callback" as a provider
# and the return leg loops back into linking.

@app.get("/api/link/callback", response_model=None)
def api_link_callback(request: Request, code: str = "", state: str = "",
                      kc_action_status: str = "") -> RedirectResponse:
    sess = _session(request)
    user = sess["preferred_username"]
    st = ws.verify_state(state) if state else None
    ws._pkce.pop(state, None)                  # consume any PKCE entry for this state
    provider = st.get("ref", "") if st else ""
    if not st or not _NAME_RE.match(provider or ""):
        audit.emit("link_refused", user=user, detail="bad_state")
        return RedirectResponse("/?link=error", status_code=303)
    # The linking action must have completed (Keycloak returns kc_action_status or
    # a code); a bare hit without either is not a completed link.
    if kc_action_status not in ("success", "") and not code:
        audit.emit("link_refused", user=user, provider=provider, detail=kc_action_status)
        return RedirectResponse(f"/?link=cancelled", status_code=303)
    # Import with the user's OWN exchanged token (subject = owner). The link is now
    # established in Keycloak; retrieval is by user identity, so the session token
    # suffices — no admin API, no demo driver.
    at = _fresh_access_token(sess["sid"])
    broker_tok = exchange.exchange_for(at, config.BROKER_AUDIENCE)
    r = httpx.post(f"{config.BROKER_URL}/v1/grants/{provider}/import",
                   headers={"Authorization": f"Bearer {broker_tok}"}, timeout=20.0)
    if r.status_code != 200:
        audit.emit("link_import_failed", user=user, provider=provider,
                   detail=f"{r.status_code} {r.text[:120]}")
        return RedirectResponse(f"/?link=import_failed", status_code=303)
    audit.emit("linked", user=user, provider=provider)
    return RedirectResponse(f"/?link=ok&provider={provider}", status_code=303)


@app.get("/api/link/{provider}")
def api_link(provider: str, request: Request) -> RedirectResponse:
    # Requires a session — a real person, in their own browser, links a provider.
    sess = _session(request)
    if not _NAME_RE.match(provider):
        raise _Http(400, "bad_request")
    # The provider rides the signed OAuth state (ref); kc_action drives linking.
    # We do NOT force prompt=login here: the user already authenticated to reach
    # this session, and forcing a re-auth on the broker RETURN leg loops in
    # Keycloak 26 when an SSO session exists (M8 finding). The sensitive proof —
    # logging into the provider — still happens in the user's own browser.
    url = ws.login_url(ref=provider, redirect_uri=LINK_REDIRECT,
                       extra={"kc_action": f"idp_link:{provider}"})
    audit.emit("link_started", user=sess["preferred_username"], provider=provider)
    return RedirectResponse(url)
