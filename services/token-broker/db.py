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
