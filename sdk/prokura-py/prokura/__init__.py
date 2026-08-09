"""Prokura agent SDK (Python v0).

M1 surface: `exchange()`. M2 adds `get_provider_token()`. M5 adds the RAG path
(served via MCP). M7 REMOVES the approval module: the CIBA ceremony is
initiated and completed by the approval service (ADR-0022) — no agent client
holds the CIBA grant, so there is nothing for an agent to drive. An agent that
receives a 428 `approval_required` challenge waits for the human's out-of-band
decision and retries with the returned `action_token`.
"""

from .exchange import ExchangeDenied, ExchangeError, exchange
from .provider_token import (
    ConsentDenied,
    ProviderTokenError,
    ScopeExceeded,
    get_provider_token,
)

__all__ = [
    "exchange",
    "ExchangeError",
    "ExchangeDenied",
    "get_provider_token",
    "ProviderTokenError",
    "ConsentDenied",
    "ScopeExceeded",
]
