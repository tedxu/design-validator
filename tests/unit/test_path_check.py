import json
import os
import shutil
import subprocess
import tempfile
import unittest

import _path  # noqa: F401
import helpers as h
import samples as s
from dvlib import commands

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
EXAMPLE = os.path.join(ROOT, "examples", "validators", "path-check")
FILES = {"store/cache.py": "\nclass SegmentCache:\n    pass\n", "store/util.py": "X = 1\n",
         "tools/util.py": "Y = 2\n", "tools/empty.py": "",
         "sub/b.go": "package b\n", "文档/notes.md": "# n\n"}
QUOTE = ("`store/cache.py`, `cache.py`, `util.py`, `store/evict.py` and `empty.py`. "
         "Also ./store/util.py, 当前在tools/util.py。 sub/b.go中 and `notes.md`.")


def run_check(inp):
    p = subprocess.run([os.path.join(EXAMPLE, "check.py")], input=json.dumps(inp),
                       capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout)


def write_json(run_dir, rel, data):
    path = os.path.join(run_dir, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


def verdicts(out):
    by_eid = {e["id"]: e for e in out["evidence"]}
    return [(c["method"].split()[2], c["verdict"],
             [by_eid[i]["source"] for i in c["evidence_ids"]]) for c in out["checks"]]


class PathCheckTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def inp(self, repo, commit):
        a = s.assumption(quote=QUOTE)
        a["statement"] = "The design names " + QUOTE
        return {"repo_root": repo, "repo_commit": commit, "assumptions": [a], "id_prefix": "path-check"}

    def test_verdicts_git_and_snapshot(self):
        want = [
            ("store/cache.py", "PASS", ["code"]),
            ("cache.py", "PASS", ["code"]),
            ("util.py", "INCONCLUSIVE", []),
            ("store/evict.py", "ISSUE", ["sandbox"]),
            ("empty.py", "INCONCLUSIVE", []),
            ("store/util.py", "PASS", ["code"]),
            ("tools/util.py", "PASS", ["code"]),
            ("sub/b.go", "PASS", ["code"]),
            ("notes.md", "PASS", ["code"]),
        ]
        repo, commit = h.make_repo(self.tmp.name, FILES)
        snap = os.path.join(self.tmp.name, "snap")
        h.write_files(snap, FILES)
        for name, root, c in (("git", repo, commit), ("snapshot", snap, None)):
            with self.subTest(name):
                out = run_check(self.inp(root, c))
                self.assertEqual(out["status"], "COMPLETED")
                self.assertEqual(verdicts(out), want)
                self.assertEqual(len(out["findings"]), 1)
                f = out["findings"][0]
                self.assertEqual((f["category"], f["severity"]), ("contradicted", "MAJOR"))
                self.assertIn("store/evict.py", f["statement"])

    def test_git_reads_the_baseline_not_the_worktree(self):
        repo, commit = h.make_repo(self.tmp.name, FILES)
        os.remove(os.path.join(repo, "store", "cache.py"))
        h.write_files(repo, {"store/evict.py": "new\n"})
        out = run_check(self.inp(repo, commit))
        got = {v[0]: v[1] for v in verdicts(out)}
        self.assertEqual((got["store/cache.py"], got["store/evict.py"]), ("PASS", "ISSUE"))

    def test_end_to_end_as_project_validator(self):
        design = "# D\n\nThe names are " + QUOTE + "\n"
        plugin = h.make_plugin(self.tmp.name)
        repo, commit = h.make_repo(self.tmp.name, dict(FILES, **{"docs/design.md": design}))
        shutil.copytree(EXAMPLE, os.path.join(repo, ".dv", "validators", "path-check"))
        code, out = commands.cmd_init("docs/design.md", repo, "standard", plugin_root=plugin)
        self.assertEqual(code, 0, out)
        run_dir = out["run_dir"]
        a = s.assumption(quote="The names are " + QUOTE)
        write_json(run_dir, "assumptions.json", {"assumptions": [a]})
        write_json(run_dir, "results/extract.json", s.result("extract"))
        self.assertEqual(commands.cmd_assumptions(run_dir)[0], 0)
        _, inp = commands.cmd_input(run_dir, "path-check")
        with open(inp["input_path"], encoding="utf-8") as f:
            result = run_check(json.load(f))
        write_json(run_dir, "results/path-check.json", result)
        code, out = commands.cmd_results(run_dir, 1)
        self.assertEqual(code, 0, out)
        graded = commands.load_json(os.path.join(run_dir, "results", "path-check.json"))
        self.assertTrue(all(e["verified"] in (True, "n/a") for e in graded["evidence"]),
                        graded["evidence"])
        self.assertEqual(graded["findings"][0]["severity"], "MAJOR")
        self.assertEqual(graded["findings"][0]["tier"], "T1")

    def test_listing_failure_is_failed_not_contradicted(self):
        repo, _ = h.make_repo(self.tmp.name, FILES)
        out = run_check(self.inp(repo, "0" * 40))
        self.assertEqual(out["status"], "FAILED")
        self.assertIn("git ls-tree", out["status_reason"])
        self.assertEqual((out["checks"], out["findings"], out["evidence"]), ([], [], []))

    def test_unreadable_file_is_inconclusive_only_for_that_check(self):
        snap = os.path.join(self.tmp.name, "snap")
        h.write_files(snap, FILES)
        os.remove(os.path.join(snap, "store", "cache.py"))
        os.symlink(os.path.join(snap, "nowhere"), os.path.join(snap, "store", "cache.py"))
        out = run_check(self.inp(snap, None))
        self.assertEqual(out["status"], "COMPLETED")
        got = {v[0]: v[1] for v in verdicts(out)}
        self.assertEqual((got["store/cache.py"], got["store/evict.py"]), ("INCONCLUSIVE", "ISSUE"))
        m = next(c["method"] for c in out["checks"] if "store/cache.py" in c["method"])
        self.assertIn("could not be read", m)


if __name__ == "__main__":
    unittest.main()
