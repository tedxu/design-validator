"""Read repository files at the run baseline and match quoted excerpts."""
from __future__ import annotations

import hashlib
import os
import posixpath
import subprocess


class SourceError(Exception):
    pass


def normalize(text):
    return " ".join(text.split())


def sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def run_git(repo_root, *args):
    p = subprocess.run(["git", *args], cwd=repo_root, capture_output=True,
                       encoding="utf-8", errors="replace")
    if p.returncode != 0:
        raise SourceError(p.stderr.strip() or f"git {args[0]} failed")
    return p.stdout


def git_ok(repo_root, *args):
    return subprocess.run(["git", *args], cwd=repo_root, capture_output=True).returncode == 0


_FORBIDDEN_PREFIXES = (".git", ".dv")


class SourceReader:
    """Reads files as of `commit`.

    Files absent at the commit are read from disk only when they were already
    in the worktree at init (`worktree_paths`), and never through a symlink
    that leaves the repository. Without a commit (snapshot mode) every file
    inside the repository is readable from disk.
    """

    def __init__(self, repo_root, commit, worktree_paths=None):
        self.repo_root = repo_root
        self.commit = commit
        self.worktree_paths = set(worktree_paths or ())
        self._cache = {}

    def read(self, path):
        norm = posixpath.normpath(path.replace("\\", "/"))
        if path.startswith("/") or os.path.isabs(path) or norm == ".." or norm.startswith("../"):
            raise SourceError(f"path must stay inside the repository: {path}")
        if norm.split("/")[0] in _FORBIDDEN_PREFIXES:
            raise SourceError(f"path is not part of the project: {path}")
        if norm in self._cache:
            return self._cache[norm]
        found = None
        if self.commit and git_ok(self.repo_root, "cat-file", "-e", f"{self.commit}:{norm}"):
            found = (run_git(self.repo_root, "show", f"{self.commit}:{norm}"), "commit")
        if found is None:
            if self.commit and norm not in self.worktree_paths:
                raise SourceError(f"file not found at the baseline commit or in the worktree at init: {path}")
            full = os.path.join(self.repo_root, norm)
            root = os.path.realpath(self.repo_root)
            if not os.path.realpath(full).startswith(root + os.sep):
                raise SourceError(f"path resolves outside the repository: {path}")
            if not os.path.isfile(full):
                raise SourceError(f"file not found: {path}")
            with open(full, encoding="utf-8", errors="replace", newline="") as f:
                found = (f.read(), "worktree")
        self._cache[norm] = found
        return found


def split_lines(text):
    """Split on newline only, like `cat -n`; tolerate CRLF."""
    lines = [line[:-1] if line.endswith("\r") else line for line in text.split("\n")]
    if lines and lines[-1] == "":
        lines.pop()
    return lines


def match_excerpt(text, line_start, line_end, excerpt, slack=0):
    lines = split_lines(text)
    if line_start < 1 or line_end < line_start:
        return f"invalid line range {line_start}-{line_end}"
    if line_start > len(lines):
        return f"line {line_start} is past the end ({len(lines)} lines)"
    needle = normalize(excerpt)
    if not needle:
        return "empty excerpt"
    lo = max(1, line_start - slack)
    hi = min(len(lines), line_end + slack)
    if needle not in normalize("\n".join(lines[lo - 1:hi])):
        return f"excerpt not found in lines {lo}-{hi}"
    return None


def _heading(line):
    stripped = line.lstrip()
    if not stripped.startswith("#"):
        return None
    level = len(stripped) - len(stripped.lstrip("#"))
    return level, normalize(stripped[level:])


def markdown_section(text, heading):
    lines = text.splitlines()
    target = normalize(heading)
    for i, line in enumerate(lines):
        head = _heading(line)
        if head and head[1] == target:
            end = len(lines)
            for j in range(i + 1, len(lines)):
                nxt = _heading(lines[j])
                if nxt and nxt[0] <= head[0]:
                    end = j
                    break
            return "\n".join(lines[i:end])
    return None
