"""Broker Postgres tables (grant records + audit log). Refresh credentials are
NEVER stored here — only in OpenBao. Tables are created idempotently at startup
(no migration framework for v0; the stack is clean-slate ``down -v && up``)."""

import psycopg

import config

_DDL = """
CREATE TABLE IF NOT EXISTS broker_grants (
    user_id        text        NOT NULL,
    provider       text        NOT NULL,
    granted_scopes text        NOT NULL DEFAULT '',
    created_at     timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, provider)
);

CREATE TABLE IF NOT EXISTS broker_audit (
    id             bigserial   PRIMARY KEY,
    correlation_id text        NOT NULL,
    user_id        text,
    agent          text,
    provider       text,
    scopes         text,
    ttl            integer,
    decision       text        NOT NULL,
    detail         text,
    ts             timestamptz NOT NULL DEFAULT now()
);

-- M9 kill switch: a propagation-free "stop now" checked on every hand-out. A row
-- with provider IS NULL denies all of the agent's grants for that user (an
-- agent-wide kill), independent of OpenFGA read state.
CREATE TABLE IF NOT EXISTS broker_denylist (
    agent      text        NOT NULL,
    user_id    text        NOT NULL,
    provider   text,
    reason     text,
    azp        text,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS broker_denylist_key
    ON broker_denylist (agent, user_id, COALESCE(provider, ''));
"""


def connect() -> psycopg.Connection:
    return psycopg.connect(config.DATABASE_URL, autocommit=True)


def init_db() -> None:
    with connect() as conn:
        conn.execute(_DDL)


def record_grant(user_id: str, provider: str, scopes: str) -> None:
    with connect() as conn:
        conn.execute(
            """INSERT INTO broker_grants (user_id, provider, granted_scopes)
               VALUES (%s, %s, %s)
               ON CONFLICT (user_id, provider)
               DO UPDATE SET granted_scopes = EXCLUDED.granted_scopes,
                             created_at = now()""",
            (user_id, provider, scopes),
        )


def list_grants(user_id: str) -> list[dict]:
    """All of a user's grants (provider + granted scopes) — M8 console read."""
    with connect() as conn:
        rows = conn.execute(
            "SELECT provider, granted_scopes FROM broker_grants WHERE user_id=%s "
            "ORDER BY provider", (user_id,),
        ).fetchall()
    return [{"provider": r[0], "granted_scopes": r[1]} for r in rows]


def get_grant(user_id: str, provider: str) -> dict | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT granted_scopes FROM broker_grants WHERE user_id=%s AND provider=%s",
            (user_id, provider),
        ).fetchone()
    if not row:
        return None
    return {"granted_scopes": row[0]}


def delete_grant(user_id: str, provider: str) -> None:
    with connect() as conn:
        conn.execute(
            "DELETE FROM broker_grants WHERE user_id=%s AND provider=%s",
            (user_id, provider),
        )


def add_deny(agent: str, user_id: str, provider: str | None, reason: str, azp: str) -> None:
    """Write a deny-list entry (M9). provider=None is an agent-wide kill for the user."""
    with connect() as conn:
        conn.execute(
            """INSERT INTO broker_denylist (agent, user_id, provider, reason, azp)
               VALUES (%s, %s, %s, %s, %s)
               ON CONFLICT (agent, user_id, COALESCE(provider, ''))
               DO UPDATE SET reason = EXCLUDED.reason, azp = EXCLUDED.azp,
                             created_at = now()""",
            (agent, user_id, provider, reason, azp),
        )


def remove_deny(agent: str, user_id: str, provider: str | None) -> None:
    """Clear a deny entry (e.g. on re-consent). Matches the exact grain written."""
    with connect() as conn:
        conn.execute(
            "DELETE FROM broker_denylist WHERE agent=%s AND user_id=%s "
            "AND COALESCE(provider,'')=COALESCE(%s,'')",
            (agent, user_id, provider),
        )


def is_denied(agent: str, user_id: str, provider: str) -> bool:
    """True if a deny entry matches this exact grant OR an agent-wide (null-provider)
    entry for the user — the hand-out chain's propagation-free stop."""
    with connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM broker_denylist WHERE agent=%s AND user_id=%s "
            "AND (provider=%s OR provider IS NULL) LIMIT 1",
            (agent, user_id, provider),
        ).fetchone()
    return row is not None


def insert_audit(
    *,
    correlation_id: str,
    user_id: str | None,
    agent: str | None,
    provider: str | None,
    scopes: str | None,
    ttl: int | None,
    decision: str,
    detail: str | None = None,
) -> None:
    with connect() as conn:
        conn.execute(
            """INSERT INTO broker_audit
               (correlation_id, user_id, agent, provider, scopes, ttl, decision, detail)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
            (correlation_id, user_id, agent, provider, scopes, ttl, decision, detail),
        )
