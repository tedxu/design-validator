import json
import tarfile
import os
import shutil
import subprocess
import tempfile
import unittest

import _path  # noqa: F401
import helpers as h
from dvlib import evalprep, registry

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FIXTURE = os.path.join(ROOT, "tests", "eval", "fixture.sh")
TTL = "docs/design/cache-ttl.md"
FLUSH = "docs/design/flush-retry.md"


def build_fixture(parent):
    repo = os.path.join(parent, "repo")
    os.makedirs(repo)
    subprocess.run(["bash", FIXTURE], cwd=repo, check=True, capture_output=True)
    return repo


def subject(repo, sha):
    return h.git(repo, "show", "-s", "--format=%s", sha)


class GlobTest(unittest.TestCase):
    def test_glob_regex(self):
        cases = [
            ("docs/design/*.md", "docs/design/a.md", True),
            ("docs/design/*.md", "docs/design/sub/a.md", False),
            ("docs/**/*.md", "docs/a.md", True),
            ("docs/**/*.md", "docs/x/y/a.md", True),
            ("docs/**", "docs/x/y", True),
            ("*.md", "docs/a.md", False),
            ("docs/design/?.md", "docs/design/a.md", True),
            ("docs/design/?.md", "docs/design/ab.md", False),
        ]
        for pattern, path, want in cases:
            with self.subTest(f"{pattern} {path}"):
                self.assertEqual(evalprep.matches_any(path, [pattern]), want)


class DiscoverTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.repo = build_fixture(cls.tmp.name)
        cls.globs = registry.load_config(cls.repo)["design_globs"]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_ranking_baselines_and_evolution(self):
        selected, skipped = evalprep.discover(self.repo, self.globs)
        self.assertEqual([c["design_path"] for c in selected], [FLUSH, TTL])
        flush, ttl = selected
        self.assertEqual((flush["baseline_kind"], flush["baseline"]), ("as-built", flush["first_commit"]))
        self.assertEqual(flush["code_paths"], ["coordinator.py", "worker.py"])
        self.assertEqual([subject(self.repo, c) for c in flush["fixes"]],
                         ["fix: deduplicate segments committed twice after a retry"])
        self.assertEqual([subject(self.repo, c) for c in flush["revisions"]],
                         ["doc: describe the idempotent segment commit"])
        self.assertEqual(ttl["baseline_kind"], "pre-implementation")
        self.assertEqual(ttl["baseline"], h.git(self.repo, "rev-parse", ttl["first_commit"] + "^"))
        self.assertEqual(ttl["code_paths"], [])
        self.assertEqual(ttl["watched_paths"], ["store/cache.py", "store/loader.py"])
        self.assertEqual([subject(self.repo, c) for c in ttl["fixes"]],
                         ["fix: evict dropped segments from the cache immediately"])
        self.assertEqual([subject(self.repo, c) for c in ttl["revisions"]],
                         ["doc: correct the cache design, SegmentCache has no TTL"])
        self.assertEqual((flush["richness"], ttl["richness"]), (2, 2))
        self.assertRegex(ttl["case_id"], r"^docs-design-cache-ttl-[0-9a-f]{7}$")
        self.assertEqual(skipped, [{"design_path": "docs/design/cache-size.md",
                                    "reason": "no revisions or fix commits after the first version"}])

    def test_limit_and_explicit_designs(self):
        self.assertEqual([c["design_path"] for c in evalprep.discover(self.repo, self.globs, limit=1)[0]],
                         [FLUSH])
        self.assertEqual([c["design_path"] for c in evalprep.discover(self.repo, self.globs,
                                                                      designs=[TTL])[0]], [TTL])
        cases = [("unknown design", self.globs, ["docs/design/nope.md"]), ("no globs", [], None)]
        for name, globs, designs in cases:
            with self.subTest(name), self.assertRaises(evalprep.EvalError):
                evalprep.discover(self.repo, globs, designs=designs)


class RootCommitTest(unittest.TestCase):
    def test_design_added_in_root_commit_is_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, _ = h.make_repo(tmp, {"docs/design/a.md": "# A\n\nUses `x.py`.\n"})
            h.write_files(repo, {"docs/design/a.md": "# A\n\nRevised.\n"})
            h.git(repo, "commit", "-q", "-am", "revise")
            selected, skipped = evalprep.discover(repo, ["docs/design/*.md"])
            self.assertEqual(selected, [])
            self.assertEqual(skipped[0]["design_path"], "docs/design/a.md")
            self.assertIn("root commit", skipped[0]["reason"])


