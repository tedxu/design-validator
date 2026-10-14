import tempfile
import unittest

import _path  # noqa: F401
import helpers as h
import samples as s
from dvlib import commands
from test_commands_stages import A1, A2, alpha, extract_ok

EXTERNAL = s.ev("alpha.E2", "external",
                {"url": "https://example.invalid/doc", "dependency": "class", "version": "SegmentCache",
                 "version_source": "store/cache.py:1"}, "documented behaviour")


class AuditTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.fx = h.RunFixture(self.tmp.name)
        self.fx.write("assumptions.json", {"assumptions": [A1, A2]})
        self.fx.write("results/extract.json", extract_ok())
        commands.cmd_assumptions(self.fx.run_dir)

    def tearDown(self):
        self.tmp.cleanup()

    def close_alpha(self, result):
        """Close stage 1, then stage 2 too unless alpha's BLOCKER skipped it."""
        self.fx.write("results/alpha.json", result)
        code, out = commands.cmd_results(self.fx.run_dir, 1)
        self.assertEqual(code, 0, out)
        if self.fx.run()["stages"]["2"] == "PENDING":
            self.fx.write("results/beta.json", s.result("beta"))
            code, out = commands.cmd_results(self.fx.run_dir, 2)
            self.assertEqual(code, 0, out)

    def test_dispute_blocker_marks_gate(self):
        self.close_alpha(alpha())
        self.fx.write("audit.json", {"reviews": [
            {"finding_id": "alpha.F1", "verdict": "disputed", "reason": "pre-existing"}]})
        code, out = commands.cmd_audit(self.fx.run_dir)
        self.assertEqual(code, 0, out)
        f = self.fx.read("results/alpha.json")["findings"][0]
        self.assertEqual((f["severity"], f["audit"], f["audit_reason"]), ("MAJOR", "disputed", "pre-existing"))
        run = self.fx.run()
        self.assertTrue(run["gate_disputed"])
        self.assertTrue(run["audited"])
        with self.assertRaises(commands.StateError):
            commands.cmd_audit(self.fx.run_dir)

    def test_unconfirmed_external_drops_to_t2(self):
        result = alpha(severity="MAJOR")
        result["evidence"].append(EXTERNAL)
        result["findings"][0]["evidence_ids"] = ["alpha.E2"]
        self.close_alpha(result)
        self.assertEqual(self.fx.read("results/alpha.json")["findings"][0]["tier"], "T1")
        self.fx.write("audit.json", {"reviews": [
            {"finding_id": "alpha.F1", "verdict": "confirmed", "reason": "ok",
             "external_checks": [{"evidence_id": "alpha.E2", "confirmed": False}]}]})
        code, out = commands.cmd_audit(self.fx.run_dir)
        self.assertEqual(code, 0, out)
        graded = self.fx.read("results/alpha.json")
        self.assertEqual(graded["evidence"][1]["tier"], "T2")
        self.assertEqual(graded["findings"][0]["tier"], "T2")
        self.assertEqual(graded["findings"][0]["audit"], "confirmed")

    def test_input_errors(self):
        self.close_alpha(alpha(severity="MAJOR"))
        cases = [
            ("unknown finding", [{"finding_id": "alpha.F9", "verdict": "confirmed", "reason": "r"}],
             "unknown finding alpha.F9"),
            ("twice", [{"finding_id": "alpha.F1", "verdict": "confirmed", "reason": "r"}] * 2,
             "alpha.F1 reviewed twice"),
            ("non-external check", [{"finding_id": "alpha.F1", "verdict": "confirmed", "reason": "r",
                                     "external_checks": [{"evidence_id": "alpha.E1", "confirmed": True}]}],
             "alpha.E1 is not an external evidence item"),
        ]
        for name, reviews, want in cases:
            with self.subTest(name):
                self.fx.write("audit.json", {"reviews": reviews})
                code, out = commands.cmd_audit(self.fx.run_dir)
                self.assertEqual(code, 1)
                self.assertTrue(any(want in e for e in out["errors"]), out["errors"])
                self.assertFalse(self.fx.run()["audited"])

    def test_requires_closed_stages(self):
        fx = h.RunFixture(tempfile.mkdtemp(dir=self.tmp.name))
        with self.assertRaises(commands.StateError):
            commands.cmd_audit(fx.run_dir)


if __name__ == "__main__":
    unittest.main()
