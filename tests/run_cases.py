#!/usr/bin/env python3
"""Run fixture cases end to end in Claude Code and check each report.

usage: run_cases.py [--cases a,b] [--workdir DIR] [--jobs N] [--claude CMD]
                    [--timeout SECONDS]

Each case runs in <workdir>/<case>: fixture.sh, then
`<claude> -p --plugin-dir <plugin> --permission-mode bypassPermissions
--output-format json "/design-validate docs/design.md <args>"`, then
check_case. Writes <workdir>/summary.json and <workdir>/validation-runs.md.
"""
import argparse
import concurrent.futures
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.dirname(HERE)
CASES = os.path.join(HERE, "cases")
sys.path.insert(0, HERE)

import check_case  # noqa: E402


def case_names(selected):
    names = sorted(d for d in os.listdir(CASES)
                   if os.path.isfile(os.path.join(CASES, d, "expected.json")))
    if not selected:
        return names
    unknown = sorted(set(selected) - set(names))
    if unknown:
        raise SystemExit(f"unknown cases: {unknown}")
    return [n for n in names if n in selected]


def load_expected(name):
    with open(os.path.join(CASES, name, "expected.json"), encoding="utf-8") as f:
        return json.load(f)


def newest_run(repo):
    runs = os.path.join(repo, ".dv", "runs")
    ids = sorted(os.listdir(runs)) if os.path.isdir(runs) else []
    return os.path.join(runs, ids[-1]) if ids else None


def run_case(name, workdir, claude, timeout=3600):
    """Run one case; never raises. Any error becomes a failure string."""
    result = {"case": name, "run": None, "seconds": 0, "cost_usd": None, "exit": None,
              "failures": []}
    start = time.time()
    try:
        repo = os.path.join(workdir, name)
        shutil.rmtree(repo, ignore_errors=True)
        os.makedirs(repo)
        fx = subprocess.run(["bash", os.path.join(CASES, name, "fixture.sh")], cwd=repo,
                            capture_output=True, text=True)
        if fx.returncode != 0:
            result["failures"] = [f"fixture failed: exit {fx.returncode}: {fx.stderr.strip()[-300:]}"]
            return result
        expected = load_expected(name)
        prompt = f"/design-validate docs/design.md {expected.get('args', '')}".strip()
        start = time.time()
        try:
            p = subprocess.run([claude, "-p", "--plugin-dir", PLUGIN, "--permission-mode",
                                "bypassPermissions", "--output-format", "json", prompt],
                               cwd=repo, capture_output=True, text=True, timeout=timeout)
            out, err, result["exit"] = p.stdout, p.stderr, p.returncode
            timed_out = False
        except subprocess.TimeoutExpired as e:
            out, err, timed_out = (e.stdout or ""), (e.stderr or ""), True
            out = out.decode("utf-8", "replace") if isinstance(out, bytes) else out
            err = err.decode("utf-8", "replace") if isinstance(err, bytes) else err
        with open(os.path.join(workdir, f"{name}.log"), "w", encoding="utf-8") as f:
            f.write(out + err)
        try:
            data = json.loads(out)
            if isinstance(data, dict):
                result["cost_usd"] = data.get("total_cost_usd")
        except ValueError:
            pass
        run = newest_run(repo)
        result["run"] = run and os.path.basename(run)
        report = os.path.join(run, "report.json") if run else None
        if timed_out:
            result["failures"] = [f"claude timed out after {timeout}s"]
        elif not report or not os.path.isfile(report):
            result["failures"] = ["no report.json produced"]
        else:
            with open(report, encoding="utf-8") as f:
                result["failures"] = check_case.check(expected, json.load(f))
    except Exception as e:  # noqa: BLE001 - one case must not abort the batch
        result["failures"] = [f"runner error: {type(e).__name__}: {e}"]
    finally:
        result["seconds"] = round(time.time() - start)
    return result


def render_runs(results, workdir):
    out = ["# Validation runs", "",
           "| # | case | run | result | seconds | cost (USD) |", "|---|---|---|---|---|---|"]
    for i, r in enumerate(results, 1):
        verdict = "PASS" if not r["failures"] else "FAIL: " + "; ".join(r["failures"])
        out.append(f"| {i} | {r['case']} | `{r['run']}` | {verdict} | {r['seconds']} | {r['cost_usd']} |")
    out.append("")
    for i, r in enumerate(results, 1):
        repo = os.path.join(workdir, r["case"])
        out += [f"## {i}. {r['case']} · `{r['run']}`", "", "### Design", "", "```markdown"]
        try:
            with open(os.path.join(repo, "docs", "design.md"), encoding="utf-8") as f:
                out += [f.read().rstrip("\n"), "```", ""]
        except OSError:
            out += ["(no design)", "```", ""]
        md = os.path.join(repo, ".dv", "runs", r["run"] or "-", "report.md")
        if not os.path.isfile(md):
            out += ["(no report)", ""]
            continue
        with open(md, encoding="utf-8") as f:
            lines = f.read().rstrip("\n").split("\n")[1:]
        for line in lines:
            m = re.match(r"^(#{1,4}) ", line)
            out.append("#" * (len(m.group(1)) + 1) + line[len(m.group(1)):] if m else line)
        out.append("")
    return "\n".join(out)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--cases", default="")
    p.add_argument("--workdir", default=None)
    p.add_argument("--jobs", type=int, default=3)
    p.add_argument("--claude", default="claude")
    p.add_argument("--timeout", type=int, default=3600, help="seconds per case")
    args = p.parse_args(argv)
    names = case_names([c for c in args.cases.split(",") if c])
    workdir = os.path.realpath(args.workdir) if args.workdir else tempfile.mkdtemp(prefix="dv-cases-")
    if os.path.commonpath([workdir, PLUGIN]) == PLUGIN:
        raise SystemExit(f"--workdir {workdir} is inside the plugin repository {PLUGIN}; "
                         "choose a directory outside it")
    os.makedirs(workdir, exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
        results = list(pool.map(lambda n: run_case(n, workdir, args.claude, args.timeout), names))
    with open(os.path.join(workdir, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    with open(os.path.join(workdir, "validation-runs.md"), "w", encoding="utf-8") as f:
        f.write(render_runs(results, workdir) + "\n")
    for r in results:
        status = "PASS" if not r["failures"] else "FAIL"
        print(f"{status} {r['case']} {r['seconds']}s ${r['cost_usd']} {'; '.join(r['failures'])}")
    print(f"workdir: {workdir}")
    return 0 if all(not r["failures"] for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
