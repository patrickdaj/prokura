#!/usr/bin/env python3
"""Flow C capture — human approval. Drives a real send_email to a 428, opens the
trusted approval UI (showing the SERVER-STORED payload), clicks Approve in a real
browser, retries the tool, and captures the delivered mail in Mailpit.

Reuses the exact smoke-test client machinery (tests/smoke)."""
import os
import sys

import httpx
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "tests", "smoke"))
import approvalkit as ak  # noqa: E402
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
        alice = ragkit.mcp_token(c, "alice", "alice")
        challenge, err = mcpkit.tool_call(c, alice, "send_email", PARAMS)
        assert not err, f"unexpected: {challenge}"
        ref, action_token = challenge["ref"], challenge["action_token"]
        print("428 approval_required — ref:", ref)

        with httpx.Client(timeout=40.0) as ac:
            ut = ak.user_token()
            auth_req_id = ak.ciba_init(ref, ac)
            ak.wait_delegated(ref, ut, ac)

            approval_url = f"{ak.APPROVAL_URL}/approvals?ref={ref}&token={ut}"
            with sync_playwright() as pw:
                b = pw.chromium.launch()
                p = b.new_page(viewport={"width": 1360, "height": 940}, device_scale_factor=2)
                p.goto(approval_url, wait_until="networkidle")
                p.wait_for_selector("#approve", timeout=10000)
                shot(p, "flowC-approval.png")          # the payload + Approve/Deny
                p.click("#approve")
                shot(p, "flowC-approved.png")           # the approved confirmation
                b.close()

            ciba_token, status = ak.poll_token(auth_req_id, ac)
            print("ciba poll:", status)

        sent, err = mcpkit.tool_call(c, alice, "send_email", {**PARAMS, "action_token": action_token})
        print("retry send_email →", sent, "err:", err)

    # the mail actually landed — capture it in Mailpit
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        p = b.new_page(viewport={"width": 1360, "height": 940}, device_scale_factor=2)
        p.goto("http://localhost:8025", wait_until="networkidle")
        p.wait_for_timeout(1500)
        try:
            p.get_by_text(PARAMS["subject"][:20], exact=False).first.click(timeout=6000)
        except Exception as e:
            print("mailpit click:", str(e)[:80])
        shot(p, "flowC-mailpit.png")
        b.close()
    print("done")


if __name__ == "__main__":
    main()