class EscapesTest(unittest.TestCase):
    """The fallback used when tarfile.data_filter is missing (Python < 3.12 without backport)."""

    def test_members(self):
        def member(name, kind=tarfile.REGTYPE, link=""):
            m = tarfile.TarInfo(name)
            m.type, m.linkname = kind, link
            return m

        with tempfile.TemporaryDirectory() as dest:
            cases = [
                ("plain file", member("a/b.txt"), False),
                ("absolute name", member("/etc/x"), True),
                ("parent name", member("../x"), True),
                ("relative link inside", member("a/l", tarfile.SYMTYPE, "../b.txt"), False),
                ("absolute link", member("a/l", tarfile.SYMTYPE, "/etc/passwd"), True),
                ("link out of tree", member("a/l", tarfile.SYMTYPE, "../../x"), True),
                ("hard link inside", member("h", tarfile.LNKTYPE, "a/b.txt"), False),
                ("hard link outside", member("h", tarfile.LNKTYPE, "../x"), True),
            ]
            for name, m, want in cases:
                with self.subTest(name):
                    self.assertEqual(evalprep._escapes(m, dest), want)


class SnapshotTest(unittest.TestCase):
    def test_run_artifacts_are_not_exported(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, commit = h.make_repo(tmp, {
                "a.py": "x = 1\n", ".dv/config.yaml": "docs: []\n", ".dv/priors/p.md": "# P\n",
                ".dv/runs/r/report.json": "{}\n", ".dv/eval/c/case.json": "{}\n",
                ".dv/active.json": "{}\n"})
            dest = os.path.join(tmp, "snap")
            evalprep.export_snapshot(repo, commit, dest)
            for rel, want in ((".dv/config.yaml", True), (".dv/priors/p.md", True), ("a.py", True),
                              (".dv/runs", False), (".dv/eval", False), (".dv/active.json", False),
                              (".git", False)):
                with self.subTest(rel):
                    self.assertEqual(os.path.exists(os.path.join(dest, rel)), want)

    def test_unsafe_symlinks_are_skipped_not_fatal(self):
        cases = [("absolute target", "a_abs", "/etc/passwd"),
                 ("target outside the tree", "b_up", "../outside")]
        with tempfile.TemporaryDirectory() as tmp:
            repo, _ = h.make_repo(tmp, {"z.py": "x = 1\n"})
            for _, name, target in cases:
                os.symlink(target, os.path.join(repo, name))
            h.git(repo, "add", "-A")
            h.git(repo, "commit", "-q", "-m", "links")
            dest = os.path.join(tmp, "snap")
            evalprep.export_snapshot(repo, "HEAD", dest)
            self.assertTrue(os.path.isfile(os.path.join(dest, "z.py")))
            for label, name, _ in cases:
                with self.subTest(label):
                    self.assertFalse(os.path.lexists(os.path.join(dest, name)))

    def test_bad_commit(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, _ = h.make_repo(tmp, {"a.py": "x\n"})
            with self.assertRaises(evalprep.EvalError):
                evalprep.export_snapshot(repo, "0" * 40, os.path.join(tmp, "snap"))


class PrepareTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = build_fixture(self.tmp.name)
        self.globs = registry.load_config(self.repo)["design_globs"]
        self.eval_dir = os.path.join(self.repo, ".dv", "eval")

    def tearDown(self):
        self.tmp.cleanup()

    def read(self, *parts):
        with open(os.path.join(*parts), encoding="utf-8") as f:
            return f.read()

    def test_case_contents(self):
        out = evalprep.prepare(self.repo, self.eval_dir, self.globs)
        self.assertEqual([c["design_path"] for c in out["cases"]], [FLUSH, TTL])
        self.assertTrue(all(c["created"] for c in out["cases"]))
        by_path = {c["design_path"]: c["case_dir"] for c in out["cases"]}

        ttl = by_path[TTL]
        v1 = self.read(ttl, "evolution", "design-v1.md")
        self.assertIn("ttl_seconds", v1)
        self.assertEqual(self.read(ttl, "snapshot", TTL), v1)
        self.assertIn("cache.invalidate(segment_id)", self.read(ttl, "snapshot", "store", "loader.py"))
        self.assertFalse(os.path.exists(os.path.join(ttl, "snapshot", ".git")))
        self.assertTrue(os.path.isfile(os.path.join(ttl, "snapshot", ".dv", "config.yaml")))
        self.assertIn("Subject: doc: correct the cache design", self.read(ttl, "evolution", "revisions.patch"))
        self.assertIn("Subject: fix: evict dropped segments", self.read(ttl, "evolution", "fixes.patch"))
        case = json.loads(self.read(ttl, "case.json"))
        self.assertEqual((case["baseline_kind"], case["snapshot"], case["evolution"]),
                         ("pre-implementation", "snapshot", "evolution"))

        flush = by_path[FLUSH]
        self.assertEqual(self.read(flush, "snapshot", FLUSH), self.read(flush, "evolution", "design-v1.md"))
        self.assertIn("uuid.uuid4()", self.read(flush, "snapshot", "worker.py"))
        self.assertNotIn("idempotent", self.read(flush, "snapshot", FLUSH))

    def test_eval_dir_ignores_itself(self):
        ignore = os.path.join(self.eval_dir, ".gitignore")
        evalprep.prepare(self.repo, self.eval_dir, self.globs)
        self.assertEqual(self.read(ignore), "*\n")
        self.assertNotIn(".dv/eval", h.git(self.repo, "status", "--porcelain"))
        with open(ignore, "w") as f:
            f.write("custom\n")
        evalprep.prepare(self.repo, self.eval_dir, self.globs)
        self.assertEqual(self.read(ignore), "custom\n")

    def test_prepare_is_idempotent_and_replaces_partial_dirs(self):
        first = evalprep.prepare(self.repo, self.eval_dir, self.globs)
        stale = first["cases"][0]["case_dir"] + ".partial"
        os.makedirs(os.path.join(stale, "junk"))
        case_json = os.path.join(first["cases"][1]["case_dir"], "case.json")
        before = os.stat(case_json).st_mtime_ns
        shutil.rmtree(first["cases"][0]["case_dir"])
        second = evalprep.prepare(self.repo, self.eval_dir, self.globs)
        self.assertEqual([c["created"] for c in second["cases"]], [True, False])
        self.assertEqual(os.stat(case_json).st_mtime_ns, before)
        self.assertFalse(os.path.exists(stale))
        self.assertFalse(os.path.exists(os.path.join(first["cases"][0]["case_dir"], "junk")))


class NoiseTest(unittest.TestCase):
    """Binary, lockfile, CI and generated paths are not code the design is about."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo, _ = h.make_repo(self.tmp.name, {"base.py": "x = 1\n"})
        self.commit("feat: add d", {
            "docs/design/d.md": "# D\n\nUses `code.go` and `go.mod`.\n",
            "code.go": "package x\n", "go.mod": "module x\n", "go.sum": "a v1\n",
            "logo.png": "\x00PNG\x00\x01", ".github/x.yml": "on: push\n",
            "api/mock_store.go": "package api\n", "api/x.pb.go": "package api\n",
            "api/zz_generated.go": "package api\n"})
        self.commit("fix: bump deps", {"go.sum": "a v2\n"})
        self.commit("fix: handle nil", {"code.go": "package x // nil\n", "go.sum": "a v3\n",
                                        "logo.png": "\x00PNG\x00\x02"})
        self.commit("doc: revise d", {"docs/design/d.md": "# D\n\nRevised.\n"})
        self.commit("feat: add e", {"docs/design/e.md": "# E\n", "diagram.png": "\x00\x01\x02"})
        self.commit("doc: revise e", {"docs/design/e.md": "# E\n\nRevised.\n"})
        self.globs = ["docs/design/*.md"]

    def commit(self, msg, files):
        h.write_files(self.repo, files)
        h.git(self.repo, "add", "-A")
        h.git(self.repo, "commit", "-q", "-m", msg)

    def by_path(self):
        return {c["design_path"]: c for c in evalprep.discover(self.repo, self.globs)[0]}

    def test_noise_is_not_watched_and_not_code(self):
        d, e = self.by_path()["docs/design/d.md"], self.by_path()["docs/design/e.md"]
        self.assertEqual((d["code_paths"], d["watched_paths"]), (["code.go"], ["code.go"]))
        self.assertEqual([subject(self.repo, c) for c in d["fixes"]], ["fix: handle nil"])
        self.assertEqual((e["baseline_kind"], e["code_paths"]), ("pre-implementation", []))

    def test_is_noise(self):
        cases = [("go.sum", True), ("sub/package-lock.json", True), ("requirements-dev.txt", True),
                 ("x/Cargo.lock", True), (".github/workflows/ci.yml", True),
                 (".gitlab-ci.yml", True), (".circleci/config.yml", True),
                 ("a/mock_store.go", True), ("a/store_mock.go", True), ("a/x.pb.go", True),
                 ("a/x_pb2.py", True), ("a/zz_generated.deepcopy.go", True),
                 ("code.go", False), ("docs/lock.md", False), ("store/cache.py", False)]
        for path, want in cases:
            with self.subTest(path):
                self.assertEqual(evalprep.is_noise(path), want)

    def test_fixes_patch_has_only_watched_paths(self):
        eval_dir = os.path.join(self.tmp.name, "eval")
        out = evalprep.prepare(self.repo, eval_dir, self.globs, designs=["docs/design/d.md"])
        with open(os.path.join(out["cases"][0]["case_dir"], "evolution", "fixes.patch")) as f:
            patch = f.read()
        self.assertIn("code.go", patch)
        self.assertNotIn("go.sum", patch)
        self.assertNotIn("logo.png", patch)


class RenameTest(unittest.TestCase):
    def test_renamed_design_keeps_its_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, _ = h.make_repo(tmp, {"base.py": "x = 1\n"})
            old, new = "docs/design/old.md", "docs/design/new.md"

            def commit(msg, files):
                h.write_files(repo, files)
                h.git(repo, "add", "-A")
                h.git(repo, "commit", "-q", "-m", msg)

            commit("doc: add design", {old: "# Old\n\nVersion one of the design.\nIt has lines.\n"})
            v1 = h.git(repo, "rev-parse", "HEAD")
            commit("doc: revise before rename",
                   {old: "# Old\n\nVersion two of the design.\nIt has lines.\n"})
            h.git(repo, "mv", old, new)
            h.git(repo, "commit", "-q", "-m", "doc: move design")
            commit("doc: revise after rename",
                   {new: "# Old\n\nVersion three of the design.\nIt has lines.\n"})
            selected, _ = evalprep.discover(repo, ["docs/design/*.md"])
            self.assertEqual(len(selected), 1)
            cand = selected[0]
            self.assertEqual((cand["design_path"], cand["first_commit"], cand["first_path"]),
                             (new, v1, old))
            self.assertEqual([subject(repo, c) for c in cand["revisions"]],
                             ["doc: revise before rename", "doc: revise after rename"])
            out = evalprep.prepare(repo, os.path.join(tmp, "eval"), ["docs/design/*.md"])
            case_dir = out["cases"][0]["case_dir"]
            with open(os.path.join(case_dir, "snapshot", old)) as f:
                self.assertIn("Version one", f.read())
            self.assertFalse(os.path.exists(os.path.join(case_dir, "snapshot", new)))
            with open(os.path.join(case_dir, "evolution", "revisions.patch")) as f:
                patch = f.read()
            self.assertIn("Version two", patch)
            self.assertIn("Version three", patch)
            with open(os.path.join(case_dir, "case.json")) as f:
                self.assertEqual(json.load(f)["first_path"], old)


class CapTest(unittest.TestCase):
    def test_cap(self):
        cases = [("short", "abc\n", 10, "abc\n"),
                 ("long", "a" * 30, 10, "a" * 10 + "\n[truncated: 20 more bytes]\n"),
                 ("multibyte", "\u00e9" * 6, 5, "\u00e9\u00e9\n[truncated: 8 more bytes]\n")]
        for name, text, limit, want in cases:
            with self.subTest(name):
                self.assertEqual(evalprep.cap(text, limit), want)

    def test_patches_are_capped(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = build_fixture(tmp)
            globs = registry.load_config(repo)["design_globs"]
            old = evalprep.PATCH_LIMIT
            evalprep.PATCH_LIMIT = 50
            try:
                out = evalprep.prepare(repo, os.path.join(tmp, "eval"), globs, designs=[TTL])
            finally:
                evalprep.PATCH_LIMIT = old
            for name in ("fixes.patch", "revisions.patch"):
                with self.subTest(name), open(os.path.join(out["cases"][0]["case_dir"],
                                                           "evolution", name)) as f:
                    lines = f.read().splitlines()
                self.assertRegex(lines[-1], r"^\[truncated: \d+ more bytes\]$")


if __name__ == "__main__":
    unittest.main()
