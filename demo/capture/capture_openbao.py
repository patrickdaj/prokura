#!/usr/bin/env python3
"""Capture the OpenBao side-effect: the provider refresh credential stored at
secret/grants/alice/acme — the secret that never leaves the vault."""
import os

from playwright.sync_api import sync_playwright

BAO = "http://localhost:8200"
ROOT = "prokura-dev-root"
SECRET_URL = f"{BAO}/ui/vault/secrets/secret/kv/grants%2Falice%2Facme/details?version=2"
IMG = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..",
                                   "docs", "walkthroughs", "img"))


def main():
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        p = b.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=2)

        # sign in with the root token
        p.goto(f"{BAO}/ui/vault/auth?with=token", wait_until="networkidle")
        p.fill("input[name=token]", ROOT)
        p.click("#auth-submit")
        p.wait_for_url(lambda u: "/auth" not in u, timeout=15000)   # login landed
        p.wait_for_timeout(1500)
        print("post-login URL:", p.url)

        # navigate IN-APP (full-page goto would drop the SPA token) — open the
        # KV engine, then drill grants/ → alice/ → acme.
        p.click("a[href='/ui/vault/secrets/secret/list']")
        p.wait_for_timeout(1000)
        for part in ("grants", "alice", "acme"):
            p.get_by_role("link", name=part, exact=False).first.click()
            p.wait_for_timeout(1100)
        p.wait_for_timeout(1200)
        p.screenshot(path=os.path.join(IMG, "flowB-openbao.png"))
        print("secret URL:", p.url)
        print("saved", os.path.join(IMG, "flowB-openbao.png"))
        b.close()


if __name__ == "__main__":
    main()
