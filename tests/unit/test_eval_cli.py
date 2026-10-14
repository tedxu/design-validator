import json
import os
import subprocess
import sys
import tempfile
import unittest

import _path  # noqa: F401
import helpers as h

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
EVAL = os.path.join(ROOT, "scripts", "eval.py")
FIXTURE = os.path.join(ROOT, "tests", "eval", "fixture.sh")


def run(args, cwd):
    p = subprocess.run([sys.executable, EVAL, *args], cwd=cwd, capture_output=True, text=True)
    return p.returncode, json.loads(p.stdout)


VALID_TRUTH = {"items": [{"id": "G1", "statement": "s", "source": "fix", "commits": ["c" * 7],
                          "tier": "T1", "reviewed": False}]}


def write(path, data):
    with open(path, "w") as f:
        f.write(data if isinstance(data, str) else json.dumps(data))


class EvalCliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cache = os.path.join(self.tmp.name, "cache")
        old = os.environ.get("XDG_CACHE_HOME")
        os.environ["XDG_CACHE_HOME"] = self.cache
        self.addCleanup(lambda: os.environ.pop("XDG_CACHE_HOME") if old is None
                        else os.environ.__setitem__("XDG_CACHE_HOME", old))
        self.repo = os.path.join(self.tmp.name, "repo")
        os.makedirs(self.repo)
        subprocess.run(["bash", FIXTURE], cwd=self.repo, check=True, capture_output=True)

    def case_dirs(self):
        _, out = run(["prepare"], self.repo)
        return [c["case_dir"] for c in out["cases"]]

    def with_report(self, case_dir, report, truth=None):
        """Give a case a run result, a report.json and a valid truth.json."""
        os.makedirs(os.path.join(case_dir, "run1"))
        write(os.path.join(case_dir, "run-result.json"), {"run_dir": "run1", "error": None})
        write(os.path.join(case_dir, "run1", "report.json"), report)
        write(os.path.join(case_dir, "truth.json"), truth or {"items": []})

    def test_flow_until_matches(self):
        code, out = run(["prepare"], self.repo)
        self.assertEqual(code, 0, out)
        self.assertEqual(len(out["cases"]), 2)
        code, out = run(["check-truth"], self.repo)
        self.assertEqual((code, out["valid"], len(out["missing"])), (0, [], 2))
        case_dir = out["missing"][0]["case_dir"]
        with open(os.path.join(case_dir, "truth.json"), "w") as f:
            json.dump({"items": [{"id": "G1", "statement": "s", "source": "fix", "commits": ["c" * 7],
                                  "tier": "T1", "reviewed": False}]}, f)
        code, out = run(["check-truth"], self.repo)
        self.assertEqual(code, 1)
        self.assertIn("is not one of this case's fix commits", json.dumps(out["errors"]))
        code, out = run(["check-matches"], self.repo)
        self.assertEqual((code, len(out["no_report"]), out["missing"]), (0, 2, []))
        code, out = run(["score"], self.repo)
        self.assertEqual(code, 0, out)
        self.assertTrue(os.path.isfile(out["report_md"]))
        self.assertEqual(len(out["excluded"]), 2)

    def test_default_eval_dir_is_outside_the_repository(self):
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        import hashlib
        import eval as ev  # noqa: E402
        real = os.path.realpath(self.repo)
        suffix = os.path.join("design-validator", "eval",
                              "repo-" + hashlib.sha256(real.encode()).hexdigest()[:8])
        cases = [("xdg", {"XDG_CACHE_HOME": self.cache}, os.path.join(self.cache, suffix)),
                 ("home", {"XDG_CACHE_HOME": "", "HOME": self.tmp.name},
                  os.path.join(self.tmp.name, ".cache", suffix))]
        for name, env, want in cases:
            with self.subTest(name):
                saved = {k: os.environ.get(k) for k in env}
                os.environ.update(env)
                try:
                    self.assertEqual(ev.default_eval_dir(self.repo), want)
                finally:
                    for k, v in saved.items():
                        if v is None:
                            os.environ.pop(k, None)
                        else:
                            os.environ[k] = v
        code, out = run(["prepare"], self.repo)
        self.assertEqual((code, out["eval_dir"]), (0, os.path.join(self.cache, suffix)))
        self.assertFalse(os.path.exists(os.path.join(self.repo, ".dv", "eval")))
        other = os.path.join(self.tmp.name, "elsewhere")
        code, out = run(["prepare", "--eval-dir", other], self.repo)
        self.assertEqual((code, out["eval_dir"]), (0, other))

    def test_cases_limits_every_step(self):
        dirs = self.case_dirs()
        keep, other = (os.path.basename(d) for d in dirs)
        write(os.path.join(dirs[1], "truth.json"), "{not json")
        code, out = run(["check-truth", "--cases", keep], self.repo)
        self.assertEqual((code, out["errors"], [m["case_id"] for m in out["missing"]]),
                         (0, {}, [keep]))
        code, out = run(["check-matches", "--cases", keep], self.repo)
        self.assertEqual((code, out["no_report"]), (0, [keep]))
        code, out = run(["score", "--cases", keep], self.repo)
        self.assertEqual((code, [e["case_id"] for e in out["excluded"]]), (0, [keep]))
        code, out = run(["check-truth"], self.repo)
        self.assertEqual((code, list(out["errors"])), (1, [other]))

    def test_list_helper_strips(self):
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        import eval as ev  # noqa: E402
        self.assertEqual(ev._list("a, b,, c ,"), ["a", "b", "c"])

    def test_malformed_truth_is_a_case_error(self):
        dirs = self.case_dirs()
        write(os.path.join(dirs[0], "truth.json"), "{not json")
        code, out = run(["check-truth"], self.repo)
        self.assertEqual(code, 1, out)
        self.assertEqual(list(out["errors"]), [os.path.basename(dirs[0])])
        self.assertIn("truth.json", json.dumps(out["errors"]))

    def test_wrong_shape_truth_is_a_case_error(self):
        dirs = self.case_dirs()
        write(os.path.join(dirs[0], "truth.json"), [])
        write(os.path.join(dirs[1], "case.json"), {})
        write(os.path.join(dirs[1], "truth.json"), VALID_TRUTH)
        code, out = run(["check-truth"], self.repo)
        self.assertEqual(code, 1, out)
        self.assertEqual(len(out["errors"]), 2, out)
        self.assertIn("case.json", json.dumps(out["errors"]))

    def test_check_matches_bad_inputs_are_case_errors(self):
        dirs = self.case_dirs()
        cases = [
            ("report {}", dirs[0], {}, "{}", "report.json"),
            ("matches malformed", dirs[1], {"findings": []}, "{not json", "matches.json"),
        ]
        for _, d, rep, matches, _ in cases:
            self.with_report(d, rep)
            write(os.path.join(d, "matches.json"), matches)
        code, out = run(["check-matches"], self.repo)
        self.assertEqual(code, 1, out)
        for name, d, _, _, fname in cases:
            with self.subTest(name):
                errs = json.dumps(out["errors"][os.path.basename(d)])
                self.assertIn(fname, errs)

    def test_check_matches_error_keeps_other_cases(self):
        dirs = self.case_dirs()
        self.with_report(dirs[0], {})
        write(os.path.join(dirs[0], "matches.json"), {"matches": []})
        self.with_report(dirs[1], {"findings": []})
        write(os.path.join(dirs[1], "matches.json"), {"matches": []})
        code, out = run(["check-matches"], self.repo)
        self.assertEqual(code, 1, out)
        self.assertEqual(out["valid"], [os.path.basename(dirs[1])])
        self.assertEqual(list(out["errors"]), [os.path.basename(dirs[0])])

    def test_errors(self):
        no_globs, _ = h.make_repo(self.tmp.name, {"a.md": "# A\n"}, name="plain")
        not_git = os.path.join(self.tmp.name, "not-git")
        os.makedirs(not_git)
        cases = [
            ("no design globs", ["prepare"], no_globs),
            ("not a git repository", ["prepare"], not_git),
            ("bad depth", ["run", "--depth", "huge"], self.repo),
            ("unknown command", ["frobnicate"], self.repo),
        ]
        for name, args, cwd in cases:
            with self.subTest(name):
                code, out = run(args, cwd)
                self.assertEqual(code, 2, out)
                self.assertFalse(out["ok"])
                self.assertTrue(out["errors"])


if __name__ == "__main__":
    unittest.main()
