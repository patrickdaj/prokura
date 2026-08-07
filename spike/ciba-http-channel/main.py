"""M0 spike (F6-A): receiver for Keycloak's built-in CIBA HTTP authentication channel.

Keycloak POSTs an authentication-delegation request here (JSON body including
binding_message; Authorization: Bearer <delegation token>). The decision goes
back to Keycloak's CIBA callback endpoint authorized by that same bearer token.

If this round-trips, the custom Java SPI is deleted from the plan (M3 becomes
Python + configuration). Deliberately minimal: in-memory state, no auth on the
spike's own endpoints — spike code, not product code.
"""

import os
from typing import Any

import httpx
from fastapi import FastAPI, Request
from pydantic import BaseModel

KEYCLOAK_INTERNAL_URL = os.environ.get("KC_INTERNAL_URL", "http://keycloak:8080")
REALM = os.environ.get("KC_REALM", "prokura")

app = FastAPI(title="prokura-ciba-spike")

# delegation-token -> request payload, insertion-ordered
pending: dict[str, dict[str, Any]] = {}
decided: list[dict[str, Any]] = []


@app.post("/ciba/delegate", status_code=201)  # Keycloak requires 201 Created
async def receive_delegation(request: Request) -> dict:
    token = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
    body = await request.json()
    pending[token] = body
    return {"received": True}


@app.get("/pending")
def list_pending() -> list[dict]:
    return [
        {"index": i, "binding_message": p.get("binding_message"), "login_hint": p.get("login_hint"),
         "scope": p.get("scope"), "is_consent_required": p.get("is_consent_required")}
        for i, p in enumerate(pending.values())
    ]


class Decision(BaseModel):
    status: str  # SUCCEED | UNAUTHORIZED | CANCELLED
    index: int = -1  # default: most recent pending request


@app.post("/decide")
async def decide(decision: Decision) -> dict:
    if not pending:
        return {"error": "no pending delegation requests"}
    token = list(pending.keys())[decision.index]
    payload = pending.pop(token)

    callback = (
        f"{KEYCLOAK_INTERNAL_URL}/realms/{REALM}"
        "/protocol/openid-connect/ext/ciba/auth/callback"
    )
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.post(
            callback,
            json={"status": decision.status},
            headers={"Authorization": f"Bearer {token}"},
        )
    decided.append({"binding_message": payload.get("binding_message"),
                    "status": decision.status, "callback_status": r.status_code})
    return {"callback_status": r.status_code, "callback_body": r.text[:500]}
