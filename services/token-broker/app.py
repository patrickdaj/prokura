"""Prokura Token Broker — provider-token lifecycle behind a strict validation
chain (token-brokering, grant-acquisition, per-agent-consent specs).

Endpoints:
  GET  /healthz
  POST /v1/tokens/{provider}          hand-out chain -> provider access token
  POST /v1/grants/{provider}/import   import a Keycloak-brokered grant into OpenBao
  POST /v1/grants/{provider}/revoke   revoke a grant (provider + OpenBao + tuples)
  GET  /consent                       per-agent consent screen (authenticated)
  POST /consent                       write the can_use tuple (sole writer)
  GET  /v1/consents                   M8: list the console user's consents (user-bound bearer)
  POST /v1/consent/revoke             M9: revoke = kill switch (tuple + deny-list + KC + signal)
  GET  /ssf/stream                    M9: CAEP/SSF revocation Security Event Tokens (poll)

Born instrumented: traceparent join key + native trace context, realtime audit.
"""

import os
import re
from urllib.parse import urlencode

from fastapi import FastAPI, Header, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse

import audit
import config
import consent
import db
import fga
import grants
import revocation
import signals
import validation
from prokura_telemetry import setup, stamp_flow
from websession import WebSession

HERE = os.path.dirname(__file__)
app = FastAPI(title="prokura-token-broker")
setup(app, config.SERVICE_NAME)

# M7 (D2): the consent surface has its own OIDC session — the owner identity for
# every consent write comes from this session, never from a URL-carried token.
ws = WebSession(
    issuer_public=config.KEYCLOAK_ISSUER,
    issuer_internal=f"{config.KEYCLOAK_INTERNAL}/realms/{config.REALM}",
    client_id=config.UI_CLIENT_ID,
    client_secret=config.UI_CLIENT_SECRET,
    redirect_uri=f"{config.BROKER_PUBLIC_URL}/callback",
    cookie_name=config.SESSION_COOKIE,
    secret=config.SESSION_SECRET,
    max_age=config.SESSION_MAX_AGE,
)

_PARAM_RE = re.compile(r"^[A-Za-z0-9 ._:-]{0,128}$")


@app.on_event("startup")
def _startup() -> None:
    db.init_db()


def _bearer(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise _Http(401, "missing_token")
    return authorization.split(" ", 1)[1]


class _Http(Exception):
    def __init__(self, status: int, detail: str):
        self.status = status
        self.detail = detail


@app.exception_handler(_Http)
async def _http_handler(_: Request, exc: _Http) -> JSONResponse:
    return JSONResponse({"error": exc.detail}, status_code=exc.status)


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True}


@app.get("/ssf/stream")
def ssf_stream(since: int = 0) -> JSONResponse:
    # M9 demo CAEP/SSF poll transmitter: revocation Security Event Tokens a
    # receiver can consume. Single in-memory stream (demo-grade).
    return JSONResponse({"events": signals.stream(since)})


@app.post("/v1/tokens/{provider}")
async def issue_token(provider: str, request: Request,
                      authorization: str | None = Header(default=None)) -> JSONResponse:
    token = _bearer(authorization)
    try:
        claims = validation.verify_bearer(token)
    except validation.TokenInvalid as e:
        # SR-01: stable machine codes out; library/upstream detail to audit only.
        audit.emit(decision="denied_invalid_token", provider=provider, detail=str(e))
        raise _Http(401, "invalid_token")
    except validation.WrongAudience as e:
        audit.emit(decision="denied_audience", provider=provider, detail=str(e))
        raise _Http(403, "wrong_audience")

    user = claims.get("preferred_username")
    agent = claims.get("azp")
    # Flow B (token brokering): tag the root span so `{ prokura.flow = "B" }` in Tempo
    # lands on this end-to-end hand-out — red at whichever step denies it below.
    stamp_flow("B", user=user, agent=agent, provider=provider)
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    requested = body.get("scopes", []) or []

    # Step: grant must exist.
    grant = db.get_grant(user, provider)
    if not grant:
        audit.emit(decision="denied_no_grant", user=user, agent=agent, provider=provider)
        raise _Http(403, "no_grant")

    # Step: requested scopes must be a subset of the grant (never contact provider otherwise).
    if not validation.scopes_subset(requested, grant["granted_scopes"]):
        audit.emit(decision="denied_scope", user=user, agent=agent, provider=provider,
                   scopes=" ".join(requested))
        raise _Http(403, "scope_exceeds_grant")

    # Step: per-agent consent (OpenFGA can_use).
    if not consent.is_allowed(agent, user, provider):
        audit.emit(decision="denied_consent", user=user, agent=agent, provider=provider)
        raise _Http(403, "not_consented")

    # Step (M9 kill switch): propagation-free deny-list — a "stop now" checked on
    # every hand-out, independent of OpenFGA read state; a null-provider entry
    # denies all of the agent's grants for this user.
    if db.is_denied(agent, user, provider):
        audit.emit(decision="denied_killed", user=user, agent=agent, provider=provider)
        raise _Http(403, "revoked")

    try:
        issued = grants.issue_provider_token(user, provider)
    except grants.GrantError as e:
        audit.emit(decision="error", user=user, agent=agent, provider=provider, detail=str(e))
        raise _Http(502, "provider_issuance_failed")

    audit.emit(decision="issued", user=user, agent=agent, provider=provider,
               scopes=issued.get("scope"), ttl=issued["expires_in"])
    # Response carries the provider access token only — never a refresh token.
    return JSONResponse({
        "access_token": issued["access_token"],
        "token_type": "Bearer",
        "expires_in": issued["expires_in"],
        "scope": issued.get("scope", ""),
        "provider": provider,
    })


