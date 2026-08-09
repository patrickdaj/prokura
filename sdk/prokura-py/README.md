# prokura (Python SDK, v0)

The agent-side helpers for **delegated identity** against a Prokura deployment: exchange a
user token for a downstream-audience one, and fetch a consent-gated third-party token. Thin
wrappers over the same HTTP contracts the services expose — one dependency (`httpx`).

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

All functions accept an optional `http: httpx.Client` so callers can reuse a connection /
inject timeouts.

## Where did the approval helpers go? (M7)

`require_approval()` and `drive_ciba_approval()` are **gone, on purpose** (ADR-0022).
The CIBA ceremony is initiated and completed by the approval service — no agent client
holds the CIBA grant anymore, so there is nothing for agent code to drive. The whole
agent-side contract for a sensitive action is now:

1. Call the tool. If it needs approval you get `428 approval_required` with
   `{ref, action_token}` — and the human has already been notified.
2. Wait. The human approves or denies in their own authenticated session.
3. Retry the same call with `action_token`. It executes exactly once, only if the
   human approved exactly this action.

An SDK helper for that would be a retry loop; write the retry loop.

## Example

```python
from prokura import get_provider_token, ConsentDenied

# consent-gated provider token (the refresh credential stays in OpenBao)
tok = get_provider_token(broker_token, "acme", ["read:acme"], base_url="http://localhost:8110")
print(tok["expires_in"])   # ≤ 900
```

The errors mirror the security model: `ConsentDenied` / `ScopeExceeded` when the broker refuses
a hand-out. See the [walkthroughs](../../docs/walkthroughs/) for these calls exercised end-to-end.
