"""Derive check verdicts, tiers and severities from verified evidence."""
from __future__ import annotations

SEVERITIES = ["MINOR", "MAJOR", "BLOCKER"]
TIER_RANK = {"T1": 1, "T2": 2, "T3": 3}
DESIGN_CATEGORIES = {"ambiguous", "unspecified", "inconsistent"}


def _valid(ev):
    return ev.get("verified") is not False


def _best(evs):
    tiers = [e["tier"] for e in evs]
    return min(tiers, key=TIER_RANK.get) if tiers else None


def _blocker_ok(evs, allowed):
    if "ANY" in allowed:
        return True
    for e in evs:
        if "T1" in allowed and e["tier"] == "T1":
            return True
        if "authoritative-docs" in allowed and e["source"] == "docs" and e.get("authoritative"):
            return True
    return False


def grade_result(result, manifest):
    evidence = {e["id"]: e for e in result["evidence"]}
    is_extract = manifest["name"] == "extract"
    truth = manifest["truth_tiers"]

    for c in result["checks"]:
        c.setdefault("claimed_verdict", c["verdict"])
        evs = [evidence[i] for i in c["evidence_ids"]
               if _valid(evidence[i]) and (is_extract or evidence[i]["source"] != "design")]
        c["tier"] = _best(evs)
        verdict, note = c["claimed_verdict"], None
        if verdict != "INCONCLUSIVE" and not any(e["tier"] in truth for e in evs):
            verdict, note = "INCONCLUSIVE", f"no verified evidence at {'/'.join(truth)}"
        c["verdict"] = verdict
        c["grading_note"] = note

    for f in result["findings"]:
        f.setdefault("claimed_severity", f["severity"])
        f.setdefault("audit", "not-audited")
        use_design = f["category"] in DESIGN_CATEGORIES
        evs = [evidence[i] for i in f["evidence_ids"]
               if _valid(evidence[i]) and (use_design or evidence[i]["source"] != "design")]
        tier = _best(evs) or "T3"
        sev, notes = f["claimed_severity"], []
        cap = manifest["max_severity"]
        if SEVERITIES.index(sev) > SEVERITIES.index(cap):
            sev = cap
            notes.append(f"capped at {cap} for {manifest['name']}")
        if tier == "T3" and sev != "MINOR":
            sev = "MINOR"
            notes.append("reasoning-only evidence")
        if sev == "BLOCKER" and not _blocker_ok(evs, manifest["blocker_evidence"]):
            sev = "MAJOR"
            notes.append(f"BLOCKER requires {'/'.join(manifest['blocker_evidence'])} evidence")
        if f["audit"] == "disputed" and sev != "MINOR":
            sev = SEVERITIES[SEVERITIES.index(sev) - 1]
            notes.append("disputed by audit")
        f["tier"] = tier
        f["reasoning_only"] = tier == "T3"
        f["severity"] = sev
        f["grading_note"] = "; ".join(notes) or None
