"""M7 separation invariant (D6): agent-side kits contain NO human capacity.

Grep-able assertions over the kit sources: no user credential, no CIBA
initiation, no approval decision, no consent write. If one of these reappears
in an agent-side kit, a script is playing the human again — the exact failure
M7 exists to prevent. The one sanctioned simulated human is humankit (Playwright
against the real login + surfaces), and the SDK ships no ceremony driver."""

import os
import re

HERE = os.path.dirname(__file__)
AGENT_KITS = ["approvalkit.py", "brokerkit.py", "mcpkit.py", "ragkit.py"]

FORBIDDEN = {
    "user password": re.compile(r"DEMO_PASSWORD|password\s*=\s*[\"']alice|[\"']alice[\"']\s*,\s*[\"']alice[\"']"),
    "CIBA initiation": re.compile(r"ext/ciba/auth(?!/callback)|ciba_init|grant-type:ciba"),
    "approval decision": re.compile(r"/decide|decision[\"']?\s*[:=]\s*[\"'](approve|deny)"),
    "consent write": re.compile(r"post\([^)]*/consent|/v1/consent/revoke"),
}


def _kit_sources() -> dict[str, str]:
    return {k: open(os.path.join(HERE, k)).read() for k in AGENT_KITS}


def test_agent_kits_hold_no_human_capacity():
    for kit, src in _kit_sources().items():
        for what, pat in FORBIDDEN.items():
            m = pat.search(src)
            assert not m, f"{kit} contains a {what}: {m.group(0)!r}"


def test_sdk_ships_no_ceremony_driver():
    sdk_dir = os.path.join(HERE, "..", "..", "sdk", "prokura-py", "prokura")
    files = [f for f in os.listdir(sdk_dir) if f.endswith(".py")]
    assert "approval.py" not in files, "the SDK approval/CIBA driver came back"
    for f in files:
        src = open(os.path.join(sdk_dir, f)).read()
        assert "ext/ciba/auth" not in src, f"sdk/{f} initiates CIBA"
        assert "grant-type:ciba" not in src, f"sdk/{f} polls the CIBA grant"


def test_passwords_only_in_humankit():
    # The only test module allowed to hold user passwords is the labeled
    # simulated human. Kits are checked above; this asserts the quarantine
    # location actually exists and is labeled.
    src = open(os.path.join(HERE, "humankit.py")).read()
    assert "SIMULATED HUMAN" in src
    assert "_PASSWORDS" in src
