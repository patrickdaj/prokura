"""The SIMULATED HUMAN (M7, D6) — the one place in the test suite where a human
capacity is played by automation, explicitly labeled as such.

Everything here drives the REAL surfaces the way a person would: the Keycloak
login page (username + password typed into the form), the Keycloak consent and
device-verification screens, and Prokura's trusted approval/consent UIs in a
real browser (Playwright, headless Chromium). Correct in mechanism, simulated
in actor — which is what CI requires.

Consequences of the quarantine:
- User passwords exist ONLY in this module. Agent-side kits (approvalkit,
  brokerkit, mcpkit, ragkit) hold none, and the separation-invariant test
  (test_party_separation.py) greps them to prove it.
- No approval decision, consent write, or CIBA leg happens outside a browser
  session here (mechanism tests hit service APIs with service credentials, but
  never a human capacity).

One browser context per user is kept alive for the pytest session (SSO makes
repeat logins form-less, like a person's browser)."""

import atexit
import http.server
import os
import threading

APPROVAL_URL = "http://localhost:8120"
BROKER_URL = "http://localhost:8110"

# One real callback listener for every auth-code flow the human completes: a
# server 302 cannot be intercepted by Playwright routing, so the redirect must
# land on a live socket (same pattern as demo/capture/flow_a.py).
CALLBACK_HOST, CALLBACK_PORT = "127.0.0.1", 9876
_hits: list[str] = []
_listener = None


def _ensure_listener() -> None:
    global _listener
    if _listener:
        return

    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):  # noqa: N802
            pass

        def do_GET(self):  # noqa: N802
            _hits.append(f"http://{CALLBACK_HOST}:{CALLBACK_PORT}{self.path}")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"<title>ok</title>Signed in \xe2\x80\x94 you can close this tab.")

    _listener = http.server.HTTPServer((CALLBACK_HOST, CALLBACK_PORT), H)
    threading.Thread(target=_listener.serve_forever, daemon=True).start()

_PASSWORDS = {
    "alice": os.environ.get("DEMO_PASSWORD", "alice"),
    "bob": os.environ.get("DEMO_PASSWORD_BOB", "bob"),
}

_pw = None
_browser = None
_contexts: dict[str, object] = {}


def _ensure_browser():
    global _pw, _browser
    if _pw is None:
        from playwright.sync_api import sync_playwright
        _pw = sync_playwright().start()
        _browser = _pw.chromium.launch()
        atexit.register(_shutdown)
    return _browser


def _context(user: str):
    """A per-user browser context (SSO cookie jar), lazily started."""
    _ensure_browser()
    if user not in _contexts:
        _contexts[user] = _browser.new_context()
    return _contexts[user]


def new_capture_context(**kwargs):
    """A fresh context on the shared browser — for demo captures that want their
    own viewport (a second sync_playwright() in one thread is not allowed).
    Caller closes it."""
    return _ensure_browser().new_context(**kwargs)


def _shutdown() -> None:
    global _pw, _browser
    try:
        if _browser:
            _browser.close()
        if _pw:
            _pw.stop()
    except Exception:
        pass
    _pw = _browser = None


def _step(page, user: str) -> bool:
    """Advance one human step if a known screen is showing. Returns True if a
    step was taken."""
    if page.locator("#kc-form-login").count():
        page.fill("#username", user)
        page.fill("#password", _PASSWORDS[user])
        page.click("#kc-login")
        page.wait_for_load_state()
        return True
    # Keycloak consent / grant-access screen (also shown for device flow):
    # a submit control named "accept" (button in KC 26, input historically).
    for sel in ("button[name=accept]", "input[name=accept]"):
        if page.locator(sel).count():
            page.click(sel)
            page.wait_for_load_state()
            return True
    return False


def _drive_until(page, user: str, done, max_steps: int = 8) -> None:
    for _ in range(max_steps):
        if done():
            return
        if not _step(page, user):
            page.wait_for_timeout(500)
    raise AssertionError(f"human flow stuck at {page.url[:120]}")


