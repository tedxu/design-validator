"""Merge drafted findings, compute coverage and render report.md."""
from __future__ import annotations

from collections import Counter

SEV_ORDER = {"BLOCKER": 0, "MAJOR": 1, "MINOR": 2}
TIER_RANK = {"T1": 1, "T2": 2, "T3": 3}
MAX_EXPANDED = 50
RUN_FIELDS = ("run_id", "design_path", "design_sha256", "repo_commit", "worktree_diff_sha256",
              "depth", "mode", "blocked_by", "gate_disputed")


def _owner(item_id):
    return item_id.rsplit(".", 1)[0]


def _union(lists):
    out = []
    for items in lists:
        for x in items:
            if x not in out:
                out.append(x)
    return out


def draft_errors(draft, results):
    originals = {f["id"] for r in results.values() for f in r["findings"]}
    errs, seen, counts = [], set(), Counter()
    for d in draft["findings"]:
        if d["id"] in seen:
            errs.append(f"{d['id']}: duplicate id")
        seen.add(d["id"])
        if not d["merged_from"]:
            errs.append(f"{d['id']}: merged_from is empty")
        for fid in d["merged_from"]:
            if fid not in originals:
                errs.append(f"{d['id']}: unknown finding {fid}")
            counts[fid] += 1
    for fid in sorted(originals):
        if counts[fid] == 0:
            errs.append(f"finding {fid} is not included in any merged finding")
        elif counts[fid] > 1:
            errs.append(f"finding {fid} is included {counts[fid]} times")
    return errs


def compute_coverage(run, assumptions, results):
    validators, status_of = [], {}
    for v in run["validators"]:
        name = v["name"]
        if not v["selected"]:
            status, reason = "NOT_RUN", v["not_selected_reason"]
        elif run["stages"].get(str(v["stage"])) == "SKIPPED":
            status, reason = "SKIPPED", "blocked by " + ", ".join(run["blocked_by"])
            if run.get("gate_disputed"):
                reason += " (blocking finding disputed by audit; consider re-running)"
        elif name not in results:
            status, reason = "NOT_RUN", "no result file"
        else:
            status, reason = results[name]["status"], results[name].get("status_reason")
        status_of[name] = status
        validators.append({"name": name, "stage": v["stage"], "status": status, "reason": reason})

    verdicts = {a["id"]: [] for a in assumptions}
    checkers = {a["id"]: set() for a in assumptions}
    for name, r in results.items():
        for c in r["checks"]:
            for aid in c["assumption_ids"]:
                if aid in verdicts:
                    verdicts[aid].append(c["verdict"])
                    checkers[aid].add(name)
    out = []
    for a in assumptions:
        vs = verdicts[a["id"]]
        if any(v != "INCONCLUSIVE" for v in vs):
            status = "CHECKED"
        elif vs:
            status = "INCONCLUSIVE"
        else:
            status = "NOT_CHECKED"
        reason = None
        if status != "CHECKED":
            targets = [v["name"] for v in run["validators"]
                       if v["scope"] == "assumption" and a["kind"] in v["targets"]]
            reason = "; ".join(f"{t} {status_of[t]}" for t in targets) or "no validator targets this kind"
        out.append({"id": a["id"], "kind": a["kind"], "status": status,
                    "checked_by": sorted(checkers[a["id"]]), "reason": reason})
    return {"validators": validators, "assumptions": out}


def build_report(run, assumptions, results, draft):
    originals = {f["id"]: f for r in results.values() for f in r["findings"]}
    findings = []
    for d in draft["findings"]:
        srcs = [originals[i] for i in d["merged_from"]]
        audits = {f["audit"] for f in srcs}
        tier = min((f["tier"] for f in srcs), key=TIER_RANK.get)
        findings.append({
            "id": d["id"],
            "severity": min((f["severity"] for f in srcs), key=SEV_ORDER.get),
            "category": d["category"],
            "statement": d["statement"],
            "tier": tier,
            "reasoning_only": tier == "T3",
            "audit": ("disputed" if audits == {"disputed"}
                      else "confirmed" if "confirmed" in audits else "not-audited"),
            "validators": sorted({_owner(i) for i in d["merged_from"]}),
            "merged_from": list(d["merged_from"]),
            "assumption_ids": _union(f["assumption_ids"] for f in srcs),
            "evidence_ids": _union(f["evidence_ids"] for f in srcs),
        })
    findings.sort(key=lambda f: SEV_ORDER[f["severity"]])
    checks = [{"id": c["id"], "validator": name, "verdict": c["verdict"], "tier": c.get("tier"),
               "assumption_ids": c["assumption_ids"], "method": c["method"],
               "search_scope": c["search_scope"], "grading_note": c.get("grading_note")}
              for name, r in results.items() for c in r["checks"]]
    return {"schema_version": "0.1", "run": {k: run.get(k) for k in RUN_FIELDS},
            "summary": draft["summary"], "findings": findings, "checks": checks,
            "coverage": compute_coverage(run, assumptions, results), "assumptions": assumptions}


