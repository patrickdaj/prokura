"""Approval state in Postgres. The action secret and the delegation bearer are
held here (server-side); the human-facing payload is rendered from `action`/
`params_json`. Single-use is enforced by an atomic conditional UPDATE on
`consumed_at`. Tables created idempotently at startup (clean-slate dev)."""

import json

import psycopg

import config

_DDL = """
CREATE TABLE IF NOT EXISTS approvals (
    ref              text        PRIMARY KEY,
    agent            text        NOT NULL,
    user_id          text        NOT NULL,
    action           text        NOT NULL,
    params_json      text        NOT NULL,
    hash             text        NOT NULL,
    scopes           text        NOT NULL DEFAULT '',
    status           text        NOT NULL DEFAULT 'pending',
    action_secret    text        NOT NULL,
    delegation_token text,
    auth_req_id      text,
    created_at       timestamptz NOT NULL DEFAULT now(),
    decided_at       timestamptz,
    consumed_at      timestamptz
);
ALTER TABLE approvals ADD COLUMN IF NOT EXISTS auth_req_id text;
"""


def connect() -> psycopg.Connection:
    return psycopg.connect(config.DATABASE_URL, autocommit=True)


def init_db() -> None:
    with connect() as conn:
        conn.execute(_DDL)


def create(ref, agent, user_id, action, params, hash_, scopes, secret) -> None:
    with connect() as conn:
        conn.execute(
            """INSERT INTO approvals
               (ref, agent, user_id, action, params_json, hash, scopes, status, action_secret)
               VALUES (%s,%s,%s,%s,%s,%s,%s,'pending',%s)""",
            (ref, agent, user_id, action, json.dumps(params), hash_, scopes, secret),
        )


def get(ref: str) -> dict | None:
    with connect() as conn:
        row = conn.execute(
            """SELECT ref, agent, user_id, action, params_json, hash, scopes, status,
                      action_secret, delegation_token, auth_req_id, consumed_at,
                      EXTRACT(EPOCH FROM now() - created_at) AS age_seconds
               FROM approvals WHERE ref=%s""", (ref,),
        ).fetchone()
    if not row:
        return None
    cols = ["ref", "agent", "user_id", "action", "params_json", "hash", "scopes",
            "status", "action_secret", "delegation_token", "auth_req_id", "consumed_at",
            "age_seconds"]
    d = dict(zip(cols, row))
    d["params"] = json.loads(d.pop("params_json"))
    return d


def list_for_user(user_id: str) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            """SELECT ref, agent, action, params_json, scopes, status, created_at
               FROM approvals WHERE user_id=%s ORDER BY created_at DESC LIMIT 50""",
            (user_id,),
        ).fetchall()
    out = []
    for r in rows:
        out.append({"ref": r[0], "agent": r[1], "action": r[2],
                    "params": json.loads(r[3]), "scopes": r[4], "status": r[5],
                    "created_at": r[6].isoformat()})
    return out


def set_auth_req_id(ref: str, auth_req_id: str) -> None:
    """The service-initiated ceremony's handle (M7): stored at registration,
    polled after the decision."""
    with connect() as conn:
        conn.execute("UPDATE approvals SET auth_req_id=%s WHERE ref=%s",
                     (auth_req_id, ref))


def set_delegation(ref: str, token: str) -> bool:
    with connect() as conn:
        cur = conn.execute(
            "UPDATE approvals SET delegation_token=%s, status='delegated' "
            "WHERE ref=%s AND status='pending'", (token, ref))
        return cur.rowcount == 1


def set_status(ref: str, status: str) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE approvals SET status=%s, decided_at=now() WHERE ref=%s",
            (status, ref))


def consume(ref: str) -> bool:
    """Atomically mark consumed; returns True only for the first caller."""
    with connect() as conn:
        cur = conn.execute(
            "UPDATE approvals SET consumed_at=now() "
            "WHERE ref=%s AND status='approved' AND consumed_at IS NULL", (ref,))
        return cur.rowcount == 1
