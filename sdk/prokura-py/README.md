# prokura (Python SDK, v0)

The agent-side helpers for **delegated identity** against a Prokura deployment: exchange a
user token for a downstream-audience one, fetch a consent-gated third-party token, and drive
human approval for a sensitive action. Thin wrappers over the same HTTP contracts the
services expose — one dependency (`httpx`).

> v0 is Python (ADR-0014); a TypeScript SDK is on the roadmap. `fga_filter()` (the RAG
> authorize-as-user helper, M5) is not in the SDK yet — the RAG service enforces it server-side.

```bash
pip install -e sdk/prokura-py     # or: pip install prokura   (once published)
```

## Public API (`from prokura import ...`)

| Function | Does | Raises |
|----------|------|--------|
| `exchange(subject_token, audience, scopes=(), *, base_url, realm, client_id, client_secret)` → `str` | RFC 8693 token exchange → a token addressed to `audience`, carrying the user's `sub` and the client's `azp` (M1) | `ExchangeError`, `ExchangeDenied` |
| `get_provider_token(broker_token, provider, scopes=(), *, base_url)` → `dict` | Consent-gated third-party access token from the broker — `{access_token, expires_in, scope}`, **never** a refresh token (M2) | `ProviderTokenError`, `ConsentDenied`, `ScopeExceeded` |
| `require_approval(subject_token, action, params, *, base_url, realm, client_id, client_secret, approval_url, login_hint=None, …)` → action token | Register a sensitive action, drive CIBA, and return the single-use action token once a human approves (M3) | `ApprovalError`, `ApprovalDenied`, `ApprovalTimeout` |
| `drive_ciba_approval(ref, *, base_url, realm, client_id, client_secret, login_hint, …)` → token | Lower-level: drive CIBA for a `ref` the **resource server** already registered (reactive step-up, M4) | `ApprovalError`, `ApprovalDenied`, `ApprovalTimeout` |

All functions accept an optional `http: httpx.Client` so callers can reuse a connection /
inject timeouts.

## Example

```python
from prokura import get_provider_token, require_approval, ConsentDenied

# consent-gated provider token (the refresh credential stays in OpenBao)
tok = get_provider_token(broker_token, "acme", ["read:acme"], base_url="http://localhost:8110")
print(tok["expires_in"])   # ≤ 900

# human-in-the-loop for a sensitive action
action_token = require_approval(
    user_token, "email.send", {"to": "board@prokura.local", "subject": "Q3"},
    base_url="http://localhost:8130", realm="prokura",
    client_id="agent-app", client_secret="…", approval_url="http://localhost:8120",
    login_hint="alice",
)
```

The errors mirror the security model: `ConsentDenied` / `ScopeExceeded` when the broker refuses
a hand-out, `ApprovalDenied` when a human says no, `ApprovalTimeout` when nobody decides in time.
See the [walkthroughs](../../docs/walkthroughs/) for these calls exercised end-to-end.
