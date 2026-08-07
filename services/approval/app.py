"""Prokura Approval Service — CIBA-gated human approval for sensitive actions
(human-approval spec). Joins the trusted computing base.

Endpoints:
  GET  /healthz
  POST /register                 agent registers {action,params} -> {ref, action_token}
  POST /ciba/delegate            Keycloak's CIBA delegation receiver (201)
  GET  /approvals                trusted UI (authenticated) — list + render payloads
  GET  /approval/{ref}           JSON payload for the UI (service-held, never agent text)
  POST /approval/{ref}/decide    approve/deny -> relay to Keycloak CIBA callback
  POST /consume                  the gated tool verifies hash + single-use here

The action token (`<ref>.<secret>`) is issued at registration but is INVALID
until the ref reaches 'approved' via the CIBA ceremony; consume() is the atomic
single-use gate.
"""

import hashlib
import json
import os
import secrets

import httpx
from fastapi import FastAPI, Header, Request
from fastapi.responses import FileResponse, JSONResponse

import audit
import config
import db
import ntfy
import validation
from telemetry import setup_telemetry, tracer

HERE = os.path.dirname(__file__)
app = FastAPI(title="prokura-approval")
setup_telemetry(app)


@app.on_event("startup")
def _startup() -> None:
    db.init_db()


class _Http(Exception):
    def __init__(self, status: int, detail: str):
        self.status, self.detail = status, detail


@app.exception_handler(_Http)
async def _h(_: Request, e: _Http) -> JSONResponse:
    return JSONResponse({"error": e.detail}, status_code=e.status)


def _bearer(authz: str | None) -> str:
    if not authz or not authz.lower().startswith("bearer "):
        raise _Http(401, "missing bearer token")
    return authz.split(" ", 1)[1]


def _hash(action: str, params: dict) -> str:
    canonical = json.dumps({"action": action, "params": params},
                           sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True}


@app.post("/register")
async def register(request: Request, authorization: str | None = Header(default=None)) -> JSONResponse:
    # Authenticated by the agent's user token (sub=user, azp=agent).
    claims = _verify(_bearer(authorization))
    user, agent = claims.get("preferred_username"), claims.get("azp")
    body = await request.json()
    action, params = body.get("action"), body.get("params", {})
    if not action:
        raise _Http(400, "action required")
    scopes = body.get("scopes", "")
    ref = "apr-" + secrets.token_hex(12)          # binding-message safe (hex only)
    secret = secrets.token_urlsafe(24)
    db.create(ref, agent, user, action, params, _hash(action, params), scopes, secret)
    audit.emit("registered", ref=ref, user=user, agent=agent, action=action)
    return JSONResponse({"ref": ref, "action_token": f"{ref}.{secret}"})


@app.post("/ciba/delegate", status_code=201)
async def ciba_delegate(request: Request) -> JSONResponse:
    # Keycloak's built-in CIBA HTTP channel POSTs here (must return 201).
    token = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
    body = await request.json()
    ref = body.get("binding_message", "")
    with tracer().start_as_current_span("ciba.delegate") as span:
        span.set_attribute("prokura.approval.ref", ref)
        row = db.get(ref)
        if row and db.set_delegation(ref, token):
            audit.emit("delegated", ref=ref, user=row["user_id"], agent=row["agent"])
            ntfy.notify(row["user_id"], ref)          # deep link + ref only
    return JSONResponse({"received": True}, status_code=201)


@app.get("/approvals")
def approvals_ui() -> FileResponse:
    return FileResponse(os.path.join(HERE, "approval.html"))


@app.get("/approval/{ref}")
def approval_payload(ref: str, authorization: str | None = Header(default=None)) -> JSONResponse:
    claims = _verify(_bearer(authorization))
    row = db.get(ref)
    if not row or row["user_id"] != claims.get("preferred_username"):
        raise _Http(404, "no such approval")
    # Rendered from service-held data — never any agent-supplied string.
    return JSONResponse({"ref": row["ref"], "agent": row["agent"], "action": row["action"],
                         "params": row["params"], "scopes": row["scopes"], "status": row["status"]})


@app.get("/my/approvals")
def my_approvals(authorization: str | None = Header(default=None)) -> JSONResponse:
    claims = _verify(_bearer(authorization))
    return JSONResponse(db.list_for_user(claims.get("preferred_username")))


@app.post("/approval/{ref}/decide")
async def decide(ref: str, request: Request, authorization: str | None = Header(default=None)) -> JSONResponse:
    claims = _verify(_bearer(authorization))       # authenticated Keycloak session
    row = db.get(ref)
    if not row or row["user_id"] != claims.get("preferred_username"):
        raise _Http(404, "no such approval")
    body = await request.json()
    approve = body.get("decision") == "approve"
    status = "SUCCEED" if approve else "UNAUTHORIZED"
    # The approval service (not the user's device) relays the decision to Keycloak.
    if row.get("delegation_token"):
        with tracer().start_as_current_span("ciba.callback") as span:
            span.set_attribute("prokura.approval.decision", status)
            httpx.post(config.CIBA_CALLBACK, json={"status": status},
                       headers={"Authorization": f"Bearer {row['delegation_token']}"}, timeout=10.0)
    db.set_status(ref, "approved" if approve else "denied")
    audit.emit("approved" if approve else "denied", ref=ref, user=row["user_id"],
               agent=row["agent"], action=row["action"])
    return JSONResponse({"ref": ref, "status": "approved" if approve else "denied"})


@app.post("/consume")
async def consume(request: Request) -> JSONResponse:
    """Called by the gated tool. Verifies the CIBA token's subject, the action
    hash, and single-use, then atomically consumes the reference."""
    body = await request.json()
    action_token = body.get("action_token", "")
    ciba_token = body.get("ciba_token", "")
    action, params = body.get("action"), body.get("params", {})
    ref = action_token.split(".", 1)[0]
    row = db.get(ref)
    if not row or f"{ref}.{row['action_secret']}" != action_token:
        raise _Http(403, "invalid action token")
    if row["status"] != "approved":
        raise _Http(403, f"action not approved (status={row['status']})")
    # The CIBA token proves the caller is the approved user's agent.
    try:
        sub = validation.verify_signature(ciba_token).get("preferred_username")
    except validation.TokenInvalid as e:
        raise _Http(401, f"invalid ciba token: {e}")
    if sub != row["user_id"]:
        raise _Http(403, "ciba token subject does not own this approval")
    if _hash(action, params) != row["hash"]:
        audit.emit("hash_mismatch", ref=ref, user=row["user_id"], agent=row["agent"])
        raise _Http(409, "action does not match the approved payload")
    if not db.consume(ref):                         # atomic single-use
        audit.emit("replay_refused", ref=ref, user=row["user_id"], agent=row["agent"])
        raise _Http(409, "action token already consumed")
    audit.emit("consumed", ref=ref, user=row["user_id"], agent=row["agent"], action=action)
    return JSONResponse({"ok": True, "ref": ref, "action": action, "params": params})


def _verify(token: str) -> dict:
    try:
        return validation.verify_signature(token)
    except validation.TokenInvalid as e:
        raise _Http(401, f"invalid token: {e}")
