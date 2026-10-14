import contextlib
import io
import json
import os
import stat
import sys
import tempfile
import unittest

import _path  # noqa: F401

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import run_cases  # noqa: E402

FAKE_CLAUDE = """#!/usr/bin/env python3
import json, os
run = os.path.join(".dv", "runs", "20261013-000000-abcdef")
os.makedirs(run)
with open(os.path.join(run, "report.json"), "w") as f:
    json.dump({"findings": [], "coverage": {"validators": []}}, f)
with open(os.path.join(run, "report.md"), "w") as f:
    f.write("# Design validation report: docs/design.md\\n\\n## Summary\\n\\nNothing.\\n")
print(json.dumps({"total_cost_usd": 0.5, "result": "done"}))
"""

BAD_CLAUDE = """#!/usr/bin/env python3
print("not json")
raise SystemExit(1)
"""

SLOW_CLAUDE = """#!/usr/bin/env python3
import time
time.sleep(5)
"""

ARRAY_CLAUDE = FAKE_CLAUDE.replace('{"total_cost_usd": 0.5, "result": "done"}', '[1, 2]')


class RunCasesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def test_case_names(self):
        self.assertIn("sound-design", run_cases.case_names(None))
        self.assertEqual(run_cases.case_names(["stale-fact", "sound-design"]),
                         ["sound-design", "stale-fact"])
        with self.assertRaises(SystemExit):
            run_cases.case_names(["nope"])

    def test_newest_run(self):
        self.assertIsNone(run_cases.newest_run(self.tmp.name))
        for rid in ("20261013-000001-aaaaaa", "20261013-000002-bbbbbb"):
            os.makedirs(os.path.join(self.tmp.name, ".dv", "runs", rid))
        self.assertTrue(run_cases.newest_run(self.tmp.name).endswith("20261013-000002-bbbbbb"))

    def test_run_case_with_fake_claude(self):
        fake = os.path.join(self.tmp.name, "claude")
        with open(fake, "w") as f:
            f.write(FAKE_CLAUDE)
        os.chmod(fake, os.stat(fake).st_mode | stat.S_IEXEC)
        work = os.path.join(self.tmp.name, "work")
        os.makedirs(work)
        cases = [("sound-design", []), ("stale-fact", ["missing finding"])]
        results = []
        for name, want in cases:
            with self.subTest(name):
                r = run_cases.run_case(name, work, fake)
                self.assertEqual((r["case"], r["run"], r["exit"], r["cost_usd"]),
                                 (name, "20261013-000000-abcdef", 0, 0.5))
                self.assertEqual(len(r["failures"]), len(want))
                for w, got in zip(want, r["failures"]):
                    self.assertIn(w, got)
                results.append(r)
        md = run_cases.render_runs(results, work)
        self.assertIn("## 1. sound-design · `20261013-000000-abcdef`", md)
        self.assertIn("### Summary", md)
        self.assertIn("# Expose SegmentCache size", md)

    def _script(self, name, body):
        path = os.path.join(self.tmp.name, name)
        with open(path, "w") as f:
            f.write(body)
        os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC)
        return path

    def _work(self):
        work = os.path.join(self.tmp.name, "work")
        os.makedirs(work, exist_ok=True)
        return work

    def _fake_cases(self, fixtures):
        root = os.path.join(self.tmp.name, "cases")
        for name, script in fixtures.items():
            d = os.path.join(root, name)
            os.makedirs(d)
            with open(os.path.join(d, "fixture.sh"), "w") as f:
                f.write(script)
            with open(os.path.join(d, "expected.json"), "w") as f:
                f.write("{}")
        return root

    def test_never_raises(self):
        cases = [
            ("bad claude output", "sound-design", None, self._script("bad", BAD_CLAUDE),
             "no report.json produced", 3600),
            ("missing claude", "sound-design", None, os.path.join(self.tmp.name, "nope"),
             "runner error", 3600),
            ("fixture fails", "broken", {"broken": "exit 1\n"}, self._script("ok", FAKE_CLAUDE),
             "fixture failed", 3600),
            ("timeout", "sound-design", None, self._script("slow", SLOW_CLAUDE),
             "claude timed out after 1s", 1),
        ]
        for label, name, fixtures, claude, want, timeout in cases:
            with self.subTest(label):
                saved = run_cases.CASES
                if fixtures:
                    run_cases.CASES = self._fake_cases(fixtures)
                try:
                    r = run_cases.run_case(name, self._work(), claude, timeout=timeout)
                finally:
                    run_cases.CASES = saved
                self.assertEqual(len(r["failures"]), 1, r)
                self.assertIn(want, r["failures"][0])
                self.assertEqual(set(r), {"case", "run", "seconds", "cost_usd", "exit", "failures"})

    def test_non_object_json_keeps_cost_none(self):
        r = run_cases.run_case("sound-design", self._work(), self._script("arr", ARRAY_CLAUDE))
        self.assertIsNone(r["cost_usd"])

    def test_rerun_same_workdir(self):
        fake = self._script("claude", FAKE_CLAUDE)
        work = self._work()
        run_cases.run_case("sound-design", work, fake)
        r = run_cases.run_case("sound-design", work, fake)
        self.assertEqual(r["run"], "20261013-000000-abcdef")
        self.assertEqual(r["failures"], [])

    def test_main_refuses_workdir_inside_plugin_repo(self):
        for sub_dir in ("tests/cases", "scratch", ""):
            with self.subTest(sub_dir):
                work = os.path.join(run_cases.PLUGIN, sub_dir, "dv-work-should-not-exist")
                with self.assertRaises(SystemExit) as cm:
                    run_cases.main(["--workdir", work, "--claude", "true"])
                self.assertNotEqual(cm.exception.code, 0)
                self.assertFalse(os.path.exists(work))

    def test_main_writes_summary_with_failing_case(self):
        fake = self._script("claude", FAKE_CLAUDE)
        saved = run_cases.CASES
        run_cases.CASES = self._fake_cases({
            "good": "mkdir docs && echo '# D' > docs/design.md\n", "bad": "exit 1\n"})
        try:
            work = os.path.join(self.tmp.name, "w2")
            with contextlib.redirect_stdout(io.StringIO()):
                rc = run_cases.main(["--workdir", work, "--claude", fake, "--jobs", "2"])
        finally:
            run_cases.CASES = saved
        self.assertEqual(rc, 1)
        with open(os.path.join(work, "summary.json")) as f:
            summary = json.load(f)
        self.assertEqual([r["case"] for r in summary], ["bad", "good"])
        self.assertEqual([bool(r["failures"]) for r in summary], [True, False])
        self.assertTrue(os.path.isfile(os.path.join(work, "validation-runs.md")))


if __name__ == "__main__":
    unittest.main()
