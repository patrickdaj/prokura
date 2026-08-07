#!/usr/bin/env python3
"""Flow D capture — FGA-filtered RAG. Runs the SAME adversarial query as alice (a
viewer) and bob (not a viewer) and records the real retrieval: candidates, which
survive the per-user filter, and whether the answer leaks 'Meridian'."""
import json
import os
import sys

import httpx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "tests", "smoke"))
import ragkit  # noqa: E402

OUT = os.path.join(os.path.dirname(__file__), "flow_d.result.json")


def run(c, user):
    tok = ragkit.mcp_token(c, user, user)
    res, err = ragkit.search_via_mcp(c, tok, ragkit.ADVERSARIAL_QUERY)
    chunks = res.get("chunks", [])
    return {
        "user": user,
        "candidates": res.get("candidates"),
        "allowed": res.get("allowed"),
        "answer": res.get("answer", ""),
        "leaks_meridian": "Meridian" in res.get("answer", ""),
        "chunks": [{"doc_id": ch.get("doc_id"), "score": ch.get("score"),
                    "allowed": ch.get("allowed")} for ch in chunks],
        "raw_keys": sorted(res.keys()),
    }


def main():
    with httpx.Client(follow_redirects=False, timeout=40.0) as c:
        out = {"query": ragkit.ADVERSARIAL_QUERY,
               "alice": run(c, "alice"), "bob": run(c, "bob")}
    json.dump(out, open(OUT, "w"), indent=2)
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
