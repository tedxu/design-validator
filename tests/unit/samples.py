"""Builders for well-formed run artifacts used across tests."""


def assumption(aid="A1", line=3, quote="SegmentCache evicts entries after ttl.",
               kind="current-fact", depends_on=()):
    return {
        "id": aid,
        "anchor": {"line_start": line, "line_end": line, "quote": quote},
        "statement": quote,
        "kind": kind,
        "conditions": [],
        "depends_on": list(depends_on),
        "origin": "explicit",
    }


def result(name, checks=(), findings=(), evidence=(), status="COMPLETED", reason=None):
    return {
        "validator": name,
        "status": status,
        "status_reason": reason,
        "checks": list(checks),
        "findings": list(findings),
        "evidence": list(evidence),
    }


def ev(eid, source, locator, excerpt, relation="supports"):
    return {"id": eid, "source": source, "locator": locator, "excerpt": excerpt, "relation": relation}


def code_ev(eid, path="store/cache.py", start=1, end=1, excerpt="class SegmentCache:",
            relation="refutes"):
    return ev(eid, "code", {"path": path, "line_start": start, "line_end": end}, excerpt, relation)


def check(cid, evidence_ids, verdict="ISSUE", assumption_ids=("A1",)):
    return {
        "id": cid,
        "assumption_ids": list(assumption_ids),
        "method": "read the cache implementation",
        "search_scope": "store/",
        "verdict": verdict,
        "evidence_ids": list(evidence_ids),
    }


def finding(fid, evidence_ids, severity="MAJOR", category="contradicted", check_ids=(),
            assumption_ids=("A1",)):
    return {
        "id": fid,
        "category": category,
        "severity": severity,
        "statement": "SegmentCache has no TTL eviction.",
        "assumption_ids": list(assumption_ids),
        "check_ids": list(check_ids),
        "evidence_ids": list(evidence_ids),
    }
