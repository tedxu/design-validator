#!/usr/bin/env bash
# A repository whose design history supplies evaluation ground truth:
#   cache-ttl.md   written before its implementation (pre-implementation);
#                  relies on a TTL that does not exist; later fixed and revised.
#   flush-retry.md committed with its code (as-built); its retry duplicates
#                  segments; later fixed and revised.
#   cache-size.md  never revised and never fixed: not evaluable.
set -euo pipefail
git init -q -b main .
commit() {  # commit <iso-date> <message>
  GIT_AUTHOR_DATE="$1" GIT_COMMITTER_DATE="$1" git -c user.name=Fixture \
    -c user.email=fixture@example.invalid -c commit.gpgsign=false commit -q -m "$2"
}
mkdir -p .dv docs/design store
cat > .dv/config.yaml <<'YAML'
eval:
  design_globs: ["docs/design/*.md"]
YAML
cat > store/cache.py <<'PY'
class SegmentCache:
    """In-memory cache of segment metadata, keyed by segment id."""
    def __init__(self):
        self._data = {}
    def put(self, segment_id, meta):
        self._data[segment_id] = meta
    def get(self, segment_id):
        return self._data.get(segment_id)
    def invalidate(self, segment_id):
        self._data.pop(segment_id, None)
PY
cat > store/loader.py <<'PY'
from store.cache import SegmentCache
cache = SegmentCache()
def on_segment_dropped(segment_id):
    # Dropped segments must disappear from the cache immediately.
    cache.invalidate(segment_id)
def load(segment_id, fetch):
    meta = cache.get(segment_id)
    if meta is None:
        meta = fetch(segment_id)
        cache.put(segment_id, meta)
    return meta
PY
git add -A
commit 2026-01-05T10:00:00 "feat: add segment cache"

cat > docs/design/cache-ttl.md <<'MD'
# Simplify segment cache invalidation

## Background

`SegmentCache` in `store/cache.py` already expires every entry after
`ttl_seconds` (default 30s), so stale entries disappear on their own.

## Proposal

Remove the explicit `cache.invalidate()` call from
`on_segment_dropped` in `store/loader.py`. Dropped segments will age
out of the cache through the existing TTL expiry.
MD
git add -A
commit 2026-01-10T10:00:00 "doc: propose relying on the cache TTL"

cat > store/loader.py <<'PY'
from store.cache import SegmentCache
cache = SegmentCache()
def on_segment_dropped(segment_id):
    pass
def load(segment_id, fetch):
    meta = cache.get(segment_id)
    if meta is None:
        meta = fetch(segment_id)
        cache.put(segment_id, meta)
    return meta
PY
git add -A
commit 2026-01-12T10:00:00 "enhance: drop explicit cache invalidation"

cat > store/loader.py <<'PY'
from store.cache import SegmentCache
cache = SegmentCache()
def on_segment_dropped(segment_id):
    # SegmentCache has no expiry; dropped segments must leave it now.
    cache.invalidate(segment_id)
def load(segment_id, fetch):
    meta = cache.get(segment_id)
    if meta is None:
        meta = fetch(segment_id)
        cache.put(segment_id, meta)
    return meta
PY
git add -A
commit 2026-01-20T10:00:00 "fix: evict dropped segments from the cache immediately"

cat > docs/design/cache-ttl.md <<'MD'
# Simplify segment cache invalidation

## Background

`SegmentCache` in `store/cache.py` has no expiry: entries leave the
cache only through `invalidate()`.

## Proposal

Keep the explicit `cache.invalidate()` call in `on_segment_dropped` in
`store/loader.py`; dropped segments must leave the cache immediately.
MD
git add -A
commit 2026-01-21T10:00:00 "doc: correct the cache design, SegmentCache has no TTL"

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
cat > docs/design/flush-retry.md <<'MD'
# Asynchronous segment flush

## Proposal

Workers flush buffered rows with `flush()` in `worker.py`: write the
segment file to object storage, then register it with
`Coordinator.commit_segment()` in `coordinator.py`.

When `commit_segment()` raises a timeout, the worker calls `flush()`
again with the same rows. Flushed segments become visible to readers as
soon as they are committed.
MD
git add -A
commit 2026-02-01T10:00:00 "feat: asynchronous segment flush"

cat > coordinator.py <<'PY'
class Coordinator:
    def __init__(self):
        self.segments = []
        self._paths = set()
    def commit_segment(self, meta):
        if meta["path"] in self._paths:
            return len(self.segments)
        self._paths.add(meta["path"])
        self.segments.append(meta)
        return len(self.segments)
PY
cat > worker.py <<'PY'
def flush(store, coordinator, rows, request_id):
    path = f"segments/{request_id}.bin"
    store.put(path, rows)
    return coordinator.commit_segment({"path": path, "rows": len(rows)})
PY
git add -A
commit 2026-02-10T10:00:00 "fix: deduplicate segments committed twice after a retry"

cat >> docs/design/flush-retry.md <<'MD'

Each flush carries a request id and derives the segment path from it;
`commit_segment()` ignores a path it already holds, so a retried flush
does not register the same rows twice.
MD
git add -A
commit 2026-02-11T10:00:00 "doc: describe the idempotent segment commit"

cat > docs/design/cache-size.md <<'MD'
# Expose SegmentCache size

## Background

`SegmentCache` in `store/cache.py` keeps entries in the dict `_data`,
keyed by segment id, and exposes `put` and `get`.

## Proposal

Add a method `size()` to `SegmentCache` that returns `len(self._data)`,
so callers can report the number of cached segments.
MD
git add -A
commit 2026-03-01T10:00:00 "doc: propose exposing the cache size"
