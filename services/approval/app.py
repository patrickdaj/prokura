"""Prokura Approval Service — CIBA-gated human approval for sensitive actions
(human-approval spec). Joins the trusted computing base.

M7 (ADR-0022): this service owns the WHOLE ceremony. /register initiates CIBA
with its own confidential client (login_hint = the verified registered user);
Keycloak delivers the delegation back to /ciba/delegate (authenticated: the
delegation bearer is a realm-signed JWT); the human decides in an authenticated
browser session (OIDC login, signed cookie — no URL-carried credentials); the
decision is relayed to Keycloak's callback and the service completes the
ceremony by polling, then DISCARDS the issued token — the ceremony is the
product. The agent's role is: receive 428 → wait → retry with action_token.

Endpoints:
  GET  /healthz
  POST /register                 tools-api registers {action,params} -> {ref, action_token}
  POST /ciba/delegate            Keycloak's CIBA delegation receiver (201; authenticated)
  GET  /login, /callback         OIDC session for the trusted surface
  GET  /approvals                trusted UI (session-gated rendering)
  GET  /approval/{ref}           JSON payload for the UI (session; never agent text)
  GET  /my/approvals             session user's approvals
  POST /approval/{ref}/decide    approve/deny in the session -> relay + complete ceremony
  POST /consume                  the gated tool verifies hash + single-use here
  GET  /v1/my/approvals          M8: user-bound bearer (aud=approval) read for the console
  GET  /v1/my/topic              M8: user-bound bearer (aud=approval) -> the subject's ntfy topic
"""

import hashlib
import json
import os
import re
import secrets
import time

import httpx
from fastapi import BackgroundTasks, FastAPI, Header, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse

import audit
import config
import db
import ntfy
import validation
from telemetry import setup_telemetry, tracer
from websession import WebSession

HERE = os.path.dirname(__file__)
app = FastAPI(title="prokura-approval")
setup_telemetry(app)

REF_RE = re.compile(r"^apr-[0-9a-f]+$")

ws = WebSession(
    issuer_public=config.KEYCLOAK_ISSUER,
    issuer_internal=f"{config.KEYCLOAK_INTERNAL}/realms/{config.REALM}",
    client_id=config.UI_CLIENT_ID,
    client_secret=config.UI_CLIENT_SECRET,
    redirect_uri=f"{config.APPROVAL_PUBLIC_URL}/callback",
    cookie_name=config.SESSION_COOKIE,
    secret=config.SESSION_SECRET,
    max_age=config.SESSION_MAX_AGE,
)


@app.on_event("startup")
def _startup() -> None:
    db.init_db()


class _Http(Exception):
    def __init__(self, status: int, code: str):
        self.status, self.code = status, code


@app.exception_handler(_Http)
async def _h(_: Request, e: _Http) -> JSONResponse:
    # SR-01: stable machine codes only — upstream/library detail goes to the
    # audit log (see audit.emit call sites), never into a response body.
    return JSONResponse({"error": e.code}, status_code=e.status)


def _hash(action: str, params: dict) -> str:
    canonical = json.dumps({"action": action, "params": params},
                           sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True}


# --- registration + server-initiated CIBA (D1) --------------------------------

