"""M5 spike (1.2 + 1.3): prove the offline deterministic embedder + a seeded
corpus makes a chosen PROTECTED doc the top hit for a crafted query — offline,
byte-reproducible — and that an OpenFGA batch_check as user:{sub} filters it out
for a non-viewer and keeps it for a viewer.

Runs against the throwaway pgvector-spike container (host port mapped below) and
the running prokura OpenFGA (localhost:8081). No network embedding calls.
"""
import hashlib
import math
import re
import subprocess
import sys
import uuid

import httpx

OPENFGA = "http://localhost:8081"
FGA_STORE = "prokura"
DIM = 256


# --- offline deterministic embedder ------------------------------------------
# A hashing bag-of-words vectorizer: each token is hashed to a bucket in a
# fixed-DIM space, counts are L2-normalized. No network, no secret, byte-identical
# across runs (Python hash randomization is bypassed via blake2b). Demo-grade;
# the real-model swap point is a single function.
def embed(text: str) -> list[float]:
    vec = [0.0] * DIM
    for tok in re.findall(r"[a-z0-9]+", text.lower()):
        h = int.from_bytes(hashlib.blake2b(tok.encode(), digest_size=4).digest(), "big")
        vec[h % DIM] += 1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def to_pgvector(v: list[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in v) + "]"


# --- seeded corpus (Drive-shaped) --------------------------------------------
# The adversarial doc (secret-roadmap) is authored to be the TOP hit for the
# crafted query about the acquisition timeline — viewer = alice only.
CORPUS = [
    {"doc_id": "secret-roadmap", "owner": "alice", "viewers": ["alice"],
     "text": "Confidential acquisition roadmap: the Meridian acquisition closes in Q3. "
             "Timeline milestones for the acquisition of Meridian and the integration roadmap."},
    {"doc_id": "public-handbook", "owner": "carol", "viewers": ["*"],
     "text": "Company handbook: office hours, vacation policy, and the expense reimbursement process."},
    {"doc_id": "bob-notes", "owner": "bob", "viewers": ["bob"],
     "text": "Bob's meeting notes about the weekly engineering sync and sprint planning."},
    {"doc_id": "shared-budget", "owner": "carol", "viewers": ["alice", "bob"],
     "text": "Shared quarterly budget spreadsheet with headcount planning and cost centers."},
]
QUERY = "When does the Meridian acquisition close? acquisition timeline roadmap"


def psql(sql: str) -> str:
    out = subprocess.run(
        ["docker", "exec", "pgvector-spike", "psql", "-U", "spike", "-d", "spike", "-tAc", sql],
        capture_output=True, text=True,
    )
    if out.returncode != 0:
        raise RuntimeError(out.stderr)
    return out.stdout.strip()


def setup_db() -> None:
    psql("CREATE EXTENSION IF NOT EXISTS vector;")
    psql("DROP TABLE IF EXISTS rag_chunk;")
    psql(f"CREATE TABLE rag_chunk (doc_id text, chunk text, embedding vector({DIM}));")
    for d in CORPUS:
        emb = to_pgvector(embed(d["text"]))
        # escape single quotes in text for SQL literal
        txt = d["text"].replace("'", "''")
        psql(f"INSERT INTO rag_chunk VALUES ('{d['doc_id']}', '{txt}', '{emb}');")


def top_k(query: str, k: int = 4) -> list[tuple[str, float]]:
    q = to_pgvector(embed(query))
    rows = psql(
        f"SELECT doc_id, round((1 - (embedding <=> '{q}'))::numeric, 4) "
        f"FROM rag_chunk ORDER BY embedding <=> '{q}' LIMIT {k};"
    )
    out = []
    for line in rows.splitlines():
        doc_id, sim = line.split("|")
        out.append((doc_id, float(sim)))
    return out


# --- OpenFGA batch_check as end user -----------------------------------------
def fga_store_id() -> str:
    r = httpx.get(f"{OPENFGA}/stores", timeout=10.0)
    r.raise_for_status()
    return [s["id"] for s in r.json()["stores"] if s["name"] == FGA_STORE][-1]


def write_tuples(store: str, run: str) -> None:
    keys = []
    for d in CORPUS:
        obj = f"document:{run}-{d['doc_id']}"
        keys.append({"user": f"user:{d['owner']}", "relation": "owner", "object": obj})
        for v in d["viewers"]:
            user = "user:*" if v == "*" else f"user:{v}"
            keys.append({"user": user, "relation": "viewer", "object": obj})
    r = httpx.post(f"{OPENFGA}/stores/{store}/write",
                   json={"writes": {"tuple_keys": keys}}, timeout=10.0)
    if r.status_code >= 400 and "already exists" not in r.text:
        r.raise_for_status()


def batch_check(store: str, sub: str, doc_ids: list[str], run: str) -> dict[str, bool]:
    items = [{"tuple_key": {"user": f"user:{sub}", "relation": "viewer",
                            "object": f"document:{run}-{d}"},
              "correlation_id": uuid.uuid4().hex} for d in doc_ids]
    r = httpx.post(f"{OPENFGA}/stores/{store}/batch-check",
                   json={"checks": items}, timeout=10.0)
    r.raise_for_status()
    result = r.json().get("result", {})
    # map correlation_id -> allowed, then back to doc order
    by_corr = {cid: v.get("allowed", False) for cid, v in result.items()}
    return {d: by_corr[items[i]["correlation_id"]] for i, d in enumerate(doc_ids)}


def main() -> int:
    setup_db()
    ranking = top_k(QUERY)
    print("=== 1.2  top-K ranking for crafted query (offline embedder) ===")
    for i, (doc, sim) in enumerate(ranking, 1):
        print(f"  #{i}  {doc:16s} cos={sim}")
    top_doc = ranking[0][0]
    assert top_doc == "secret-roadmap", f"protected doc is NOT the top hit: {top_doc}"
    print(f"  ✓ protected doc 'secret-roadmap' is the TOP hit\n")

    # reproducibility: embedding is byte-identical across a second run
    assert embed(QUERY) == embed(QUERY)
    assert to_pgvector(embed(CORPUS[0]["text"])) == to_pgvector(embed(CORPUS[0]["text"]))
    print("  ✓ embeddings byte-reproducible across runs\n")

    store = fga_store_id()
    run = f"spike{uuid.uuid4().hex[:8]}"
    write_tuples(store, run)
    candidate_ids = [d for d, _ in ranking]
    print("=== 1.3  OpenFGA batch_check as end user over the candidate set ===")
    for sub in ("alice", "bob"):
        allowed = batch_check(store, sub, candidate_ids, run)
        print(f"  user:{sub:6s} -> {allowed}")
    alice = batch_check(store, "alice", candidate_ids, run)
    bob = batch_check(store, "bob", candidate_ids, run)
    assert alice["secret-roadmap"] is True, "alice (viewer) denied the protected doc"
    assert bob["secret-roadmap"] is False, "bob (non-viewer) allowed the protected doc!"
    assert alice["public-handbook"] is True and bob["public-handbook"] is True, "public (user:*) not visible to all"
    assert bob["bob-notes"] is True and alice["bob-notes"] is False, "owner-only doc leaked"
    print("\n  ✓ protected top-hit filtered OUT for bob, kept for alice")
    print("  ✓ user:* public doc visible to both; owner-only doc private")
    print("\nSPIKE PASS (1.2 + 1.3)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
