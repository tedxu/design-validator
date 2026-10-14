import os
import tempfile
import unittest

import _path  # noqa: F401
import helpers as h
import samples as s
from dvlib import commands

VALIDATORS = {
    "facts": (1, {"kind": "command", "scope": "assumption", "targets": ["current-fact"]}),
    "whole": (2, {"kind": "command", "scope": "design"}),
    "costly": (2, {"kind": "command", "scope": "design", "cost": "high"}),
}


class InputTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.fx = h.RunFixture(self.tmp.name, validators=VALIDATORS)
        a2 = s.assumption("A2", 4, "We rely on it.", kind="design-choice")
        self.fx.write("assumptions.json", {"assumptions": [s.assumption(), a2]})
        self.fx.write("results/extract.json", s.result("extract"))

    def tearDown(self):
        self.tmp.cleanup()

    def test_input_files(self):
        self.assertEqual(commands.cmd_assumptions(self.fx.run_dir)[0], 0)
        cases = [("facts", ["A1"]), ("whole", ["A1", "A2"])]
        for name, ids in cases:
            with self.subTest(name):
                code, out = commands.cmd_input(self.fx.run_dir, name)
                self.assertEqual(code, 0, out)
                self.assertEqual(out["input_path"],
                                 os.path.join(os.path.abspath(self.fx.run_dir), "inputs", f"{name}.json"))
                data = commands.load_json(out["input_path"])
                self.assertEqual([a["id"] for a in data["assumptions"]], ids)
                self.assertEqual(out["assumptions"], len(ids))
                self.assertEqual(data["id_prefix"], name)
                self.assertEqual(data["repo_commit"], self.fx.commit)
                self.assertTrue(data["worktree_matches_baseline"])
                self.assertEqual(data["design_path"],
                                 os.path.join(os.path.abspath(self.fx.run_dir), "design.md"))
                self.assertEqual(data["context"]["history"], {"git": True, "pr_comments": False})
                self.assertEqual(data["context"]["priors"], self.fx.run()["priors"])

    def test_refused(self):
        cases = [
            ("before stage 0 closes", "facts", False),
            ("not selected at this depth", "costly", True),
            ("unknown", "nope", True),
            ("extract", "extract", True),
        ]
        for name, validator, close_stage0 in cases:
            with self.subTest(name):
                fx = h.RunFixture(tempfile.mkdtemp(dir=self.tmp.name), validators=VALIDATORS)
                fx.write("assumptions.json", {"assumptions": [s.assumption()]})
                fx.write("results/extract.json", s.result("extract"))
                if close_stage0:
                    self.assertEqual(commands.cmd_assumptions(fx.run_dir)[0], 0)
                with self.assertRaises(commands.StateError):
                    commands.cmd_input(fx.run_dir, validator)
                self.assertFalse(os.path.exists(os.path.join(fx.run_dir, "inputs", f"{validator}.json")))


if __name__ == "__main__":
    unittest.main()
