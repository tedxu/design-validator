#!/usr/bin/env python3
"""Compare a run's report.json with a fixture case's expected.json."""
import json
import os
import sys

SEV = {"MINOR": 1, "MAJOR": 2, "BLOCKER": 3}


def _matches(finding, want):
    if "validator" in want and want["validator"] not in finding["validators"]:
        return False
    cats = want.get("category")
    if cats is not None:
        cats = [cats] if isinstance(cats, str) else cats
        if finding["category"] not in cats:
            return False
    if "min_severity" in want and SEV[finding["severity"]] < SEV[want["min_severity"]]:
        return False
    return True


def check(expected, report):
    failures = []
    for want in expected.get("must_find", []):
        if not any(_matches(f, want) for f in report["findings"]):
            failures.append(f"missing finding matching {want}")
    for want in expected.get("must_not_find", []):
        hits = [f["id"] for f in report["findings"] if _matches(f, want)]
        if hits:
            failures.append(f"unexpected findings {hits} matching {want}")
    statuses = {v["name"]: v["status"] for v in report["coverage"]["validators"]}
    for name, status in expected.get("coverage", {}).items():
        if statuses.get(name) != status:
            failures.append(f"validator {name}: expected {status}, got {statuses.get(name)}")
    return failures


def main(argv):
    if len(argv) != 3:
        print("usage: check_case.py <case-dir> <run-dir>")
        return 2
    with open(os.path.join(argv[1], "expected.json"), encoding="utf-8") as f:
        expected = json.load(f)
    with open(os.path.join(argv[2], "report.json"), encoding="utf-8") as f:
        report = json.load(f)
    failures = check(expected, report)
    for failure in failures:
        print("FAIL", failure)
    print("PASS" if not failures else f"{len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
