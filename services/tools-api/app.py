"""Prokura Tools-API — a resource server exposing a sensitive action,
`email.send`, that requires human approval. Before sending, it verifies the
action against the approved payload hash and enforces single-use, via the
approval service's /consume endpoint (human-approval spec, F8-A).

The action is gated twice: the bearer must be addressed to this resource
(aud=agent-tools-api — the M1 defense), AND the presented action token must map
to an approved, unconsumed reference whose hash matches this exact action.
"""

import os
import smtplib
from email.message import EmailMessage

import httpx
from fastapi import FastAPI, Header, Request
from fastapi.responses import JSONResponse

import config
import validation
from telemetry import setup_telemetry, tracer

app = FastAPI(title="prokura-tools-api")
setup_telemetry(app)


class _Http(Exception):
    def __init__(self, status: int, detail: str):
        self.status, self.detail = status, detail


@app.exception_handler(_Http)
async def _h(_: Request, e: _Http) -> JSONResponse:
    return JSONResponse({"error": e.detail}, status_code=e.status)


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True}


@app.post("/tools/email/send")
async def email_send(request: Request, authorization: str | None = Header(default=None)) -> JSONResponse:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise _Http(401, "missing bearer token")
    ciba_token = authorization.split(" ", 1)[1]
    try:
        validation.verify_bearer(ciba_token)         # aud=agent-tools-api (M1 defense)
    except validation.TokenInvalid as e:
        raise _Http(401, f"invalid token: {e}")
    except validation.WrongAudience as e:
        raise _Http(403, f"wrong audience: {e}")

    body = await request.json()
    action_token = body.get("action_token", "")
    params = {k: body.get(k) for k in ("to", "subject", "body")}
    if not all(params.values()):
        raise _Http(400, "to, subject, body required")

    # Verify hash + single-use against the approval service. This is the gate:
    # the action must match exactly what the human approved, and be unconsumed.
    with tracer().start_as_current_span("approval.consume") as span:
        span.set_attribute("prokura.action", "email.send")
        r = httpx.post(f"{config.APPROVAL_URL}/consume", json={
            "action_token": action_token, "ciba_token": ciba_token,
            "action": "email.send", "params": params}, timeout=10.0)
    if r.status_code != 200:
        detail = r.json().get("error", r.text[:150]) if r.headers.get("content-type","").startswith("application/json") else r.text[:150]
        raise _Http(r.status_code if r.status_code in (401, 403, 409) else 502,
                    f"approval refused: {detail}")

    # Approved, matched, and consumed — send through the Mailpit sink.
    with tracer().start_as_current_span("email.send"):
        msg = EmailMessage()
        msg["From"] = config.MAIL_FROM
        msg["To"] = params["to"]
        msg["Subject"] = params["subject"]
        msg.set_content(params["body"])
        with smtplib.SMTP(config.MAILPIT_HOST, config.MAILPIT_PORT, timeout=10) as s:
            s.send_message(msg)
    return JSONResponse({"sent": True, "to": params["to"], "subject": params["subject"]})
