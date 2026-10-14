import json
import os
import signal
import stat
import subprocess
import sys
import tempfile
import time
import unittest

import _path  # noqa: F401
import helpers as h
from dvlib import evalrun

SCRIPTS = os.path.dirname(os.path.dirname(evalrun.__file__))


def alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True

FAKE = """#!/usr/bin/env python3
import json, os, subprocess, sys, time
mode = os.environ.get("FAKE_MODE", "ok")
with open("calls.txt", "a") as f:
    f.write(" ".join(sys.argv[1:]) + "\\n")
probe = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True)
with open("git-probe.txt", "w") as f:
    f.write(str(probe.returncode))
if mode == "hang":
    child = subprocess.Popen(["sleep", "60"])
    with open(os.environ["FAKE_PIDS"], "w") as f:
        f.write(f"{os.getpid()}\\n{child.pid}\\n")
    time.sleep(60)
if mode == "grandchild":
    subprocess.Popen(["sleep", "30"])
    time.sleep(30)
if mode == "sleep":
    time.sleep(5)
if mode == "partial":
    print("partial-output", flush=True)
    time.sleep(30)
if mode in ("ok", "sleep", "report-hang"):
    run = os.path.join(".dv", "runs", os.environ.get("FAKE_RUN", "20261013-000000-abcdef"))
    os.makedirs(run, exist_ok=True)
    with open(os.path.join(run, "report.json"), "w") as f:
        json.dump({"findings": [], "coverage": {"validators": [], "assumptions": []}}, f)
    print(json.dumps({"total_cost_usd": 1.25}), flush=True)
    if mode == "report-hang":
        time.sleep(30)
else:
    print("boom")
    sys.exit(1)
"""


class RunTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo, _ = h.make_repo(self.tmp.name, {"a.py": "x\n"})
        self.eval_dir = os.path.join(self.repo, ".dv", "eval")
        self.fake = os.path.join(self.tmp.name, "claude")
        with open(self.fake, "w") as f:
            f.write(FAKE)
        os.chmod(self.fake, os.stat(self.fake).st_mode | stat.S_IEXEC)

    def tearDown(self):
        os.environ.pop("FAKE_MODE", None)
        self.tmp.cleanup()

    def make_case(self, name, **extra):
        case_dir = os.path.join(self.eval_dir, name)
        os.makedirs(os.path.join(case_dir, "snapshot", "docs"))
        with open(os.path.join(case_dir, "case.json"), "w") as f:
            json.dump(dict({"case_id": name, "design_path": "docs/d.md", "snapshot": "snapshot"},
                           **extra), f)
        return case_dir

    def test_renamed_design_runs_under_its_first_path(self):
        case_dir = self.make_case("c1", first_path="docs/old.md")
        evalrun.run_case(case_dir, "/plugin", self.fake)
        self.assertIn("/design-validate docs/old.md --depth", self.read(case_dir, "snapshot", "calls.txt"))

    def read(self, *parts):
        with open(os.path.join(*parts)) as f:
            return f.read()

    def test_snapshot_cannot_see_the_outer_repository(self):
        case_dir = self.make_case("c1")
        snap = os.path.join(case_dir, "snapshot")
        plain = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=snap, capture_output=True)
        self.assertEqual(plain.returncode, 0)  # without the ceiling git finds the outer repo
        evalrun.run_case(case_dir, "/plugin", self.fake)
        self.assertNotEqual(self.read(snap, "git-probe.txt"), "0")

    def test_success_then_skip(self):
        case_dir = self.make_case("c1")
        first = evalrun.run_case(case_dir, "/plugin", self.fake, depth="deep")
        self.assertEqual((first["run_dir"], first["cost_usd"], first["exit"], first["error"], first["skipped"]),
                         ("snapshot/.dv/runs/20261013-000000-abcdef", 1.25, 0, None, False))
        self.assertIn("/design-validate docs/d.md --depth deep", self.read(case_dir, "snapshot", "calls.txt"))
        self.assertIn("--plugin-dir /plugin", self.read(case_dir, "snapshot", "calls.txt"))
        self.assertEqual(json.loads(self.read(case_dir, evalrun.RESULT))["run_dir"], first["run_dir"])
        self.assertTrue(evalrun.report_path(case_dir, evalrun.load_result(case_dir)))
        second = evalrun.run_case(case_dir, "/plugin", self.fake)
        self.assertTrue(second["skipped"])
        self.assertEqual(self.read(case_dir, "snapshot", "calls.txt").count("\n"), 1)

    def test_failures_are_results_not_exceptions(self):
        cases = [
            ("no report", "fail", 60, None, "no report.json produced"),
            ("timeout", "sleep", 1, None, "claude timed out after 1s"),
            ("missing binary", "ok", 60, "/nonexistent/claude", "could not start claude"),
        ]
        for name, mode, timeout, claude, want in cases:
            with self.subTest(name):
                os.environ["FAKE_MODE"] = mode
                case_dir = self.make_case(name.replace(" ", "-"))
                r = evalrun.run_case(case_dir, "/plugin", claude or self.fake, timeout=timeout)
                self.assertIn(want, r["error"])
                self.assertIsNone(r["run_dir"])
                self.assertTrue(os.path.isfile(os.path.join(case_dir, evalrun.RESULT)))

    def test_run_all_isolates_a_broken_case(self):
        self.make_case("a-good")
        bad = os.path.join(self.eval_dir, "b-bad")
        os.makedirs(bad)
        with open(os.path.join(bad, "case.json"), "w") as f:
            f.write("{not json")
        out = evalrun.run_all(self.eval_dir, "/plugin", self.fake, jobs=2)
        self.assertFalse(out["ok"])
        by_id = {r["case_id"]: r for r in out["results"]}
        self.assertIsNone(by_id["a-good"]["error"])
        self.assertIn("runner error", by_id["b-bad"]["error"])
        self.assertEqual(evalrun.case_dirs(os.path.join(self.tmp.name, "none")), [])
        self.assertEqual([os.path.basename(d) for d in evalrun.case_dirs(self.eval_dir, only=["a-good"])],
                         ["a-good"])

    def test_corrupt_result_is_treated_as_missing(self):
        case_dir = self.make_case("c1")
        for text in ["{not json", ""]:
            with self.subTest(text=text):
                with open(os.path.join(case_dir, evalrun.RESULT), "w") as f:
                    f.write(text)
                self.assertIsNone(evalrun.load_result(case_dir))
        r = evalrun.run_case(case_dir, "/plugin", self.fake)
        self.assertFalse(r["skipped"])
        self.assertIsNone(r["error"])

    def test_no_temp_files_left_behind(self):
        case_dir = self.make_case("c1")
        evalrun.run_case(case_dir, "/plugin", self.fake)
        self.assertEqual(sorted(n for n in os.listdir(case_dir) if n.startswith("run-result")),
                         [evalrun.RESULT])

    def test_failed_result_is_retried(self):
        for mode, timeout in [("fail", 60), ("sleep", 1)]:
            with self.subTest(mode):
                os.environ["FAKE_MODE"] = mode
                case_dir = self.make_case("retry-" + mode)
                first = evalrun.run_case(case_dir, "/plugin", self.fake, timeout=timeout)
                self.assertTrue(first["error"])
                os.environ["FAKE_MODE"] = "ok"
                second = evalrun.run_case(case_dir, "/plugin", self.fake)
                self.assertFalse(second["skipped"])
                self.assertIsNone(second["error"])
                self.assertTrue(evalrun.report_path(case_dir, evalrun.load_result(case_dir)))
        out = evalrun.run_all(self.eval_dir, "/plugin", self.fake)
        self.assertTrue(out["ok"])
        self.assertTrue(all(r["skipped"] for r in out["results"]))

    def test_timeout_kills_grandchildren_and_keeps_partial_log(self):
        for mode in ["grandchild", "partial"]:
            with self.subTest(mode):
                os.environ["FAKE_MODE"] = mode
                case_dir = self.make_case("kill-" + mode)
                start = time.time()
                r = evalrun.run_case(case_dir, "/plugin", self.fake, timeout=1)
                self.assertLess(time.time() - start, 10)
                self.assertIn("timed out after 1s", r["error"])
        self.assertIn("partial-output", self.read(self.eval_dir, "kill-partial", "claude.log"))

    def test_stale_report_is_not_attributed_to_a_later_attempt(self):
        case_dir = self.make_case("stale")
        os.environ["FAKE_MODE"] = "report-hang"
        first = evalrun.run_case(case_dir, "/plugin", self.fake, timeout=3)
        self.assertIn("timed out", first["error"])
        self.assertTrue(os.path.isfile(os.path.join(case_dir, "snapshot", ".dv", "runs",
                                                    "20261013-000000-abcdef", "report.json")))
        os.environ["FAKE_MODE"] = "fail"
        second = evalrun.run_case(case_dir, "/plugin", self.fake)
        self.assertEqual((second["error"], second["run_dir"]), ("no report.json produced", None))

    def test_interrupt_kills_running_claude(self):
        for sig in (signal.SIGTERM, signal.SIGINT):
            with self.subTest(sig.name):
                name = "int-" + sig.name.lower()
                self.make_case(name)
                pid_file = os.path.join(self.tmp.name, name + ".pids")
                code = (f"import sys; sys.path.insert(0, {SCRIPTS!r}); from dvlib import evalrun; "
                        f"evalrun.run_all({self.eval_dir!r}, '/plugin', {self.fake!r}, only=[{name!r}])")
                env = dict(os.environ, FAKE_MODE="hang", FAKE_PIDS=pid_file)
                runner = subprocess.Popen([sys.executable, "-c", code], env=env,
                                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                pids = []
                try:
                    deadline = time.time() + 15
                    while len(pids) < 2 and time.time() < deadline:
                        time.sleep(0.1)
                        if os.path.isfile(pid_file):
                            pids = [int(x) for x in self.read(pid_file).split()]
                    self.assertEqual(len(pids), 2, "fake claude never started")
                    runner.send_signal(sig)
                    runner.wait(timeout=10)
                    deadline = time.time() + 5
                    while any(alive(p) for p in pids) and time.time() < deadline:
                        time.sleep(0.1)
                    self.assertEqual([p for p in pids if alive(p)], [])
                finally:
                    runner.kill()
                    runner.wait()
                    for p in pids:
                        try:
                            os.kill(p, signal.SIGKILL)
                        except OSError:
                            pass

    def test_runner_error_has_full_key_set(self):
        bad = os.path.join(self.eval_dir, "bad")
        os.makedirs(bad)
        with open(os.path.join(bad, "case.json"), "w") as f:
            f.write("{not json")
        r = evalrun.run_all(self.eval_dir, "/plugin", self.fake)["results"][0]
        for key in ["case_id", "run_dir", "seconds", "cost_usd", "exit", "error", "skipped"]:
            self.assertIn(key, r)


if __name__ == "__main__":
    unittest.main()
