import unittest

import _path  # noqa: F401
import samples as s
from dvlib import structure

DESIGN = "# Design\n\nSegmentCache evicts entries after ttl.\nWe rely on it.\n"


class ResultErrorsTest(unittest.TestCase):
    def test_cases(self):
        d1 = s.ev("v.E2", "design", {"line_start": 3, "line_end": 3}, "SegmentCache evicts entries after ttl.")
        d4 = s.ev("v.E3", "design", {"line_start": 4, "line_end": 4}, "We rely on it.")
        ok = s.result("v", checks=[s.check("v.C1", ["v.E1"])],
                      findings=[s.finding("v.F1", ["v.E1"], check_ids=["v.C1"])],
                      evidence=[s.code_ev("v.E1")])
        cases = [
            ("ok", ok, []),
            ("wrong validator", dict(ok, validator="w"), ["validator is 'w', expected 'v'"]),
            ("bad id prefix", dict(ok, evidence=[s.code_ev("w.E1")]),
             ["w.E1: id must look like v.E<n>", "v.C1: unknown evidence v.E1",
              "v.F1: unknown evidence v.E1"]),
            ("duplicate id", dict(ok, evidence=[s.code_ev("v.E1"), s.code_ev("v.E1")]),
             ["v.E1: duplicate id"]),
            ("unknown assumption", dict(ok, checks=[s.check("v.C1", ["v.E1"], assumption_ids=["A9"])]),
             ["v.C1: unknown assumption A9"]),
            ("unknown check", dict(ok, findings=[s.finding("v.F1", ["v.E1"], check_ids=["v.C7"])]),
             ["v.F1: unknown check v.C7"]),
            ("group numbering accepted", dict(ok, evidence=[s.code_ev("v.E2001")],
                                              checks=[s.check("v.C2001", ["v.E2001"])],
                                              findings=[s.finding("v.F2001", ["v.E2001"],
                                                                  check_ids=["v.C2001"])]),
             []),
            ("inconsistent with one place", dict(ok, findings=[
                s.finding("v.F1", ["v.E2"], category="inconsistent")], evidence=[s.code_ev("v.E1"), d1]),
             ["v.F1: an inconsistent finding cites the conflicting statements: "
              "at least two design evidence items at different lines"]),
            ("inconsistent with the same place twice", dict(ok, findings=[
                s.finding("v.F1", ["v.E2", "v.E3"], category="inconsistent")],
                evidence=[s.code_ev("v.E1"), d1, dict(d1, id="v.E3")]),
             ["v.F1: an inconsistent finding cites the conflicting statements: "
              "at least two design evidence items at different lines"]),
            ("inconsistent with two places", dict(ok, findings=[
                s.finding("v.F1", ["v.E2", "v.E3"], category="inconsistent")],
                evidence=[s.code_ev("v.E1"), d1, d4]),
             []),
        ]
        for name, result, want in cases:
            with self.subTest(name):
                self.assertEqual(structure.result_errors(result, "v", {"A1"}), want)


class AssumptionErrorsTest(unittest.TestCase):
    def test_cases(self):
        a1 = s.assumption()
        cases = [
            ("ok", [a1, s.assumption("A2", 4, "We rely on it.", depends_on=["A1"])], []),
            ("duplicate", [a1, a1], ["A1: duplicate id"]),
            ("unknown dependency", [s.assumption(depends_on=["A5"])], ["A1: depends_on unknown assumption A5"]),
            ("self dependency", [s.assumption(depends_on=["A1"])], ["A1: depends on itself"]),
            ("quote not in design", [s.assumption(quote="Nothing like this")],
             ["A1: anchor excerpt not found in lines 1-4"]),
            ("quote within slack", [s.assumption(line=1)], []),
        ]
        for name, assumptions, want in cases:
            with self.subTest(name):
                self.assertEqual(structure.assumption_errors(assumptions, DESIGN), want)


if __name__ == "__main__":
    unittest.main()
