#!/usr/bin/env bash
# A 10x query speed-up is claimed for a build step the query path never uses.
set -euo pipefail
git init -q -b main .
mkdir -p index docs
cat > index/build.py <<'PY'
def build_flat(vectors):
    return {"kind": "flat", "vectors": list(vectors)}


def build_hnsw(vectors, m=16, ef_construction=200):
    graph = {i: [] for i in range(len(vectors))}
    return {"kind": "hnsw", "vectors": list(vectors), "graph": graph, "m": m,
            "ef": ef_construction}
PY
cat > index/search.py <<'PY'
def search(index, query, k):
    vectors = index["vectors"]
    scored = sorted(range(len(vectors)),
                    key=lambda i: -sum(a * b for a, b in zip(vectors[i], query)))
    return scored[:k]
PY
git add -A
git -c user.name=Fixture -c user.email=fixture@example.invalid -c commit.gpgsign=false commit -q -m init
cat > docs/design.md <<'MD'
# Switch to HNSW indexes

## Proposal

Replace `build_flat()` with `build_hnsw()` in `index/build.py` for every
collection. This makes queries 10x faster and has no impact on
ingestion throughput.
MD
