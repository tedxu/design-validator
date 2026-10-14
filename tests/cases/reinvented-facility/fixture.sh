#!/usr/bin/env bash
# The design builds a new backoff mechanism next to an existing retry helper.
set -euo pipefail
git init -q -b main .
mkdir -p util client docs
cat > util/retry.py <<'PY'
import time


def retry(fn, attempts=3, backoff=0.1):
    """Call fn until it succeeds, sleeping backoff * 2**i between attempts."""
    for i in range(attempts):
        try:
            return fn()
        except IOError:
            if i == attempts - 1:
                raise
            time.sleep(backoff * 2 ** i)
PY
cat > client/upload.py <<'PY'
from util.retry import retry


def upload(store, key, data):
    return retry(lambda: store.put(key, data))
PY
cat > client/download.py <<'PY'
def download(store, key):
    return store.get(key)
PY
git add -A
git -c user.name=Fixture -c user.email=fixture@example.invalid -c commit.gpgsign=false commit -q -m init
cat > docs/design.md <<'MD'
# Retry downloads

## Proposal

`download()` in `client/download.py` fails on the first transient
`IOError`. Add a new module `client/backoff.py` with a `Backoff` class
that implements exponential backoff (initial delay, multiplier, maximum
attempts, jitter), and wrap the `store.get` call in `download()` in a
loop driven by `Backoff`.
MD
