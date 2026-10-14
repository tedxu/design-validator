"""Ground-truth and match checks, and evaluation metrics."""
from __future__ import annotations

import glob
import json
import os

from . import evalrun, report, schema


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def truth_errors(truth, case):
    errs = schema.validate(truth, schema.load_schema("truth"))
    if errs:
        return errs
    seen = set()
    for item in truth["items"]:
        iid = item["id"]
        if iid in seen:
            errs.append(f"{iid}: duplicate id")
        seen.add(iid)
        pool = case["revisions"] if item["source"] == "revision" else case["fixes"]
        if not item["commits"]:
            errs.append(f"{iid}: cite at least one commit")
        for c in item["commits"]:
            if not any(full.startswith(c) for full in pool):
                errs.append(f"{iid}: {c} is not one of this case's {item['source']} commits")
        if item["tier"] == "T1" and item["source"] != "fix":
            errs.append(f"{iid}: tier T1 requires source 'fix'")
    return errs


def match_errors(matches, rep, truth):
    errs = schema.validate(matches, schema.load_schema("matches"))
    if errs:
        return errs
    findings = [f["id"] for f in rep["findings"]]
    truth_ids = {t["id"] for t in truth["items"]}
    counts = {}
    for m in matches["matches"]:
        fid = m["finding_id"]
        counts[fid] = counts.get(fid, 0) + 1
        if fid not in findings:
            errs.append(f"{fid}: not a finding of this run")
        if m["verdict"] == "match":
            if not m["truth_ids"]:
                errs.append(f"{fid}: a match names at least one truth id")
            errs += [f"{fid}: unknown truth id {t}" for t in m["truth_ids"] if t not in truth_ids]
        elif m["truth_ids"]:
            errs.append(f"{fid}: only a match names truth ids")
    errs += [f"{fid}: listed {n} times" for fid, n in counts.items() if n > 1]
    errs += [f"{fid}: missing from matches" for fid in findings if fid not in counts]
    return errs


def _ratio(a, b):
    return round(a / b, 3) if b else None


def _group(rows, key):
    groups = {}
    for row in rows:
        values = row[key] if isinstance(row[key], list) else [row[key]]
        for v in values:
            groups.setdefault(str(v), []).append(row)
    return dict(sorted(groups.items()))


def _recall(rows):
    hit = sum(r["hit"] for r in rows)
    return {"hit": hit, "total": len(rows), "recall": _ratio(hit, len(rows))}


def _precision(rows):
    m = sum(r["verdict"] == "match" for r in rows)
    refuted = sum(r["verdict"] == "refuted" for r in rows)
    return {"findings": len(rows), "match": m, "refuted": refuted,
            "strict": _ratio(m, len(rows)), "lenient": _ratio(m, m + refuted)}


def _evidence_counts(run_dir):
    ok = bad = 0
    for path in glob.glob(os.path.join(run_dir, "results", "*.json")):
        for e in load_json(path).get("evidence", []):
            ok += e.get("verified") is True
            bad += e.get("verified") is False
    return ok, bad


def score(eval_dir, only=None):
    truths, findings, cases, excluded = [], [], [], []
    ev_ok = ev_bad = gaps = 0
    seconds, costs = [], []
    for case_dir in evalrun.case_dirs(eval_dir, only):
        case = load_json(os.path.join(case_dir, "case.json"))
        cid = case["case_id"]
        result = evalrun.load_result(case_dir)
        rpath = evalrun.report_path(case_dir, result)
        tpath = os.path.join(case_dir, "truth.json")
        mpath = os.path.join(case_dir, "matches.json")
        missing = [name for name, ok in (("truth.json", os.path.isfile(tpath)), ("report", rpath),
                                         ("matches.json", os.path.isfile(mpath))) if not ok]
        if missing:
            excluded.append({"case_id": cid, "reason": "missing " + ", ".join(missing)})
            continue
        loaded = {}
        for label, path in (("truth.json", tpath), ("report.json", rpath), ("matches.json", mpath)):
            try:
                loaded[label] = load_json(path)
            except (OSError, ValueError):
                excluded.append({"case_id": cid, "reason": f"unreadable {label}"})
                break
        if len(loaded) < 3:
            continue
        truth, rep, matches = loaded["truth.json"], loaded["report.json"], loaded["matches.json"]
        errs = truth_errors(truth, case) + match_errors(matches, rep, truth)
        if errs:
            excluded.append({"case_id": cid,
                             "reason": f"{len(errs)} invalid entries; run check-truth and check-matches"})
            continue
        verdicts = {m["finding_id"]: m["verdict"] for m in matches["matches"]}
        hit = {t for m in matches["matches"] if m["verdict"] == "match" for t in m["truth_ids"]}
        for t in truth["items"]:
            truths.append({"tier": t["tier"], "reviewed": t["reviewed"],
                           "baseline_kind": case["baseline_kind"], "hit": t["id"] in hit})
        for f in rep["findings"]:
            findings.append({"severity": f["severity"], "validators": f["validators"],
                             "verdict": verdicts[f["id"]]})
        ok, bad = _evidence_counts(os.path.dirname(rpath))
        ev_ok, ev_bad = ev_ok + ok, ev_bad + bad
        case_gaps = report.gap_count(rep)
        gaps += case_gaps
        if result.get("seconds") is not None:
            seconds.append(result["seconds"])
        if result.get("cost_usd") is not None:
            costs.append(result["cost_usd"])
        cases.append({
            "case_id": cid, "design_path": case["design_path"], "baseline_kind": case["baseline_kind"],
            "truth": len(truth["items"]), "hit": sum(t["id"] in hit for t in truth["items"]),
            "findings": len(rep["findings"]),
            "match": sum(v == "match" for v in verdicts.values()),
            "refuted": sum(v == "refuted" for v in verdicts.values()),
            "coverage_gaps": case_gaps, "seconds": result.get("seconds"),
            "cost_usd": result.get("cost_usd")})
    return {
        "cases": cases,
        "excluded": excluded,
        "recall": {"all": _recall(truths),
                   "by_tier": {k: _recall(v) for k, v in _group(truths, "tier").items()},
                   "by_reviewed": {k: _recall(v) for k, v in _group(truths, "reviewed").items()},
                   "by_baseline_kind": {k: _recall(v)
                                        for k, v in _group(truths, "baseline_kind").items()}},
        "precision": {"all": _precision(findings),
                      "by_severity": {k: _precision(v) for k, v in _group(findings, "severity").items()},
                      "by_validator": {k: _precision(v)
                                       for k, v in _group(findings, "validators").items()}},
        "blocker_false_positives": sum(f["severity"] == "BLOCKER" and f["verdict"] == "refuted"
                                       for f in findings),
        "citation_failure_rate": _ratio(ev_bad, ev_ok + ev_bad),
        "coverage_gaps": gaps,
        "avg_seconds": _ratio(sum(seconds), len(seconds)),
        "avg_cost_usd": _ratio(sum(costs), len(costs)),
        "truth_reviewed": bool(truths) and all(t["reviewed"] for t in truths),
    }


