import os
import re
import tempfile
import unittest

import _path  # noqa: F401
from dvlib import registry, sources

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class BuiltinTest(unittest.TestCase):
    def test_registry_loads(self):
        with tempfile.TemporaryDirectory() as repo:
            reg = registry.load_registry(repo, registry.load_config(repo), plugin_root=ROOT)
        want = {
            "extract": (0, "design", True, "BLOCKER", ["ANY"], "low"),
            "fact-check": (1, "assumption", True, "BLOCKER", ["T1"], "medium"),
            "conformance": (1, "design", True, "BLOCKER", ["T1", "authoritative-docs"], "low"),
            "inference": (2, "assumption", True, "BLOCKER", ["T1"], "medium"),
            "impact": (2, "design", True, "BLOCKER", ["T1"], "high"),
            "claims": (2, "assumption", False, "MAJOR", ["T1"], "medium"),
            "alternatives": (3, "design", False, "MINOR", ["T1"], "low"),
            "simplicity": (3, "design", False, "MAJOR", ["T1"], "low"),
            "completeness": (3, "design", False, "MAJOR", ["T1"], "medium"),
        }
        for name, fields in want.items():
            with self.subTest(name):
                m = reg[name]
                self.assertEqual((m["stage"], m["scope"], m["can_block"], m["max_severity"],
                                  m["blocker_evidence"], m["cost"]), fields)

    def test_prior_headings_unique_and_resolvable(self):
        want = {
            "distributed-failure-modes.md": 10,
            "compatibility-rules.md": 7,
            "consistency-patterns.md": 7,
            "performance-evidence.md": 7,
        }
        self.assertEqual(sorted(os.listdir(os.path.join(ROOT, "priors"))), sorted(want))
        for pack, count in want.items():
            with open(os.path.join(ROOT, "priors", pack), encoding="utf-8") as f:
                text = f.read()
            headings = re.findall(r"^## (.+)$", text, flags=re.M)
            with self.subTest(pack):
                self.assertEqual(len(headings), count)
                self.assertEqual(len(headings), len(set(headings)))
                self.assertRegex(text, r"^# .+\n\nPrior knowledge pack for ")
            for heading in headings:
                with self.subTest(f"{pack}: {heading}"):
                    section = sources.markdown_section(text, heading)
                    self.assertIsNotNone(section)
                    self.assertIn("Applies when", section)

    def test_prompts_reference_rules(self):
        names = sorted(os.listdir(os.path.join(ROOT, "validators")))
        for name in names:
            with self.subTest(name):
                with open(os.path.join(ROOT, "validators", name, "prompt.md"), encoding="utf-8") as f:
                    text = f.read()
                self.assertIn("rules/evidence.md", text)
                self.assertNotRegex(text.lower(), r"\bsuggest(ed)? fix")
                self.assertRegex(text, r"\n## Severity\n")

    def test_builtin_set(self):
        self.assertEqual(sorted(os.listdir(os.path.join(ROOT, "validators"))),
                         ["alternatives", "claims", "completeness", "conformance", "extract",
                          "fact-check", "impact", "inference", "simplicity"])


if __name__ == "__main__":
    unittest.main()
