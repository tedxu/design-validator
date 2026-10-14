import unittest

import _path  # noqa: F401
import samples as s
from dvlib import schema

NAMES = ("assumptions", "result", "audit", "report-draft")

VALID_RESULT = s.result(
    "fact-check",
    checks=[s.check("fact-check.C1", ["fact-check.E1"])],
    findings=[s.finding("fact-check.F1", ["fact-check.E1"], check_ids=["fact-check.C1"])],
    evidence=[s.code_ev("fact-check.E1")],
)


def _without(d, key):
    return {k: v for k, v in d.items() if k != key}


class SchemaFilesTest(unittest.TestCase):
    def test_keywords_supported(self):
        for name in NAMES:
            with self.subTest(name):
                schema.check_schema(schema.load_schema(name))

    def test_samples(self):
        bad_kind = dict(s.assumption(), kind="guess")
        no_locator = _without(s.code_ev("fact-check.E1"), "locator")
        graded = dict(s.code_ev("fact-check.E1"), tier="T1", verified=True,
                      content_sha256="ab", content_origin="commit")
        cases = [
            ("assumptions ok", "assumptions", {"assumptions": [s.assumption()]}, True),
            ("assumptions bad kind", "assumptions", {"assumptions": [bad_kind]}, False),
            ("assumptions bad id", "assumptions", {"assumptions": [dict(s.assumption(), id="X1")]}, False),
            ("result ok", "result", VALID_RESULT, True),
            ("result graded fields allowed", "result", dict(VALID_RESULT, evidence=[graded]), True),
            ("result evidence without locator", "result", dict(VALID_RESULT, evidence=[no_locator]), False),
            ("result bad status", "result", dict(VALID_RESULT, status="SKIPPED"), False),
            ("audit ok", "audit",
             {"reviews": [{"finding_id": "fact-check.F1", "verdict": "disputed", "reason": "r",
                           "external_checks": [{"evidence_id": "fact-check.E2", "confirmed": False}]}]},
             True),
            ("audit bad verdict", "audit",
             {"reviews": [{"finding_id": "x.F1", "verdict": "maybe", "reason": "r"}]}, False),
            ("draft ok", "report-draft",
             {"summary": "s", "findings": [{"id": "R1", "merged_from": ["fact-check.F1"],
                                            "category": "contradicted", "statement": "s"}]},
             True),
            ("draft bad id", "report-draft",
             {"summary": "s", "findings": [{"id": "F1", "merged_from": [], "category": "contradicted",
                                            "statement": "s"}]},
             False),
        ]
        for name, schema_name, instance, ok in cases:
            with self.subTest(name):
                errors = schema.validate(instance, schema.load_schema(schema_name))
                self.assertEqual(errors == [], ok, errors)


if __name__ == "__main__":
    unittest.main()
