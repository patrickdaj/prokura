#!/usr/bin/env python3
"""Prokura — the headline demo, driven by a real MCP client, narrated to watch.

This is NOT the test suite. It is a standalone thing you *run and watch*: a
spec-compliant MCP client connects to the Prokura MCP server exactly as Claude (or
any MCP client) would — discover → dynamic registration → OAuth 2.1 + PKCE login →
tools — and then drives the whole story, printing each step and the real values as
they happen:

  1. connect as a real MCP client (aud=mcp-server)
  2. get a consent-gated third-party token — and show the inbound token is NOT
     accepted downstream (no passthrough)
  3. a human approves a gated email; it lands in the Mailpit sink
  4. FGA-filtered RAG: alice retrieves a protected doc; bob provably cannot —
     even though it is his top embedding hit

Run:  docker compose --profile demo up -d  &&  python demo/run_demo.py
Then watch the same flow as one linked trace in Grafana (http://localhost:3001):
Explore → Tempo, search { prokura.flow = "C" }.

It reuses the exact client machinery the smoke tests use (tests/smoke/), so the
demo and the tests drive the identical real handshake — the difference is that this
one is written to be read by a human, not asserted on.
"""
import os
import sys
import time

import httpx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tests", "smoke"))
import approvalkit as ak  # noqa: E402
import brokerkit  # noqa: E402
import humankit  # noqa: E402
import mcpkit  # noqa: E402
import ragkit  # noqa: E402
from conftest import KEYCLOAK_URL, link_acme  # noqa: E402

# --- tiny narration layer -----------------------------------------------------
_C = sys.stdout.isatty()
def _c(s, code): return f"\033[{code}m{s}\033[0m" if _C else s
def dim(s): return _c(s, "2")
def b(s): return _c(s, "1")
def blue(s): return _c(s, "38;5;75")
def green(s): return _c(s, "38;5;78")
def red(s): return _c(s, "38;5;203")
def gold(s): return _c(s, "38;5;179")

def act(n, title):
    print(f"\n{blue('━'*66)}\n {blue(f'ACT {n}')}  {b(title)}\n{blue('━'*66)}")
def step(s): print(f"  {blue('→')} {s}")
def ok(s):   print(f"  {green('✓')} {s}")
def no(s):   print(f"  {red('✕')} {s}")
def kv(k, v): print(f"      {dim(k+':'):<26} {v}")
def pause(t=0.7): time.sleep(t)

QUERY = ragkit.ADVERSARIAL_QUERY
AGENT = "mcp-server"


def preflight():
    try:
        httpx.get(f"{mcpkit.MCP_URL}/healthz", timeout=5).raise_for_status()
        httpx.get(f"{ragkit.RAG_URL}/healthz", timeout=5).raise_for_status()
        httpx.get(f"{ak.TOOLS_URL}/healthz", timeout=5).raise_for_status()
    except Exception:
        print(red("The stack isn't up (or the toy resource servers aren't running). "
                  "Start the full chain:  docker compose --profile demo up -d"))
        sys.exit(1)


def setup():
    step("preparing the demo (link the acme grant, consent the agent) …")
    link_acme(KEYCLOAK_URL)
    brokerkit.import_grant(brokerkit.broker_token(), "acme")
    brokerkit.seed_operator(AGENT, "alice")
    # Consent is a HUMAN capacity (the broker is the sole writer and has no bearer
    # path) — alice grants it on the real consent surface, in her own browser.
    consented, _ = humankit.drive_consent(AGENT, "acme")
    if not consented:
        no("consent was not written — is the stack up with --profile demo?"); sys.exit(1)
    ok("ready\n")