@app.post("/register")
async def register(request: Request, authorization: str | None = Header(default=None)) -> JSONResponse:
    # Authenticated by the CALLER's verified token (the tools-api relays the
    # user token it validated); login_hint derives from these verified claims,
    # never from any agent-supplied string.
    claims = _verify_bearer(authorization)
    user, agent = claims.get("preferred_username"), claims.get("azp")
    body = await request.json()
    action, params = body.get("action"), body.get("params", {})
    if not action:
        raise _Http(400, "action_required")
    scopes = body.get("scopes", "")
    ref = "apr-" + secrets.token_hex(12)          # binding-message safe (hex only)
    secret = secrets.token_urlsafe(24)
    db.create(ref, agent, user, action, params, _hash(action, params), scopes, secret)
    audit.emit("registered", ref=ref, user=user, agent=agent, action=action)

    # The approval service initiates the ceremony — its own client, its own
    # trust position. No agent can reach this grant (agent-app lost it).
    # MUST be async: Keycloak delivers the delegation to our /ciba/delegate
    # synchronously inside this call — a blocking client here deadlocks the
    # event loop against our own receiver.
    with tracer().start_as_current_span("ciba.initiate") as span:
        span.set_attribute("prokura.approval.ref", ref)
        try:
            async with httpx.AsyncClient(timeout=10.0) as ac:
                r = await ac.post(config.CIBA_AUTH_URL, data={
                    "client_id": config.CIBA_CLIENT_ID,
                    "client_secret": config.CIBA_CLIENT_SECRET,
                    "scope": "openid", "login_hint": user, "binding_message": ref,
                })
        except httpx.HTTPError as e:
            audit.emit("ciba_init_failed", ref=ref, user=user, agent=agent, detail=str(e))
            raise _Http(502, "ciba_unavailable")
    if r.status_code != 200:
        audit.emit("ciba_init_failed", ref=ref, user=user, agent=agent,
                   detail=f"{r.status_code} {r.text[:200]}")
        raise _Http(502, "ciba_init_failed")
    db.set_auth_req_id(ref, r.json()["auth_req_id"])
    audit.emit("ciba_initiated", ref=ref, user=user, agent=agent, action=action)
    return JSONResponse({"ref": ref, "action_token": f"{ref}.{secret}"})


@app.post("/ciba/delegate", status_code=201)
async def ciba_delegate(request: Request) -> JSONResponse:
    # SR-02: authenticate BEFORE parsing — the delegation bearer is a
    # realm-signed JWT minted for this ceremony; its azp must be our own CIBA
    # client (the only initiator). Body bounded before json parse.
    token = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
    if not token:
        raise _Http(401, "unauthenticated")
    try:
        bearer_claims = validation.verify_signature(token)
    except validation.TokenInvalid as e:
        audit.emit("delegate_refused", detail=str(e))
        raise _Http(401, "unauthenticated")
    if bearer_claims.get("azp") != config.CIBA_CLIENT_ID:
        audit.emit("delegate_refused", detail=f"azp={bearer_claims.get('azp')}")
        raise _Http(403, "wrong_initiator")
    raw = await request.body()
    if len(raw) > config.DELEGATE_BODY_CAP:
        raise _Http(413, "body_too_large")
    try:
        body = json.loads(raw)
    except ValueError:
        raise _Http(400, "invalid_body")
    ref = body.get("binding_message", "")
    with tracer().start_as_current_span("ciba.delegate") as span:
        span.set_attribute("prokura.approval.ref", ref)
        row = db.get(ref) if REF_RE.match(ref or "") else None
        if row and db.set_delegation(ref, token):
            audit.emit("delegated", ref=ref, user=row["user_id"], agent=row["agent"])
            ntfy.notify(row["user_id"], ref)          # deep link + ref only
    return JSONResponse({"received": True}, status_code=201)


# --- browser session (D2/D3) --------------------------------------------------

@app.get("/login")
def login(ref: str = "") -> RedirectResponse:
    if ref and not REF_RE.match(ref):
        ref = ""                                   # never round-trip junk
    return RedirectResponse(ws.login_url(ref))


@app.get("/callback", response_model=None)
def callback(code: str = "", state: str = "") -> JSONResponse | RedirectResponse:
    out = ws.handle_callback(code, state) if code and state else None
    if out is None:
        return JSONResponse({"error": "login_failed"}, status_code=400)
    sess, ref = out
    # Redirect target is FIXED to this surface's own path; only the ref varies
    # (validated above) — no open-redirect surface.
    resp = RedirectResponse(f"/approvals#{ref}" if ref else "/approvals", status_code=303)
    resp.set_cookie(config.SESSION_COOKIE, ws.cookie_value(sess),
                    httponly=True, samesite="lax", max_age=config.SESSION_MAX_AGE)
    audit.emit("surface_login", user=sess["preferred_username"])
    return resp


def _effective_status(row: dict) -> str:
    """An undecided approval past the backchannel window is expired — enforced
    here because no agent-side poll exists to surface Keycloak's expiry
    (ADR-0022)."""
    if (row["status"] in ("pending", "delegated")
            and float(row.get("age_seconds") or 0) > config.APPROVAL_TTL_SECONDS):
        return "expired"
    return row["status"]


def _session(request: Request) -> dict:
    sess = ws.session_from(request.cookies.get(config.SESSION_COOKIE))
    if not sess:
        raise _Http(401, "session_required")
    return sess