def _fmt(v):
    if v is None:
        return "n/a"
    return str(round(v, 3)) if isinstance(v, float) else str(v)


def render_markdown(out):
    r, p = out["recall"], out["precision"]
    lines = [
        "# Design validator evaluation", "",
        f"- Cases scored: {len(out['cases'])}; excluded: {len(out['excluded'])}",
        ("- Ground truth: reviewed" if out["truth_reviewed"] else
         "- Ground truth: not reviewed (weak truth from history; not a conclusion)"),
        "- Runs used snapshots without git history.", "",
        "## Headline", "", "| metric | value |", "|---|---|",
        f"| recall | {r['all']['hit']}/{r['all']['total']} ({_fmt(r['all']['recall'])}) |",
        f"| strict precision | {_fmt(p['all']['strict'])} |",
        f"| lenient precision | {_fmt(p['all']['lenient'])} |",
        f"| BLOCKER false positives | {out['blocker_false_positives']} |",
        f"| citation failure rate | {_fmt(out['citation_failure_rate'])} |",
        f"| coverage gaps | {out['coverage_gaps']} |",
        f"| average seconds | {_fmt(out['avg_seconds'])} |",
        f"| average cost (USD) | {_fmt(out['avg_cost_usd'])} |", "",
        "## Recall by group", "", "| group | value | hit | total | recall |", "|---|---|---|---|---|"]
    for group in ("by_tier", "by_reviewed", "by_baseline_kind"):
        for k, v in r[group].items():
            lines.append(f"| {group[3:]} | {k} | {v['hit']} | {v['total']} | {_fmt(v['recall'])} |")
    lines += ["", "## Precision by group", "",
              "| group | findings | match | refuted | strict | lenient |", "|---|---|---|---|---|---|"]
    for group in ("by_severity", "by_validator"):
        for k, v in p[group].items():
            lines.append(f"| {k} | {v['findings']} | {v['match']} | {v['refuted']} | "
                         f"{_fmt(v['strict'])} | {_fmt(v['lenient'])} |")
    lines += ["", "## Cases", "",
              "| case | design | baseline | truth hit | findings (match/refuted) | gaps | seconds | cost |",
              "|---|---|---|---|---|---|---|---|"]
    for c in out["cases"]:
        lines.append(f"| {c['case_id']} | {c['design_path']} | {c['baseline_kind']} | "
                     f"{c['hit']}/{c['truth']} | {c['findings']} ({c['match']}/{c['refuted']}) | "
                     f"{c['coverage_gaps']} | {_fmt(c['seconds'])} | {_fmt(c['cost_usd'])} |")
    if out["excluded"]:
        lines += ["", "## Excluded", ""]
        lines += [f"- {e['case_id']}: {e['reason']}" for e in out["excluded"]]
    return "\n".join(lines) + "\n"


def write_report(eval_dir, out):
    json_path = os.path.join(eval_dir, "report.json")
    md_path = os.path.join(eval_dir, "report.md")
    os.makedirs(eval_dir, exist_ok=True)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
        f.write("\n")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(render_markdown(out))
    return json_path, md_path
