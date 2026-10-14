import unittest

import _path  # noqa: F401
import check_case

REPORT = {
    "findings": [{"id": "R1", "severity": "MAJOR", "category": "contradicted", "validators": ["fact-check"]}],
    "coverage": {"validators": [{"name": "completeness", "status": "SKIPPED"}]},
}


class CheckCaseTest(unittest.TestCase):
    def test_cases(self):
        cases = [
            ("found", {"must_find": [{"validator": "fact-check", "category": "contradicted",
                                      "min_severity": "MAJOR"}]}, 0),
            ("category list", {"must_find": [{"category": ["unspecified", "contradicted"]}]}, 0),
            ("severity too low", {"must_find": [{"min_severity": "BLOCKER"}]}, 1),
            ("wrong validator", {"must_find": [{"validator": "completeness"}]}, 1),
            ("must not find hit", {"must_not_find": [{"min_severity": "MAJOR"}]}, 1),
            ("must not find clear", {"must_not_find": [{"min_severity": "BLOCKER"}]}, 0),
            ("coverage ok", {"coverage": {"completeness": "SKIPPED"}}, 0),
            ("coverage mismatch", {"coverage": {"completeness": "COMPLETED"}}, 1),
        ]
        for name, expected, want in cases:
            with self.subTest(name):
                self.assertEqual(len(check_case.check(expected, REPORT)), want)


if __name__ == "__main__":
    unittest.main()