@app.post("/v1/grants/{provider}/import")
def import_grant(provider: str, authorization: str | None = Header(default=None)) -> JSONResponse:
    token = _bearer(authorization)
    try:
        claims = validation.verify_bearer(token)
    except validation.TokenInvalid as e:
        audit.emit(decision="denied_invalid_token", provider=provider, detail=str(e))
        raise _Http(401, "invalid_token")
    except validation.WrongAudience as e:
        audit.emit(decision="denied_audience", provider=provider, detail=str(e))
        raise _Http(403, "wrong_audience")
    user = claims.get("preferred_username")
    try:
        summary = grants.import_grant(token, user, provider)
    except grants.GrantError as e:
        audit.emit(decision="import_failed", user=user, provider=provider, detail=str(e))
        raise _Http(502, "grant_import_failed")
    audit.emit(decision="grant_imported", user=user, provider=provider,
               scopes=summary["scopes"])
    return JSONResponse(summary)


@app.post("/v1/grants/{provider}/revoke")
def revoke_grant(provider: str, authorization: str | None = Header(default=None)) -> JSONResponse:
    token = _bearer(authorization)
    try:
        claims = validation.verify_signature(token)
    except validation.TokenInvalid as e:
        audit.emit(decision="denied_invalid_token", detail=str(e))
        raise _Http(401, "invalid_token")
    user = claims.get("preferred_username")
    grants.revoke_grant(user, provider)
    fga.delete_all_can_use(user, provider)  # revoke drops all can_use tuples
    audit.emit(decision="grant_revoked", user=user, provider=provider)
    return JSONResponse({"revoked": True, "provider": provider})


# --- consent surface session (M7, D2) -----------------------------------------

def _session(request: Request) -> dict:
    sess = ws.session_from(request.cookies.get(config.SESSION_COOKIE))
    if not sess:
        raise _Http(401, "session_required")
    return sess


@app.get("/login")
def login(agent: str = "", provider: str = "", scopes: str = "") -> RedirectResponse:
    # The consent target rides the signed OAuth state; junk is dropped, and the
    # post-login redirect is fixed to /consent (no open-redirect surface).
    target = {k: v for k, v in (("agent", agent), ("provider", provider),
                                ("scopes", scopes)) if v and _PARAM_RE.match(v)}
    return RedirectResponse(ws.login_url(urlencode(target)))


@app.get("/callback", response_model=None)
def callback(code: str = "", state: str = "") -> JSONResponse | RedirectResponse:
    out = ws.handle_callback(code, state) if code and state else None
    if out is None:
        return JSONResponse({"error": "login_failed"}, status_code=400)
    sess, target = out
    resp = RedirectResponse(f"/consent?{target}" if target else "/consent", status_code=303)
    resp.set_cookie(config.SESSION_COOKIE, ws.cookie_value(sess),
                    httponly=True, samesite="lax", max_age=config.SESSION_MAX_AGE)
    audit.emit(decision="surface_login", user=sess["preferred_username"])
    return resp


@app.get("/whoami")
def whoami(request: Request) -> JSONResponse:
    sess = _session(request)
    return JSONResponse({"user": sess["preferred_username"]})


@app.get("/consent")
def consent_screen() -> FileResponse:
    return FileResponse(os.path.join(HERE, "consent.html"))


