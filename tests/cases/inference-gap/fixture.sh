#!/usr/bin/env bash
# A per-node admission cap is generalised into a cluster-wide cap.
set -euo pipefail
git init -q -b main .
mkdir -p sched docs
cat > sched/admission.py <<'PY'
MAX_INFLIGHT = 8


class Node:
    def __init__(self):
        self.inflight = 0


def admit(node):
    """Admit one task on this node unless it already runs MAX_INFLIGHT."""
    if node.inflight >= MAX_INFLIGHT:
        return False
    node.inflight += 1
    return True
PY
cat > sched/cluster.py <<'PY'
from sched.admission import Node, admit

NODES = [Node() for _ in range(3)]


def submit(task_id):
    for node in NODES:
        if admit(node):
            return node
    return None
PY
cat > sched/meta.py <<'PY'
# The metadata store accepts at most 10 concurrent connections.
MAX_CONNECTIONS = 10
PY
git add -A
git -c user.name=Fixture -c user.email=fixture@example.invalid -c commit.gpgsign=false commit -q -m init
cat > docs/design.md <<'MD'
# Refresh metadata inside running tasks

## Background

`admit()` in `sched/admission.py` lets a node run at most 8 tasks at
once (`MAX_INFLIGHT`).

## Proposal

Each running task opens one connection to the metadata store to refresh
its view. Because admission caps in-flight tasks at 8, the cluster never
runs more than 8 tasks at the same time, so tasks never hold more than 8
metadata connections, below the store's limit of 10 (`MAX_CONNECTIONS`
in `sched/meta.py`). No connection pooling is needed.
MD
