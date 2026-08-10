"""Prokura RAG retriever (M5) — Flow D: authorization-filtered retrieval.

A FastAPI resource server (aud=rag-server, the F2 defense) that owns a pgvector
store and authorizes candidate chunks AS THE END USER against OpenFGA — never as
the agent principal. This is the confused-deputy defense SPEC.md §11 exists to make
concrete: an agent retrieves only the documents the querying user is entitled to see.

Endpoints:
  GET  /healthz
  POST /rag/search    embed query -> pgvector top-K -> OpenFGA batch_check as
                      user:{preferred_username} -> only authorized chunks (+ answer)

Ingestion (Drive-shaped manifest -> tuples then embeddings) runs at startup.
Born instrumented: traceparent join key + native trace context, realtime rag_audit.
"""

import audit
import config
import db
import fga
import ingest
import validation
from embedder import embed
from fastapi import FastAPI, Header, Request
from fastapi.responses import JSONResponse
from prokura_telemetry import setup, stamp_flow, tracer

app = FastAPI(title="prokura-rag")
setup(app, config.SERVICE_NAME)


@app.on_event("startup")
def _startup() -> None:
    db.init_db()
    ingest.ingest_if_needed()


class _Http(Exception):
    def __init__(self, status: int, detail: str):
        self.status = status
        self.detail = detail


@app.exception_handler(_Http)
async def _http_handler(_: Request, exc: _Http) -> JSONResponse:
    return JSONResponse({"error": exc.detail, "chunks": []}, status_code=exc.status)


def _bearer(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise _Http(401, "missing_token")
    return authorization.split(" ", 1)[1]


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True}


@app.post("/rag/search")
async def search(request: Request,
                 authorization: str | None = Header(default=None)) -> JSONResponse:
    token = _bearer(authorization)

    # F2 defense: only a token of THIS resource's audience is accepted. A foreign
    # audience (e.g. an mcp-server token forwarded verbatim) is refused — no chunks.
    try:
        claims = validation.verify_bearer(token)
    except validation.TokenInvalid as e:
        # SR-01: stable machine codes out; library detail to audit only.
        audit.emit(decision="denied_invalid_token", detail=str(e))
        raise _Http(401, "invalid_token")
    except validation.WrongAudience as e:
        audit.emit(decision="denied_audience", detail=str(e))
        raise _Http(403, "wrong_audience")

    # The end-user identity is derived from the validated token, never from the
    # caller. No end user (agent-only credentials) -> refuse: agent identity is
    # insufficient for a user-context retrieval (Flow D).
    user = validation.end_user(claims)
    agent = claims.get("azp")
    # Flow D (FGA-filtered RAG): tag the root span so `{ prokura.flow = "D" }` finds
    # this retrieval end-to-end.
    stamp_flow("D", user=user, agent=agent)
    if not user:
        audit.emit(decision="denied_no_user", agent=agent)
        raise _Http(403, "no_end_user")

    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    query = (body.get("query") or "").strip()
    if not query:
        raise _Http(400, "query is required")
    k = int(body.get("top_k") or config.TOP_K)

    with tracer().start_as_current_span("rag.search") as span:
        span.set_attribute("prokura.rag.user", user)
        # 1. Retrieve candidates by vector similarity (pre-authorization).
        candidates = db.top_k(embed(query), k)
        candidate_docs = list(dict.fromkeys(c["doc_id"] for c in candidates))
        # 2. Authorize the candidate set AS THE END USER — the whole point.
        allowed_map = fga.batch_check_viewer(user, candidate_docs)
        # 3. Keep only chunks from documents the user may view.
        authorized = [c for c in candidates if allowed_map.get(c["doc_id"])]
        span.set_attribute("prokura.rag.candidates", len(candidate_docs))
        span.set_attribute("prokura.rag.allowed",
                           sum(1 for v in allowed_map.values() if v))

    audit.emit(decision="retrieved", user=user, agent=agent,
               candidates=len(candidate_docs),
               allowed=sum(1 for v in allowed_map.values() if v))

    return JSONResponse({
        "user": user,
        "query": query,
        "candidates": len(candidate_docs),
        "allowed": sum(1 for v in allowed_map.values() if v),
        "chunks": [{"doc_id": c["doc_id"], "text": c["chunk"],
                    "similarity": round(c["similarity"], 4)} for c in authorized],
        "answer": _answer(query, authorized),
    })


def _answer(query: str, chunks: list[dict]) -> str:
    """A demo 'answer': the authorized chunk text stitched together. The leakage
    assertion is on content presence, so the answer is only ever built from chunks
    that survived the FGA filter — an unauthorized doc can never reach it."""
    if not chunks:
        return "No documents you are authorized to view match this query."
    return " ".join(c["chunk"] for c in chunks)
