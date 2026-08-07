#!/usr/bin/env python3
"""Capture the delegation-chain console (:8095): the trace stream and a span
waterfall for one action. Probes the DOM first so the row-click is reliable."""
import os
import sys

from playwright.sync_api import sync_playwright

CONSOLE = "http://localhost:8095"
IMG = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..",
                                    "docs", "walkthroughs", "img"))


def main(prefix="flowA", row_match=None):
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        p = b.new_page(viewport={"width": 1500, "height": 900}, device_scale_factor=2)
        p.goto(CONSOLE, wait_until="networkidle")
        p.wait_for_timeout(1500)

        # Probe: list the trace-stream rows so we can pick one deterministically.
        rows = p.eval_on_selector_all(
            "[class*=row], [class*=trace] *, tr, li",
            "els => els.filter(e => /POST|GET|\\/mcp|realm|approval|tokens/.test(e.innerText||'')"
            " && (e.innerText||'').length < 80)"
            ".slice(0,12).map((e,i) => ({i, text:(e.innerText||'').replace(/\\s+/g,' ').trim().slice(0,60)}))")
        print("ROWS:")
        for r in rows:
            print(" ", r)

        p.screenshot(path=os.path.join(IMG, f"{prefix}-trace-overview.png"))
        print("saved overview")

        # Click a representative row to render the span waterfall on the right.
        try:
            target = row_match or "login-actions/authenticate"
            p.get_by_text(target).first.click(timeout=5000)
            p.wait_for_timeout(1200)
            p.screenshot(path=os.path.join(IMG, f"{prefix}-trace.png"))
            print("saved waterfall (clicked:", target, ")")
        except Exception as e:
            print("waterfall click failed:", str(e)[:120])
        b.close()


if __name__ == "__main__":
    main(*sys.argv[1:])
