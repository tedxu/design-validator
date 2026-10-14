#!/usr/bin/env python3
"""Example command validator: do files named in factual assumptions exist at the baseline?

Reads the validator input on stdin and prints a result
on stdout. A path with directories must match a file exactly or as a suffix;
a bare file name must match exactly one file. Several matches, or an empty
file, leave the check INCONCLUSIVE.
"""
import hashlib
import json
import os
import re
import subprocess
import sys

EXT = r"(?:go|py|cpp|cc|c|h|hpp|rs|java|ts|js|proto|yaml|yml|json|toml|md|sql|sh)"
PATH = re.compile(rf"(?<![\w./-])((?:[\w.-]+/)*[\w-][\w.-]*\.{EXT})(?::\d+(?:-\d+)?)?(?![\w/])", re.ASCII)


def git(repo, *args):
    p = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)
    return p.returncode, p.stdout, p.stderr


def list_files(inp):
    repo, commit = inp["repo_root"], inp["repo_commit"]
    if commit:
        code, out, err = git(repo, "ls-tree", "-r", "-z", "--name-only", commit)
        if code != 0:
            first = (err.strip().splitlines() or ["no error output"])[0]
            return None, f"git ls-tree -r -z --name-only {commit} failed: {first}"
        return [f for f in out.split("\0") if f], None
    files = []
    for root, dirs, names in os.walk(repo):
        dirs[:] = sorted(d for d in dirs if d not in (".git", ".dv"))
        for n in sorted(names):
            files.append(os.path.relpath(os.path.join(root, n), repo).replace(os.sep, "/"))
    return files, None


def read(inp, path):
    if inp["repo_commit"]:
        code, out, _ = git(inp["repo_root"], "show", f"{inp['repo_commit']}:{path}")
        return out if code == 0 else ""
    with open(os.path.join(inp["repo_root"], path), encoding="utf-8", errors="replace") as f:
        return f.read()


def first_line(text):
    for i, line in enumerate(text.split("\n"), 1):
        if line.strip():
            return i, line.strip()
    return None


def main():
    inp = json.load(sys.stdin)
    name = inp["id_prefix"]
    files, failure = list_files(inp)
    if failure:
        json.dump({"validator": name, "status": "FAILED", "status_reason": failure,
                   "checks": [], "findings": [], "evidence": []}, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0
    fileset = set(files)
    by_base = {}
    for f in files:
        by_base.setdefault(f.rsplit("/", 1)[-1], []).append(f)
    where = (f"files at {inp['repo_commit'][:12]}" if inp["repo_commit"] else "files on disk")
    listing_cmd = (f"git ls-tree -r -z --name-only {inp['repo_commit']}" if inp["repo_commit"]
                   else "find . -type f -not -path './.git/*' -not -path './.dv/*'")
    listing_sha = hashlib.sha256("\n".join(files).encode("utf-8")).hexdigest()
    out = {"validator": name, "status": "COMPLETED", "status_reason": None,
           "checks": [], "findings": [], "evidence": []}
    counters = {"C": 0, "E": 0, "F": 0}

    def new_id(kind):
        counters[kind] += 1
        return f"{name}.{kind}{counters[kind]}"

    for a in inp["assumptions"]:
        names = []
        for m in PATH.finditer(a["anchor"]["quote"] + "\n" + a["statement"]):
            n = m.group(1)
            while n.startswith("./"):
                n = n[2:]
            if n not in names:
                names.append(n)
        for p in names:
            if p in fileset:
                matches = [p]
            elif "/" in p:
                matches = [f for f in files if f.endswith("/" + p)]
            else:
                matches = by_base.get(p, [])
            cid = new_id("C")
            check = {"id": cid, "assumption_ids": [a["id"]],
                     "method": f"Looked up {p} among the {len(files)} {where}.",
                     "search_scope": f"all {len(files)} {where}",
                     "verdict": "INCONCLUSIVE", "evidence_ids": []}
            if len(matches) == 1:
                try:
                    found = first_line(read(inp, matches[0]))
                except OSError as e:
                    found = None
                    check["method"] += f" {matches[0]} could not be read: {e}."
                    matches = None
                if matches is None:
                    pass
                elif found:
                    eid = new_id("E")
                    out["evidence"].append({
                        "id": eid, "source": "code",
                        "locator": {"path": matches[0], "line_start": found[0], "line_end": found[0]},
                        "excerpt": found[1], "relation": "supports"})
                    check["verdict"], check["evidence_ids"] = "PASS", [eid]
                else:
                    check["method"] += f" {matches[0]} is empty, so nothing can be cited."
            elif not matches:
                eid = new_id("E")
                out["evidence"].append({
                    "id": eid, "source": "sandbox",
                    "locator": {"command": listing_cmd, "output_sha256": listing_sha},
                    "excerpt": f"{p} is not among the {len(files)} files listed",
                    "relation": "refutes"})
                check["verdict"], check["evidence_ids"] = "ISSUE", [eid]
                out["findings"].append({
                    "id": new_id("F"), "category": "contradicted", "severity": "MAJOR",
                    "statement": f"Assumption {a['id']} names {p}, which is not among the {where}.",
                    "assumption_ids": [a["id"]], "check_ids": [cid], "evidence_ids": [eid]})
            else:
                check["method"] += f" Several files match: {', '.join(sorted(matches)[:5])}."
            out["checks"].append(check)
    json.dump(out, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
