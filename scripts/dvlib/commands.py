"""Subcommand implementations behind scripts/verify.py."""
from __future__ import annotations

import hashlib
import json
import os

from . import evidence, gate, grading, hygiene, registry, report, runinit, schema, sources, structure

SEVERITY_KEYS = ("BLOCKER", "MAJOR", "MINOR")


class StateError(Exception):
    """The run is in a state where this subcommand cannot proceed."""


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def dump_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, path)


def load_run(run_dir):
    path = os.path.join(run_dir, "run.json")
    if not os.path.isfile(path):
        raise StateError(f"{path} not found; run 'verify.py init' first")
    return load_json(path)


def save_run(run_dir, run):
    dump_json(os.path.join(run_dir, "run.json"), run)


def manifests(run):
    return {v["name"]: v for v in run["validators"]}


def read_design(run_dir):
    with open(os.path.join(run_dir, "design.md"), encoding="utf-8", newline="") as f:
        return f.read()


def build_context(run_dir, run):
    return evidence.Context(
        repo_root=run["repo_root"], commit=run["repo_commit"], design_text=read_design(run_dir),
        docs=run["docs"], priors=run["priors"],
        reader=sources.SourceReader(run["repo_root"], run["repo_commit"], run.get("worktree_paths")))


def read_json_file(path, label, errors):
    if not os.path.isfile(path):
        errors.append(f"{label} is missing")
        return None
    try:
        return load_json(path)
    except json.JSONDecodeError as e:
        errors.append(f"{label}: invalid JSON ({e})")
        return None


def _load_result(run_dir, name, assumption_ids, errors, text, kind="agent"):
    label = f"results/{name}.json"
    if name != "extract" and not os.path.isfile(os.path.join(run_dir, "results", f"{name}.json")):
        errors.append(f"{label} is missing (write a FAILED result if the validator failed)")
        return None
    data = read_json_file(os.path.join(run_dir, "results", f"{name}.json"), label, errors)
    if data is None:
        return None
    errs = schema.validate(data, schema.load_schema("result"))
    if not errs:
        errs = structure.result_errors(data, name, assumption_ids) + text.result_errors(data, kind)
    errors.extend(f"{label}: {e}" for e in errs)
    return None if errs else data


def _save_result(run_dir, run, name, result):
    """Write a graded result and pin its hash so later edits are detected."""
    path = os.path.join(run_dir, "results", f"{name}.json")
    dump_json(path, result)
    with open(path, "rb") as f:
        run.setdefault("result_sha256", {})[name] = hashlib.sha256(f.read()).hexdigest()


def _grade_and_save(run_dir, run, name, result, manifest, ctx):
    for item in result["evidence"]:
        evidence.verify_evidence(item, ctx, kind=manifest["kind"])
    grading.grade_result(result, manifest)
    _save_result(run_dir, run, name, result)


def _require_pending(run, stage):
    state = run["stages"].get(str(stage))
    if state is None:
        raise StateError(f"stage {stage} has no selected validators")
    if state == "SKIPPED":
        raise StateError(f"stage {stage} was skipped (blocked by {', '.join(run['blocked_by'])})")
    if state == "COMPLETED":
        raise StateError(f"stage {stage} is already closed")
    open_before = sorted((k for k, st in run["stages"].items() if int(k) < stage and st == "PENDING"),
                         key=int)
    if open_before:
        raise StateError(f"close stage(s) {', '.join(open_before)} first")


def _require_all_closed(run):
    pending = sorted((k for k, st in run["stages"].items() if st == "PENDING"), key=int)
    if pending:
        raise StateError(f"stage(s) {', '.join(pending)} not closed yet")


def summarize(results):
    return {name: {"status": r["status"],
                   "findings": {sev: sum(1 for f in r["findings"] if f["severity"] == sev)
                                for sev in SEVERITY_KEYS}}
            for name, r in results.items()}


def cmd_init(design, repo, depth, plugin_root=registry.PLUGIN_ROOT, now=None, baseline=None):
    return 0, runinit.init_run(design, repo, depth, plugin_root=plugin_root, now=now, baseline=baseline)


