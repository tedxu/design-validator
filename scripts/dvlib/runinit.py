"""Create a run directory and its run.json."""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import time

from . import registry, sources


RUNS = os.path.join(".dv", "runs")
MARKER = os.path.join(RUNS, "active.json")


class InitError(Exception):
    pass


def write_marker(repo_root, run_dir, allowed_roots):
    """Mark a run as active so hooks/scope_guard.py confines tool calls to `allowed_roots`."""
    with open(os.path.join(repo_root, MARKER), "w", encoding="utf-8") as f:
        json.dump({"run_dir": run_dir, "repo_root": repo_root, "allowed_roots": allowed_roots,
                   "started_at": time.time()}, f, indent=2)
        f.write("\n")


def release_marker(repo_root, run_dir):
    path = os.path.join(repo_root, MARKER)
    try:
        with open(path, encoding="utf-8") as f:
            owner = json.load(f).get("run_dir")
    except (OSError, ValueError):
        return
    if owner and os.path.realpath(owner) == os.path.realpath(run_dir):
        os.remove(path)


def resolve_baseline(repo_root, baseline):
    """(commit, worktree_matches) for `baseline` (default HEAD)."""
    try:
        head = sources.run_git(repo_root, "rev-parse", "--verify", "HEAD").strip()
    except sources.SourceError as e:
        raise InitError(f"repository has no commits: {e}") from e
    if baseline is None:
        return head, True
    if baseline.startswith("-"):
        raise InitError(f"baseline is not a commit in this repository: {baseline}")
    if not sources.git_ok(repo_root, "rev-parse", "--verify", "--quiet", f"{baseline}^{{commit}}"):
        raise InitError(f"baseline is not a commit in this repository: {baseline}")
    commit = sources.run_git(repo_root, "rev-parse", "--verify", f"{baseline}^{{commit}}").strip()
    return commit, commit == head


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def worktree_paths(repo_root):
    """Files absent at HEAD that exist at init: untracked or newly added."""
    untracked = sources.run_git(repo_root, "ls-files", "--others", "--exclude-standard").splitlines()
    added = sources.run_git(repo_root, "diff", "HEAD", "--name-only", "--diff-filter=A").splitlines()
    return sorted({p for p in untracked + added if p and not p.startswith(".dv/")})


def worktree_diff_sha256(repo_root):
    diff = sources.run_git(repo_root, "diff", "HEAD", "--binary")
    untracked = [p for p in sources.run_git(repo_root, "ls-files", "--others",
                                            "--exclude-standard").splitlines()
                 if not p.startswith(".dv/")]
    if not diff and not untracked:
        return None
    return _sha((diff + "\0" + "\n".join(untracked)).encode("utf-8"))


def init_run(design, repo, depth, plugin_root=registry.PLUGIN_ROOT, now=None, baseline=None):
    repo_root = os.path.abspath(repo)
    design_abs = design if os.path.isabs(design) else os.path.join(repo_root, design)
    if not os.path.isfile(design_abs):
        raise InitError(f"design file not found: {design}")
    with open(design_abs, "rb") as f:
        data = f.read()
    try:
        data.decode("utf-8")
    except UnicodeDecodeError as e:
        raise InitError(f"design file is not UTF-8: {design}") from e

    config = registry.load_config(repo_root)
    reg = registry.load_registry(repo_root, config, plugin_root=plugin_root)
    selected, skipped = registry.select(reg, depth)

    if os.path.exists(os.path.join(repo_root, ".git")):
        commit, matches = resolve_baseline(repo_root, baseline)
        mode = "normal"
        if matches:
            diff_sha, wt_paths = worktree_diff_sha256(repo_root), worktree_paths(repo_root)
        else:
            # The worktree is another revision: nothing on disk stands for the baseline.
            diff_sha, wt_paths = None, []
    elif baseline is not None:
        raise InitError("--baseline needs a git repository")
    else:
        commit, diff_sha, mode, wt_paths, matches = None, None, "eval", None, None

    design_sha = _sha(data)
    stamp = (now or datetime.datetime.now()).strftime("%Y%m%d-%H%M%S")
    run_id = f"{stamp}-{design_sha[:6]}"
    run_dir = os.path.join(repo_root, RUNS, run_id)
    if os.path.exists(run_dir):
        raise InitError(f"run directory already exists: {run_dir}")
    os.makedirs(os.path.join(run_dir, "results"))
    with open(os.path.join(run_dir, "design.md"), "wb") as f:
        f.write(data)

    validators = []
    for name, m in sorted(reg.items(), key=lambda kv: (kv[1]["stage"], kv[0])):
        entry = dict(m)
        entry["entry_path"] = os.path.join(m["dir"], m["entry"])
        entry["entry_sha256"] = registry.entry_sha256(m)
        entry["selected"] = name in selected
        entry["not_selected_reason"] = skipped.get(name)
        validators.append(entry)

    priors = [os.path.join(repo_root, p) for p in config["priors"]]
    default_project = os.path.join(repo_root, ".dv", "priors")
    if os.path.isdir(default_project) and default_project not in priors:
        priors.append(default_project)
    priors.append(os.path.join(plugin_root, "priors"))

    run = {
        "schema_version": "0.1",
        "run_id": run_id,
        "repo_root": repo_root,
        "design_path": os.path.relpath(design_abs, repo_root),
        "design_sha256": design_sha,
        "repo_commit": commit,
        "baseline_ref": (baseline or "HEAD") if commit else None,
        "worktree_matches_baseline": matches,
        "worktree_diff_sha256": diff_sha,
        "worktree_paths": wt_paths,
        "depth": depth,
        "mode": mode,
        "plugin_root": os.path.abspath(plugin_root),
        "docs": config["docs"],
        "priors": priors,
        "history": {"git": commit is not None, "pr_comments": config["pr_comments"]},
        "validators": validators,
        "stages": {str(s): "PENDING" for s in sorted({v["stage"] for v in validators if v["selected"]})},
        "blocked_by": [],
        "gate_disputed": False,
        "audited": False,
        "result_sha256": {},
    }
    with open(os.path.join(run_dir, "run.json"), "w", encoding="utf-8") as f:
        json.dump(run, f, indent=2, ensure_ascii=False)
        f.write("\n")
    write_marker(repo_root, run_dir, [repo_root, run["plugin_root"], *priors])
    dispatch = [{k: v[k] for k in ("name", "stage", "kind", "scope", "targets", "entry_path")}
                for v in validators if v["selected"]]
    return {"ok": True, "run_dir": run_dir, "run_id": run_id, "mode": mode,
            "repo_commit": commit, "worktree_matches_baseline": matches,
            "dispatch": dispatch, "not_selected": skipped}