# --- generic OAuth legs -------------------------------------------------------

def auth_code_login(auth_url: str, redirect_prefix: str, user: str = "alice") -> str:
    """Open an authorization URL in the user's browser, complete login (and any
    consent screen) on the REAL Keycloak pages, and return the full redirect
    URL (carrying ?code=...) captured by the live callback listener. The
    redirect_prefix must point at the humankit listener (127.0.0.1:9876)."""
    assert redirect_prefix.startswith(f"http://{CALLBACK_HOST}:{CALLBACK_PORT}"), \
        f"redirect must land on the humankit listener, got {redirect_prefix}"
    _ensure_listener()
    ctx = _context(user)
    n0 = len(_hits)
    page = ctx.new_page()
    try:
        page.goto(auth_url)
        _drive_until(page, user,
                     lambda: len(_hits) > n0 and _hits[-1].startswith(redirect_prefix))
    finally:
        page.close()
    return _hits[-1]


def approve_device(verification_uri_complete: str, user: str = "alice") -> None:
    """Complete an RFC 8628 device-code verification as the human: real login,
    real device-consent screen, in the user's own browser session."""
    ctx = _context(user)
    page = ctx.new_page()
    try:
        page.goto(verification_uri_complete)

        def done():
            body = page.content()
            return "Device Login Successful" in body or "successfully" in body.lower()

        _drive_until(page, user, done)
    finally:
        page.close()


# --- Prokura trusted surfaces -------------------------------------------------

def drive_approval(ref: str, user: str = "alice", approve: bool = True) -> str:
    """Follow the deep link (/approvals#ref) as the human: OIDC login on the
    approval surface, review the service-rendered payload, click Approve/Deny.
    Returns the result line shown to the user."""
    ctx = _context(user)
    page = ctx.new_page()
    try:
        page.goto(f"{APPROVAL_URL}/approvals#{ref}")
        _drive_until(page, user,
                     lambda: page.url.startswith(APPROVAL_URL) and (
                         page.locator("#approve").is_visible()
                         or page.locator("#state").is_visible()))
        if not page.locator("#approve").is_visible():
            return page.locator("#state").inner_text()
        page.click("#approve" if approve else "#deny")
        page.locator("#result").wait_for(state="visible", timeout=10_000)
        return page.locator("#result").inner_text()
    finally:
        page.close()


def drive_consent(agent: str, provider: str, user: str = "alice",
                  allow: bool = True) -> tuple[bool, str]:
    """Open the broker's consent screen for (agent, provider) as the human:
    OIDC login, click Allow/Deny. Returns (ok, result_text) — ok is True only
    when the surface confirmed a consent write."""
    ctx = _context(user)
    page = ctx.new_page()
    try:
        page.goto(f"{BROKER_URL}/consent?agent={agent}&provider={provider}")
        _drive_until(page, user,
                     lambda: page.url.startswith(f"{BROKER_URL}/consent")
                     and page.locator("#allow").is_visible())
        page.click("#allow" if allow else "#deny")
        page.locator("#result").wait_for(state="visible", timeout=10_000)
        text = page.locator("#result").inner_text()
        return text.startswith("✓"), text
    finally:
        page.close()


def revoke_consent(agent: str, provider: str, user: str = "alice") -> dict:
    """Revoke one agent's consent from the human's authenticated session on the
    consent surface (the revoke endpoint is session-only in M7)."""
    ctx = _context(user)
    page = ctx.new_page()
    try:
        page.goto(f"{BROKER_URL}/consent")
        _drive_until(page, user,
                     lambda: page.url.startswith(f"{BROKER_URL}/consent")
                     and page.locator("#allow").is_visible())
        return page.evaluate(
            """async ([agent, provider]) => {
                const r = await fetch('/v1/consent/revoke', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({agent, provider})});
                return {status: r.status, body: await r.json()};
            }""", [agent, provider])
    finally:
        page.close()
