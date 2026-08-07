"""Prokura Token Broker — provider-token lifecycle behind a strict validation
chain (token-brokering, grant-acquisition, per-agent-consent specs).

Endpoints:
  GET  /healthz
  POST /v1/tokens/{provider}          hand-out chain -> provider access token
  POST /v1/grants/{provider}/import   import a Keycloak-brokered grant into OpenBao
  POST /v1/grants/{provider}/revoke   revoke a grant (provider + OpenBao + tuples)
  GET  /consent                       per-agent consent screen (authenticated)
  POST /consent                       write the can_use tuple (sole writer)
  POST /v1/consent/revoke             revoke one agent's consent

Born instrumented: traceparent join key + prokura.correlation_id, realtime audit.
"""

import os

from fastapi import FastAPI, Header, Request
from fastapi.responses import FileResponse, JSONResponse

import audit
import consent
import db
import fga
import grants
import validation
from telemetry import setup_telemetry

HERE = os.path.dirname(__file__)
app = FastAPI(title="prokura-token-broker")
setup_telemetry(app)


@app.on_event("startup")
def _startup() -> None:
    db.init_db()


def _bearer(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise _Http(401, "missing bearer token")
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


@app.post("/v1/tokens/{provider}")
async def issue_token(provider: str, request: Request,
                      authorization: str | None = Header(default=None)) -> JSONResponse:
    token = _bearer(authorization)
    try:
        claims = validation.verify_bearer(token)
    except validation.TokenInvalid as e:
        raise _Http(401, f"invalid token: {e}")
    except validation.WrongAudience as e:
        audit.emit(decision="denied_audience", provider=provider, detail=str(e))
        raise _Http(403, f"wrong audience: {e}")

    user = claims.get("preferred_username")
    agent = claims.get("azp")
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
        raise _Http(403, "no grant for this user/provider")

    # Step: requested scopes must be a subset of the grant (never contact provider otherwise).
    if not validation.scopes_subset(requested, grant["granted_scopes"]):
        audit.emit(decision="denied_scope", user=user, agent=agent, provider=provider,
                   scopes=" ".join(requested))
        raise _Http(403, "requested scopes exceed grant")

    # Step: per-agent consent (OpenFGA can_use).
    if not consent.is_allowed(agent, user, provider):
        audit.emit(decision="denied_consent", user=user, agent=agent, provider=provider)
        raise _Http(403, "agent not consented for this grant")

    try:
        issued = grants.issue_provider_token(user, provider)
    except grants.GrantError as e:
        audit.emit(decision="error", user=user, agent=agent, provider=provider, detail=str(e))
        raise _Http(502, f"provider issuance failed: {e}")

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
        raise _Http(401, f"invalid token: {e}")
    except validation.WrongAudience as e:
        raise _Http(403, f"wrong audience: {e}")
    user = claims.get("preferred_username")
    try:
        summary = grants.import_grant(token, user, provider)
    except grants.GrantError as e:
        audit.emit(decision="import_failed", user=user, provider=provider, detail=str(e))
        raise _Http(502, f"grant import failed: {e}")
    audit.emit(decision="grant_imported", user=user, provider=provider,
               scopes=summary["scopes"])
    return JSONResponse(summary)


@app.post("/v1/grants/{provider}/revoke")
def revoke_grant(provider: str, authorization: str | None = Header(default=None)) -> JSONResponse:
    token = _bearer(authorization)
    try:
        claims = validation.verify_signature(token)
    except validation.TokenInvalid as e:
        raise _Http(401, f"invalid token: {e}")
    user = claims.get("preferred_username")
    grants.revoke_grant(user, provider)
    fga.delete_all_can_use(user, provider)  # revoke drops all can_use tuples
    audit.emit(decision="grant_revoked", user=user, provider=provider)
    return JSONResponse({"revoked": True, "provider": provider})


@app.get("/consent")
def consent_screen() -> FileResponse:
    return FileResponse(os.path.join(HERE, "consent.html"))


@app.post("/consent")
async def write_consent(request: Request,
                        authorization: str | None = Header(default=None)) -> JSONResponse:
    token = _bearer(authorization)
    try:
        claims = validation.verify_signature(token)
    except validation.TokenInvalid as e:
        raise _Http(401, f"invalid token: {e}")
    # The authenticated user is the grant owner — a user consents only for their
    # own grants. operator == owner is then enforced inside consent.grant_consent.
    user = claims.get("preferred_username")
    body = await request.json()
    agent = body.get("agent")
    provider = body.get("provider")
    if not agent or not provider:
        raise _Http(400, "agent and provider required")
    if not grants.grant_exists(user, provider):
        raise _Http(404, "no grant to consent to")
    try:
        consent.grant_consent(agent, user, provider)
    except consent.ConsentRefused as e:
        audit.emit(decision="consent_refused", user=user, agent=agent, provider=provider,
                   detail=str(e))
        raise _Http(403, f"consent refused: {e}")
    audit.emit(decision="consent_granted", user=user, agent=agent, provider=provider)
    return JSONResponse({"consented": True, "agent": agent, "provider": provider})


@app.post("/v1/consent/revoke")
async def revoke_consent(request: Request,
                         authorization: str | None = Header(default=None)) -> JSONResponse:
    token = _bearer(authorization)
    try:
        claims = validation.verify_signature(token)
    except validation.TokenInvalid as e:
        raise _Http(401, f"invalid token: {e}")
    user = claims.get("preferred_username")
    body = await request.json()
    agent = body.get("agent")
    provider = body.get("provider")
    consent.revoke_consent(agent, user, provider)
    audit.emit(decision="consent_revoked", user=user, agent=agent, provider=provider)
    return JSONResponse({"revoked": True, "agent": agent, "provider": provider})
