import json
import os
import tempfile
import unittest

import _path  # noqa: F401
from dvlib import evalscore

SHA_FIX = "a" * 40
SHA_REV = "b" * 40
CASE = {"case_id": "c", "design_path": "d.md", "baseline_kind": "as-built",
        "revisions": [SHA_REV], "fixes": [SHA_FIX], "snapshot": "snapshot"}


def item(gid, source="fix", tier="T1", commits=None, reviewed=False):
    return {"id": gid, "statement": "s", "source": source,
            "commits": commits if commits is not None else ([SHA_FIX[:7]] if source == "fix" else [SHA_REV]),
            "tier": tier, "reviewed": reviewed}


def finding(fid, severity="MAJOR", validators=("fact-check",)):
    return {"id": fid, "severity": severity, "category": "contradicted", "statement": "s",
            "validators": list(validators)}


def match(fid, verdict="match", truth_ids=("G1",)):
    return {"finding_id": fid, "verdict": verdict,
            "truth_ids": list(truth_ids) if verdict == "match" else [], "reason": "r"}


class TruthErrorsTest(unittest.TestCase):
    def test_cases(self):
        cases = [
            ("valid", [item("G1"), item("G2", "revision", "T2")], []),
            ("empty list", [], []),
            ("duplicate id", [item("G1"), item("G1")], ["G1: duplicate id"]),
            ("foreign commit", [item("G1", commits=["c" * 7])],
             ["G1: ccccccc is not one of this case's fix commits"]),
            ("revision cites a fix commit", [item("G1", "revision", "T2", commits=[SHA_FIX])],
             ["G1: " + SHA_FIX + " is not one of this case's revision commits"]),
            ("T1 needs a fix", [item("G1", "revision", "T1")], ["G1: tier T1 requires source 'fix'"]),
            ("no commits", [item("G1", commits=[])], ["G1: cite at least one commit"]),
        ]
        for name, items, want in cases:
            with self.subTest(name):
                self.assertEqual(evalscore.truth_errors({"items": items}, CASE), want)
        with self.subTest("schema"):
            errs = evalscore.truth_errors({"items": [dict(item("G1"), source="review")]}, CASE)
            self.assertTrue(errs and errs[0].startswith("$"), errs)


class MatchErrorsTest(unittest.TestCase):
    def test_cases(self):
        rep = {"findings": [finding("R1"), finding("R2")]}
        truth = {"items": [item("G1")]}
        cases = [
            ("valid", [match("R1"), match("R2", "unrelated")], []),
            ("missing finding", [match("R1")], ["R2: missing from matches"]),
            ("listed twice", [match("R1"), match("R1", "refuted"), match("R2", "unrelated")],
             ["R1: listed 2 times"]),
            ("unknown finding", [match("R1"), match("R2", "unrelated"), match("R9", "unrelated")],
             ["R9: not a finding of this run"]),
            ("match without truth", [dict(match("R1"), truth_ids=[]), match("R2", "unrelated")],
             ["R1: a match names at least one truth id"]),
            ("unrelated with truth", [match("R1"), dict(match("R2", "unrelated"), truth_ids=["G1"])],
             ["R2: only a match names truth ids"]),
            ("unknown truth id", [match("R1", truth_ids=["G7"]), match("R2", "unrelated")],
             ["R1: unknown truth id G7"]),
        ]
        for name, matches, want in cases:
            with self.subTest(name):
                self.assertEqual(evalscore.match_errors({"matches": matches}, rep, truth), want)


class ScoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.eval_dir = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, rel, data):
        path = os.path.join(self.eval_dir, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)

    def make_case(self, cid, kind, truth, findings, matches, evidence, coverage, seconds, cost):
        self.write(f"{cid}/case.json", dict(CASE, case_id=cid, baseline_kind=kind))
        run = "snapshot/.dv/runs/r1"
        self.write(f"{cid}/run-result.json", {"case_id": cid, "run_dir": run, "seconds": seconds,
                                              "cost_usd": cost, "exit": 0, "error": None})
        self.write(f"{cid}/{run}/report.json", {"findings": findings, "coverage": coverage})
        self.write(f"{cid}/{run}/results/v.json", {"evidence": [{"verified": v} for v in evidence]})
        self.write(f"{cid}/truth.json", {"items": truth})
        if matches is not None:
            self.write(f"{cid}/matches.json", {"matches": matches})

    def test_metrics(self):
        cov_gaps = {"validators": [{"status": "COMPLETED"}, {"status": "SKIPPED"}],
                    "assumptions": [{"status": "CHECKED"}, {"status": "NOT_CHECKED"}]}
        cov_ok = {"validators": [{"status": "COMPLETED"}], "assumptions": [{"status": "CHECKED"}]}
        self.make_case(
            "a", "as-built", [item("G1"), item("G2", "revision", "T2")],
            [finding("R1", "BLOCKER"), finding("R2", "MINOR", ["completeness"]),
             finding("R3", "MAJOR", ["completeness", "simplicity"])],
            [match("R1"), match("R2", "unrelated"), match("R3", "refuted")],
            [True, True, True, False, "n/a"], cov_gaps, 100, 2.0)
        self.make_case("b", "pre-implementation", [item("G1", reviewed=True)], [finding("R1")],
                       [match("R1")], [True, True], cov_ok, 200, 4.0)
        self.make_case("c", "as-built", [item("G1")], [finding("R1")], None, [], cov_ok, 50, 1.0)

        out = evalscore.score(self.eval_dir)
        self.assertEqual([c["case_id"] for c in out["cases"]], ["a", "b"])
        self.assertEqual(out["excluded"], [{"case_id": "c", "reason": "missing matches.json"}])
        r = out["recall"]
        cases = [
            ("recall all", r["all"], {"hit": 2, "total": 3, "recall": 0.667}),
            ("recall T1", r["by_tier"]["T1"], {"hit": 2, "total": 2, "recall": 1.0}),
            ("recall T2", r["by_tier"]["T2"], {"hit": 0, "total": 1, "recall": 0.0}),
            ("recall unreviewed", r["by_reviewed"]["False"], {"hit": 1, "total": 2, "recall": 0.5}),
            ("recall reviewed", r["by_reviewed"]["True"], {"hit": 1, "total": 1, "recall": 1.0}),
            ("recall as-built", r["by_baseline_kind"]["as-built"], {"hit": 1, "total": 2, "recall": 0.5}),
        ]
        p = out["precision"]
        cases += [
            ("precision all", p["all"],
             {"findings": 4, "match": 2, "refuted": 1, "strict": 0.5, "lenient": 0.667}),
            ("precision MINOR", p["by_severity"]["MINOR"],
             {"findings": 1, "match": 0, "refuted": 0, "strict": 0.0, "lenient": None}),
            ("precision MAJOR", p["by_severity"]["MAJOR"],
             {"findings": 2, "match": 1, "refuted": 1, "strict": 0.5, "lenient": 0.5}),
            ("precision completeness", p["by_validator"]["completeness"],
             {"findings": 2, "match": 0, "refuted": 1, "strict": 0.0, "lenient": 0.0}),
            ("precision fact-check", p["by_validator"]["fact-check"],
             {"findings": 2, "match": 2, "refuted": 0, "strict": 1.0, "lenient": 1.0}),
        ]
        cases += [
            ("blocker false positives", out["blocker_false_positives"], 0),
            ("citation failure rate", out["citation_failure_rate"], 0.167),
            ("coverage gaps", out["coverage_gaps"], 2),
            ("avg seconds", out["avg_seconds"], 150.0),
            ("avg cost", out["avg_cost_usd"], 3.0),
            ("truth reviewed", out["truth_reviewed"], False),
        ]
        for name, got, want in cases:
            with self.subTest(name):
                self.assertEqual(got, want)
        md = evalscore.render_markdown(out)
        for text in ("# Design validator evaluation", "not reviewed", "| recall | 2/3 (0.667) |",
                     "missing matches.json", "| MINOR | 1 | 0 | 0 | 0.0 | n/a |"):
            with self.subTest(text):
                self.assertIn(text, md)

    def test_markdown_rounds_case_values(self):
        cov = {"validators": [], "assumptions": []}
        self.make_case("a", "as-built", [item("G1")], [finding("R1")], [match("R1")], [], cov,
                       1, 1.7925282000000005)
        md = evalscore.render_markdown(evalscore.score(self.eval_dir))
        self.assertIn("| 1 | 1.793 |", md)
        self.assertNotIn("1.7925282", md)

    def test_blocker_false_positive_counted(self):
        cov = {"validators": [], "assumptions": []}
        self.make_case("a", "as-built", [item("G1")],
                       [finding("R1", "BLOCKER"), finding("R2", "BLOCKER")],
                       [match("R1", "refuted"), match("R2")], [], cov, 1, 1.0)
        self.assertEqual(evalscore.score(self.eval_dir)["blocker_false_positives"], 1)

    def test_result_with_error_but_report_is_scored(self):
        cov = {"validators": [], "assumptions": []}
        self.make_case("a", "as-built", [item("G1")], [finding("R1")], [match("R1")], [], cov, 1, 1.0)
        self.write("a/run-result.json", {"case_id": "a", "run_dir": "snapshot/.dv/runs/r1",
                                         "seconds": 1, "cost_usd": 1.0, "exit": 1,
                                         "error": "claude timed out after 1s"})
        out = evalscore.score(self.eval_dir)
        self.assertEqual([c["case_id"] for c in out["cases"]], ["a"])
        self.assertEqual(out["excluded"], [])

    def test_malformed_json_excludes_case_naming_file(self):
        cov = {"validators": [], "assumptions": []}
        for name in ("truth.json", "matches.json", "snapshot/.dv/runs/r1/report.json"):
            with self.subTest(name):
                self.make_case("a", "as-built", [item("G1")], [finding("R1")], [match("R1")],
                               [], cov, 1, 1.0)
                self.make_case("b", "as-built", [item("G1")], [finding("R1")], [match("R1")],
                               [], cov, 1, 1.0)
                path = os.path.join(self.eval_dir, "a", name)
                with open(path, "w", encoding="utf-8") as f:
                    f.write("{not json")
                out = evalscore.score(self.eval_dir)
                self.assertEqual([c["case_id"] for c in out["cases"]], ["b"])
                self.assertEqual(len(out["excluded"]), 1)
                self.assertIn(os.path.basename(name), out["excluded"][0]["reason"])
                self.assertIn("unreadable", out["excluded"][0]["reason"])

    def test_empty_and_invalid(self):
        out = evalscore.score(self.eval_dir)
        self.assertEqual((out["cases"], out["recall"]["all"]["recall"], out["precision"]["all"]["strict"],
                          out["citation_failure_rate"], out["avg_seconds"], out["truth_reviewed"]),
                         ([], None, None, None, None, False))
        self.assertIn("n/a", evalscore.render_markdown(out))
        self.make_case("x", "as-built", [item("G1", commits=["c" * 7])], [], [], [],
                       {"validators": [], "assumptions": []}, 1, None)
        out = evalscore.score(self.eval_dir)
        self.assertEqual(out["excluded"][0]["case_id"], "x")
        self.assertIn("invalid", out["excluded"][0]["reason"])
        json_path, md_path = evalscore.write_report(self.eval_dir, out)
        self.assertTrue(os.path.isfile(json_path) and os.path.isfile(md_path))


if __name__ == "__main__":
    unittest.main()