def gap_count(rep):
    cov = rep["coverage"]
    return (sum(1 for v in cov["validators"] if v["status"] != "COMPLETED")
            + sum(1 for a in cov["assumptions"] if a["status"] != "CHECKED"))


def _cell(text):
    return " ".join(str(text if text is not None else "").split()).replace("|", "\\|")


def _finding_line(f):
    flags = [f["tier"]]
    if f["reasoning_only"]:
        flags.append("reasoning only")
    if f["audit"] == "disputed":
        flags.append("disputed")
    return (f"- **{f['id']}** [{f['severity']}] {f['category']} · {' · '.join(flags)} — "
            f"{f['statement']} (from {', '.join(f['merged_from'])})")


def render_markdown(rep):
    r = rep["run"]
    cov = rep["coverage"]
    findings = rep["findings"]
    lines = [f"# Design validation report: {r['design_path']}", ""]
    baseline = f"`{r['repo_commit']}`" if r["repo_commit"] else "snapshot (no git)"
    if r["worktree_diff_sha256"]:
        baseline += " + uncommitted changes"
    lines.append(f"- Run `{r['run_id']}` · depth `{r['depth']}` · mode `{r['mode']}` · baseline {baseline}")
    if r["blocked_by"]:
        note = " (disputed by audit)" if r["gate_disputed"] else ""
        lines.append(f"- Later stages blocked by {', '.join(r['blocked_by'])}{note}")
    lines += ["", "## Summary", "", rep["summary"].strip() or "_No summary._", ""]

    top = [f for f in findings if f["severity"] in ("BLOCKER", "MAJOR")]
    lines += ["## Blocking and major issues", ""]
    lines += [_finding_line(f) for f in top] or ["None."]

    gaps = [f"- Validator `{v['name']}`: {v['status']}" + (f" — {v['reason']}" if v["reason"] else "")
            for v in cov["validators"] if v["status"] != "COMPLETED"]
    gaps += [f"- Assumption {a['id']}: {a['status']}" + (f" — {a['reason']}" if a["reason"] else "")
             for a in cov["assumptions"] if a["status"] != "CHECKED"]
    lines += ["", "## Coverage gaps", ""] + (gaps or ["None."])

    lines += ["", f"## All issues ({len(findings)})", ""]
    lines += [_finding_line(f) for f in findings[:MAX_EXPANDED]]
    overflow = findings[MAX_EXPANDED:]
    if overflow:
        counts = Counter((", ".join(f["validators"]), f["category"]) for f in overflow)
        parts = [f"{v} / {c} ×{n}" for (v, c), n in sorted(counts.items())]
        lines.append(f"- {len(overflow)} more: " + "; ".join(parts) + " (see report.json)")

    lines += ["", f"## Checks performed ({len(rep['checks'])})", "",
              "| Check | Verdict | Tier | Assumptions | Method | Scope |", "|---|---|---|---|---|---|"]
    for c in rep["checks"]:
        lines.append(f"| {c['id']} | {c['verdict']} | {c['tier'] or '-'} | "
                     f"{_cell(', '.join(c['assumption_ids']))} | {_cell(c['method'])} | "
                     f"{_cell(c['search_scope'])} |")

    lines += ["", "## Coverage", "", "| Validator | Stage | Status | Reason |", "|---|---|---|---|"]
    for v in cov["validators"]:
        lines.append(f"| {v['name']} | {v['stage']} | {v['status']} | {_cell(v['reason'])} |")

    status = {a["id"]: a["status"] for a in cov["assumptions"]}
    lines += ["", "## Assumptions", ""]
    for a in rep["assumptions"]:
        anchor = a["anchor"]
        lines.append(f"- **{a['id']}** ({a['kind']}, {a['origin']}, lines {anchor['line_start']}-"
                     f"{anchor['line_end']}, {status.get(a['id'], '-')}): {a['statement']}")
    return "\n".join(lines) + "\n"
