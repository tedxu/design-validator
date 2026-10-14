"""ID and cross-reference checks for assumptions and validator results."""
from __future__ import annotations

import re

from .sources import match_excerpt


VERIFY_OWNED = {
    "checks": ("claimed_verdict", "tier", "grading_note"),
    "findings": ("claimed_severity", "tier", "reasoning_only", "grading_note", "audit", "audit_reason"),
}


def result_errors(result, name, assumption_ids):
    errs = []
    for key, fields in VERIFY_OWNED.items():
        for item in result[key]:
            for field in fields:
                if field in item:
                    errs.append(f"{item['id']}: field '{field}' is written by verify.py; omit it")
    if result["validator"] != name:
        errs.append(f"validator is '{result['validator']}', expected '{name}'")
    patterns = {k: re.compile(rf"{re.escape(name)}\.{k}[0-9]+") for k in "CFE"}
    seen = set()
    for kind, key in (("C", "checks"), ("F", "findings"), ("E", "evidence")):
        for item in result[key]:
            iid = item["id"]
            if not patterns[kind].fullmatch(iid):
                errs.append(f"{iid}: id must look like {name}.{kind}<n>")
            if iid in seen:
                errs.append(f"{iid}: duplicate id")
            seen.add(iid)
    evidence_ids = {e["id"] for e in result["evidence"] if patterns["E"].fullmatch(e["id"])}
    check_ids = {c["id"] for c in result["checks"] if patterns["C"].fullmatch(c["id"])}

    def refs(owner, ids, known, what):
        for i in ids:
            if i not in known:
                errs.append(f"{owner}: unknown {what} {i}")

    for c in result["checks"]:
        refs(c["id"], c["evidence_ids"], evidence_ids, "evidence")
        refs(c["id"], c["assumption_ids"], assumption_ids, "assumption")
    by_id = {e["id"]: e for e in result["evidence"]}
    for f in result["findings"]:
        refs(f["id"], f["evidence_ids"], evidence_ids, "evidence")
        if f["category"] == "inconsistent":
            places = {(by_id[i]["locator"].get("line_start"), by_id[i]["locator"].get("line_end"))
                      for i in f["evidence_ids"] if i in by_id and by_id[i]["source"] == "design"}
            if len(places) < 2:
                errs.append(f"{f['id']}: an inconsistent finding cites the conflicting statements: "
                            f"at least two design evidence items at different lines")
        refs(f["id"], f["check_ids"], check_ids, "check")
        refs(f["id"], f["assumption_ids"], assumption_ids, "assumption")
    return errs


def assumption_errors(assumptions, design_text):
    errs = []
    known = {a["id"] for a in assumptions}
    seen = set()
    for a in assumptions:
        if a["id"] in seen:
            errs.append(f"{a['id']}: duplicate id")
            continue
        seen.add(a["id"])
        for d in a["depends_on"]:
            if d == a["id"]:
                errs.append(f"{a['id']}: depends on itself")
            elif d not in known:
                errs.append(f"{a['id']}: depends_on unknown assumption {d}")
        anchor = a["anchor"]
        err = match_excerpt(design_text, anchor["line_start"], anchor["line_end"], anchor["quote"],
                            slack=3)
        if err:
            errs.append(f"{a['id']}: anchor {err}")
    return errs
