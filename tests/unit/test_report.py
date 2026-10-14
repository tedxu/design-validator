import tempfile
import unittest

import _path  # noqa: F401
import helpers as h
import samples as s
from dvlib import commands, report
from test_commands_stages import A1, A2, alpha, extract_ok


def draft(*items, summary="Overall."):
    return {"summary": summary, "findings": [
        {"id": f"R{i}", "merged_from": list(m), "category": "contradicted", "statement": f"s{i}"}
        for i, m in enumerate(items, 1)]}


class ReportCommandTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.fx = h.RunFixture(self.tmp.name)
        self.fx.write("assumptions.json", {"assumptions": [A1, A2]})
        self.fx.write("results/extract.json", extract_ok())
        commands.cmd_assumptions(self.fx.run_dir)

    def tearDown(self):
        self.tmp.cleanup()

    def test_blocked_run_report(self):
        self.fx.write("results/alpha.json", alpha())
        commands.cmd_results(self.fx.run_dir, 1)
        self.fx.write("report-draft.json", draft(["alpha.F1"]))
        code, out = commands.cmd_report(self.fx.run_dir)
        self.assertEqual(code, 0, out)
        rep = self.fx.read("report.json")
        self.assertEqual(rep["findings"][0]["severity"], "BLOCKER")
        self.assertEqual(rep["findings"][0]["validators"], ["alpha"])
        cov = {v["name"]: (v["status"], v["reason"]) for v in rep["coverage"]["validators"]}
        self.assertEqual(cov["alpha"], ("COMPLETED", None))
        self.assertEqual(cov["beta"], ("SKIPPED", "blocked by alpha.F1"))
        self.assertEqual(cov["gamma"], ("NOT_RUN", "depth=standard excludes cost=high"))
        acov = {a["id"]: (a["status"], a["reason"]) for a in rep["coverage"]["assumptions"]}
        self.assertEqual(acov["A1"], ("CHECKED", None))
        self.assertEqual(acov["A2"], ("NOT_CHECKED", "alpha COMPLETED"))
        with open(out["report_md"], encoding="utf-8") as f:
            md = f.read()
        for heading in ("## Blocking and major issues", "## Coverage gaps", "## Checks performed",
                        "## Coverage", "## Assumptions"):
            self.assertIn(heading, md)

    def test_disputed_gate_reason(self):
        self.fx.write("results/alpha.json", alpha())
        commands.cmd_results(self.fx.run_dir, 1)
        self.fx.write("audit.json", {"reviews": [
            {"finding_id": "alpha.F1", "verdict": "disputed", "reason": "r"}]})
        commands.cmd_audit(self.fx.run_dir)
        self.fx.write("report-draft.json", draft(["alpha.F1"]))
        commands.cmd_report(self.fx.run_dir)
        cov = {v["name"]: v for v in self.fx.read("report.json")["coverage"]["validators"]}
        self.assertIn("disputed by audit", cov["beta"]["reason"])

    def test_inconclusive_assumption_and_merge(self):
        result = alpha(excerpt="def evict(self):")
        result["findings"].append(s.finding("alpha.F2", ["alpha.E1"], severity="MAJOR"))
        self.fx.write("results/alpha.json", result)
        commands.cmd_results(self.fx.run_dir, 1)
        self.fx.write("results/beta.json", s.result("beta"))
        commands.cmd_results(self.fx.run_dir, 2)
        self.fx.write("report-draft.json", draft(["alpha.F1", "alpha.F2"]))
        code, out = commands.cmd_report(self.fx.run_dir)
        self.assertEqual(code, 0, out)
        rep = self.fx.read("report.json")
        self.assertEqual(len(rep["findings"]), 1)
        self.assertEqual(rep["findings"][0]["merged_from"], ["alpha.F1", "alpha.F2"])
        acov = {a["id"]: a["status"] for a in rep["coverage"]["assumptions"]}
        self.assertEqual(acov["A1"], "INCONCLUSIVE")

    def test_draft_errors(self):
        self.fx.write("results/alpha.json", alpha(severity="MAJOR"))
        commands.cmd_results(self.fx.run_dir, 1)
        self.fx.write("results/beta.json", s.result("beta"))
        commands.cmd_results(self.fx.run_dir, 2)
        cases = [
            ("omitted finding", draft(), "finding alpha.F1 is not included"),
            ("included twice", draft(["alpha.F1"], ["alpha.F1"]), "finding alpha.F1 is included 2 times"),
            ("unknown finding", draft(["alpha.F1", "beta.F3"]), "R1: unknown finding beta.F3"),
            ("empty merge", draft(["alpha.F1"], []), "R2: merged_from is empty"),
        ]
        for name, d, want in cases:
            with self.subTest(name):
                self.fx.write("report-draft.json", d)
                code, out = commands.cmd_report(self.fx.run_dir)
                self.assertEqual(code, 1)
                self.assertTrue(any(want in e for e in out["errors"]), out["errors"])

    def test_requires_closed_stages(self):
        with self.assertRaises(commands.StateError):
            commands.cmd_report(self.fx.run_dir)


class RenderTest(unittest.TestCase):
    def test_overflow_and_empty(self):
        run = {"run_id": "r", "design_path": "d.md", "design_sha256": "x", "repo_commit": None,
               "worktree_diff_sha256": None, "depth": "quick", "mode": "eval", "blocked_by": [],
               "gate_disputed": False}
        findings = [{"id": f"R{i}", "severity": "MINOR", "category": "ambiguous", "statement": f"s{i}",
                     "tier": "T1", "reasoning_only": False, "audit": "not-audited",
                     "validators": ["extract"], "merged_from": [f"extract.F{i}"],
                     "assumption_ids": [], "evidence_ids": []} for i in range(1, 56)]
        rep = {"run": run, "summary": "", "findings": findings, "checks": [],
               "coverage": {"validators": [], "assumptions": []}, "assumptions": []}
        md = report.render_markdown(rep)
        self.assertIn("**R50**", md)
        self.assertNotIn("**R51**", md)
        self.assertIn("5 more: extract / ambiguous ×5", md)
        empty = report.render_markdown(dict(rep, findings=[]))
        self.assertIn("## All issues (0)", empty)
        self.assertIn("_No summary._", empty)


if __name__ == "__main__":
    unittest.main()