@app.get("/approvals")
def approvals_ui() -> FileResponse:
    return FileResponse(os.path.join(HERE, "approval.html"))


@app.get("/whoami")
def whoami(request: Request) -> JSONResponse:
    # The page asks who is signed in before rendering; 401 sends it to /login.
    sess = _session(request)
    return JSONResponse({"user": sess["preferred_username"]})


@app.get("/approval/{ref}")
def approval_payload(ref: str, request: Request) -> JSONResponse:
    sess = _session(request)
    row = db.get(ref)
    if not row or row["user_id"] != sess["preferred_username"]:
        raise _Http(404, "not_found")
    # Rendered from service-held data — never any agent-supplied string.
    return JSONResponse({"ref": row["ref"], "agent": row["agent"], "action": row["action"],
                         "params": row["params"], "scopes": row["scopes"],
                         "status": _effective_status(row)})


@app.get("/my/approvals")
def my_approvals(request: Request) -> JSONResponse:
    sess = _session(request)
    return JSONResponse(db.list_for_user(sess["preferred_username"]))


# --- M8: user-bound read APIs for the authority console -----------------------
# Authenticated by an exchanged user-bound bearer (aud=approval); the subject is
# taken from the verified token only. Read-only: no decision path exists here
# (decide/{ref} is session-only above). These never expose another user's data.

def _user_bearer(authorization: str | None) -> dict:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise _Http(401, "missing_token")
    token = authorization.split(" ", 1)[1]
    try:
        return validation.verify_bearer(token)
    except validation.WrongAudience as e:
        audit.emit("read_refused", detail=f"audience: {e}")
        raise _Http(403, "wrong_audience")
    except validation.TokenInvalid as e:
        audit.emit("read_refused", detail=str(e))
        raise _Http(401, "invalid_token")


@app.get("/v1/my/approvals")
def v1_my_approvals(authorization: str | None = Header(default=None)) -> JSONResponse:
    claims = _user_bearer(authorization)
    user = claims.get("preferred_username")
    return JSONResponse({"user": user, "approvals": db.list_for_user(user)})


@app.get("/v1/my/topic")
def v1_my_topic(authorization: str | None = Header(default=None)) -> JSONResponse:
    # The topic salt never leaves this service (ADR-0007); the console only ever
    # sees the derived topic for its own signed-in user. Derivation runs only
    # after the bearer verifies (wrong-audience/invalid refused above).
    claims = _user_bearer(authorization)
    user = claims.get("preferred_username")
    topic = ntfy.topic_for(user)
    return JSONResponse({
        "user": user,
        "topic": topic,
        "subscribe_url": f"{config.NTFY_PUBLIC_URL}/{topic}",
    })


@app.post("/approval/{ref}/decide")
async def decide(ref: str, request: Request, background: BackgroundTasks) -> JSONResponse:
    # Decisions happen ONLY in the authenticated browser session, and only by
    # the approval's target user. No bearer path exists.
    sess = _session(request)
    row = db.get(ref)
    if not row or row["user_id"] != sess["preferred_username"]:
        raise _Http(404, "not_found")
    status_now = _effective_status(row)
    if status_now == "expired":
        db.set_status(ref, "expired")
        audit.emit("expired", ref=ref, user=row["user_id"], agent=row["agent"])
        raise _Http(409, "expired")
    if status_now not in ("pending", "delegated"):
        raise _Http(409, "already_decided")
    body = await request.json()
    approve = body.get("decision") == "approve"
    status = "SUCCEED" if approve else "UNAUTHORIZED"
    # The approval service (not the user's device) relays the decision to Keycloak.
    if row.get("delegation_token"):
        with tracer().start_as_current_span("ciba.callback") as span:
            span.set_attribute("prokura.approval.decision", status)
            async with httpx.AsyncClient(timeout=10.0) as ac:
                await ac.post(config.CIBA_CALLBACK, json={"status": status},
                              headers={"Authorization": f"Bearer {row['delegation_token']}"})
    db.set_status(ref, "approved" if approve else "denied")
    audit.emit("approved" if approve else "denied", ref=ref, user=row["user_id"],
               agent=row["agent"], action=row["action"])
    # Complete the ceremony out-of-band: poll the token endpoint and discard the
    # result. No party consumes this token — the ceremony record is the product.
    if row.get("auth_req_id"):
        background.add_task(_complete_ceremony, ref, row["auth_req_id"],
                            row["user_id"], row["agent"])
    return JSONResponse({"ref": ref, "status": "approved" if approve else "denied"})


