"""Verify one evidence record against the run baseline and assign its tier."""
from __future__ import annotations

import os
import posixpath
from dataclasses import dataclass

from . import sources

TIER_BY_SOURCE = {"code": "T1", "prior": "T1", "sandbox": "T1", "design": "T1", "external": "T1",
                  "docs": "T2", "history": "T2", "reasoning": "T3"}
_LINES = {"line_start", "line_end"}
LOCATOR_FIELDS = {
    "code": {"path"} | _LINES,
    "docs": {"path"} | _LINES,
    "design": set(_LINES),
    "prior": {"pack", "heading"},
    "sandbox": {"command", "output_sha256"},
    "external": {"url", "dependency", "version", "version_source"},
    "reasoning": set(),
}
FILLED = ("tier", "verified", "verify_error", "content_sha256", "content_origin", "authoritative")


@dataclass
class Context:
    repo_root: str
    commit: object
    design_text: str
    docs: list
    priors: list
    reader: sources.SourceReader


def verify_evidence(ev, ctx, kind="agent"):
    for key in FILLED:
        ev.pop(key, None)
    source = ev["source"]
    ev["tier"] = TIER_BY_SOURCE[source]
    error = _locator_error(source, ev["locator"])
    if error is None:
        try:
            error = ("sandbox evidence is only accepted from command validators"
                     if source == "sandbox" and kind != "command" else _HANDLERS[source](ev, ctx))
        except sources.SourceError as e:
            error = str(e)
    if error is not None:
        ev["verified"] = False
        ev["verify_error"] = error
    elif "verified" not in ev:
        ev["verified"] = True


def _locator_error(source, loc):
    if source == "history":
        if set(loc) not in ({"commit"}, {"url"}):
            return "locator for history must be {commit} or {url}"
        value = next(iter(loc.values()))
        return None if isinstance(value, str) and value else "locator value must be a non-empty string"
    want = LOCATOR_FIELDS[source]
    if set(loc) != want:
        return f"locator for {source} must have exactly {sorted(want)}"
    for key in sorted(want & _LINES):
        v = loc[key]
        if not isinstance(v, int) or isinstance(v, bool) or v < 1:
            return f"locator.{key} must be a positive integer"
    for key in sorted(want - _LINES):
        if not isinstance(loc[key], str) or not loc[key]:
            return f"locator.{key} must be a non-empty string"
    return None


def _is_authoritative(path, docs):
    p = posixpath.normpath(path.replace("\\", "/"))
    for d in docs:
        if d["authority"] != "authoritative":
            continue
        root = posixpath.normpath(d["path"])
        if p == root or p.startswith(root + "/"):
            return True
    return False


def _file(ev, ctx):
    loc = ev["locator"]
    text, origin = ctx.reader.read(loc["path"])
    ev["content_sha256"] = sources.sha256_text(text)
    ev["content_origin"] = origin
    if ev["source"] == "docs":
        ev["authoritative"] = _is_authoritative(loc["path"], ctx.docs)
    return sources.match_excerpt(text, loc["line_start"], loc["line_end"], ev["excerpt"])


def _design(ev, ctx):
    loc = ev["locator"]
    return sources.match_excerpt(ctx.design_text, loc["line_start"], loc["line_end"], ev["excerpt"],
                                 slack=3)


def _prior(ev, ctx):
    loc = ev["locator"]
    pack = loc["pack"]
    if os.path.basename(pack) != pack:
        return "locator.pack must be a file name"
    for directory in ctx.priors:
        path = os.path.join(directory, pack)
        if not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8") as f:
            section = sources.markdown_section(f.read(), loc["heading"])
        if section is None:
            return f"heading '{loc['heading']}' not found in {pack}"
        needle = sources.normalize(ev["excerpt"])
        if not needle or needle not in sources.normalize(section):
            return f"excerpt not found under '{loc['heading']}' in {pack}"
        return None
    return f"prior pack {pack} not found"


def _external(ev, ctx):
    ev["verified"] = "n/a"
    loc = ev["locator"]
    path, sep, line = loc["version_source"].rpartition(":")
    problem = None
    if not sep or not path or not line.isdigit():
        problem = "version_source must be 'path:line'"
    else:
        try:
            lines = sources.split_lines(ctx.reader.read(path)[0])
            n = int(line)
            if n < 1 or n > len(lines):
                problem = f"{path} has no line {n}"
            elif loc["dependency"] not in lines[n - 1] or loc["version"] not in lines[n - 1]:
                problem = f"{path}:{n} does not mention {loc['dependency']} {loc['version']}"
        except sources.SourceError as e:
            problem = str(e)
    if problem:
        ev["tier"] = "T2"
        ev["verify_error"] = problem
    return None


def _history(ev, ctx):
    loc = ev["locator"]
    if "url" in loc:
        ev["verified"] = "n/a"
        return None
    if ctx.commit is None:
        return "history is unavailable without git (snapshot mode)"
    c = loc["commit"]
    if not sources.git_ok(ctx.repo_root, "cat-file", "-e", f"{c}^{{commit}}"):
        return f"commit {c} not found"
    if not sources.git_ok(ctx.repo_root, "merge-base", "--is-ancestor", c, ctx.commit):
        return f"commit {c} is not an ancestor of the baseline"
    shown = sources.run_git(ctx.repo_root, "show", "--no-color", c)
    needle = sources.normalize(ev["excerpt"])
    if not needle or needle not in sources.normalize(shown):
        return f"excerpt not found in 'git show {c}'"
    return None


def _sandbox(ev, ctx):
    ev["verified"] = "n/a"
    return None


def _reasoning(ev, ctx):
    if not ev["excerpt"].strip():
        return "reasoning evidence needs the argument in excerpt"
    ev["verified"] = "n/a"
    return None


_HANDLERS = {"code": _file, "docs": _file, "design": _design, "prior": _prior,
             "external": _external, "history": _history, "sandbox": _sandbox,
             "reasoning": _reasoning}
