import os
import tempfile
import unittest

import _path  # noqa: F401
import helpers as h
from dvlib import registry


class ManifestTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.vdir = os.path.join(self.tmp.name, "validators")

    def tearDown(self):
        self.tmp.cleanup()

    def load(self, dirname, stage, **fields):
        h.write_validator(self.vdir, dirname, stage, **fields)
        return registry.load_manifest(os.path.join(self.vdir, dirname), "builtin")

    def test_defaults(self):
        cases = [
            ("cannot block", {}, "MAJOR", ["T1"]),
            ("can block", {"can_block": True}, "BLOCKER", ["T1"]),
            ("explicit cap", {"max_severity": "MINOR"}, "MINOR", ["T1"]),
        ]
        for name, fields, want_max, want_be in cases:
            with self.subTest(name):
                m = self.load("v", 1, **fields)
                self.assertEqual(m["max_severity"], want_max)
                self.assertEqual(m["blocker_evidence"], want_be)
                self.assertEqual(m["origin"], "builtin")

    def test_invalid(self):
        cases = [
            ("name mismatch", "v", 1, {"name": "other"}),
            ("bad kind", "v", 1, {"kind": "llm"}),
            ("stage 0 reserved", "v", 0, {}),
            ("extract must be stage 0", "extract", 1, {}),
            ("assumption scope needs targets", "v", 1, {"scope": "assumption"}),
            ("bad target", "v", 1, {"scope": "assumption", "targets": ["fact"]}),
            ("bad tier", "v", 1, {"truth_tiers": ["T4"]}),
            ("blocker cap needs can_block", "v", 1, {"max_severity": "BLOCKER"}),
            ("bad blocker evidence", "v", 1, {"blocker_evidence": ["T2"]}),
            ("bad cost", "v", 1, {"cost": "huge"}),
            ("missing entry", "v", 1, {"entry": "missing.md"}),
            ("missing kind", "v", 1, {"kind": h.OMIT}),
            ("unknown field", "v", 1, {"colour": "red"}),
        ]
        for label, name, stage, fields in cases:
            with self.subTest(label):
                with self.assertRaises(registry.RegistryError):
                    self.load(name, stage, **fields)


class RegistryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.plugin = h.make_plugin(self.tmp.name, {
            "alpha": (1, {"cost": "low"}),
            "beta": (2, {"cost": "medium"}),
            "gamma": (3, {"cost": "high"}),
        })
        self.repo = os.path.join(self.tmp.name, "repo")
        os.makedirs(self.repo)

    def tearDown(self):
        self.tmp.cleanup()

    def config(self, text):
        h.write_files(self.repo, {".dv/config.yaml": text})
        return registry.load_config(self.repo)

    def test_select_by_depth(self):
        reg = registry.load_registry(self.repo, registry.load_config(self.repo), plugin_root=self.plugin)
        cases = [
            ("quick", ["extract", "alpha"], {"beta", "gamma"}),
            ("standard", ["extract", "alpha", "beta"], {"gamma"}),
            ("deep", ["extract", "alpha", "beta", "gamma"], set()),
        ]
        for depth, want_sel, want_skip in cases:
            with self.subTest(depth):
                selected, skipped = registry.select(reg, depth)
                self.assertEqual(selected, want_sel)
                self.assertEqual(set(skipped), want_skip)
        with self.assertRaises(registry.RegistryError):
            registry.select(reg, "huge")

    def test_project_overrides_builtin(self):
        h.write_validator(os.path.join(self.repo, ".dv", "validators"), "alpha", 2, cost="medium")
        reg = registry.load_registry(self.repo, registry.load_config(self.repo), plugin_root=self.plugin)
        self.assertEqual(reg["alpha"]["origin"], "project")
        self.assertEqual(reg["alpha"]["stage"], 2)

    def test_config_disable_and_override(self):
        cfg = self.config("validators:\n  disable: [beta]\n  override:\n    gamma: {stage: 1, cost: low}\n")
        reg = registry.load_registry(self.repo, cfg, plugin_root=self.plugin)
        self.assertNotIn("beta", reg)
        self.assertEqual((reg["gamma"]["stage"], reg["gamma"]["cost"]), (1, "low"))

    def test_config_errors(self):
        cases = [
            ("unknown top key", "colour: red\n"),
            ("bad authority", "docs:\n  - path: docs\n    authority: maybe\n"),
            ("escaping path", "docs:\n  - path: ../other\n"),
            ("absolute prior", "priors: [/etc]\n"),
            ("bad history", "history:\n  pr_comments: yes\n"),
        ]
        for name, text in cases:
            with self.subTest(name):
                with self.assertRaises(registry.RegistryError):
                    self.config(text)

    def test_registry_errors(self):
        cases = [
            ("disable extract", "validators:\n  disable: [extract]\n"),
            ("disable unknown", "validators:\n  disable: [nope]\n"),
            ("override field", "validators:\n  override:\n    alpha: {kind: command}\n"),
            ("override to stage 0", "validators:\n  override:\n    alpha: {stage: 0}\n"),
        ]
        for name, text in cases:
            with self.subTest(name):
                cfg = self.config(text)
                with self.assertRaises(registry.RegistryError):
                    registry.load_registry(self.repo, cfg, plugin_root=self.plugin)

    def test_config_values(self):
        cfg = self.config(
            "docs:\n  - path: ./docs/guides\n    authority: authoritative\n  - path: docs/design\n"
            "priors: [.dv/priors]\n")
        self.assertEqual(cfg["docs"], [{"path": "docs/guides", "authority": "authoritative"},
                                       {"path": "docs/design", "authority": "informative"}])
        self.assertEqual(cfg["priors"], [".dv/priors"])
        self.assertEqual(registry.load_config(os.path.join(self.tmp.name, "nowhere"))["docs"], [])


if __name__ == "__main__":
    unittest.main()
