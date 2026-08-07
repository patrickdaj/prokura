"""Local, offline, deterministic embedder (demo-grade).

A blake2b hashing bag-of-words vectorizer: each token is hashed to a bucket in a
fixed ``DIM``-dimensional space, counts are L2-normalized, similarity is cosine
(pgvector ``<=>``). Properties that matter for the demo:

- **Offline / no secret** — no embedding API, no model download, no network call.
- **Deterministic / byte-reproducible** — blake2b bypasses Python's per-process
  hash randomization, so the same text embeds to the same vector on every run and
  the adversarial "protected doc is the top hit" case reproduces exactly.

This is explicitly demo-grade. The property under test is *authorization*
(non-leakage), which a lexical embedder proves exactly as well as a semantic one.

**Real-model swap point:** replace the body of ``embed()`` with a call to a
sentence-transformer (e.g. ``SentenceTransformer("all-MiniLM-L6-v2").encode(text)``)
and set ``DIM`` to that model's output dimension (384 for MiniLM). Nothing else in
the service changes — ingestion and retrieval only depend on ``DIM`` and ``embed``.
"""

import hashlib
import math
import re

DIM = 256

_TOKEN = re.compile(r"[a-z0-9]+")


def embed(text: str) -> list[float]:
    """Return the unit-normalized embedding vector for ``text``."""
    vec = [0.0] * DIM
    for tok in _TOKEN.findall(text.lower()):
        h = int.from_bytes(hashlib.blake2b(tok.encode(), digest_size=4).digest(), "big")
        vec[h % DIM] += 1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def to_pgvector(vec: list[float]) -> str:
    """Serialize an embedding as a pgvector literal, e.g. ``[0.1,0.0,...]``."""
    return "[" + ",".join(f"{x:.6f}" for x in vec) + "]"
