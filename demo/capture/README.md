# Walkthrough capture

Scripts that regenerate the **real** assets embedded in the guided walkthroughs
(`docs/walkthroughs/`). Each drives the *running* stack — nothing is mocked — and
writes PNGs into `docs/walkthroughs/img/`.

```bash
docker compose --profile demo up -d        # full chain must be running (toy servers are demo-profiled)
pip install playwright && playwright install chromium

# Flow A — real login + explicit consent + delegated token
python demo/capture/flow_a.py              # -> flowA-01-login / -02-consent / -03-granted .png

# Flow B — the provider refresh credential sealed in OpenBao
python demo/capture/capture_openbao.py     # -> flowB-openbao.png

# Flow C — 428 -> trusted approval UI -> real Approve click -> Mailpit
python demo/capture/capture_approval.py    # -> flowC-approval / -approved / -mailpit .png

# Flow D — alice-vs-bob FGA-filtered retrieval (data, not a screenshot)
python demo/capture/capture_rag.py         # -> flow_d.result.json

# Telemetry — REAL Grafana/Tempo/Loki screenshots (the observability surface).
# Find a flow-tagged trace id first (health-check noise carries no tag):
#   curl -s 'http://localhost:3001/api/datasources/proxy/uid/tempo/api/search' \
#     --data-urlencode 'q={ span.prokura.flow = "D" }' -G | python3 -m json.tool
python demo/capture/capture_grafana.py trace <trace_id> trace-flowD      # Tempo waterfall
python demo/capture/capture_grafana.py logs <trace_id> trace-logs        # trace->logs (Loki) jump
python demo/capture/capture_grafana.py dashboard prokura-delegation dashboard-overview
```

Notes:
- `flow_a.py` configures an explicit consent screen for **its own** DCR client only
  (a per-client `default-client-scope` + `consentRequired`), so scripted logins used
  by the other captures and the smoke tests are unaffected.
- `capture_grafana.py` deep-links Grafana **Explore → Tempo/Loki**, collapses noise
  (query editor + Keycloak's internal subtrees), and clips the panel to a PNG. It
  replaced the old `capture_trace.py`/`capture_console.py` (which drove the removed
  `:8095` console) — the observability surface is Grafana now (ADR-0025).
- The walkthrough pages are static HTML: the telemetry visuals are real screenshots in
  `docs/walkthroughs/img/`, so re-running a capture and committing the new PNG refreshes them.
