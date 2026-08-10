"""Capture REAL Grafana/Tempo trace-waterfall screenshots for the walkthroughs.

Replaces the old hand-drawn `.wf` recreations (and the decommissioned
`capture_console.py`): the observability surface is Grafana now, so the docs show
the real thing. Given a trace id, it deep-links Grafana Explore → Tempo, collapses
the query editor + Keycloak's internal subtrees (so the cross-service story reads
cleanly), and clips the Trace panel to a PNG under docs/walkthroughs/img/.

Prereqs:
    docker compose --profile demo up -d
    pip install playwright && playwright install chromium

Usage:
    # find a flow-tagged, full-chain (mcp-rooted) trace id, then:
    python demo/capture/capture_grafana.py <trace_id> <out_name>
    # e.g. python demo/capture/capture_grafana.py 46dc6485...d426 trace-flowD

Find trace ids by flow (health-check noise carries no tag):
    curl -s 'http://localhost:3001/api/datasources/proxy/uid/tempo/api/search' \
      --data-urlencode 'q={ span.prokura.flow = "D" }' -G | python3 -m json.tool
"""

import json
import os
import sys
import urllib.parse

from playwright.sync_api import sync_playwright

GRAFANA = os.environ.get("PROKURA_GRAFANA_URL", "http://localhost:3001")
IMG = os.path.join(os.path.dirname(__file__), "..", "..", "docs", "walkthroughs", "img")
TRACE_PANEL = '[data-testid="data-testid Panel header Trace"]'


def explore_url(trace_id: str) -> str:
    panes = {"t": {"datasource": "tempo",
                   "queries": [{"refId": "A", "datasource": {"type": "tempo", "uid": "tempo"},
                                "query": trace_id, "queryType": "traceql"}],
                   "range": {"from": "now-3h", "to": "now"}}}
    q = urllib.parse.urlencode({"schemaVersion": 1, "panes": json.dumps(panes), "orgId": 1})
    return f"{GRAFANA}/explore?{q}"


def loki_url(trace_id: str) -> str:
    """Explore → Loki filtered to one trace's audit lines — the trace→logs jump the
    Tempo→Loki derived field performs, joined by the native trace id."""
    expr = f'{{service_name=~"mcp|rag|token-broker|approval|authority"}} | trace_id = "{trace_id}"'
    panes = {"t": {"datasource": "loki",
                   "queries": [{"refId": "A", "datasource": {"type": "loki", "uid": "loki"},
                                "expr": expr, "queryType": "range"}],
                   "range": {"from": "now-3h", "to": "now"}}}
    q = urllib.parse.urlencode({"schemaVersion": 1, "panes": json.dumps(panes), "orgId": 1})
    return f"{GRAFANA}/explore?{q}"


def _collapse_noise(page) -> None:
    """Collapse the query editor and Keycloak's internal subtrees so the waterfall
    shows the cross-service chain (mcp → exchange → rag → pgvector → fga → openfga)."""
    # Query editor row: the "Collapse query row" toggle — reclaim vertical space.
    try:
        page.get_by_label("Collapse query row").first.click(timeout=2000)
    except Exception:
        pass
    # NOTE: we no longer collapse the keycloak/exchange subtrees. The collector's
    # filter/noise processor already drops Keycloak's internal spans, leaving just the
    # single `POST /realms/.../token` span — the `→ Keycloak` edge we WANT in frame.


def capture_trace(trace_id: str, out_name: str) -> str:
    out = os.path.abspath(os.path.join(IMG, f"{out_name}.png"))
    with sync_playwright() as p:
        browser = p.chromium.launch()
        # Tall viewport so the whole (now noise-filtered, ~15-span) waterfall renders —
        # the collector's filter/noise processor keeps traces short enough to show in full.
        page = browser.new_page(viewport={"width": 1440, "height": 1900}, device_scale_factor=2)
        page.goto(explore_url(trace_id), wait_until="networkidle")
        page.wait_for_selector(TRACE_PANEL, timeout=15000)
        page.wait_for_timeout(1500)
        _collapse_noise(page)
        page.wait_for_timeout(800)
        box = page.query_selector(TRACE_PANEL).bounding_box()
        # Clip the full domain tree: filtered traces are ~15 spans, so the whole flow
        # (down to openbao.rotate_grant / fga.batch_check) fits — no payload below the fold.
        clip = {"x": box["x"], "y": box["y"], "width": box["width"],
                "height": min(box["height"], 1800)}
        page.screenshot(path=out, clip=clip)
        browser.close()
    print(f"wrote {out}")
    return out


def capture_logs(trace_id: str, out_name: str) -> str:
    """The trace→logs jump: one trace's audit lines in Loki, joined by native trace id."""
    out = os.path.abspath(os.path.join(IMG, f"{out_name}.png"))
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=2)
        page.goto(loki_url(trace_id), wait_until="networkidle")
        page.wait_for_timeout(3500)
        try:
            page.get_by_label("Collapse query row").first.click(timeout=2000)
        except Exception:
            pass
        page.wait_for_timeout(800)
        # Clip the logs results region (below the toolbar).
        page.screenshot(path=out, clip={"x": 250, "y": 150, "width": 1190, "height": 620})
        browser.close()
    print(f"wrote {out}")
    return out


def capture_dashboard(uid: str, out_name: str) -> str:
    """A provisioned dashboard, kiosk mode (no Grafana chrome)."""
    out = os.path.abspath(os.path.join(IMG, f"{out_name}.png"))
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=2)
        page.goto(f"{GRAFANA}/d/{uid}?from=now-1h&to=now&kiosk", wait_until="networkidle")
        page.wait_for_timeout(4000)
        page.screenshot(path=out, clip={"x": 0, "y": 0, "width": 1440, "height": 560})
        browser.close()
    print(f"wrote {out}")
    return out


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "trace" and len(sys.argv) == 4:
        capture_trace(sys.argv[2], sys.argv[3])
    elif mode == "logs" and len(sys.argv) == 4:
        capture_logs(sys.argv[2], sys.argv[3])
    elif mode == "dashboard" and len(sys.argv) == 4:
        capture_dashboard(sys.argv[2], sys.argv[3])
    elif len(sys.argv) == 3:            # back-compat: `<trace_id> <name>` == trace mode
        capture_trace(sys.argv[1], sys.argv[2])
    else:
        print(__doc__)
        print("\nmodes:\n  trace <id> <name>\n  logs <trace_id> <name>\n  dashboard <uid> <name>")
        sys.exit(2)
