#!/usr/bin/env bash
# A project command validator (the path-check example) finds a file that does not exist.
set -euo pipefail
PLUGIN=$(cd "$(dirname "$0")/../../.." && pwd)
git init -q -b main .
mkdir -p store docs .dv/validators
cp -R "$PLUGIN/examples/validators/path-check" .dv/validators/
cat > store/cache.py <<'PY'
class SegmentCache:
    """In-memory cache of segment metadata, keyed by segment id."""
    def __init__(self):
        self._data = {}
PY
git add -A
git -c user.name=Fixture -c user.email=fixture@example.invalid -c commit.gpgsign=false commit -q -m init
cat > docs/design.md <<'MD'
# Cache eviction metrics

## Background

`SegmentCache` in `store/cache.py` evicts entries through the LRU policy
implemented in `store/evict.py`.

## Proposal

Count evictions and expose the counter as a metric.
MD
