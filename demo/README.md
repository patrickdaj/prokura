# Prokura demo

`run_demo.py` is the headline demo you **run and watch** — not the test suite. A
spec-compliant MCP client connects to the Prokura MCP server exactly as Claude (or any
MCP client) would — discover → dynamic client registration → OAuth 2.1 + PKCE login →
tools — and then drives the whole story, printing each step and the real values as they
happen.

```bash
docker compose up -d          # bring the stack up
python demo/run_demo.py        # watch a real MCP client drive the chain
```

Four acts:

1. **Connect** as a real MCP client → an `aud=mcp-server` token, `tools/list`.
2. **A consent-gated provider token** — short-lived, no refresh token; and the inbound
   MCP token is **refused downstream** (no passthrough — each tool re-exchanges).
3. **Human approval** — `send_email` is refused with a `428`, a human approves the
   server-stored payload via CIBA, the retry sends once, the mail lands in Mailpit.
4. **FGA-filtered RAG** — alice retrieves a protected doc; bob provably cannot, even
   though it is his **top embedding hit**.

Then watch the same flow as one linked trace in the console
(`http://localhost:8095`), or step through it in the
[walkthroughs](../docs/walkthroughs/index.html).

It reuses the exact client machinery the smoke tests use (`tests/smoke/`), so the demo
and the tests drive the identical real handshake — this one is written to be read by a
human, not asserted on.
