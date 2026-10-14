import json
import os
import re
import unittest

import _path  # noqa: F401

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class SkillDocsTest(unittest.TestCase):
    def read(self, rel):
        with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
            return f.read()

    def test_frontmatter(self):
        text = self.read("skills/design-validate/SKILL.md")
        m = re.match(r"---\nname: design-validate\ndescription: (.+)\n---\n", text)
        self.assertIsNotNone(m)

    def test_uses_every_subcommand(self):
        text = self.read("skills/design-validate/SKILL.md")
        for sub in ("init", "assumptions", "results", "audit", "report", "input"):
            with self.subTest(sub):
                self.assertRegex(text, rf"\$VERIFY {sub}\b")

    def test_command_validator_errors_are_never_retried_by_subagent(self):
        text = " ".join(self.read("skills/design-validate/SKILL.md").split())
        self.assertIn("never dispatch a subagent for a `command` validator", text)

    def test_audit_doc_matches_schema(self):
        text = self.read("skills/design-validate/audit.md")
        for field in ("finding_id", "verdict", "reason", "external_checks", "evidence_id", "confirmed"):
            with self.subTest(field):
                self.assertIn(field, text)

    def test_eval_skill(self):
        text = self.read("skills/design-validate-eval/SKILL.md")
        self.assertRegex(text, r"^---\nname: design-validate-eval\ndescription: .+\n---\n")
        for sub in ("prepare", "check-truth", "run", "check-matches", "score"):
            with self.subTest(sub):
                self.assertRegex(text, rf"\$EVAL {sub}\b")
        for ref in ("truth.md", "match.md", "--stop-after prepare"):
            with self.subTest(ref):
                self.assertIn(ref, text)

    def test_eval_prompts_match_schemas(self):
        def load(name):
            with open(os.path.join(ROOT, "schemas", f"{name}.schema.json"), encoding="utf-8") as f:
                return json.load(f)

        def terms(schema, key):
            item = schema["properties"][key]["items"]
            out = set(item["properties"])
            for prop in item["properties"].values():
                out.update(prop.get("enum", []))
            return out

        truth = self.read("skills/design-validate-eval/truth.md")
        for field in terms(load("truth"), "items"):
            with self.subTest(f"truth {field}"):
                self.assertIn(f"`{field}`", truth)
        match = self.read("skills/design-validate-eval/match.md")
        for field in terms(load("matches"), "matches"):
            with self.subTest(f"match {field}"):
                self.assertIn(f"`{field}`", match)

    def test_eval_safety_rules(self):
        skill = " ".join(self.read("skills/design-validate-eval/SKILL.md").split())
        for text in ("no case has valid truth and stop", "`reviewed: true`",
                     "(edits must still pass `check-truth`)",
                     "delete its `matches.json`", "`no_report`", "`truth_reviewed`"):
            with self.subTest(text):
                self.assertIn(text, skill)
        truth = self.read("skills/design-validate-eval/truth.md")
        for text in ("`snapshot/`", "`run-result.json`", "`claude.log`", ".dv/runs"):
            with self.subTest(text):
                self.assertIn(text, truth)
        self.assertIn("Do not change `truth.json`", self.read("skills/design-validate-eval/match.md"))


if __name__ == "__main__":
    unittest.main()
