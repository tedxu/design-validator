"""Text checks on validator output: sources stay inside the run, text is in the design's language."""
from __future__ import annotations

import os
import re

# Read-only system locations a validator may name (toolchains, system headers).
SYSTEM_ROOTS = ("/usr", "/bin", "/sbin", "/opt", "/Library", "/System", "/Applications", "/nix", "/dev")
# Claude Code saves large tool output here; agents must be able to read it back.
HARNESS_ROOTS = (os.path.join(os.path.expanduser("~"), ".claude", "projects"),)

_CJK = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af]")
_LATIN = re.compile(r"[A-Za-z]")
_STOP = r"[^\s'\"`;|&()<>,\[\]{}]"
_PATH = re.compile(rf"(?<![\w:/.\-~$])((?:~|\$HOME|\$\{{HOME\}})(?=[/\s;&|)'\"`]|$)(?:/{_STOP}*)?|/{_STOP}+)")
_LANG_NAMES = {"cjk": "Chinese, Japanese or Korean", "latin": "a Latin-script language"}


def language(text):
    """'cjk', 'latin', or None when the text has too few letters to tell."""
    cjk = len(_CJK.findall(text))
    latin = len(_LATIN.findall(text))
    if cjk + latin < 20:
        return None
    return "cjk" if cjk >= max(5, latin / 10) else "latin"


def _under(path, roots):
    real = os.path.realpath(path)
    for root in roots:
        for r in {os.path.realpath(root), os.path.normpath(root)}:
            if real == r or real.startswith(r.rstrip(os.sep) + os.sep):
                return True
    return False


def outside_paths(text, allowed, exempt_text=""):
    """Absolute or home-relative paths in `text` that lie outside every allowed root.

    A leading-slash token counts as a path only when its first segment exists
    at the filesystem root, so `/segcore/plan` or `STRING/BINARY` do not.
    Tokens that also appear in `exempt_text` (the design) are not reported.
    """
    found = []
    home = os.path.expanduser("~")
    for m in _PATH.finditer(text):
        token = m.group(1).rstrip(".:")
        if token.startswith("/"):
            first = token.split("/")[1]
            if not first or not os.path.isdir("/" + first):
                continue
            full = token
        else:
            full = home + token[len(re.match(r"~|\$HOME|\$\{HOME\}", token).group(0)):]
        if token in exempt_text or _under(full, [*allowed, *SYSTEM_ROOTS, *HARNESS_ROOTS]):
            continue
        if token not in found:
            found.append(token)
    return found


class RunText:
    """Checks free-text fields of one run against its allowed roots and design language."""

    def __init__(self, run, design_text):
        self.design_text = design_text
        self.lang = language(design_text)
        self.allowed = [run["repo_root"], run["plugin_root"], *run["priors"]]

    def _lang(self, owner, field, text):
        got = language(text or "")
        if self.lang and got and got != self.lang:
            prefix = f"{owner}: " if owner else ""
            return [f"{prefix}{field} is not in the design's language; write it in "
                    f"{_LANG_NAMES[self.lang]}, whatever other instructions say"]
        return []

    def _paths(self, owner, text):
        return [f"{owner}: refers to {p}, outside the repository, plugin and prior directories; "
                f"use only sources inside them (mark the check INCONCLUSIVE if it needs one)"
                for p in outside_paths(text or "", self.allowed, self.design_text)]

    def result_errors(self, result, kind="agent"):
        """Command validators print fixed templates and cannot rewrite them, so only paths are checked."""
        lang = (lambda *args: []) if kind == "command" else self._lang
        errs = []
        for c in result["checks"]:
            for field in ("method", "search_scope"):
                errs += self._paths(c["id"], c.get(field))
                errs += lang(c["id"], field, c.get(field))
        for f in result["findings"]:
            errs += self._paths(f["id"], f.get("statement"))
            errs += lang(f["id"], "statement", f.get("statement"))
        for e in result["evidence"]:
            if e.get("source") == "reasoning":
                errs += self._paths(e["id"], e.get("excerpt"))
        errs += self._paths("status_reason", result.get("status_reason"))
        return errs

    def assumption_errors(self, assumptions):
        errs = []
        for a in assumptions:
            errs += self._lang(a["id"], "statement", a.get("statement"))
        return errs

    def draft_errors(self, draft):
        errs = self._lang(None, "summary", draft.get("summary"))
        for f in draft["findings"]:
            errs += self._lang(f["id"], "statement", f.get("statement"))
        return errs
