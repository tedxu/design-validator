"""Run /design-validate headless in each prepared snapshot."""
from __future__ import annotations

import concurrent.futures
import json
import os
import signal
import subprocess
import threading
import time

RESULT = "run-result.json"

# Live claude processes, so an interrupt can kill them with their process groups.
_LIVE = set()
_LIVE_LOCK = threading.Lock()
_STOP = threading.Event()


def _killpg(proc):
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except OSError:
        pass


def _start(cmd, **kwargs):
    """Start a process in its own session and track it; refuse after an interrupt."""
    with _LIVE_LOCK:
        if _STOP.is_set():
            raise OSError("interrupted")
        proc = subprocess.Popen(cmd, start_new_session=True, **kwargs)
        _LIVE.add(proc)
    return proc


def _forget(proc):
    with _LIVE_LOCK:
        _LIVE.discard(proc)


def _kill_live():
    with _LIVE_LOCK:
        _STOP.set()
        for proc in list(_LIVE):
            _killpg(proc)


def case_dirs(eval_dir, only=None):
    if not os.path.isdir(eval_dir):
        return []
    names = sorted(d for d in os.listdir(eval_dir)
                   if os.path.isfile(os.path.join(eval_dir, d, "case.json")))
    return [os.path.join(eval_dir, d) for d in names if not only or d in only]


def _run_ids(snapshot):
    runs = os.path.join(snapshot, ".dv", "runs")
    return set(os.listdir(runs)) if os.path.isdir(runs) else set()


def new_run(snapshot, before):
    """The newest run dir with a report that is not in `before`, or None."""
    runs = os.path.join(snapshot, ".dv", "runs")
    for rid in sorted(_run_ids(snapshot) - before, reverse=True):
        if os.path.isfile(os.path.join(runs, rid, "report.json")):
            return os.path.join(runs, rid)
    return None


def load_result(case_dir):
    path = os.path.join(case_dir, RESULT)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None  # unreadable result: treat as never run
    return data if isinstance(data, dict) else None


def report_path(case_dir, result):
    if not result or not result.get("run_dir"):
        return None
    path = os.path.join(case_dir, result["run_dir"], "report.json")
    return path if os.path.isfile(path) else None


def run_case(case_dir, plugin_root, claude="claude", depth="standard", timeout=3600):
    """Run one case unless it already has a report; never raises for claude failures."""
    done = load_result(case_dir)
    if done and done.get("error") is None and report_path(case_dir, done):
        return dict(done, skipped=True)
    with open(os.path.join(case_dir, "case.json"), encoding="utf-8") as f:
        case = json.load(f)
    snapshot = os.path.join(case_dir, case["snapshot"])
    # Stop git from walking up into the evaluated repository and its later history.
    env = dict(os.environ, GIT_CEILING_DIRECTORIES=os.path.abspath(case_dir))
    prompt = f"/design-validate {case.get('first_path', case['design_path'])} --depth {depth}"
    result = {"case_id": case["case_id"], "run_dir": None, "seconds": None, "cost_usd": None,
              "exit": None, "error": None}
    log = ""
    before = _run_ids(snapshot)  # only a run created by this attempt counts
    start = time.time()
    proc = None
    try:
        proc = _start([claude, "-p", "--plugin-dir", plugin_root, "--permission-mode",
                       "bypassPermissions", "--output-format", "json", prompt],
                      cwd=snapshot, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                      text=True)
        try:
            out, err = proc.communicate(timeout=timeout)
            log = (out or "") + (err or "")
            result["exit"] = proc.returncode
            try:
                data = json.loads(out)
                if isinstance(data, dict):
                    result["cost_usd"] = data.get("total_cost_usd")
            except ValueError:
                pass
        except subprocess.TimeoutExpired:
            # Kill the whole process group: tool subprocesses may hold the pipes open.
            _killpg(proc)
            out, err = proc.communicate()
            log = (out or "") + (err or "")
            result["error"] = f"claude timed out after {timeout}s"
    except OSError as e:
        result["error"] = f"could not start claude: {e}"
    finally:
        if proc is not None:
            _forget(proc)
    if _STOP.is_set() and result["error"] is None:
        result["error"] = "interrupted"
    result["seconds"] = round(time.time() - start)
    with open(os.path.join(case_dir, "claude.log"), "w", encoding="utf-8") as f:
        f.write(log)
    run = new_run(snapshot, before)
    if run:
        result["run_dir"] = os.path.relpath(run, case_dir)
    elif result["error"] is None:
        result["error"] = "no report.json produced"
    tmp = os.path.join(case_dir, RESULT + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
        f.write("\n")
    os.replace(tmp, os.path.join(case_dir, RESULT))
    return dict(result, skipped=False)


def run_all(eval_dir, plugin_root, claude="claude", depth="standard", jobs=2, timeout=3600,
            only=None):
    def one(case_dir):
        try:
            return run_case(case_dir, plugin_root, claude, depth, timeout)
        except Exception as e:  # noqa: BLE001 - one broken case must not stop the others
            return {"case_id": os.path.basename(case_dir), "run_dir": None, "seconds": None,
                    "cost_usd": None, "exit": None, "error": f"runner error: {e!r}",
                    "skipped": False}

    _STOP.clear()
    previous = {}

    def interrupted(signum, frame):
        _kill_live()
        for sig, handler in previous.items():
            signal.signal(sig, handler)
        handler = previous.get(signum)
        if callable(handler):
            handler(signum, frame)
        else:
            os.kill(os.getpid(), signum)  # default action now that our handler is gone

    if threading.current_thread() is threading.main_thread():
        for sig in (signal.SIGINT, signal.SIGTERM):
            if signal.getsignal(sig) is not signal.SIG_IGN:
                previous[sig] = signal.signal(sig, interrupted)
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=max(1, jobs))
    try:
        results = list(pool.map(one, case_dirs(eval_dir, only)))
    finally:
        pool.shutdown(wait=True, cancel_futures=True)
        for sig, handler in previous.items():
            signal.signal(sig, handler)
    return {"ok": all(not r.get("error") for r in results), "results": results}
