# Walkthrough capture

Scripts that regenerate the **real** assets embedded in the guided walkthroughs
(`docs/walkthroughs/`). Each drives the *running* stack — nothing is mocked — and
writes PNGs into `docs/walkthroughs/img/` or prints an HTML `.wf` waterfall
fragment pasted into the flow pages.

```bash
docker compose up -d                       # stack must be running
pip install playwright && playwright install chromium

# Flow A — real login + explicit consent + delegated token
python demo/capture/flow_a.py              # -> flowA-01-login / -02-consent / -03-granted .png

# Flow B — the provider refresh credential sealed in OpenBao
python demo/capture/capture_openbao.py     # -> flowB-openbao.png

# Flow C — 428 -> trusted approval UI -> real Approve click -> Mailpit
python demo/capture/capture_approval.py    # -> flowC-approval / -approved / -mailpit .png

# Flow D — alice-vs-bob FGA-filtered retrieval (data, not a screenshot)
python demo/capture/capture_rag.py         # -> flow_d.result.json

# Any cross-service trace, curated to its meaningful spans, as a native waterfall
python demo/capture/capture_trace.py <trace_id>          # by id
python demo/capture/capture_trace.py --find get_provider_token   # auto-pick richest match
python demo/capture/capture_console.py                   # console overview + a span waterfall (png)
```

Notes:
- `flow_a.py` configures an explicit consent screen for **its own** DCR client only
  (a per-client `default-client-scope` + `consentRequired`), so scripted logins used
  by the other captures and the smoke tests are unaffected.
- `capture_trace.py` reads Tempo through the console proxy (`/api/tempo/...`) and keeps
  only the cross-service spans (dropping DB/cache noise). Per-service colors live in
  `docs/walkthroughs/walkthrough.css` (`.svc-*` / `.bar-*`).
- The walkthrough pages are static HTML; the trace waterfalls are inlined fragments,
  so re-running a capture and pasting the new fragment is how you refresh them.
