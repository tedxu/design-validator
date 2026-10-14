#!/usr/bin/env bash
# Renaming a persisted field breaks a reader the design does not mention.
set -euo pipefail
git init -q -b main .
mkdir -p stats tools docs
cat > stats/export.py <<'PY'
import json


def write_stats(path, segments):
    records = [{"segment_id": s.id, "rows": s.rows} for s in segments]
    with open(path, "w") as f:
        json.dump(records, f)
PY
cat > tools/capacity.py <<'PY'
import json


def total_rows(path):
    with open(path) as f:
        return sum(rec["rows"] for rec in json.load(f))
PY
git add -A
git -c user.name=Fixture -c user.email=fixture@example.invalid -c commit.gpgsign=false commit -q -m init
cat > docs/design.md <<'MD'
# Consistent field names in segment stats

## Proposal

Rename the `rows` key to `num_rows` in the records that `write_stats()`
in `stats/export.py` writes, to match the naming used elsewhere. The
file format is otherwise unchanged.
MD
