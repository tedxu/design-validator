import json
import os
import subprocess
import sys
import tempfile
import time
import unittest

import _path  # noqa: F401
import helpers as h
import samples as s
from dvlib import commands

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GUARD = os.path.join(ROOT, "hooks", "scope_guard.py")


def guard(cwd, tool, tool_input):
    p = subprocess.run([sys.executable, GUARD], input=json.dumps(
        {"cwd": cwd, "hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": tool_input}),
        capture_output=True, text=True)
    return p.returncode, p.stderr


class ScopeGuardTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = os.path.realpath(self.tmp.name)
        self.fx = h.RunFixture(base)
        self.repo = os.path.realpath(self.fx.repo)
        self.other = os.path.join(base, "other-clone")
        os.makedirs(self.other)

    def tearDown(self):
        self.tmp.cleanup()

    def marker(self):
        return os.path.join(self.repo, ".dv", "runs", "active.json")

    def test_tool_calls_during_a_run(self):
        verify = os.path.join(self.fx.plugin, "scripts", "verify.py")
        cases = [
            ("read inside", "Read", {"file_path": f"{self.repo}/store/cache.py"}, 0),
            ("read relative", "Read", {"file_path": "store/cache.py"}, 0),
            ("read plugin prompt", "Read", {"file_path": f"{self.fx.plugin}/validators/x/prompt.md"}, 0),
            ("read other clone", "Read", {"file_path": f"{self.other}/a.go"}, 2),
            ("grep other clone", "Grep", {"pattern": "x", "path": self.other}, 2),
            ("glob other clone", "Glob", {"pattern": "*.go", "path": self.other}, 2),
            ("bash git show", "Bash", {"command": "git show HEAD:store/cache.py | cat -n"}, 0),
            ("bash verify", "Bash", {"command": f'python3 "{verify}" results .dv/runs/x --stage 1'}, 0),
            ("bash system tool", "Bash", {"command": "/usr/bin/env python3 -c 1"}, 0),
            ("bash cd other clone", "Bash", {"command": f"cd {self.other}; git reflog --all"}, 2),
            ("bash git -C other", "Bash", {"command": f"git -C {self.other} log -1"}, 2),
            ("bash home", "Bash", {"command": "ls ~/Source"}, 2),
            ("bash parent dir", "Bash", {"command": "cd ../other-clone && ls"}, 2),
            ("bash cd down then back up", "Bash",
             {"command": f"cd {self.fx.run_dir}/results && ls && cd ../../../.. && git status"}, 0),
            ("bash cd down then out", "Bash", {"command": "cd store && cat ../../other-clone/a"}, 2),
            ("bash dev null", "Bash", {"command": "git grep -n x 2>/dev/null"}, 0),
            ("bash ellipsis", "Bash", {"command": "head -3 a; echo ...; tail -3 a"}, 0),
            ("bash tilde in text", "Bash", {"command": "python3 - <<'EOF'\nm = ~mask\nprint('~250 rows')\nEOF"}, 0),
            ("bash git range", "Bash", {"command": "git log --oneline base..pr ..pr"}, 0),
            ("read harness tool output", "Read",
             {"file_path": os.path.expanduser("~/.claude/projects/p/s/tool-results/b1.txt")}, 0),
            ("bash scratch in tmp", "Bash", {"command": "cat > /tmp/fc2.py <<'EOF'\nx = 1\nEOF"}, 2),
        ]
        for name, tool, tool_input, want in cases:
            with self.subTest(name):
                code, err = guard(self.repo, tool, tool_input)
                self.assertEqual(code, want, err)
                if want:
                    self.assertIn("outside", err)
                    self.assertIn(os.path.join(self.fx.run_dir, "tmp"), err)

    def test_marker_found_from_subdirectory(self):
        code, _ = guard(os.path.join(self.repo, "store"), "Read", {"file_path": f"{self.other}/a"})
        self.assertEqual(code, 2)

    def test_inactive_when_no_or_stale_marker(self):
        with open(self.marker(), encoding="utf-8") as f:
            data = json.load(f)
        data["started_at"] = time.time() - 3 * 3600
        with open(self.marker(), "w", encoding="utf-8") as f:
            json.dump(data, f)
        self.assertEqual(guard(self.repo, "Read", {"file_path": f"{self.other}/a"})[0], 0)
        os.remove(self.marker())
        self.assertEqual(guard(self.repo, "Read", {"file_path": f"{self.other}/a"})[0], 0)

    def test_report_releases_marker(self):
        fx = self.fx
        fx.write("assumptions.json", {"assumptions": [s.assumption()]})
        fx.write("results/extract.json", s.result("extract"))
        self.assertEqual(commands.cmd_assumptions(fx.run_dir)[0], 0)
        fx.write("results/alpha.json", s.result("alpha"))
        self.assertEqual(commands.cmd_results(fx.run_dir, 1)[0], 0)
        fx.write("results/beta.json", s.result("beta"))
        self.assertEqual(commands.cmd_results(fx.run_dir, 2)[0], 0)
        fx.write("report-draft.json", {"summary": "No findings were raised by any validator.",
                                       "findings": []})
        self.assertTrue(os.path.isfile(self.marker()))
        # The skill passes a run directory relative to the repository root.
        cwd = os.getcwd()
        os.chdir(fx.repo)
        try:
            code, out = commands.cmd_report(os.path.relpath(fx.run_dir, fx.repo))
        finally:
            os.chdir(cwd)
        self.assertEqual(code, 0, out)
        self.assertFalse(os.path.exists(self.marker()))

    def test_marker_lists_allowed_roots(self):
        with open(self.marker(), encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["run_dir"], self.fx.run_dir)
        self.assertIn(self.fx.plugin, data["allowed_roots"])
        self.assertIn(os.path.join(self.fx.plugin, "priors"), data["allowed_roots"])

    def test_plugin_registers_hook(self):
        with open(os.path.join(ROOT, "hooks", "hooks.json"), encoding="utf-8") as f:
            hooks = json.load(f)["hooks"]["PreToolUse"]
        matchers = " ".join(entry["matcher"] for entry in hooks)
        for tool in ("Read", "Grep", "Glob", "Bash"):
            self.assertIn(tool, matchers)
        self.assertIn("scope_guard.py", json.dumps(hooks))


if __name__ == "__main__":
    unittest.main()
