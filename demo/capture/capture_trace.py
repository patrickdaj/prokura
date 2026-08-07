#!/usr/bin/env python3
"""Render a real cross-service trace as a native `.wf` waterfall fragment.

Pulls a trace from the Tempo API (via the console's datasource proxy), curates
the ~10 meaningful cross-service spans out of the ~145 (dropping DB/cache noise),
and emits an HTML fragment that drops straight into a walkthrough page.

  .venv/bin/python demo/capture/capture_trace.py <trace_id> > frag.html
  .venv/bin/python demo/capture/capture_trace.py --find get_provider_token
"""
import html
import sys

import httpx

CONSOLE = "http://localhost:8095"

# service.name -> css class + short label
SVC = {"mcp": ("mcp", "mcp"), "keycloak": ("kc", "keycloak"),
       "token-broker": ("broker", "broker"), "openfga": ("fga", "openfga"),
       "rag": ("rag", "rag"), "tools-api": ("tools", "tools-api"),
       "approval": ("appr", "approval")}

# ordered curation: (matcher over the span, display label, forced svc or None).
# A span is kept if any matcher returns True; first match wins its label.
CURATE = [
    (lambda s: s["name"] == "POST /mcp" and s["svc"] == "mcp", "POST /mcp", None),
    (lambda s: s["name"].startswith("tool."), None, None),
    (lambda s: s["name"] == "keycloak.mcp_exchange", "keycloak.mcp_exchange", None),
    (lambda s: s["name"].startswith("POST /realms") and s["name"].endswith("token"),
     "token endpoint", None),
    (lambda s: s["name"] == "POST /v1/tokens/{provider}", "POST /v1/tokens", None),
    (lambda s: s["name"] == "fga.check", "fga.check", None),
    (lambda s: s["name"] == "openfga.v1.OpenFGAService/Check", "Check (authz)", None),
    (lambda s: s["name"].startswith("openbao."), None, "bao"),
    (lambda s: s["name"] == "provider.refresh", "provider.refresh", None),
    # Flow D — FGA-filtered RAG
    (lambda s: s["name"] == "POST /rag/search", "POST /rag/search", None),
    (lambda s: s["name"] == "pgvector.top_k", "pgvector.top_k (embedding search)", None),
    (lambda s: s["name"] in ("fga.batch_check", "fga.filter"), "fga.batch_check (filter as user)", None),
    (lambda s: s["name"] == "openfga.v1.OpenFGAService/BatchCheck", "BatchCheck (authz)", None),
    # Flow C — human approval / send_email
    (lambda s: s["name"] == "POST /tools/email/send", "POST /tools/email/send", None),
    (lambda s: s["name"] == "approval.consume", "approval.consume", None),
    (lambda s: s["name"] == "POST /consume", "POST /consume (verify + single-use)", None),
    (lambda s: s["name"] == "email.send", "email.send", None),
]


def load_spans(trace_id):
    d = httpx.get(f"{CONSOLE}/api/tempo/trace/{trace_id}", timeout=15).json()
    spans = []
    for b in d.get("batches", []):
        svc = next((a["value"].get("stringValue") for a in b.get("resource", {}).get("attributes", [])
                    if a["key"] == "service.name"), "?")
        for ss in b.get("scopeSpans", []):
            for s in ss.get("spans", []):
                spans.append({"svc": svc, "name": s.get("name", ""),
                              "start": int(s.get("startTimeUnixNano", 0)),
                              "end": int(s.get("endTimeUnixNano", 0))})
    return spans


def find_trace(needle):
    q = f'{{ name = "tool.{needle}" }}' if needle.startswith(("get_", "send_", "rag_")) \
        else f'{{ name =~ ".*{needle}.*" }}'
    r = httpx.get(f"{CONSOLE}/api/tempo/search", params={"q": q, "minutes": 180, "limit": 20},
                  timeout=15).json()
    # richest trace wins (most spans = the full fan-out)
    best = None
    for t in r.get("traces", []):
        tid = t.get("traceID")
        n = len(load_spans(tid))
        if not best or n > best[1]:
            best = (tid, n)
    return best[0] if best else None


SHORT_FOR_CLS = {"bao": "openbao", "fga": "openfga", "broker": "broker",
                 "kc": "keycloak", "mcp": "mcp", "rag": "rag"}
# names allowed to appear more than once (the two keycloak token calls: the
# inbound exchange and the outbound provider re-issuance are both worth showing)
REPEATABLE = {"POST /realms/{realm}/protocol/{protocol}/token"}


def curate(spans):
    kept, seen = [], set()
    for s in spans:
        for matcher, label, forced in CURATE:
            if matcher(s):
                key = s["name"] if s["name"] not in REPEATABLE else (s["name"], s["start"])
                if key in seen:
                    break
                seen.add(key)
                cls, short = SVC.get(s["svc"], ("mcp", s["svc"]))
                if forced:
                    cls, short = forced, SHORT_FOR_CLS.get(forced, forced)
                kept.append({**s, "label": label or s["name"], "cls": cls, "short": short})
                break
    kept.sort(key=lambda s: s["start"])
    return kept


def render(trace_id, spans):
    kept = curate(spans)
    t0 = min(s["start"] for s in kept)
    total = max(s["end"] for s in kept) - t0
    total_ms = total / 1e6
    used = sorted({(s["cls"], s["short"]) for s in kept}, key=lambda x: x[0])
    legend = "".join(f'<span><i class="bar-{c}"></i>{n}</span>' for c, n in used)
    rows = []
    for s in kept:
        left = (s["start"] - t0) / total * 100
        width = max((s["end"] - s["start"]) / total * 100, 0.6)
        dur = (s["end"] - s["start"]) / 1e6
        rows.append(
            f'<div class="sp"><div class="nm"><span class="svc svc-{s["cls"]}">{s["short"]}</span>'
            f'{html.escape(s["label"])}</div>'
            f'<div class="track"><div class="bar bar-{s["cls"]}" style="left:{left:.1f}%;width:{width:.1f}%"></div></div>'
            f'<div class="d">{dur:.1f}</div></div>')
    return (f'<div class="wf wide">\n<div class="legend">{legend}'
            f'<span style="margin-left:auto">trace {trace_id[:16]}… · {len(kept)} key spans · '
            f'{total_ms:.0f} ms end-to-end</span></div>\n' + "\n".join(rows) + "\n</div>")


def main(argv):
    if argv and argv[0] == "--find":
        tid = find_trace(argv[1])
        print(f"<!-- found trace {tid} for {argv[1]} -->", file=sys.stderr)
    else:
        tid = argv[0]
    spans = load_spans(tid)
    print(render(tid, spans))


if __name__ == "__main__":
    main(sys.argv[1:])