@app.post("/consent")
async def write_consent(request: Request) -> JSONResponse:
    # The grant OWNER is the session identity — the human signed in on this
    # surface. No bearer path exists; a user consents only for their own
    # grants, and operator == owner is enforced inside consent.grant_consent
    # (F1-A/Q3-B, now against a real session).
    sess = _session(request)
    user = sess["preferred_username"]
    body = await request.json()
    agent = body.get("agent")
    provider = body.get("provider")
    if not agent or not provider:
        raise _Http(400, "missing_fields")
    if not grants.grant_exists(user, provider):
        raise _Http(404, "no_grant")
    try:
        consent.grant_consent(agent, user, provider)
    except consent.ConsentRefused as e:
        audit.emit(decision="consent_refused", user=user, agent=agent, provider=provider,
                   detail=str(e))
        raise _Http(403, "consent_refused")
    # M9: granting consent clears any prior kill deny-entry, so a re-consented
    # agent is usable again (the durable tuple and the deny-list agree).
    revocation.unkill(agent, user, provider)
    audit.emit(decision="consent_granted", user=user, agent=agent, provider=provider)
    return JSONResponse({"consented": True, "agent": agent, "provider": provider})


@app.post("/v1/consent/revoke")
async def revoke_consent(request: Request,
                         authorization: str | None = Header(default=None)) -> JSONResponse:
    # Two owner-authenticated paths converge here (M8, D3): the consent surface's
    # own session (M7) OR an exchanged user-bound bearer from the authority
    # console (aud=token-broker). Either way the OWNER is a verified identity and
    # revoke only ever deletes a tuple under grant:{owner}/*, so a foreign subject
    # cannot revoke another user's consent. azp is audited.
    user, azp = _owner_from_session_or_bearer(request, authorization)
    body = await request.json()
    agent = body.get("agent")
    provider = body.get("provider")
    # M9: per-grant revoke fans out to the kill switch (tuple delete + deny-list
    # + CAEP signal) and returns a measured time-to-stop plus the honest in-flight
    # residual. Scoped: the agent's session and other grants are untouched, and
    # the deny-list blocks re-acquiring THIS grant even with a fresh token.
    result = revocation.kill(agent, user, provider, azp=azp)
    audit.emit(decision="consent_revoked", user=user, agent=agent, provider=provider,
               detail=f"azp={azp} stop_ms={result['stop_ms']}")
    return JSONResponse({"revoked": True, "agent": agent, "provider": provider,
                         "stop_ms": result["stop_ms"],
                         "residual_seconds": result["residual_seconds"]})


@app.get("/v1/consents")
def list_consents(authorization: str | None = Header(default=None)) -> JSONResponse:
    # M8: the console lists the signed-in user's per-agent consents. User-bound
    # bearer only (aud=token-broker); the subject is the verified token subject,
    # so no principal can read another's register.
    token = _bearer(authorization)
    try:
        claims = validation.verify_bearer(token)
    except validation.TokenInvalid as e:
        audit.emit(decision="denied_invalid_token", detail=str(e))
        raise _Http(401, "invalid_token")
    except validation.WrongAudience as e:
        audit.emit(decision="denied_audience", detail=str(e))
        raise _Http(403, "wrong_audience")
    user = claims.get("preferred_username")
    grants = db.list_grants(user)
    consents = []
    for g in grants:
        for agent in fga.list_can_use_agents(user, g["provider"]):
            consents.append({"agent": agent, "provider": g["provider"],
                             "scopes": g["granted_scopes"]})
    # grants (providers linked, with scopes) so the console can show what is
    # connected even before any agent is consented; consents is the per-agent view.
    return JSONResponse({"user": user, "consents": consents,
                         "grants": [{"provider": g["provider"], "scopes": g["granted_scopes"]}
                                    for g in grants]})


def _owner_from_session_or_bearer(
        request: Request, authorization: str | None) -> tuple[str, str]:
    """Resolve the acting owner and azp. Prefer the surface session (M7 consent
    screen, azp=broker-ui); fall back to a user-bound bearer (M8 console,
    aud=token-broker). Raises 401 if neither authenticates."""
    sess = ws.session_from(request.cookies.get(config.SESSION_COOKIE))
    if sess:
        return sess["preferred_username"], config.UI_CLIENT_ID
    if authorization:
        try:
            claims = validation.verify_bearer(_bearer(authorization))
        except validation.TokenInvalid as e:
            audit.emit(decision="denied_invalid_token", detail=str(e))
            raise _Http(401, "invalid_token")
        except validation.WrongAudience as e:
            audit.emit(decision="denied_audience", detail=str(e))
            raise _Http(403, "wrong_audience")
        return claims.get("preferred_username"), claims.get("azp")
    raise _Http(401, "session_required")
