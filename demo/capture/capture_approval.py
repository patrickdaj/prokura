#!/usr/bin/env python3
"""Flow C capture — human approval (M7 ceremony). Drives a real send_email to a
428 (the approval service initiates CIBA server-side at registration), follows
the deep link as the HUMAN — real OIDC login on the approval surface, real
Approve click — retries the tool, and captures the delivered mail in Mailpit.

Reuses the exact smoke-test client machinery (tests/smoke); the browser leg here
is a capture-flavored simulated human (alice's password lives only in the
browser-driving code, never in agent-side calls)."""
import os
import sys

import httpx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "tests", "smoke"))
import approvalkit as ak  # noqa: E402
import humankit  # noqa: E402
import brokerkit  # noqa: E402
import mcpkit  # noqa: E402
import ragkit  # noqa: E402
from conftest import KEYCLOAK_URL, link_acme  # noqa: E402

IMG = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..",
                                   "docs", "walkthroughs", "img"))
AGENT = "mcp-server"
PARAMS = {"to": "board@prokura.local", "subject": "Q3 board update — revenue & hiring",
          "body": "Revenue up 12% QoQ. Hiring plan and full deck attached for Thursday."}


def shot(page, name, wait=1400):
    page.wait_for_timeout(wait)
    page.screenshot(path=os.path.join(IMG, name))
    print("saved", name)


def main():
    link_acme(KEYCLOAK_URL)
    brokerkit.seed_operator(AGENT, "alice")
    with httpx.Client(follow_redirects=False, timeout=40.0) as c:
        alice = ragkit.mcp_token(c, "alice")
        challenge, err = mcpkit.tool_call(c, alice, "send_email", PARAMS)
        assert not err, f"unexpected: {challenge}"
        ref, action_token = challenge["ref"], challenge["action_token"]
        print("428 approval_required — ref:", ref,
              "(ceremony already initiated server-side)")

        # The HUMAN leg: follow the deep link, sign in on the real surface, approve.
        ctx = humankit.new_capture_context(
            viewport={"width": 1360, "height": 940}, device_scale_factor=2)
        p = ctx.new_page()
        p.goto(f"{ak.APPROVAL_URL}/approvals#{ref}", wait_until="networkidle")
        if p.locator("#kc-form-login").count():
            p.fill("#username", "alice")
            p.fill("#password", "alice")
            shot(p, "flowC-login.png", wait=400)   # the M7 surface sign-in
            p.click("#kc-login")
            p.wait_for_load_state("networkidle")
        p.wait_for_selector("#approve", timeout=10000)
        shot(p, "flowC-approval.png")              # the payload + Approve/Deny
        p.click("#approve")
        shot(p, "flowC-approved.png")               # the approved confirmation
        ctx.close()

        sent, err = mcpkit.tool_call(c, alice, "send_email", {**PARAMS, "action_token": action_token})
        print("retry send_email →", sent, "err:", err)

    # the mail actually landed — capture it in Mailpit
    ctx = humankit.new_capture_context(
        viewport={"width": 1360, "height": 940}, device_scale_factor=2)
    p = ctx.new_page()
    p.goto("http://localhost:8025", wait_until="networkidle")
    p.wait_for_timeout(1500)
    try:
        p.get_by_text(PARAMS["subject"][:20], exact=False).first.click(timeout=6000)
    except Exception as e:
        print("mailpit click:", str(e)[:80])
    shot(p, "flowC-mailpit.png")
    ctx.close()
    print("done")


if __name__ == "__main__":
    main()
