#!/usr/bin/env python3
"""PreToolUse hook: while a design-validate run is active, keep tool calls inside its sources.

A run is active when `<repo>/.dv/runs/active.json` exists (written by `verify.py
init`, removed by `verify.py report`) and is younger than TTL_SECONDS. The
hook then blocks file tools and shell commands that name a path outside the
repository, the plugin and the prior directories. Without an active run, and
on any unexpected input, it allows the call.
"""
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))

from dvlib import hygiene  # noqa: E402

TTL_SECONDS = 2 * 3600
PATH_KEYS = ("file_path", "path", "notebook_path")
_ARG = r"[^\s'\"`;|&()<>]"
# `cd <dir>` (tracked so later relative paths resolve from it) or a `..` path.
_CD_OR_PARENT = re.compile(
    rf"(?:(?<=\s)|^|(?<=[;&|(]))(?:cd\s+({_ARG}+)|(\.\.(?:/{_ARG}*)?)(?=[\s;&|)]|$))")


def find_marker(cwd):
    d = os.path.abspath(cwd)
    while True:
        path = os.path.join(d, ".dv", "runs", "active.json")
        if os.path.isfile(path):
            return path
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


def outside(tool, tool_input, cwd, allowed):
    if tool == "Bash":
        cmd = tool_input.get("command") or ""
        found = hygiene.outside_paths(cmd, allowed)
        cur = cwd
        for m in _CD_OR_PARENT.finditer(cmd):
            target, parent = m.groups()
            if target is not None:
                cur = os.path.normpath(os.path.join(cur, os.path.expanduser(target)))
                if target.startswith(".") and hygiene.outside_paths(cur, allowed):
                    found.append(target)
            elif hygiene.outside_paths(os.path.normpath(os.path.join(cur, parent)), allowed):
                found.append(parent)
        return found
    found = []
    for key in PATH_KEYS:
        value = tool_input.get(key)
        if isinstance(value, str) and value:
            full = os.path.normpath(os.path.join(cwd, os.path.expanduser(value)))
            if hygiene.outside_paths(full, allowed):
                found.append(value)
    return found


def main():
    try:
        data = json.load(sys.stdin)
        cwd = data.get("cwd") or os.getcwd()
        marker = find_marker(cwd)
        if marker is None:
            return 0
        with open(marker, encoding="utf-8") as f:
            run = json.load(f)
        if time.time() - float(run.get("started_at", 0)) > TTL_SECONDS:
            return 0
        found = outside(data.get("tool_name", ""), data.get("tool_input") or {}, cwd,
                        run["allowed_roots"])
    except Exception:  # noqa: BLE001 - never break the session on bad input
        return 0
    if not found:
        return 0
    sys.stderr.write(
        f"design-validate scope guard: {', '.join(found)} is outside the repository, plugin and "
        f"prior directories of the active run {os.path.basename(run['run_dir'])}. Use only sources "
        f"inside {', '.join(run['allowed_roots'])}; if a check needs another source, mark it "
        f"INCONCLUSIVE and name the source in search_scope. Write scratch files under "
        f"{os.path.join(run['run_dir'], 'tmp')}. The guard ends when the report is "
        f"written or after {TTL_SECONDS // 3600} hours; delete {marker} to end it sooner.\n")
    return 2


if __name__ == "__main__":
    sys.exit(main())
