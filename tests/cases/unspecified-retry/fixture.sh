#!/usr/bin/env bash
# Retry after a commit timeout can duplicate segments and orphan files.
set -euo pipefail
git init -q -b main .
mkdir -p docs
cat > coordinator.py <<'PY'
class Coordinator:
    def __init__(self):
        self.segments = []

    def commit_segment(self, meta):
        self.segments.append(meta)
        return len(self.segments)
PY
cat > worker.py <<'PY'
import uuid


def flush(store, coordinator, rows):
    path = f"segments/{uuid.uuid4()}.bin"
    store.put(path, rows)
    return coordinator.commit_segment({"path": path, "rows": len(rows)})
PY
git add -A
git -c user.name=Fixture -c user.email=fixture@example.invalid -c commit.gpgsign=false commit -q -m init
cat > docs/design.md <<'MD'
# Asynchronous segment flush

## Proposal

Workers flush buffered rows with `flush()` in `worker.py`: write the
segment file to object storage, then register it with
`Coordinator.commit_segment()` in `coordinator.py`.

When `commit_segment()` raises a timeout, the worker calls `flush()`
again with the same rows. Flushed segments become visible to readers as
soon as they are committed.
MD