def _complete_ceremony(ref: str, auth_req_id: str, user: str, agent: str) -> None:
    for _ in range(4):
        try:
            r = httpx.post(config.TOKEN_URL, data={
                "grant_type": "urn:openid:params:grant-type:ciba",
                "auth_req_id": auth_req_id,
                "client_id": config.CIBA_CLIENT_ID,
                "client_secret": config.CIBA_CLIENT_SECRET}, timeout=10.0)
        except httpx.HTTPError as e:
            audit.emit("ceremony_error", ref=ref, user=user, agent=agent, detail=str(e))
            return
        if r.status_code == 200:
            # Token deliberately discarded (ADR-0022).
            audit.emit("ceremony_completed", ref=ref, user=user, agent=agent)
            return
        err = r.json().get("error", "") if r.headers.get(
            "content-type", "").startswith("application/json") else r.text[:80]
        if err == "access_denied":                  # the deny leg completes too
            audit.emit("ceremony_completed", ref=ref, user=user, agent=agent,
                       detail="denied")
            return
        if err not in ("authorization_pending", "slow_down"):
            audit.emit("ceremony_error", ref=ref, user=user, agent=agent, detail=err)
            return
        time.sleep(5)                               # realm cibaInterval
    audit.emit("ceremony_error", ref=ref, user=user, agent=agent, detail="poll_timeout")


# --- consumption (unchanged gate: hash + single-use + owner) ------------------

@app.post("/consume")
async def consume(request: Request) -> JSONResponse:
    """Called by the gated tool. Verifies the presenting user, the action hash,
    and single-use, then atomically consumes the reference. M7: the caller
    proves the USER with the user-bound token it validated (the CIBA-issued
    token no longer exists on the agent side — ADR-0022); the approved status
    itself attests the human ceremony."""
    body = await request.json()
    action_token = body.get("action_token", "")
    user_token = body.get("user_token", "")
    action, params = body.get("action"), body.get("params", {})
    ref = action_token.split(".", 1)[0]
    row = db.get(ref)
    if not row or f"{ref}.{row['action_secret']}" != action_token:
        raise _Http(403, "invalid_action_token")
    if _effective_status(row) == "expired":
        audit.emit("consume_refused", ref=ref, user=row["user_id"], agent=row["agent"],
                   detail="expired")
        raise _Http(403, "expired")
    if row["status"] != "approved":
        audit.emit("consume_refused", ref=ref, user=row["user_id"], agent=row["agent"],
                   detail=f"status={row['status']}")
        raise _Http(403, "not_approved")
    # The user-bound token proves the caller acts for the approved user.
    try:
        sub = validation.verify_signature(user_token).get("preferred_username")
    except validation.TokenInvalid as e:
        audit.emit("consume_refused", ref=ref, user=row["user_id"], agent=row["agent"],
                   detail=str(e))
        raise _Http(401, "invalid_token")
    if sub != row["user_id"]:
        audit.emit("consume_refused", ref=ref, user=row["user_id"], agent=row["agent"],
                   detail="subject_mismatch")
        raise _Http(403, "wrong_subject")
    if _hash(action, params) != row["hash"]:
        audit.emit("hash_mismatch", ref=ref, user=row["user_id"], agent=row["agent"])
        raise _Http(409, "action_mismatch")
    if not db.consume(ref):                         # atomic single-use
        audit.emit("replay_refused", ref=ref, user=row["user_id"], agent=row["agent"])
        raise _Http(409, "already_consumed")
    audit.emit("consumed", ref=ref, user=row["user_id"], agent=row["agent"], action=action)
    return JSONResponse({"ok": True, "ref": ref, "action": action, "params": params})


def _verify_bearer(authz: str | None) -> dict:
    if not authz or not authz.lower().startswith("bearer "):
        raise _Http(401, "missing_token")
    try:
        return validation.verify_signature(authz.split(" ", 1)[1])
    except validation.TokenInvalid as e:
        audit.emit("token_refused", detail=str(e))   # SR-01: detail to audit only
        raise _Http(401, "invalid_token")
