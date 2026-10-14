import tempfile
import unittest

import _path  # noqa: F401
import helpers as h
import samples as s
from dvlib import commands

A1 = s.assumption()
A2 = s.assumption("A2", 4, "We rely on it.")


def extract_ok():
    return s.result("extract")


def extract_blocker():
    design_ev = s.ev("extract.E1", "design", {"line_start": 3, "line_end": 3},
                     "SegmentCache evicts entries after ttl.")
    return s.result("extract", findings=[s.finding("extract.F1", ["extract.E1"], severity="BLOCKER",
                                                   category="ambiguous", assumption_ids=[])],
                    evidence=[design_ev])


def alpha(excerpt="class SegmentCache:", severity="BLOCKER"):
    return s.result("alpha", checks=[s.check("alpha.C1", ["alpha.E1"])],
                    findings=[s.finding("alpha.F1", ["alpha.E1"], severity=severity,
                                        check_ids=["alpha.C1"])],
                    evidence=[s.code_ev("alpha.E1", excerpt=excerpt)])


class StagesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.fx = h.RunFixture(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def close_stage0(self, extract=None):
        self.fx.write("assumptions.json", {"assumptions": [A1, A2]})
        self.fx.write("results/extract.json", extract or extract_ok())
        return commands.cmd_assumptions(self.fx.run_dir)

    def test_assumptions_errors_do_not_close_stage(self):
        cases = [
            ("bad quote", {"assumptions": [s.assumption(quote="nowhere")]}, extract_ok(), "A1: anchor"),
            ("unknown dependency", {"assumptions": [s.assumption(depends_on=["A7"])]}, extract_ok(),
             "unknown assumption A7"),
            ("schema", {"assumptions": [dict(A1, kind="guess")]}, extract_ok(), "assumptions.json: $"),
            ("missing extract result", {"assumptions": [A1]}, None, "results/extract.json is missing"),
        ]
        for name, assumptions, extract, want in cases:
            with self.subTest(name):
                fx = h.RunFixture(tempfile.mkdtemp(dir=self.tmp.name))
                fx.write("assumptions.json", assumptions)
                if extract is not None:
                    fx.write("results/extract.json", extract)
                code, out = commands.cmd_assumptions(fx.run_dir)
                self.assertEqual(code, 1)
                self.assertTrue(any(want in e for e in out["errors"]), out["errors"])
                self.assertEqual(fx.run()["stages"]["0"], "PENDING")

    def test_extract_blocker_skips_everything(self):
        code, out = self.close_stage0(extract_blocker())
        self.assertEqual(code, 0, out)
        run = self.fx.run()
        self.assertEqual(run["stages"], {"0": "COMPLETED", "1": "SKIPPED", "2": "SKIPPED"})
        self.assertEqual(run["blocked_by"], ["extract.F1"])
        with self.assertRaises(commands.StateError):
            commands.cmd_results(self.fx.run_dir, 1)

    def test_t1_blocker_gates_later_stages(self):
        self.close_stage0()
        self.fx.write("results/alpha.json", alpha())
        code, out = commands.cmd_results(self.fx.run_dir, 1)
        self.assertEqual(code, 0, out)
        self.assertEqual(out["blocked_by"], ["alpha.F1"])
        self.assertEqual(self.fx.run()["stages"]["2"], "SKIPPED")
        graded = self.fx.read("results/alpha.json")
        self.assertEqual(graded["evidence"][0]["verified"], True)
        self.assertEqual(graded["findings"][0]["tier"], "T1")

    def test_unverified_blocker_is_downgraded(self):
        self.close_stage0()
        self.fx.write("results/alpha.json", alpha(excerpt="def evict(self):"))
        code, out = commands.cmd_results(self.fx.run_dir, 1)
        self.assertEqual(code, 0, out)
        self.assertEqual(out["blocked_by"], [])
        graded = self.fx.read("results/alpha.json")
        self.assertEqual(graded["checks"][0]["verdict"], "INCONCLUSIVE")
        self.assertEqual(graded["findings"][0]["severity"], "MINOR")
        self.assertEqual(self.fx.run()["stages"], {"0": "COMPLETED", "1": "COMPLETED", "2": "PENDING"})

    def test_results_input_errors(self):
        self.close_stage0()
        dup = alpha()
        dup["evidence"].append(s.code_ev("alpha.E1"))
        cases = [
            ("missing file", None, "results/alpha.json is missing"),
            ("duplicate id", dup, "alpha.E1: duplicate id"),
            ("unknown assumption",
             dict(alpha(), checks=[s.check("alpha.C1", ["alpha.E1"], assumption_ids=["A9"])]),
             "unknown assumption A9"),
        ]
        for name, result, want in cases:
            with self.subTest(name):
                if result is not None:
                    self.fx.write("results/alpha.json", result)
                code, out = commands.cmd_results(self.fx.run_dir, 1)
                self.assertEqual(code, 1)
                self.assertTrue(any(want in e for e in out["errors"]), out["errors"])
                self.assertEqual(self.fx.run()["stages"]["1"], "PENDING")

    def test_failed_result_is_accepted(self):
        self.close_stage0()
        self.fx.write("results/alpha.json", s.result("alpha", status="FAILED", reason="timeout"))
        code, _ = commands.cmd_results(self.fx.run_dir, 1)
        self.assertEqual(code, 0)

    def test_state_errors(self):
        with self.assertRaises(commands.StateError):
            commands.cmd_results(self.fx.run_dir, 1)        # stage 0 still open
        self.close_stage0()
        with self.assertRaises(commands.StateError):
            commands.cmd_assumptions(self.fx.run_dir)       # stage 0 already closed
        with self.assertRaises(commands.StateError):
            commands.cmd_results(self.fx.run_dir, 2)        # stage 1 still open
        with self.assertRaises(commands.StateError):
            commands.cmd_results(self.fx.run_dir, 7)        # no such stage
        self.fx.write("results/alpha.json", alpha(severity="MINOR"))
        commands.cmd_results(self.fx.run_dir, 1)
        with self.assertRaises(commands.StateError):
            commands.cmd_results(self.fx.run_dir, 1)        # already closed


if __name__ == "__main__":
    unittest.main()
