"""Notify-only push via ntfy. A notification carries ONLY a deep link and the
reference ID — never action params. The topic is per-user and unguessable
(derived from a server-side salt), so it is not enumerable and a fabricated
publish to it changes no approval state (decisions happen only in the UI)."""

import hashlib

import httpx

import config


def topic_for(user_id: str) -> str:
    digest = hashlib.sha256(f"{config.NTFY_TOPIC_SALT}:{user_id}".encode()).hexdigest()
    return f"prokura-approvals-{digest[:20]}"


def notify(user_id: str, ref: str) -> None:
    """Publish a capability-free notification: a deep link + reference ID only."""
    topic = topic_for(user_id)
    deep_link = f"{config.APPROVAL_PUBLIC_URL}/approvals#{ref}"
    try:
        httpx.post(
            f"{config.NTFY_URL}/{topic}",
            content=f"Approval requested. Review: {deep_link}",
            headers={"Title": "Prokura approval", "X-Tags": "lock",
                     "Click": deep_link, "X-Ref": ref},
            auth=(config.NTFY_USER, config.NTFY_PASSWORD),
            timeout=5.0,
        )
    except httpx.HTTPError:
        pass  # notify is best-effort; the UI is the source of truth
