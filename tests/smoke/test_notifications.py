"""Smoke 3.5: Mailpit receives SMTP; ntfy denies anonymous access (F7)."""

import smtplib
import time
import uuid
from email.message import EmailMessage

import httpx

from conftest import MAILPIT_SMTP


def test_mailpit_receives_smtp(mailpit: str) -> None:
    marker = f"prokura-smoke-{uuid.uuid4().hex[:8]}"
    msg = EmailMessage()
    msg["From"] = "agent@prokura.local"
    msg["To"] = "alice@prokura.local"
    msg["Subject"] = marker
    msg.set_content("Prokura smoke test — gated email lands here, not in Gmail.")

    with smtplib.SMTP(*MAILPIT_SMTP, timeout=10) as smtp:
        smtp.send_message(msg)

    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        r = httpx.get(f"{mailpit}/api/v1/search", params={"query": f"subject:{marker}"}, timeout=10.0)
        if r.status_code == 200 and r.json().get("messages_count", 0) >= 1:
            return
        time.sleep(1)
    raise AssertionError(f"message {marker!r} never appeared in Mailpit")


def test_ntfy_rejects_anonymous_publish(ntfy: str) -> None:
    r = httpx.post(f"{ntfy}/prokura-smoke-topic", content="spoofed approval", timeout=10.0)
    assert r.status_code == 403, f"anonymous publish must be denied, got {r.status_code}"


def test_ntfy_rejects_anonymous_subscribe(ntfy: str) -> None:
    r = httpx.get(f"{ntfy}/prokura-smoke-topic/json", params={"poll": "1"}, timeout=10.0)
    assert r.status_code == 403, f"anonymous subscribe must be denied, got {r.status_code}"
