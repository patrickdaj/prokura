# M5 spike — RAG authorization

`rag_spike.py` is the pre-build spike (mirroring M0/M2/M3/M4). It proves, against
the live stack, the four unknowns the RAG service depends on:

1. **pgvector** — `postgres:17-alpine` does *not* bundle it; `pgvector/pgvector:pg17`
   does (0.8.6). `CREATE EXTENSION vector`, a `vector(N)` column, and cosine top-K
   (`<=>`) all work. The build switches the compose Postgres image tag accordingly.
2. **Offline embedder** — a deterministic blake2b hashing bag-of-words vectorizer
   makes the protected `secret-roadmap` doc the #1 hit for the crafted query,
   byte-reproducibly and offline.
3. **FGA-as-user filter** — OpenFGA `batch-check` with subject `user:{end-user}`
   filters the protected doc out for a non-viewer, keeps it for a viewer.
4. **Exchange** — `mcp-server → aud=rag-server` (RFC 8693) preserves `sub`
   (verified separately in the apply run; see design.md).

## Run

The spike used a throwaway pgvector container so the running stack was untouched:

```bash
docker run --rm -d --name pgvector-spike \
  -e POSTGRES_USER=spike -e POSTGRES_PASSWORD=spike -e POSTGRES_DB=spike \
  pgvector/pgvector:pg17
python spike/rag/rag_spike.py     # needs the prokura stack up (OpenFGA on :8081)
docker rm -f pgvector-spike
```

The shipped service (`services/rag/`) uses the identical embedder and batch-check
shapes against the main Postgres (now pgvector-enabled) and OpenFGA. Findings are
recorded in `openspec/changes/add-rag-authorization/design.md`.
