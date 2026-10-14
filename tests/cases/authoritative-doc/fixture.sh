#!/usr/bin/env bash
# The design overwrites object keys that an authoritative rule makes immutable.
set -euo pipefail
git init -q -b main .
mkdir -p .dv docs/rules storage
cat > .dv/config.yaml <<'YAML'
docs:
  - path: docs/rules
    authority: authoritative
YAML
cat > docs/rules/object-storage.md <<'MD'
# Object storage rules

## Immutable keys

Objects in the data bucket are immutable. A key, once written, must
never be overwritten or deleted while any snapshot may reference it.
Writers always create a new key for new content.
MD
cat > storage/writer.py <<'PY'
def write_segment(bucket, segment_id, data):
    key = f"seg/{segment_id}.bin"
    bucket.put(key, data)
    return key
PY
git add -A
git -c user.name=Fixture -c user.email=fixture@example.invalid -c commit.gpgsign=false commit -q -m init
cat > docs/design.md <<'MD'
# In-place compaction

## Proposal

To save space, compaction writes the merged result of several segments
over the key of the first input segment: `write_segment()` in
`storage/writer.py` is called with that segment's id, overwriting
`seg/<id>.bin`. The other input keys are deleted right after.
MD
