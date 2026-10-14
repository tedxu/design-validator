import json
import os
import subprocess
import tempfile
import unittest

import _path  # noqa: F401
from dvlib import registry

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CASES = os.path.join(ROOT, "tests", "cases")
KEYS = {"must_find", "must_not_find", "coverage", "args"}
FILTER_KEYS = {"validator", "category", "min_severity"}
ALL = ["authoritative-doc", "blocker-gate", "broken-consumer", "inference-gap", "path-check",
       "perf-claim", "reinvented-facility", "sound-design", "stale-fact", "unspecified-retry"]


class CaseFixtureTest(unittest.TestCase):
    def test_case_set(self):
        names = sorted(d for d in os.listdir(CASES) if os.path.isdir(os.path.join(CASES, d)))
        self.assertEqual(names, ALL)

    def test_each_fixture_builds_a_loadable_repo(self):
        for name in ALL:
            with self.subTest(name), tempfile.TemporaryDirectory() as tmp:
                with open(os.path.join(CASES, name, "expected.json"), encoding="utf-8") as f:
                    expected = json.load(f)
                self.assertLessEqual(set(expected), KEYS)
                for want in expected.get("must_find", []) + expected.get("must_not_find", []):
                    self.assertLessEqual(set(want), FILTER_KEYS)
                args = expected.get("args", "").split()
                self.assertTrue(all(a in ("--depth", "quick", "standard", "deep") for a in args), args)
                subprocess.run(["bash", os.path.join(CASES, name, "fixture.sh")], cwd=tmp, check=True,
                               capture_output=True)
                self.assertTrue(os.path.isfile(os.path.join(tmp, "docs", "design.md")))
                status = subprocess.run(["git", "status", "--porcelain"], cwd=tmp, check=True,
                                        capture_output=True, text=True).stdout.split("\n")
                untracked = [l for l in status if l]
                self.assertEqual(len(untracked), 1, untracked)
                self.assertIn(untracked[0], ("?? docs/", "?? docs/design.md"))
                config = registry.load_config(tmp)
                reg = registry.load_registry(tmp, config, plugin_root=ROOT)
                named = {w["validator"] for w in expected.get("must_find", []) if "validator" in w}
                named |= set(expected.get("coverage", {}))
                self.assertLessEqual(named, set(reg))


if __name__ == "__main__":
    unittest.main()
