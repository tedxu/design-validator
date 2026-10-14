"""Find historical designs and prepare leak-free evaluation cases."""
from __future__ import annotations

import fnmatch
import json
import os
import re
import shutil
import subprocess
import tarfile

from . import sources

FIX_LIMIT = 30
PATCH_LIMIT = 200 * 1024  # bytes per evolution patch file
# Paths that are never code a design is about: dependency manifests and
# lockfiles, CI/tooling directories, and generated sources. A pattern ending
# in "/" names a directory anywhere in the path; any other pattern is matched
# against the file name. These do not count as code for the baseline kind and
# are never watched for fixes.
NOISE = ("go.mod", "go.sum", "package.json", "package-lock.json", "yarn.lock",
         "pnpm-lock.yaml", "Cargo.toml", "Cargo.lock", "poetry.lock", "Pipfile.lock",
         "requirements*.txt", "Gemfile.lock", "*.lock",
         ".github/", ".gitlab-ci.yml", ".circleci/",
         "*mock_*", "*_mock.*", "*.pb.*", "*_pb2.*", "*generated*")
EXCLUDED = (".dv/runs", ".dv/eval", ".dv/active.json")
_TICK = re.compile(r"`([^`\s]+)`")
_FIX = re.compile(r"fix(?:\(|:|\s)", re.I)


class EvalError(Exception):
    pass


def glob_regex(pattern):
    """Translate a design glob to a regex: '**' spans directories, '*' and '?' do not."""
    out, i = [], 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return re.compile("".join(out) + r"\Z")


def matches_any(path, globs):
    return any(glob_regex(g).match(path) for g in globs)


def _git(repo, *args):
    return sources.run_git(repo, "-c", "core.quotePath=false", *args)


def first_adds(repo, globs):
    """{design path: (first commit, path in that commit)}, for designs tracked at HEAD.

    Renames are followed: the first commit is the one that added the file
    under its earliest name.
    """
    tracked = set(_git(repo, "ls-files").splitlines())
    out = _git(repo, "log", "--reverse", "-M", "--diff-filter=AR", "--format=@@%H",
               "--name-status", "HEAD")
    origin, commit = {}, None
    for line in out.splitlines():
        if line.startswith("@@"):
            commit = line[2:]
            continue
        fields = line.split("\t")
        if fields[0] == "A" and len(fields) == 2:
            origin.setdefault(fields[1], (commit, fields[1]))
        elif fields[0].startswith("R") and len(fields) == 3:
            origin[fields[2]] = origin.get(fields[1], (commit, fields[1]))
    return {p: v for p, v in origin.items() if p in tracked and matches_any(p, globs)}


def _follow(repo, first, path):
    """(revisions of path after first, every name it had), following renames.

    Pure renames are not revisions.
    """
    # --follow ignores renames when combined with --reverse; reverse here instead.
    out = _git(repo, "log", "--follow", "--format=@@%H", "--name-status",
               f"{first}..HEAD", "--", path)
    revisions, names, commit = [], {path}, None
    for line in out.splitlines():
        if line.startswith("@@"):
            commit = line[2:]
        elif line:
            fields = line.split("\t")
            names.update(fields[1:])
            if fields[0] != "R100":
                revisions.append(commit)
    return revisions[::-1], sorted(names)


def is_noise(path):
    parts = path.split("/")
    for pattern in NOISE:
        if pattern.endswith("/"):
            if pattern[:-1] in parts[:-1]:
                return True
        elif fnmatch.fnmatchcase(parts[-1], pattern):
            return True
    return False


def _changed(repo, commit):
    """Text files a commit changed, without binary or noise paths."""
    out = _git(repo, "show", "--no-renames", "--format=", "--numstat", commit)
    paths = []
    for line in out.splitlines():
        added, _, rest = line.partition("\t")
        _, _, path = rest.partition("\t")
        if path and added != "-" and not is_noise(path):
            paths.append(path)
    return paths


