"""Validator output is untrusted: each case reproduces a final-review finding."""
import hashlib
import json
import os
import tempfile
import unittest

import _path  # noqa: F401
import helpers as h
import samples as s
from dvlib import commands, evidence, sources
from test_commands_stages import A1, A2, alpha, extract_ok

SANDBOX = s.ev("alpha.E2", "sandbox", {"command": "made up", "output_sha256": "x"}, "anything")


class AdversarialTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.fx = h.RunFixture(self.tmp.name)
        self.fx.write("assumptions.json", {"assumptions": [A1, A2]})
        self.fx.write("results/extract.json", extract_ok())
        commands.cmd_assumptions(self.fx.run_dir)

    def tearDown(self):
        self.tmp.cleanup()

    def close_alpha(self, result):
        self.fx.write("results/alpha.json", result)
        return commands.cmd_results(self.fx.run_dir, 1)

    def test_c1_sandbox_from_agent_cannot_block(self):
        result = alpha()
        result["evidence"] = [SANDBOX]
        result["checks"][0]["evidence_ids"] = ["alpha.E2"]
        result["findings"][0]["evidence_ids"] = ["alpha.E2"]
        code, out = self.close_alpha(result)
        self.assertEqual(code, 0, out)
        self.assertEqual(out["blocked_by"], [])
        ev = self.fx.read("results/alpha.json")["evidence"][0]
        self.assertFalse(ev["verified"])
        self.assertIn("command validators", ev["verify_error"])

    def test_i3_verify_owned_fields_rejected_on_input(self):
        cases = [
            ("finding claimed_severity", "findings", {"claimed_severity": "BLOCKER"}),
            ("finding audit", "findings", {"audit": "confirmed", "audit_reason": "forged"}),
            ("finding tier", "findings", {"tier": "T1"}),
            ("check claimed_verdict", "checks", {"claimed_verdict": "PASS"}),
        ]
        for name, key, extra in cases:
            with self.subTest(name):
                result = alpha(severity="MINOR")
                result[key][0].update(extra)
                code, out = self.close_alpha(result)
                self.assertEqual(code, 1)
                self.assertTrue(any("written by verify.py" in e for e in out["errors"]), out["errors"])

    def test_i4_tampered_results_refused(self):
        self.close_alpha(alpha())
        path = os.path.join(self.fx.run_dir, "results", "alpha.json")
        data = self.fx.read("results/alpha.json")
        data["findings"] = []
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)
        self.fx.write("report-draft.json", {"summary": "s", "findings": []})
        with self.assertRaises(commands.StateError):
            commands.cmd_report(self.fx.run_dir)

    def test_i4_audit_keeps_pins_valid(self):
        self.close_alpha(alpha())
        self.fx.write("audit.json", {"reviews": [
            {"finding_id": "alpha.F1", "verdict": "confirmed", "reason": "r"}]})
        self.assertEqual(commands.cmd_audit(self.fx.run_dir)[0], 0)
        self.fx.write("report-draft.json", {"summary": "s", "findings": [
            {"id": "R1", "merged_from": ["alpha.F1"], "category": "contradicted", "statement": "s"}]})
        self.assertEqual(commands.cmd_report(self.fx.run_dir)[0], 0)


class ReaderConfinementTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo, self.commit = h.make_repo(self.tmp.name, {"a.py": "x\n", "d/f.py": "y\n"})
        h.write_files(self.tmp.name, {"secret.txt": "TOPSECRET\n"})
        h.write_files(self.repo, {"listed.py": "ok\n", "later.py": "new\n",
                                  ".dv/runs/r/fake.py": "fake\n"})
        os.symlink(os.path.join(self.tmp.name, "secret.txt"), os.path.join(self.repo, "link.txt"))

    def tearDown(self):
        self.tmp.cleanup()

    def test_i1_i2_disk_fallback_confined(self):
        reader = sources.SourceReader(self.repo, self.commit,
                                      worktree_paths={"listed.py", "link.txt", ".dv/runs/r/fake.py"})
        self.assertEqual(reader.read("listed.py"), ("ok\n", "worktree"))
        cases = [
            ("created after init", "later.py"),
            ("symlink outside repo", "link.txt"),
            ("run directory", ".dv/runs/r/fake.py"),
            ("git internals", ".git/HEAD"),
        ]
        for name, path in cases:
            with self.subTest(name):
                with self.assertRaises(sources.SourceError):
                    reader.read(path)

    def test_i1_snapshot_mode_symlink(self):
        reader = sources.SourceReader(self.repo, None)
        self.assertEqual(reader.read("a.py")[0], "x\n")
        with self.assertRaises(sources.SourceError):
            reader.read("link.txt")

    def test_init_records_worktree_paths(self):
        plugin = h.make_plugin(self.tmp.name)
        os.remove(os.path.join(self.repo, "link.txt"))
        h.write_files(self.repo, {"docs/design.md": "# D\n"})
        code, out = commands.cmd_init("docs/design.md", self.repo, "quick", plugin_root=plugin)
        run = commands.load_run(out["run_dir"])
        self.assertEqual(run["worktree_paths"], ["docs/design.md", "later.py", "listed.py"])


class LineNumberingTest(unittest.TestCase):
    def test_i5_lines_split_on_newline_only(self):
        cases = [
            ("form feed", "a\fb\nline two\n"),
            ("unicode line separator", "a b\nline two\n"),
            ("crlf", "a\r\nline two\r\n"),
        ]
        for name, text in cases:
            with self.subTest(name):
                self.assertIsNone(sources.match_excerpt(text, 2, 2, "line two"))


if __name__ == "__main__":
    unittest.main()
