#!/usr/bin/env bash
# Design claims a TTL eviction that SegmentCache does not have.
set -euo pipefail
git init -q -b main .
mkdir -p store docs
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
git -c user.name=Fixture -c user.email=fixture@example.invalid -c commit.gpgsign=false commit -q -m init
cat > docs/design.md <<'MD'
# Simplify segment cache invalidation

## Background

`SegmentCache` in `store/cache.py` already expires every entry after
`ttl_seconds` (default 30s), so stale entries disappear on their own.

## Proposal

Remove the explicit `cache.invalidate()` call from
`on_segment_dropped` in `store/loader.py`. Dropped segments will age
out of the cache through the existing TTL expiry.
MD