def cmd_assumptions(run_dir):
    run = load_run(run_dir)
    _require_pending(run, 0)
    errors = []
    text = hygiene.RunText(run, read_design(run_dir))
    data = read_json_file(os.path.join(run_dir, "assumptions.json"), "assumptions.json", errors)
    ids = set()
    if data is not None:
        errs = schema.validate(data, schema.load_schema("assumptions"))
        if not errs:
            ids = {a["id"] for a in data["assumptions"]}
            errs = (structure.assumption_errors(data["assumptions"], read_design(run_dir))
                    + text.assumption_errors(data["assumptions"]))
        errors.extend(f"assumptions.json: {e}" for e in errs)
    result = _load_result(run_dir, "extract", ids, errors, text)
    if errors:
        return 1, {"ok": False, "errors": errors}
    _grade_and_save(run_dir, run, "extract", result, manifests(run)["extract"], build_context(run_dir, run))
    blockers = gate.close_stage(run, 0, {"extract": result})
    save_run(run_dir, run)
    return 0, {"ok": True, "assumptions": len(data["assumptions"]),
               "results": summarize({"extract": result}), "blocked_by": blockers,
               "stages": run["stages"]}


def cmd_results(run_dir, stage):
    run = load_run(run_dir)
    if stage < 1:
        raise StateError("stage 0 is closed with 'verify.py assumptions'")
    _require_pending(run, stage)
    assumptions = load_json(os.path.join(run_dir, "assumptions.json"))["assumptions"]
    ids = {a["id"] for a in assumptions}
    names = [v["name"] for v in run["validators"] if v["selected"] and v["stage"] == stage]
    errors, loaded = [], {}
    text = hygiene.RunText(run, read_design(run_dir))
    kinds = {v["name"]: v["kind"] for v in run["validators"]}
    for name in names:
        result = _load_result(run_dir, name, ids, errors, text, kinds[name])
        if result is not None:
            loaded[name] = result
    if errors:
        return 1, {"ok": False, "errors": errors}
    ctx = build_context(run_dir, run)
    by_name = manifests(run)
    for name, result in loaded.items():
        _grade_and_save(run_dir, run, name, result, by_name[name], ctx)
    blockers = gate.close_stage(run, stage, loaded)
    save_run(run_dir, run)
    return 0, {"ok": True, "stage": stage, "results": summarize(loaded), "blocked_by": blockers,
               "stages": run["stages"]}


