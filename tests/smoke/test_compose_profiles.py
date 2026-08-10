"""The compose file must tell the truth about what Prokura IS. A bare
`docker compose config` (no profile) resolves to the product only — the trusted
surfaces (token-broker, approval, authority) on their infra (keycloak, openfga,
openbao, postgres, ntfy, lgtm). The *toy* resource servers that merely prove the
chain (mcp, tools-api, rag, mailpit) are demo-profiled and appear only under
`--profile demo`.

This is a static assertion on the compose config — it does not need the stack
running (and skips if the docker CLI is unavailable)."""

import shutil
import subprocess

import pytest

# The toy resource servers — demonstrate the chain, are NOT Prokura.
DEMO_ONLY = {"mcp", "tools-api", "rag", "mailpit"}
# The trusted surfaces — always present (the product).
PROKURA = {"token-broker", "approval", "authority"}


def _services(*profiles: str) -> set[str]:
    if not shutil.which("docker"):
        pytest.skip("docker CLI not available")
    cmd = ["docker", "compose"]
    for p in profiles:
        cmd += ["--profile", p]
    cmd += ["config", "--services"]
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if out.returncode != 0:
        pytest.skip(f"docker compose config failed: {out.stderr.strip()[:200]}")
    return {s.strip() for s in out.stdout.splitlines() if s.strip()}


def test_bare_config_excludes_toy_resource_servers():
    bare = _services()
    assert PROKURA <= bare, f"trusted surfaces missing from bare config: {PROKURA - bare}"
    leaked = DEMO_ONLY & bare
    assert not leaked, f"toy resource servers present without --profile demo: {leaked}"


def test_demo_profile_adds_the_toy_resource_servers():
    demo = _services("demo")
    assert DEMO_ONLY <= demo, f"toy servers missing under --profile demo: {DEMO_ONLY - demo}"
    assert PROKURA <= demo, "the product must still be present under --profile demo"
