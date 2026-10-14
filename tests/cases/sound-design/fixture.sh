#!/usr/bin/env bash
# An accurate, low-risk design; no BLOCKER or MAJOR finding is expected.
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
PY
git add -A
git -c user.name=Fixture -c user.email=fixture@example.invalid -c commit.gpgsign=false commit -q -m init
cat > docs/design.md <<'MD'
# Expose SegmentCache size

## Background

`SegmentCache` in `store/cache.py` keeps entries in the dict `_data`,
keyed by segment id, and exposes `put` and `get`.

## Proposal

Add a method `size()` to `SegmentCache` that returns `len(self._data)`,
so callers can report the number of cached segments. The method only
reads `_data`; it does not change `put` or `get`, persistence or
concurrency behaviour. The cache is used from a single thread today and
that does not change.
MD
