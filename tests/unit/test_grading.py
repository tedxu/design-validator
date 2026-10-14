import copy
import unittest

import _path  # noqa: F401
import samples as s
from dvlib import grading


def manifest(name="alpha", truth=("T1",), max_severity="BLOCKER", blocker=("T1",)):
    return {"name": name, "truth_tiers": list(truth), "max_severity": max_severity,
            "blocker_evidence": list(blocker)}


def ev(eid, source, tier, verified=True, authoritative=None):
    item = {"id": eid, "source": source, "locator": {}, "excerpt": "x", "relation": "refutes",
            "tier": tier, "verified": verified}
    if authoritative is not None:
        item["authoritative"] = authoritative
    return item


CODE = ev("alpha.E1", "code", "T1")
BAD = ev("alpha.E2", "code", "T1", verified=False)
REASON = ev("alpha.E3", "reasoning", "T3", verified="n/a")
DESIGN = ev("alpha.E4", "design", "T1")
AUTH = ev("alpha.E5", "docs", "T2", authoritative=True)
INFO = ev("alpha.E6", "docs", "T2", authoritative=False)
ALL = [CODE, BAD, REASON, DESIGN, AUTH, INFO]


def graded(m, checks=(), findings=()):
    r = s.result(m["name"], checks=checks, findings=findings, evidence=copy.deepcopy(ALL))
    grading.grade_result(r, m)
    return r


class CheckGradingTest(unittest.TestCase):
    def test_cases(self):
        cases = [
            ("t1 pass stays", manifest(), ["alpha.E1"], "PASS", "PASS", "T1"),
            ("t3 only under T1 truth", manifest(), ["alpha.E3"], "PASS", "INCONCLUSIVE", "T3"),
            ("failed evidence only", manifest(), ["alpha.E2"], "ISSUE", "INCONCLUSIVE", None),
            ("no evidence", manifest(), [], "PASS", "INCONCLUSIVE", None),
            ("design ignored outside extract", manifest(), ["alpha.E4"], "ISSUE", "INCONCLUSIVE", None),
            ("design counts for extract", manifest(name="extract", truth=("T1", "T2", "T3")),
             ["extract.E4"], "ISSUE", "ISSUE", "T1"),
            ("t3 allowed when declared", manifest(truth=("T1", "T3")), ["alpha.E3"], "ISSUE", "ISSUE", "T3"),
            ("inconclusive stays", manifest(), ["alpha.E1"], "INCONCLUSIVE", "INCONCLUSIVE", "T1"),
        ]
        for name, m, ev_ids, claimed, want_verdict, want_tier in cases:
            with self.subTest(name):
                prefix = m["name"]
                ids = [i.replace("alpha", prefix) for i in ev_ids]
                r = s.result(prefix, checks=[s.check(f"{prefix}.C1", ids, verdict=claimed)],
                             evidence=[dict(copy.deepcopy(e), id=e["id"].replace("alpha", prefix))
                                       for e in ALL])
                grading.grade_result(r, m)
                c = r["checks"][0]
                self.assertEqual((c["verdict"], c["tier"]), (want_verdict, want_tier))
                self.assertEqual(c["claimed_verdict"], claimed)


class FindingGradingTest(unittest.TestCase):
    def test_cases(self):
        cases = [
            ("t1 blocker stays", manifest(), "BLOCKER", "contradicted", ["alpha.E1"], "BLOCKER", "T1"),
            ("reasoning only capped", manifest(), "MAJOR", "contradicted", ["alpha.E3"], "MINOR", "T3"),
            ("failed evidence becomes t3", manifest(), "MAJOR", "contradicted", ["alpha.E2"], "MINOR", "T3"),
            ("validator cap", manifest(max_severity="MAJOR"), "BLOCKER", "contradicted", ["alpha.E1"],
             "MAJOR", "T1"),
            ("authoritative docs may block", manifest(blocker=("T1", "authoritative-docs")),
             "BLOCKER", "nonconformance", ["alpha.E5"], "BLOCKER", "T2"),
            ("informative docs cannot block", manifest(blocker=("T1", "authoritative-docs")),
             "BLOCKER", "nonconformance", ["alpha.E6"], "MAJOR", "T2"),
            ("t2 cannot block by default", manifest(), "BLOCKER", "impact", ["alpha.E5"], "MAJOR", "T2"),
            ("design counts for ambiguous", manifest(), "MAJOR", "ambiguous", ["alpha.E4"], "MAJOR", "T1"),
            ("design counts for inconsistent", manifest(), "MAJOR", "inconsistent", ["alpha.E4"], "MAJOR", "T1"),
            ("design ignored for contradicted", manifest(), "MAJOR", "contradicted", ["alpha.E4"],
             "MINOR", "T3"),
        ]
        for name, m, claimed, category, ev_ids, want_sev, want_tier in cases:
            with self.subTest(name):
                r = graded(m, findings=[s.finding("alpha.F1", ev_ids, severity=claimed, category=category)])
                f = r["findings"][0]
                self.assertEqual((f["severity"], f["tier"]), (want_sev, want_tier), f.get("grading_note"))
                self.assertEqual(f["reasoning_only"], want_tier == "T3")
                self.assertEqual(f["audit"], "not-audited")

    def test_audit_dispute_and_idempotence(self):
        cases = [("blocker to major", "BLOCKER", "MAJOR"), ("major to minor", "MAJOR", "MINOR"),
                 ("minor stays", "MINOR", "MINOR")]
        for name, claimed, want in cases:
            with self.subTest(name):
                r = graded(manifest(), findings=[s.finding("alpha.F1", ["alpha.E1"], severity=claimed)])
                r["findings"][0]["audit"] = "disputed"
                grading.grade_result(r, manifest())
                grading.grade_result(r, manifest())
                self.assertEqual(r["findings"][0]["severity"], want)


if __name__ == "__main__":
    unittest.main()