def _cited(repo, commit, path, baseline):
    """Backticked paths in the first version that exist at the baseline."""
    tokens = []
    for token in _TICK.findall(_git(repo, "show", f"{commit}:{path}")):
        p = token.split(":")[0].rstrip(".,")
        if p and not p.startswith("-") and not is_noise(p) and p not in tokens:
            tokens.append(p)
    if not tokens:
        return set()
    # One batch query instead of one git process per token.
    proc = subprocess.run(["git", "cat-file", "--batch-check"], cwd=repo, capture_output=True,
                          input="".join(f"{baseline}:{p}\n" for p in tokens),
                          encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        raise sources.SourceError(proc.stderr.strip() or "git cat-file --batch-check failed")
    found = set()
    for p, line in zip(tokens, proc.stdout.splitlines()):
        fields = line.split(" ")  # "<sha> <type> <size>", or "<name> missing|ambiguous"
        if len(fields) == 3 and fields[1] in ("blob", "tree", "commit"):
            found.add(p)
    return found


def candidate(repo, path, first, globs, first_path=None):
    """Describe one design as an evaluation candidate, or return (None, reason)."""
    first_path = first_path or path
    code = [p for p in _changed(repo, first)
            if p != first_path and not p.endswith(".md") and not matches_any(p, globs)]
    if code:
        baseline, kind = first, "as-built"
    elif sources.git_ok(repo, "rev-parse", "--verify", "-q", f"{first}^"):
        baseline, kind = _git(repo, "rev-parse", f"{first}^").strip(), "pre-implementation"
    else:
        return None, "the first version is in the root commit, so there is no earlier baseline"
    revisions, _ = _follow(repo, first, path)
    watched = sorted(set(code) | _cited(repo, first, first_path, baseline))
    fixes = []
    if watched:
        out = _git(repo, "log", "--reverse", "--format=%H%x00%s", f"{first}..HEAD", "--", *watched)
        for line in out.splitlines():
            sha, _, subject = line.partition("\x00")
            if _FIX.match(subject):
                fixes.append(sha)
    fixes = fixes[:FIX_LIMIT]
    return {
        "design_path": path,
        "first_path": first_path,
        "first_commit": first,
        "first_date": int(_git(repo, "show", "-s", "--format=%ct", first).strip()),
        "baseline": baseline,
        "baseline_kind": kind,
        "code_paths": code,
        "watched_paths": watched,
        "revisions": revisions,
        "fixes": fixes,
        "richness": len(revisions) + len(fixes),
    }, None


def case_id(path, first):
    stem = re.sub(r"[^A-Za-z0-9]+", "-", os.path.splitext(path)[0]).strip("-").lower()
    return f"{stem[-60:].strip('-')}-{first[:7]}"


def discover(repo, globs, limit=5, designs=None):
    """Rank evaluable designs by how much they evolved; return (selected, skipped)."""
    if not globs:
        raise EvalError("eval.design_globs is empty in .dv/config.yaml")
    firsts = first_adds(repo, globs)
    if designs:
        missing = [d for d in designs if d not in firsts]
        if missing:
            raise EvalError(f"not a tracked design matching eval.design_globs: {missing}")
    selected, skipped = [], []
    for path in list(designs) if designs else sorted(firsts):
        first, first_path = firsts[path]
        cand, reason = candidate(repo, path, first, globs, first_path)
        if cand is not None and cand["richness"] == 0:
            cand, reason = None, "no revisions or fix commits after the first version"
        if cand is None:
            skipped.append({"design_path": path, "reason": reason})
            continue
        cand["case_id"] = case_id(path, cand["first_commit"])
        selected.append(cand)
    if not designs:
        selected.sort(key=lambda c: (-c["richness"], -c["first_date"], c["design_path"]))
        selected = selected[:limit]
    return selected, skipped


def _safe_filter(member, dest):
    """Apply tarfile's 'data' filter; skip members it rejects as unsafe."""
    try:
        return tarfile.data_filter(member, dest)
    except tarfile.FilterError:
        return None


def _escapes(member, dest):
    """Fallback for Pythons without tarfile.data_filter: does the member leave dest?"""
    root = os.path.realpath(dest)

    def outside(path):
        real = os.path.realpath(path)
        return real != root and not real.startswith(root + os.sep)

    if os.path.isabs(member.name) or outside(os.path.join(dest, member.name)):
        return True
    if member.issym():
        if os.path.isabs(member.linkname):
            return True
        return outside(os.path.join(dest, os.path.dirname(member.name), member.linkname))
    if member.islnk():
        return os.path.isabs(member.linkname) or outside(os.path.join(dest, member.linkname))
    return False


def export_snapshot(repo, commit, dest):
    """Extract `git archive <commit>` into dest, leaving out run artifacts.

    Members that escape dest (absolute or out-of-tree links) are skipped.
    """
    os.makedirs(dest)
    proc = subprocess.Popen(["git", "archive", "--format=tar", commit], cwd=repo,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    tar_error = None
    try:
        with tarfile.open(fileobj=proc.stdout, mode="r|") as tar:
            for member in tar:
                name = member.name.rstrip("/")
                if any(name == e or name.startswith(e + "/") for e in EXCLUDED):
                    continue
                if hasattr(tarfile, "data_filter"):
                    tar.extract(member, dest, filter=_safe_filter)
                elif not _escapes(member, dest):
                    tar.extract(member, dest)
        proc.stdout.read()  # drain tar padding so git is not killed by SIGPIPE
    except tarfile.TarError as e:
        tar_error = e
    finally:
        proc.stdout.close()
        err = proc.stderr.read().decode("utf-8", "replace")
        proc.stderr.close()
        proc.wait()
    if proc.returncode != 0:
        raise EvalError(f"git archive {commit} failed: {err.strip()}")
    if tar_error is not None:
        raise EvalError(f"git archive {commit} produced an unreadable archive: {tar_error}")


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def cap(text, limit):
    """Truncate text to `limit` UTF-8 bytes, ending with a truncation note."""
    data = text.encode("utf-8")
    if len(data) <= limit:
        return text
    head = data[:limit].decode("utf-8", "ignore")
    return f"{head}\n[truncated: {len(data) - len(head.encode('utf-8'))} more bytes]\n"


def _shows(repo, commits, *paths):
    return cap("\n".join(_git(repo, "show", "--stat", "--patch",
                          "--format=commit %H%nDate: %cI%nSubject: %s%n", sha, "--", *paths)
                          for sha in commits), PATCH_LIMIT)


def prepare_case(repo, eval_dir, cand):
    """Create <eval_dir>/<case_id>/ once; return (case_dir, created)."""
    case_dir = os.path.join(eval_dir, cand["case_id"])
    if os.path.isfile(os.path.join(case_dir, "case.json")):
        return case_dir, False
    tmp = case_dir + ".partial"
    shutil.rmtree(tmp, ignore_errors=True)
    first_path = cand.get("first_path", cand["design_path"])
    design_v1 = _git(repo, "show", f"{cand['first_commit']}:{first_path}")
    _write(os.path.join(tmp, "evolution", "design-v1.md"), design_v1)
    _write(os.path.join(tmp, "evolution", "revisions.patch"),
           _shows(repo, cand["revisions"],
                  *_follow(repo, cand["first_commit"], cand["design_path"])[1]))
    _write(os.path.join(tmp, "evolution", "fixes.patch"), _shows(repo, cand["fixes"], *cand["watched_paths"]))
    snapshot = os.path.join(tmp, "snapshot")
    export_snapshot(repo, cand["baseline"], snapshot)
    if cand["baseline_kind"] == "pre-implementation":
        _write(os.path.join(snapshot, first_path), design_v1)
    _write(os.path.join(tmp, "case.json"),
           json.dumps(dict(cand, snapshot="snapshot", evolution="evolution"), indent=2) + "\n")
    shutil.rmtree(case_dir, ignore_errors=True)
    os.rename(tmp, case_dir)
    return case_dir, True


def prepare(repo, eval_dir, globs, limit=5, designs=None):
    selected, skipped = discover(repo, globs, limit, designs)
    os.makedirs(eval_dir, exist_ok=True)
    ignore = os.path.join(eval_dir, ".gitignore")
    if not os.path.exists(ignore):
        _write(ignore, "*\n")  # never commit evaluation artifacts, wherever they live
    cases = []
    for cand in selected:
        case_dir, created = prepare_case(repo, eval_dir, cand)
        cases.append({"case_id": cand["case_id"], "design_path": cand["design_path"],
                      "baseline_kind": cand["baseline_kind"], "richness": cand["richness"],
                      "case_dir": case_dir, "created": created})
    return {"ok": True, "eval_dir": eval_dir, "cases": cases, "skipped": skipped}
