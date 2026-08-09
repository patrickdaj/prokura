"""M7 spike surface: one FastAPI app, parameterized by port/cookie-name/client,
run twice (:8961 as surface A, :8962 as surface B) to prove two localhost
sessions coexist in one cookie jar (task 1.2).

Routes:
  GET  /            whoami — 401 without a session, identity JSON with one
  GET  /login       redirect to Keycloak (auth code + PKCE)
  GET  /callback    token exchange -> signed session cookie -> redirect to /
  POST /act         the authorized POST of task 1.1 (session required)
"""

import os
import sys

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse

from websession import WebSession

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8961
NAME = f"surface-{'a' if PORT == 8961 else 'b'}"

ws = WebSession(
    issuer_public=os.environ.get("KC_PUBLIC", "http://localhost:8180/realms/prokura"),
    issuer_internal=os.environ.get("KC_INTERNAL", "http://localhost:8180/realms/prokura"),
    client_id=f"spike-{NAME}",
    client_secret=f"spike-{NAME}-secret",
    redirect_uri=f"http://localhost:{PORT}/callback",
    cookie_name=f"prokura_{NAME}_session",
    secret=f"spike-cookie-key-{NAME}",
)

app = FastAPI(title=f"spike-{NAME}")


@app.get("/")
def whoami(request: Request) -> JSONResponse:
    sess = ws.session_from(request.cookies.get(ws.cookie_name))
    if not sess:
        return JSONResponse({"error": "no session", "login": "/login"}, status_code=401)
    return JSONResponse({"surface": NAME, **sess})


@app.get("/login")
def login(ref: str = "") -> RedirectResponse:
    return RedirectResponse(ws.login_url(ref))


@app.get("/callback")
def callback(code: str, state: str) -> Response:
    out = ws.handle_callback(code, state)
    if out is None:
        return JSONResponse({"error": "login failed"}, status_code=400)
    sess, ref = out
    resp = RedirectResponse(f"/#{ref}" if ref else "/", status_code=303)
    resp.set_cookie(ws.cookie_name, ws.cookie_value(sess),
                    httponly=True, samesite="lax", max_age=ws.max_age)
    return resp


@app.post("/act")
def act(request: Request) -> JSONResponse:
    sess = ws.session_from(request.cookies.get(ws.cookie_name))
    if not sess:
        return JSONResponse({"error": "no session"}, status_code=401)
    return JSONResponse({"acted_as": sess["preferred_username"], "surface": NAME})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")
