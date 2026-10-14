import datetime
import os
import tempfile
import unittest

import _path  # noqa: F401
import helpers as h
from dvlib import commands, runinit, sources

NOW = datetime.datetime(2026, 10, 12, 12, 0, 0)


class InitTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def test_git_repo(self):
        fx = h.RunFixture(self.tmp.name)
        run = fx.run()
        self.assertEqual(run["mode"], "normal")
        self.assertEqual(run["repo_commit"], fx.commit)
        self.assertIsNone(run["worktree_diff_sha256"])
        self.assertEqual(run["stages"], {"0": "PENDING", "1": "PENDING", "2": "PENDING"})
        by_name = {v["name"]: v for v in run["validators"]}
        self.assertTrue(by_name["extract"]["selected"])
        self.assertFalse(by_name["gamma"]["selected"])
        self.assertEqual(by_name["gamma"]["not_selected_reason"], "depth=standard excludes cost=high")
        self.assertEqual([d["name"] for d in fx.init_output["dispatch"]], ["extract", "alpha", "beta"])
        self.assertTrue(os.path.isfile(os.path.join(fx.run_dir, "design.md")))
        self.assertEqual(run["priors"][-1], os.path.join(fx.plugin, "priors"))
        self.assertEqual(run["history"], {"git": True, "pr_comments": False})
        self.assertTrue(fx.run_dir.endswith("20261012-120000-" + run["design_sha256"][:6]))

    def test_dirty_worktree_and_own_runs(self):
        fx = h.RunFixture(self.tmp.name)
        # The first run's .dv/ directory must not count as a worktree change.
        code, out = commands.cmd_init("docs/design.md", fx.repo, "quick", plugin_root=fx.plugin,
                                      now=NOW + datetime.timedelta(seconds=1))
        self.assertEqual(code, 0)
        self.assertIsNone(commands.load_run(out["run_dir"])["worktree_diff_sha256"])
        h.write_files(fx.repo, {"store/cache.py": "changed\n"})
        code, out = commands.cmd_init("docs/design.md", fx.repo, "quick", plugin_root=fx.plugin,
                                      now=NOW + datetime.timedelta(seconds=2))
        self.assertIsNotNone(commands.load_run(out["run_dir"])["worktree_diff_sha256"])

    def test_run_state_under_runs(self):
        fx = h.RunFixture(self.tmp.name)
        fx.run()
        runs = os.path.join(fx.repo, ".dv", "runs")
        self.assertTrue(os.path.isfile(os.path.join(runs, "active.json")))
        self.assertFalse(os.path.exists(os.path.join(runs, ".gitignore")))

    def test_snapshot_dir(self):
        plugin = h.make_plugin(self.tmp.name)
        snap = os.path.join(self.tmp.name, "snap")
        h.write_files(snap, {"d.md": "# D\n"})
        code, out = commands.cmd_init("d.md", snap, "standard", plugin_root=plugin, now=NOW)
        run = commands.load_run(out["run_dir"])
        self.assertEqual((run["mode"], run["repo_commit"]), ("eval", None))
        self.assertEqual(run["history"], {"git": False, "pr_comments": False})

    def test_errors(self):
        plugin = h.make_plugin(self.tmp.name)
        empty = os.path.join(self.tmp.name, "empty")
        os.makedirs(empty)
        h.git(empty, "init", "-q")
        h.write_files(empty, {"d.md": "# D\n"})
        cases = [
            ("missing design", "nope.md", empty),
            ("no commits", "d.md", empty),
        ]
        for name, design, repo in cases:
            with self.subTest(name):
                with self.assertRaises(runinit.InitError):
                    commands.cmd_init(design, repo, "standard", plugin_root=plugin, now=NOW)


class BaselineTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.plugin = h.make_plugin(self.tmp.name)
        self.repo, self.base = h.make_repo(self.tmp.name, {"store/cache.py": "v1\n"})
        h.write_files(self.repo, {"store/cache.py": "v2\n", "store/new.py": "new\n"})
        h.git(self.repo, "add", "-A")
        h.git(self.repo, "commit", "-q", "-m", "impl")
        self.head = h.git(self.repo, "rev-parse", "HEAD")
        h.write_files(self.repo, {"docs/design.md": "# D\n\nClaim.\n"})

    def tearDown(self):
        self.tmp.cleanup()

    def init(self, baseline, seconds=0):
        return commands.cmd_init("docs/design.md", self.repo, "standard", plugin_root=self.plugin,
                                 now=NOW + datetime.timedelta(seconds=seconds), baseline=baseline)

    def test_baseline_ref(self):
        cases = [
            ("default is HEAD", None, self.head, True, ["docs/design.md"]),
            ("branch name at HEAD", "main", self.head, True, ["docs/design.md"]),
            ("older commit", self.base[:10], self.base, False, []),
        ]
        for i, (name, ref, commit, matches, wt) in enumerate(cases):
            with self.subTest(name):
                code, out = self.init(ref, seconds=i)
                self.assertEqual(code, 0, out)
                run = commands.load_run(out["run_dir"])
                self.assertEqual(run["repo_commit"], commit)
                self.assertEqual(run["baseline_ref"], ref or "HEAD")
                self.assertEqual(out["worktree_matches_baseline"], matches)
                self.assertEqual(run["worktree_paths"], wt)

    def test_older_baseline_reads_only_that_commit(self):
        _, out = self.init(self.base)
        reader = commands.build_context(out["run_dir"], commands.load_run(out["run_dir"])).reader
        self.assertEqual(reader.read("store/cache.py")[0], "v1\n")
        with self.assertRaises(sources.SourceError):
            reader.read("store/new.py")

    def test_bad_baseline(self):
        with self.assertRaises(runinit.InitError):
            self.init("no-such-ref")
        snap = os.path.join(self.tmp.name, "snap")
        h.write_files(snap, {"docs/design.md": "# D\n"})
        with self.assertRaises(runinit.InitError):
            commands.cmd_init("docs/design.md", snap, "standard", plugin_root=self.plugin, now=NOW,
                              baseline="HEAD")


if __name__ == "__main__":
    unittest.main()
