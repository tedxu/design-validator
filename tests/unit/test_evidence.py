import os
import tempfile
import unittest

import _path  # noqa: F401
import helpers as h
import samples as s
from dvlib import evidence, sources

REPO_FILES = {
    "store/cache.py": "class SegmentCache:\n    def get(self, key):\n        return self._data.get(key)\n",
    "docs/rules.md": "# Rules\n\nAll writes go through the WAL.\n",
    "go.mod": "module x\n\nrequire go.etcd.io/etcd/client/v3 v3.5.12\n",
}
PRIOR = "# Failure modes\n\n## Response lost\n\nRetries may duplicate side effects.\n\n## Other\n\nx\n"
DESIGN = "# Design\n\nWe cache segments.\nTTL is configurable.\n"


class VerifyEvidenceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.repo, cls.commit = h.make_repo(cls.tmp.name, REPO_FILES)
        h.git(cls.repo, "checkout", "-q", "-b", "side")
        h.write_files(cls.repo, {"side.txt": "side change\n"})
        h.git(cls.repo, "add", "-A")
        h.git(cls.repo, "commit", "-q", "-m", "side")
        cls.side_commit = h.git(cls.repo, "rev-parse", "HEAD")
        h.git(cls.repo, "checkout", "-q", "main")
        cls.priors = os.path.join(cls.tmp.name, "priors")
        h.write_files(cls.priors, {"failure.md": PRIOR})

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def ctx(self, commit="baseline"):
        commit = self.commit if commit == "baseline" else commit
        return evidence.Context(
            repo_root=self.repo, commit=commit, design_text=DESIGN,
            docs=[{"path": "docs", "authority": "authoritative"}],
            priors=[self.priors], reader=sources.SourceReader(self.repo, commit))

    def test_cases(self):
        E = s.ev
        cases = [
            ("code ok", s.code_ev("x.E1"), True, "T1", None),
            ("code mismatch", s.code_ev("x.E1", excerpt="def evict"), False, "T1", "excerpt not found"),
            ("code path escape", s.code_ev("x.E1", path="../etc/passwd"), False, "T1", "inside the repository"),
            ("code bad locator", E("x.E1", "code", {"path": "store/cache.py", "line_start": 1}, "c"),
             False, "T1", "locator for code"),
            ("code zero line", s.code_ev("x.E1", start=0), False, "T1", "positive integer"),
            ("docs authoritative",
             E("x.E1", "docs", {"path": "docs/rules.md", "line_start": 3, "line_end": 3}, "through the WAL"),
             True, "T2", None),
            ("design with slack",
             E("x.E1", "design", {"line_start": 3, "line_end": 3}, "TTL is configurable."),
             True, "T1", None),
            ("prior ok",
             E("x.E1", "prior", {"pack": "failure.md", "heading": "Response lost"}, "Retries may duplicate"),
             True, "T1", None),
            ("prior wrong section",
             E("x.E1", "prior", {"pack": "failure.md", "heading": "Other"}, "Retries may duplicate"),
             False, "T1", "excerpt not found under"),
            ("prior unknown pack",
             E("x.E1", "prior", {"pack": "none.md", "heading": "Other"}, "x"), False, "T1", "not found"),
            ("external version matched",
             E("x.E1", "external", {"url": "https://etcd.io/docs", "dependency": "go.etcd.io/etcd/client/v3",
                                    "version": "v3.5.12", "version_source": "go.mod:3"}, "Txn is atomic"),
             "n/a", "T1", None),
            ("external version mismatch",
             E("x.E1", "external", {"url": "https://etcd.io/docs", "dependency": "go.etcd.io/etcd/client/v3",
                                    "version": "v3.6.0", "version_source": "go.mod:3"}, "Txn is atomic"),
             "n/a", "T2", "does not mention"),
            ("history ancestor", E("x.E1", "history", {"commit": self.commit}, "class SegmentCache:"),
             True, "T2", None),
            ("history not ancestor", E("x.E1", "history", {"commit": self.side_commit}, "side change"),
             False, "T2", "not an ancestor"),
            ("history url", E("x.E1", "history", {"url": "https://example.invalid/pr/1"}, "review"),
             "n/a", "T2", None),
            ("reasoning", E("x.E1", "reasoning", {}, "because retries resend"), "n/a", "T3", None),
            ("empty reasoning", E("x.E1", "reasoning", {}, " "), False, "T3", "needs the argument"),
            ("sandbox from agent", E("x.E1", "sandbox", {"command": "make t", "output_sha256": "ab"}, "ok"),
             False, "T1", "command validators"),
        ]
        for name, item, want_verified, want_tier, want_error in cases:
            with self.subTest(name):
                evidence.verify_evidence(item, self.ctx())
                self.assertEqual(item["verified"], want_verified, item.get("verify_error"))
                self.assertEqual(item["tier"], want_tier)
                if want_error:
                    self.assertIn(want_error, item["verify_error"])

    def test_docs_authority_and_provenance(self):
        auth = s.ev("x.E1", "docs", {"path": "docs/rules.md", "line_start": 3, "line_end": 3}, "WAL")
        other = s.ev("x.E2", "docs", {"path": "store/cache.py", "line_start": 1, "line_end": 1}, "class")
        evidence.verify_evidence(auth, self.ctx())
        evidence.verify_evidence(other, self.ctx())
        self.assertTrue(auth["authoritative"])
        self.assertFalse(other["authoritative"])
        self.assertEqual(auth["content_origin"], "commit")
        self.assertEqual(len(auth["content_sha256"]), 64)

    def test_sandbox_from_command_validator(self):
        item = s.ev("x.E1", "sandbox", {"command": "make t", "output_sha256": "ab"}, "ok")
        evidence.verify_evidence(item, self.ctx(), kind="command")
        self.assertEqual((item["verified"], item["tier"]), ("n/a", "T1"))

    def test_history_without_git(self):
        item = s.ev("x.E1", "history", {"commit": self.commit}, "class SegmentCache:")
        evidence.verify_evidence(item, self.ctx(commit=None))
        self.assertFalse(item["verified"])

    def test_reverify_is_idempotent(self):
        item = s.code_ev("x.E1", excerpt="def evict")
        evidence.verify_evidence(item, self.ctx())
        item["excerpt"] = "class SegmentCache:"
        evidence.verify_evidence(item, self.ctx())
        self.assertTrue(item["verified"])
        self.assertNotIn("verify_error", item)


if __name__ == "__main__":
    unittest.main()
