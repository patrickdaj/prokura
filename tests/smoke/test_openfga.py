"""Smoke 3.3: the corrected FGA model (F1-A) is loaded and answers checks.

The model failing to load was SPEC-REVIEW finding F1's blocker scenario —
this test is the regression guard.
"""

import uuid

import httpx


def test_model_loaded(openfga: str, fga_store_id: str) -> None:
    r = httpx.get(f"{openfga}/stores/{fga_store_id}/authorization-models", timeout=10.0)
    r.raise_for_status()
    models = r.json()["authorization_models"]
    assert models, "no authorization model in store — model.json failed to load"
    types = {t["type"] for t in models[0]["type_definitions"]}
    assert types == {"user", "agent", "grant", "document", "tool"}


def test_can_use_check(openfga: str, fga_store_id: str) -> None:
    grant = f"grant:alice/github-{uuid.uuid4().hex[:8]}"

    write = httpx.post(
        f"{openfga}/stores/{fga_store_id}/write",
        json={
            "writes": {
                "tuple_keys": [
                    {"user": "agent:smoke-agent", "relation": "can_use", "object": grant},
                    {"user": "user:alice", "relation": "owner", "object": grant},
                ]
            }
        },
        timeout=10.0,
    )
    assert write.status_code == 200, write.text

    def check(user: str) -> bool:
        r = httpx.post(
            f"{openfga}/stores/{fga_store_id}/check",
            json={"tuple_key": {"user": user, "relation": "can_use", "object": grant}},
            timeout=10.0,
        )
        r.raise_for_status()
        return r.json()["allowed"]

    assert check("agent:smoke-agent") is True
    # per-agent-consent spec: no tuple, no access
    assert check("agent:other-agent") is False
