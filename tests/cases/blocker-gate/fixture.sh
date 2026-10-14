#!/usr/bin/env bash
# The design's core premise (no local state) is false: state lives in a local SQLite file.
set -euo pipefail
git init -q -b main .
mkdir -p service docs
cat > service/state.py <<'PY'
import sqlite3

_conn = sqlite3.connect("state.db")
_conn.execute("CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, user TEXT)")


def save_session(session_id, user):
    _conn.execute("INSERT OR REPLACE INTO sessions VALUES (?, ?)", (session_id, user))
    _conn.commit()


def load_session(session_id):
    row = _conn.execute("SELECT user FROM sessions WHERE id = ?", (session_id,)).fetchone()
    return row[0] if row else None
PY
cat > service/app.py <<'PY'
from service.state import load_session, save_session


def login(session_id, user):
    save_session(session_id, user)


def whoami(session_id):
    return load_session(session_id)
PY
git add -A
git -c user.name=Fixture -c user.email=fixture@example.invalid -c commit.gpgsign=false commit -q -m init
cat > docs/design.md <<'MD'
# Horizontal scaling of the session service

## Background

The session service keeps no local state: `service/state.py` stores
sessions in the database server configured by `DATABASE_URL`.

## Proposal

Because the service is stateless, run three replicas behind a round-robin
load balancer without session affinity. Any replica can answer `whoami`
for a session created through any other replica.
MD
