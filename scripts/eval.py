#!/usr/bin/env python3
"""Deterministic parts of the evaluation flow.

Exit codes: 0 ok; 1 input files have fixable errors; 2 cannot proceed.
stdout is always one JSON object.
"""
import argparse
import hashlib
import json
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dvlib import evalprep, evalrun, evalscore, registry, schema, sources  # noqa: E402


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError(message)


def _parser():
    p = _Parser(prog="eval.py", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True, parser_class=_Parser)
    subs = {}
    for name in ("prepare", "check-truth", "run", "check-matches", "score"):
        subs[name] = sub.add_parser(name)
        subs[name].add_argument("--repo", default=".")
        subs[name].add_argument("--eval-dir", default=None)
    subs["prepare"].add_argument("--limit", type=int, default=5)
    subs["prepare"].add_argument("--designs", default="")
    subs["run"].add_argument("--depth", default="standard", choices=sorted(registry.DEPTH_COSTS))
    subs["run"].add_argument("--jobs", type=int, default=2)
    subs["run"].add_argument("--timeout", type=int, default=3600)
    subs["run"].add_argument("--claude", default="claude")
    for name in ("check-truth", "run", "check-matches", "score"):
        subs[name].add_argument("--cases", default="", help="comma list of case ids; empty = all")
    return p


def default_eval_dir(repo):
    """<cache>/design-validator/eval/<repo name>-<hash of its real path>.

    Outside the repository on purpose: Claude Code loads CLAUDE.md from a
    snapshot's parent directories, which would leak the repository's
    current instructions into a historical run.
    """
    real = os.path.realpath(repo)
    cache = os.environ.get("XDG_CACHE_HOME") or os.path.join(os.path.expanduser("~"), ".cache")
    digest = hashlib.sha256(real.encode("utf-8")).hexdigest()[:8]
    return os.path.join(cache, "design-validator", "eval",
                        f"{os.path.basename(real)}-{digest}")


def _list(text):
    return [x.strip() for x in text.split(",") if x.strip()]


def cmd_prepare(repo, eval_dir, limit, designs):
    if not os.path.exists(os.path.join(repo, ".git")):
        raise evalprep.EvalError("eval needs a git repository")
    globs = registry.load_config(repo)["design_globs"]
    return 0, evalprep.prepare(repo, eval_dir, globs, limit, designs or None)


def _load(path, check=None):
    """Load a per-case JSON file; ValueError names the file on any problem."""
    name = os.path.basename(path)
    try:
        data = evalscore.load_json(path)
    except (OSError, ValueError) as e:
        raise ValueError(f"{name}: cannot read: {e}") from e
    problem = check(data) if check else None
    if problem:
        raise ValueError(f"{name}: {problem}")
    return data


def _check_case(d):
    ok = isinstance(d, dict) and all(isinstance(d.get(k), list) for k in ("revisions", "fixes"))
    return None if ok else "expected an object with 'revisions' and 'fixes' lists"


def _check_report(d):
    ok = (isinstance(d, dict) and isinstance(d.get("findings"), list)
          and all(isinstance(f, dict) and "id" in f for f in d["findings"]))
    return None if ok else "expected an object with a 'findings' list of objects with ids"


def _check_truth(d):
    errs = schema.validate(d, schema.load_schema("truth"))
    return "; ".join(errs) if errs else None


def cmd_check_truth(eval_dir, only=None):
    valid, missing, errors = [], [], {}
    for case_dir in evalrun.case_dirs(eval_dir, only):
        cid = os.path.basename(case_dir)
        path = os.path.join(case_dir, "truth.json")
        if not os.path.isfile(path):
            missing.append({"case_id": cid, "case_dir": case_dir})
            continue
        try:
            case = _load(os.path.join(case_dir, "case.json"), _check_case)
            truth = _load(path)
            errs = evalscore.truth_errors(truth, case)
        except ValueError as e:
            errs = [str(e)]
        if errs:
            errors[cid] = errs
        else:
            valid.append(cid)
    return (1 if errors else 0), {"ok": not errors, "valid": valid, "missing": missing,
                                  "errors": errors}


def cmd_check_matches(eval_dir, only=None):
    valid, missing, no_report, errors = [], [], [], {}
    for case_dir in evalrun.case_dirs(eval_dir, only):
        cid = os.path.basename(case_dir)
        rpath = evalrun.report_path(case_dir, evalrun.load_result(case_dir))
        if not rpath:
            no_report.append(cid)
            continue
        path = os.path.join(case_dir, "matches.json")
        if not os.path.isfile(path):
            missing.append({"case_id": cid, "case_dir": case_dir, "report": rpath})
            continue
        try:
            matches = _load(path)
            rep = _load(rpath, _check_report)
            truth = _load(os.path.join(case_dir, "truth.json"), _check_truth)
            errs = evalscore.match_errors(matches, rep, truth)
        except ValueError as e:
            errs = [str(e)]
        if errs:
            errors[cid] = errs
        else:
            valid.append(cid)
    return (1 if errors else 0), {"ok": not errors, "valid": valid, "missing": missing,
                                  "no_report": no_report, "errors": errors}


def cmd_score(eval_dir, only=None):
    out = evalscore.score(eval_dir, only)
    json_path, md_path = evalscore.write_report(eval_dir, out)
    return 0, {"ok": True, "report_json": json_path, "report_md": md_path, "cases": out["cases"],
               "excluded": out["excluded"], "recall": out["recall"]["all"],
               "precision": out["precision"]["all"]}


def main(argv=None):
    try:
        args = _parser().parse_args(argv)
        repo = os.path.abspath(args.repo)
        eval_dir = os.path.abspath(args.eval_dir or default_eval_dir(repo))
        only = _list(getattr(args, "cases", "")) or None
        if args.cmd == "prepare":
            code, out = cmd_prepare(repo, eval_dir, args.limit, _list(args.designs))
        elif args.cmd == "check-truth":
            code, out = cmd_check_truth(eval_dir, only)
        elif args.cmd == "run":
            code, out = 0, evalrun.run_all(eval_dir, registry.PLUGIN_ROOT, args.claude, args.depth,
                                           args.jobs, args.timeout, only)
        elif args.cmd == "check-matches":
            code, out = cmd_check_matches(eval_dir, only)
        else:
            code, out = cmd_score(eval_dir, only)
    except (evalprep.EvalError, sources.SourceError, registry.RegistryError) as e:
        code, out = 2, {"ok": False, "errors": [str(e)]}
    except ValueError as e:
        code, out = 2, {"ok": False, "errors": [f"usage: {e}"]}
    except Exception as e:  # noqa: BLE001 - report every failure as JSON
        traceback.print_exc(file=sys.stderr)
        code, out = 2, {"ok": False, "errors": [f"internal error: {e!r}"]}
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return code


if __name__ == "__main__":
    sys.exit(main())
