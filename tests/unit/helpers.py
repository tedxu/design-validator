"""Filesystem and git fixtures shared by unit tests."""
import datetime
import json
import os
import subprocess

OMIT = object()
GIT = ["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
       "-c", "commit.gpgsign=false"]
BASE_FIELDS = {"version": 1, "kind": "agent", "scope": "design", "targets": [],
               "truth_tiers": ["T1"], "can_block": False, "cost": "low", "entry": "prompt.md"}


def _y(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if v is None:
        return "null"
    if isinstance(v, list):
        return "[" + ", ".join(_y(x) for x in v) + "]"
    if isinstance(v, dict):
        return "{" + ", ".join(f"{k}: {_y(x)}" for k, x in v.items()) + "}"
    return str(v)


def to_yaml(d):
    return "".join(f"{k}: {_y(v)}\n" for k, v in d.items())


def write_files(root, files):
    for rel, text in files.items():
        path = os.path.join(root, rel)
        os.makedirs(os.path.dirname(path) or root, exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(text)


def write_validator(vdir, dirname, stage, **fields):
    merged = {"name": dirname, "stage": stage, **BASE_FIELDS, **fields}
    merged = {k: v for k, v in merged.items() if v is not OMIT}
    write_files(os.path.join(vdir, dirname), {
        "validator.yaml": to_yaml(merged),
        "prompt.md": f"prompt for {dirname}\n",
    })


def make_plugin(tmp, validators=None, priors=None):
    root = os.path.join(tmp, "plugin")
    vdir = os.path.join(root, "validators")
    write_validator(vdir, "extract", 0, can_block=True, max_severity="BLOCKER",
                    blocker_evidence=["ANY"], truth_tiers=["T1", "T2", "T3"])
    for name, (stage, fields) in (validators or {}).items():
        write_validator(vdir, name, stage, **fields)
    os.makedirs(os.path.join(root, "priors"), exist_ok=True)
    write_files(os.path.join(root, "priors"), priors or {})
    return root


def git(repo, *args):
    return subprocess.run([*GIT, *args], cwd=repo, check=True, capture_output=True,
                          text=True).stdout.strip()


def make_repo(tmp, files, name="repo"):
    repo = os.path.join(tmp, name)
    os.makedirs(repo)
    git(repo, "init", "-q", "-b", "main")
    write_files(repo, files)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "init")
    return repo, git(repo, "rev-parse", "HEAD")


DESIGN_TEXT = "# Design\n\nSegmentCache evicts entries after ttl.\nWe rely on it.\n"
REPO_FILES = {"store/cache.py": "class SegmentCache:\n    def get(self, key):\n        return self._data.get(key)\n"}
STAGE_VALIDATORS = {
    "alpha": (1, {"scope": "assumption", "targets": ["current-fact"], "can_block": True,
                  "max_severity": "BLOCKER", "truth_tiers": ["T1"]}),
    "beta": (2, {"scope": "design", "truth_tiers": ["T1", "T3"]}),
    "gamma": (2, {"cost": "high"}),
}
PRIOR_TEXT = "# Failure modes\n\n## Response lost\n\nRetries may duplicate side effects.\n"


class RunFixture:
    def __init__(self, tmp, validators=None, repo_files=None, design=None, depth="standard"):
        from dvlib import commands
        self.plugin = make_plugin(tmp, STAGE_VALIDATORS if validators is None else validators,
                                  priors={"failure.md": PRIOR_TEXT})
        files = dict(REPO_FILES if repo_files is None else repo_files)
        files["docs/design.md"] = DESIGN_TEXT if design is None else design
        self.repo, self.commit = make_repo(tmp, files)
        code, out = commands.cmd_init("docs/design.md", self.repo, depth, plugin_root=self.plugin,
                                      now=datetime.datetime(2026, 10, 12, 12, 0, 0))
        assert code == 0, out
        self.run_dir = out["run_dir"]
        self.init_output = out

    def write(self, rel, data):
        path = os.path.join(self.run_dir, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)

    def read(self, rel):
        with open(os.path.join(self.run_dir, rel), encoding="utf-8") as f:
            return json.load(f)

    def run(self):
        return self.read("run.json")
