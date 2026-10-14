import os
import tempfile
import unittest

import _path  # noqa: F401
import helpers as h
import samples as s
from dvlib import commands, hygiene

ZH = "设计声称缓存会在三十秒后自动过期，但代码中没有任何过期逻辑。"
EN = "The design claims the cache expires entries after thirty seconds."


class LanguageTest(unittest.TestCase):
    def test_language(self):
        cases = [
            ("english", EN, "latin"),
            ("chinese", ZH, "cjk"),
            ("chinese with identifiers",
             "设计称 Arrow 构建器仅在源数据比请求行数短时断言 (BuildDenseVectorArray, valid_data)。", "cjk"),
            ("english quoting one cjk word", EN + " The comment says 缓存.", "latin"),
            ("too short", "ok", None),
            ("identifiers only", "fact-check.C1", None),
        ]
        for name, text, want in cases:
            with self.subTest(name):
                self.assertEqual(hygiene.language(text), want)


class OutsidePathsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = os.path.realpath(self.tmp.name)
        self.repo = os.path.join(self.root, "repo")
        self.other = os.path.join(self.root, "other")
        os.makedirs(self.repo)
        os.makedirs(self.other)

    def tearDown(self):
        self.tmp.cleanup()

    def test_outside_paths(self):
        home = os.path.expanduser("~")
        cases = [
            ("inside repo", f"read {self.repo}/store/cache.py", []),
            ("other clone", f"cd {self.other}; git reflog --all", [self.other]),
            ("home tilde", "ran git -C ~/Source/other-project show", ["~/Source/other-project"]),
            ("home var", "ls $HOME/Source", ["$HOME/Source"]),
            ("repo relative", "read internal/core/src/segcore/segment_c.cpp", []),
            ("type list", "accepts STRING/BINARY/BOOL only", []),
            ("url", "see https://example.com/a/b", []),
            ("leading slash, no such root", "the /segcore/plan path", []),
            ("approximate number", "pays above ~250 rows and ~2x", []),
            ("bare home", "cd ~ && ls", ["~"]),
        ]
        for name, text, want in cases:
            with self.subTest(name):
                self.assertEqual(hygiene.outside_paths(text, [self.repo]), want)
        self.assertEqual(hygiene.outside_paths(f"{home}/x", [home]), [])
        self.assertEqual(hygiene.outside_paths(f"writes {self.other}/data", [self.repo],
                                               exempt_text=f"Data goes to {self.other}/data."), [])


class RunTextTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.fx = h.RunFixture(self.tmp.name)
        self.fx.write("assumptions.json", {"assumptions": [s.assumption()]})
        self.fx.write("results/extract.json", s.result("extract"))

    def tearDown(self):
        self.tmp.cleanup()

    def alpha(self, method=None, statement=None, reasoning=None):
        chk = s.check("alpha.C1", ["alpha.E1"])
        if method:
            chk["method"] = method
        fnd = s.finding("alpha.F1", ["alpha.E1"], check_ids=["alpha.C1"], severity="MINOR")
        if statement:
            fnd["statement"] = statement
        evs = [s.code_ev("alpha.E1")]
        if reasoning:
            evs.append(s.ev("alpha.E2", "reasoning", {}, reasoning))
            fnd["evidence_ids"].append("alpha.E2")
        return s.result("alpha", checks=[chk], findings=[fnd], evidence=evs)

    def test_results_rejects_outside_reads_and_wrong_language(self):
        outside = os.path.join(os.path.dirname(os.path.realpath(self.fx.repo)), "plugin-clone")
        os.makedirs(outside)
        cases = [
            ("method reads another clone", self.alpha(method=f"cd {outside}; git reflog --all"),
             "alpha.C1: refers to " + outside),
            ("reasoning cites home", self.alpha(reasoning="In ~/Source/other-project the commit exists."),
             "alpha.E2: refers to ~/Source/other-project"),
            ("statement in another language", self.alpha(statement=ZH),
             "alpha.F1: statement is not in the design's language"),
        ]
        self.assertEqual(commands.cmd_assumptions(self.fx.run_dir)[0], 0)
        for name, result, want in cases:
            with self.subTest(name):
                self.fx.write("results/alpha.json", result)
                code, out = commands.cmd_results(self.fx.run_dir, 1)
                self.assertEqual(code, 1, out)
                self.assertTrue(any(want in e for e in out["errors"]), out["errors"])
                self.assertEqual(self.fx.run()["stages"]["1"], "PENDING")

    def test_plugin_and_prior_paths_are_allowed(self):
        self.assertEqual(commands.cmd_assumptions(self.fx.run_dir)[0], 0)
        prior = os.path.join(self.fx.plugin, "priors", "failure.md")
        self.fx.write("results/alpha.json", self.alpha(method=f"applied {prior} to {self.fx.repo}/store"))
        code, out = commands.cmd_results(self.fx.run_dir, 1)
        self.assertEqual(code, 0, out)

    def test_assumption_statement_language(self):
        bad = s.assumption()
        bad["statement"] = ZH
        self.fx.write("assumptions.json", {"assumptions": [bad]})
        code, out = commands.cmd_assumptions(self.fx.run_dir)
        self.assertEqual(code, 1)
        self.assertTrue(any("A1: statement is not in the design's language" in e for e in out["errors"]),
                        out["errors"])

    def test_report_draft_language(self):
        self.assertEqual(commands.cmd_assumptions(self.fx.run_dir)[0], 0)
        self.fx.write("results/alpha.json", self.alpha())
        self.assertEqual(commands.cmd_results(self.fx.run_dir, 1)[0], 0)
        self.fx.write("results/beta.json", s.result("beta"))
        self.assertEqual(commands.cmd_results(self.fx.run_dir, 2)[0], 0)
        self.fx.write("report-draft.json", {"summary": ZH, "findings": [
            {"id": "R1", "merged_from": ["alpha.F1"], "category": "contradicted", "statement": EN}]})
        code, out = commands.cmd_report(self.fx.run_dir)
        self.assertEqual(code, 1)
        self.assertTrue(any("summary is not in the design's language" in e for e in out["errors"]),
                        out["errors"])


class ChineseDesignTest(unittest.TestCase):
    def test_chinese_design_accepts_chinese_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            design = "# 设计\n\n" + ZH + "\n我们依赖这一点。\n"
            fx = h.RunFixture(tmp, design=design)
            a = s.assumption(quote=ZH)
            fx.write("assumptions.json", {"assumptions": [a]})
            fx.write("results/extract.json", s.result("extract"))
            code, out = commands.cmd_assumptions(fx.run_dir)
            self.assertEqual(code, 0, out)


class CommandValidatorTextTest(unittest.TestCase):
    def test_command_output_skips_language_but_not_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = h.RunFixture(tmp, validators={"cmdv": (1, {"kind": "command", "scope": "assumption",
                                                             "targets": ["current-fact"]})})
            fx.write("assumptions.json", {"assumptions": [s.assumption()]})
            fx.write("results/extract.json", s.result("extract"))
            self.assertEqual(commands.cmd_assumptions(fx.run_dir)[0], 0)
            chk = s.check("cmdv.C1", ["cmdv.E1"])
            fnd = s.finding("cmdv.F1", ["cmdv.E1"], check_ids=["cmdv.C1"], severity="MINOR")
            fnd["statement"] = ZH
            fx.write("results/cmdv.json", s.result("cmdv", checks=[chk], findings=[fnd],
                                                   evidence=[s.code_ev("cmdv.E1")]))
            code, out = commands.cmd_results(fx.run_dir, 1)
            self.assertEqual(code, 0, out)

            fx2 = h.RunFixture(tempfile.mkdtemp(dir=tmp), validators={
                "cmdv": (1, {"kind": "command", "scope": "assumption", "targets": ["current-fact"]})})
            fx2.write("assumptions.json", {"assumptions": [s.assumption()]})
            fx2.write("results/extract.json", s.result("extract"))
            self.assertEqual(commands.cmd_assumptions(fx2.run_dir)[0], 0)
            chk2 = dict(chk, method="cd ~/Source/other && git log")
            fx2.write("results/cmdv.json", s.result("cmdv", checks=[chk2],
                                                    evidence=[s.code_ev("cmdv.E1")]))
            code, out = commands.cmd_results(fx2.run_dir, 1)
            self.assertEqual(code, 1)
            self.assertTrue(any("refers to ~/Source/other" in e for e in out["errors"]), out["errors"])


if __name__ == "__main__":
    unittest.main()