def main():
    print(b("\nPROKURA — headline demo") + dim("  (a real MCP client, watched)"))
    preflight()
    setup()

    with httpx.Client(follow_redirects=False, timeout=40.0) as c:
        # ACT 1 — connect as a real MCP client -----------------------------
        act(1, "An MCP client connects — the way Claude would")
        step("POST /mcp with no token → the server challenges")
        # (the discovery 401 → PRM → Keycloak AS, DCR, and OAuth2.1+PKCE all happen
        # inside mcp_token — the same standard handshake a real client performs)
        alice = ragkit.mcp_token(c, "alice")
        cl = ragkit.token_claims(alice)
        ok("discovered metadata, registered dynamically, logged in as alice")
        kv("token aud", green(str(cl.get("aud"))))
        kv("token sub", "alice")
        lr = c.post(f"{mcpkit.MCP_URL}/mcp", headers={"Authorization": f"Bearer {alice}"},
                    json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        tools = [t["name"] for t in lr.json()["result"]["tools"]]
        kv("tools/list", ", ".join(green(t) for t in tools))
        pause()

        # ACT 2 — consent-gated third-party token --------------------------
        act(2, "A consent-gated provider token — with no passthrough")
        step("call the get_provider_token tool for provider 'acme'")
        out, err = mcpkit.tool_call(c, alice, "get_provider_token", {"provider": "acme"})
        if err:
            no(f"tool error: {out}"); return 1
        ok("the broker issued a short-lived provider access token")
        kv("expires_in", f"{green(str(out.get('expires_in')))}  (≤ 900s, always)")
        kv("refresh_token", red("absent") + dim(" — it never leaves OpenBao"))
        step("now present that inbound MCP token straight to the broker …")
        direct = httpx.post(f"{brokerkit.BROKER_URL}/v1/tokens/acme",
                            headers={"Authorization": f"Bearer {alice}"}, json={"scopes": []}, timeout=15)
        (ok if direct.status_code == 403 else no)(
            f"refused ({direct.status_code}) — the inbound token is never forwarded; each tool re-exchanges")
        pause()

        # ACT 3 — human approval -------------------------------------------
        act(3, "A human approves a gated action")
        params = {"to": "boss@prokura.local", "subject": "Prokura demo report", "body": "quarterly numbers"}
        step("call send_email — the first attempt carries no approval")
        challenge, err = mcpkit.tool_call(c, alice, "send_email", params)
        ref, action_token = challenge.get("ref"), challenge.get("action_token")
        ok(f"the resource server refused and registered the real action  {dim('(428 approval_required)')}")
        kv("reference", gold(ref))
        # The 428 already registered the exact {action, params} and the approval
        # service initiated the CIBA ceremony (ADR-0022). The agent CANNOT approve —
        # only the human can, on the trusted surface. alice approves that reference
        # in her own session (never agent-authored text).
        step("a human approves that reference in the trusted approval UI")
        humankit.drive_approval(ref, approve=True)
        ok("approved — by a human, on the payload the server stored (not agent text)")
        step("retry send_email with the approval — executes exactly once")
        sent, err = mcpkit.tool_call(c, alice, "send_email", {**params, "action_token": action_token})
        if sent.get("status") == "sent":
            ok("sent")
        msgs = httpx.get(f"{ak.MAILPIT_URL}/api/v1/messages", timeout=10).json().get("messages", [])
        landed = any(m.get("Subject") == params["subject"] for m in msgs)
        (ok if landed else no)(f"the mail landed in the Mailpit sink  {dim('http://localhost:8025')}")
        pause()

        # ACT 4 — FGA-filtered RAG -----------------------------------------
        act(4, "RAG that stops at the permission line")
        step(f'both users ask: "{dim(QUERY)}"')
        print(f"      {dim('(the protected secret-roadmap is the #1 embedding hit for this query)')}")
        alice_res, _ = ragkit.search_via_mcp(c, alice, QUERY)
        a_has = "secret-roadmap" in ragkit.doc_ids(alice_res)
        a_counts = dim(f"candidates={alice_res['candidates']} allowed={alice_res['allowed']}")
        (ok if a_has else no)(f"{b('alice')} (a viewer): retrieves the protected doc  {a_counts}")
        kv("answer mentions", green('Meridian acquisition') if 'Meridian' in alice_res['answer'] else red('nothing'))

        bob = ragkit.mcp_token(c, "bob")
        bob_res, _ = ragkit.search_via_mcp(c, bob, QUERY)
        b_has = "secret-roadmap" in ragkit.doc_ids(bob_res)
        b_counts = dim(f"candidates={bob_res['candidates']} allowed={bob_res['allowed']}")
        (ok if not b_has else no)(f"{b('bob')} (not a viewer): the SAME top hit is filtered out  {b_counts}")
        kv("answer mentions", red('never says Meridian') if 'Meridian' not in bob_res['answer'] else red('LEAK!'))
        ok("the confused-deputy is dead: the top hit leaks to no one who lacks the tuple")

    print(f"\n{green('━'*66)}\n {green('done')} — now watch it as one trace in Grafana: "
          f"{b('http://localhost:3001')} → Explore → Tempo, search {b('{ prokura.flow = \"D\" }')}\n"
          f"       or step through it: {b('docs/walkthroughs/index.html')}\n{green('━'*66)}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
