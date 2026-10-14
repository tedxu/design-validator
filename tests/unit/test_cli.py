import json
import os
import subprocess
import sys
import tempfile
import unittest

import _path  # noqa: F401
import helpers as h

VERIFY = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                      "scripts", "verify.py")


def run_cli(args, plugin, cwd):
    env = dict(os.environ, DV_PLUGIN_ROOT=plugin)
    p = subprocess.run([sys.executable, VERIFY, *args], cwd=cwd, env=env, capture_output=True, text=True)
    return p.returncode, json.loads(p.stdout)


class CliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.plugin = h.make_plugin(self.tmp.name)
        self.repo, _ = h.make_repo(self.tmp.name, {"docs/design.md": "# D\n\nClaim.\n"})

    def tearDown(self):
        self.tmp.cleanup()

    def test_input_requires_validator(self):
        code, out = run_cli(["init", "docs/design.md"], self.plugin, self.repo)
        self.assertEqual(code, 0, out)
        code, out = run_cli(["input", out["run_dir"]], self.plugin, self.repo)
        self.assertEqual(code, 2)
        self.assertIn("usage", out["errors"][0])

    def test_exit_codes(self):
        code, out = run_cli(["init", "docs/design.md", "--depth", "quick"], self.plugin, self.repo)
        self.assertEqual(code, 0, out)
        run_dir = out["run_dir"]
        self.assertEqual([d["name"] for d in out["dispatch"]], ["extract"])
        cases = [
            ("missing input files", ["assumptions", run_dir], 1),
            ("stage before stage 0", ["results", run_dir, "--stage", "1"], 2),
            ("report before closing", ["report", run_dir], 2),
            ("missing design", ["init", "nope.md"], 2),
            ("bad depth", ["init", "docs/design.md", "--depth", "huge"], 2),
            ("missing run", ["assumptions", os.path.join(self.tmp.name, "none")], 2),
            ("bad baseline", ["init", "docs/design.md", "--baseline", "no-such-ref"], 2),
        ]
        for name, args, want in cases:
            with self.subTest(name):
                code, out = run_cli(args, self.plugin, self.repo)
                self.assertEqual(code, want, out)
                self.assertFalse(out["ok"])
                self.assertTrue(out["errors"])

    def test_baseline_flag(self):
        code, out = run_cli(["init", "docs/design.md", "--baseline", "HEAD"], self.plugin, self.repo)
        self.assertEqual(code, 0, out)
        self.assertTrue(out["worktree_matches_baseline"])


if __name__ == "__main__":
    unittest.main()
