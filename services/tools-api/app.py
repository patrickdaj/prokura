"""Prokura Tools-API — a resource server exposing a sensitive action,
`email.send`, that requires human approval. Before sending, it verifies the
action against the approved payload hash and enforces single-use, via the
approval service's /consume endpoint (human-approval spec, F8-A).

The action is gated twice: the bearer must be addressed to this resource
(aud=agent-tools-api — the M1 defense), AND the presented action token must map
to an approved, unconsumed reference whose hash matches this exact action.

Reactive approval (M4, re-wired in M7): the approval **trigger** lives here, not
on the agent. A call arriving WITHOUT an action_token is refused with a `428`
`approval_required` challenge — the tools-API registers the exact `{action,
params}` it observed with the approval service, which initiates the CIBA
ceremony itself (ADR-0022). The agent's whole role is: wait, then retry with the
returned action token. The action that gets approved is the one this server saw,
never one the agent described.
"""

import os
import smtplib
from email.message import EmailMessage

import httpx
from fastapi import FastAPI, Header, Request
from fastapi.responses import JSONResponse

import config
import validation
from prokura_telemetry import setup, tracer

app = FastAPI(title="prokura-tools-api")
setup(app, config.SERVICE_NAME)


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
        raise _Http(401, "missing_token")
    user_token = authorization.split(" ", 1)[1]
    try:
        validation.verify_bearer(user_token)         # aud=agent-tools-api (M1 defense)
    except validation.TokenInvalid:
        # SR-01: stable codes only; the library detail stays server-side.
        raise _Http(401, "invalid_token")
    except validation.WrongAudience:
        raise _Http(403, "wrong_audience")

    body = await request.json()
    action_token = body.get("action_token", "")
    params = {k: body.get(k) for k in ("to", "subject", "body")}
    if not all(params.values()):
        raise _Http(400, "missing_fields")

    # Reactive approval (M4): no action token means the caller has not (yet)
    # been approved. The trigger is HERE, not on the agent — we register the
    # exact action we observed with the approval service and challenge with 428.
    if not action_token:
        # M7 (ADR-0022): registration now also makes the approval service
        # initiate the CIBA ceremony server-side. The agent's next step is only
        # to wait and retry with the action token — nothing else exists for it.
        with tracer().start_as_current_span("approval.register") as span:
            span.set_attribute("prokura.action", "email.send")
            reg = httpx.post(f"{config.APPROVAL_URL}/register",
                             headers={"Authorization": authorization},
                             json={"action": "email.send", "params": params}, timeout=15.0)
        if reg.status_code != 200:
            raise _Http(502, "approval_registration_failed")
        j = reg.json()
        # 428 Precondition Required: the request must first satisfy the human-approval
        # precondition. The action that will be approved is the one registered above.
        return JSONResponse({"error": "approval_required", "ref": j["ref"],
                             "action_token": j["action_token"]}, status_code=428)

    # Verify hash + single-use against the approval service. This is the gate:
    # the action must match exactly what the human approved, and be unconsumed.
    # Our validated bearer proves WHICH user the caller acts for (M7: the
    # CIBA-issued token no longer exists on the agent side).
    with tracer().start_as_current_span("approval.consume") as span:
        span.set_attribute("prokura.action", "email.send")
        r = httpx.post(f"{config.APPROVAL_URL}/consume", json={
            "action_token": action_token, "user_token": user_token,
            "action": "email.send", "params": params}, timeout=10.0)
    if r.status_code != 200:
        # Relay the approval service's stable machine code (SR-01: never free text).
        code = r.json().get("error", "approval_refused") if r.headers.get(
            "content-type", "").startswith("application/json") else "approval_refused"
        raise _Http(r.status_code if r.status_code in (401, 403, 409) else 502, code)

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