def cmd_input(run_dir, name):
    """Write the input file for one selected validator (used by command validators)."""
    run = load_run(run_dir)
    if name == registry.RESERVED:
        raise StateError("extract takes no input file")
    m = manifests(run).get(name)
    if m is None or not m["selected"]:
        raise StateError(f"validator '{name}' is not selected in this run")
    if run["stages"].get("0") != "COMPLETED":
        raise StateError("close stage 0 with 'verify.py assumptions' first")
    assumptions = load_json(os.path.join(run_dir, "assumptions.json"))["assumptions"]
    if m["scope"] == "assumption":
        assumptions = [a for a in assumptions if a["kind"] in m["targets"]]
    abs_run = os.path.abspath(run_dir)
    data = {
        "run_dir": abs_run,
        "repo_root": run["repo_root"],
        "repo_commit": run["repo_commit"],
        "worktree_matches_baseline": run.get("worktree_matches_baseline"),
        "design_path": os.path.join(abs_run, "design.md"),
        "assumptions": assumptions,
        "context": {"docs": run["docs"], "priors": run["priors"],
                    "history": run.get("history", {"git": run["repo_commit"] is not None,
                                                   "pr_comments": False})},
        "id_prefix": name,
    }
    path = os.path.join(abs_run, "inputs", f"{name}.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    dump_json(path, data)
    return 0, {"ok": True, "input_path": path, "assumptions": len(assumptions)}


def owner_of(item_id):
    return item_id.rsplit(".", 1)[0]


def load_closed_results(run_dir, run):
    results = {}
    pins = run.get("result_sha256", {})
    for v in run["validators"]:
        if v["selected"] and run["stages"].get(str(v["stage"])) == "COMPLETED":
            path = os.path.join(run_dir, "results", f"{v['name']}.json")
            with open(path, "rb") as f:
                digest = hashlib.sha256(f.read()).hexdigest()
            if pins.get(v["name"]) != digest:
                raise StateError(f"results/{v['name']}.json changed after its stage closed; re-run validation")
            results[v["name"]] = load_json(path)
    return results


def cmd_audit(run_dir):
    run = load_run(run_dir)
    _require_all_closed(run)
    if run.get("audited"):
        raise StateError("audit already applied")
    results = load_closed_results(run_dir, run)
    findings = {f["id"]: (name, f) for name, r in results.items() for f in r["findings"]}
    evidence_by_id = {e["id"]: e for r in results.values() for e in r["evidence"]}
    errors = []
    data = read_json_file(os.path.join(run_dir, "audit.json"), "audit.json", errors)
    if data is not None:
        errs = schema.validate(data, schema.load_schema("audit"))
        if not errs:
            seen = set()
            for review in data["reviews"]:
                fid = review["finding_id"]
                if fid not in findings:
                    errs.append(f"unknown finding {fid}")
                elif fid in seen:
                    errs.append(f"{fid} reviewed twice")
                seen.add(fid)
                for ext in review.get("external_checks", []):
                    item = evidence_by_id.get(ext["evidence_id"])
                    if item is None or item["source"] != "external":
                        errs.append(f"{ext['evidence_id']} is not an external evidence item")
        errors.extend(f"audit.json: {e}" for e in errs)
    if errors:
        return 1, {"ok": False, "errors": errors}

    touched = set()
    for review in data["reviews"]:
        name, f = findings[review["finding_id"]]
        f["audit"] = review["verdict"]
        f["audit_reason"] = review["reason"]
        touched.add(name)
        for ext in review.get("external_checks", []):
            if not ext["confirmed"]:
                item = evidence_by_id[ext["evidence_id"]]
                item["tier"] = "T2"
                item["verify_error"] = "external source not confirmed by audit"
                touched.add(owner_of(item["id"]))
    by_name = manifests(run)
    for name in sorted(touched):
        grading.grade_result(results[name], by_name[name])
        _save_result(run_dir, run, name, results[name])
    for bid in run["blocked_by"]:
        if bid in findings and findings[bid][1]["severity"] != "BLOCKER":
            run["gate_disputed"] = True
    run["audited"] = True
    save_run(run_dir, run)
    return 0, {"ok": True, "reviewed": len(data["reviews"]), "gate_disputed": run["gate_disputed"]}


def cmd_report(run_dir):
    run = load_run(run_dir)
    _require_all_closed(run)
    results = load_closed_results(run_dir, run)
    assumptions = load_json(os.path.join(run_dir, "assumptions.json"))["assumptions"]
    errors = []
    draft = read_json_file(os.path.join(run_dir, "report-draft.json"), "report-draft.json", errors)
    if draft is not None:
        errs = schema.validate(draft, schema.load_schema("report-draft"))
        if not errs:
            errs = (report.draft_errors(draft, results)
                    + hygiene.RunText(run, read_design(run_dir)).draft_errors(draft))
        errors.extend(f"report-draft.json: {e}" for e in errs)
    if errors:
        return 1, {"ok": False, "errors": errors}
    rep = report.build_report(run, assumptions, results, draft)
    json_path = os.path.join(run_dir, "report.json")
    md_path = os.path.join(run_dir, "report.md")
    dump_json(json_path, rep)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(report.render_markdown(rep))
    runinit.release_marker(run["repo_root"], run_dir)
    counts = {sev: sum(1 for f in rep["findings"] if f["severity"] == sev) for sev in SEVERITY_KEYS}
    return 0, {"ok": True, "report_json": json_path, "report_md": md_path, "findings": counts,
               "coverage_gaps": report.gap_count(rep)}
