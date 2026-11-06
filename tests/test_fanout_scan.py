"""Tests for scripts/fanout_scan.py, the scanner behind the fan-out view (hooks/fanouts/).

Every test builds its run folders in a temporary directory and hands the scanner a fake process
table, so nothing here reads a real run or calls ps or lsof.
"""
import io
import json
import os
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import fanout_scan as fs  # noqa: E402

NOW = float(int(time.time()))
CLEANRUN = "/x/agenting/3.4.1/scripts/cleanrun.py"


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def jl(*objs):
    return "".join(json.dumps(o, ensure_ascii=False) + "\n" for o in objs)


def iso(t):
    return datetime.fromtimestamp(t, timezone.utc).isoformat(timespec="seconds")


def hms(t):
    return datetime.fromtimestamp(t, timezone.utc).strftime("%H:%M:%S")


def touch(path, t):
    os.utime(path, (t, t))


def node(pid, out, script="scripts/workflows/flow.js", etime=600, pre=()):
    """A clean_runtime.mjs process as ps prints it: a path with spaces arrives split."""
    return {"pid": pid, "ppid": 1, "etime": etime,
            "argv": ["node", *pre, "scripts/workflows/clean_runtime.mjs", script, "--out", *out.split(" "), "--jobs", "6"]}


def cleanrun(pid, ppid, out_dir, model="claude-opus-5-5", effort="xhigh", etime=120, tasks=None, retries=None):
    argv = ["python3", CLEANRUN, "run", "--tasks", tasks or os.path.join(os.path.dirname(out_dir), "tasks.jsonl"),
            "--model", model, "--effort", effort, "--out-dir", *out_dir.split(" "), "--jobs", "1"]
    if retries is not None:
        argv += ["--retries", str(retries)]
    return {"pid": pid, "ppid": ppid, "etime": etime, "argv": argv}


def claude_child(pid, ppid):
    return {"pid": pid, "ppid": ppid, "etime": 100, "argv": ["claude", "-p", "--model", "claude-opus-5-5"]}


def no_lookup(pid):
    raise AssertionError(f"lsof should not be needed for pid {pid}")


class Runtime:
    """A clean_runtime.mjs OUT folder."""

    def __init__(self, root, name="run1"):
        self.out = os.path.join(root, name)
        os.makedirs(self.out)
        self.journal, self.log = [], []

    def started(self, label, phase, key=None):
        self.journal.append({"type": "started", "key": key or f"c1:{label}", "label": label, "phase": phase})

    def result(self, label, key=None):
        self.journal.append({"type": "result", "key": key or f"c1:{label}", "result": {"text": "x" * 50}})

    def call(self, label, summary=None, ledger=(), output=False, tasks_at=None, stderr=None):
        cid = fs.call_id(label)
        calldir = os.path.join(self.out, "calls", cid)
        cdir = os.path.join(calldir, "out")
        os.makedirs(cdir, exist_ok=True)
        if tasks_at is not None:
            write(os.path.join(calldir, "tasks.jsonl"), jl({"id": cid, "prompt": "p", "files": []}))
            touch(os.path.join(calldir, "tasks.jsonl"), tasks_at)
        if summary is not None:
            write(os.path.join(cdir, "summary.json"), json.dumps(summary))
        if ledger:
            write(os.path.join(cdir, "ledger.jsonl"), jl(*[{"id": cid, **e} for e in ledger]))
        if output:
            write(os.path.join(cdir, "outputs", cid + ".json"), json.dumps({"id": cid, "output": {"text": "ok"}}))
        if stderr is not None:
            write(os.path.join(calldir, "stderr.txt"), stderr)
        return cdir

    def flush(self, log_at=None):
        write(os.path.join(self.out, "journal.jsonl"), jl(*self.journal))
        write(os.path.join(self.out, "log.txt"), "".join(
            (m if m.startswith("[") else f"[09:00:00] {m}") + "\n" for m in self.log))
        if log_at is not None:
            touch(os.path.join(self.out, "log.txt"), log_at)


def attempt(cost=1.0, tokens=1000, wall=60.0, valid=True, problems=(), ts=None, cache_write=0, cache_read=0):
    e = {"event": "attempt", "charged_usd": cost, "output_tokens": tokens, "wall_s": wall,
         "cache_write": cache_write, "cache_read": cache_read,
         "valid": valid, "problems": list(problems), "model": "claude-opus-5-5", "effort": "xhigh"}
    if ts is not None:
        e["ts"] = iso(ts)
    return e


def by_label(fanout):
    return {a["label"]: a for a in fanout["agents"]}


def scan(procs, known=(), lookup=no_lookup, now=NOW):
    return fs.scan(procs, list(known), fs.Resolver({}, lookup), now)[0]


class ParsingTest(unittest.TestCase):
    def test_etime_forms(self):
        self.assertEqual(fs.parse_etime("05"), 5)
        self.assertEqual(fs.parse_etime("04:48"), 288)
        self.assertEqual(fs.parse_etime("1:02:03"), 3723)
        self.assertEqual(fs.parse_etime("2-01:00:00"), 2 * 86400 + 3600)

    def test_ps_rows_keep_the_whole_command(self):
        rows = fs.parse_ps("  12341     1   33:40 node a.mjs b.js --out d\n  bad row\n")
        self.assertEqual(rows, [{"pid": 12341, "ppid": 1, "etime": 2020,
                                 "argv": ["node", "a.mjs", "b.js", "--out", "d"]}])

    def test_call_id_matches_clean_runtime(self):
        self.assertEqual(fs.call_id("duzelt:T5.6"), "duzelt_T5.6")
        self.assertEqual(fs.call_id("gkc-düzelt:G5 A"), "gkc-d_zelt_G5_A")
        self.assertEqual(len(fs.call_id("x" * 300)), 120)

    def test_flag_forms(self):
        self.assertEqual(fs.flag(["--out", "a"], "--out"), "a")
        self.assertEqual(fs.flag(["--out=b"], "--out"), "b")
        self.assertIsNone(fs.flag(["--out"], "--out"))
        self.assertEqual(fs.flag_tokens(["--out", "My", "Runs/r1", "--jobs", "6"], "--out"), ["My", "Runs/r1"])

    def test_a_node_without_out_is_not_a_runtime(self):
        self.assertIsNone(fs.runtime_script(["node", "clean_runtime.mjs", "flow.js"]))
        self.assertEqual(fs.runtime_script(["node", "x/clean_runtime.mjs", "flow.js", "--out", "d"]), "flow.js")

    def test_interpreter_options_before_the_script_are_skipped(self):
        argv = ["/opt/homebrew/bin/node", "--enable-source-maps", "--no-warnings", "--max-old-space-size=8192",
                "scripts/workflows/clean_runtime.mjs", "flow.js", "--out", "d"]
        self.assertEqual(fs.runtime_script(argv), "flow.js")
        self.assertTrue(fs.is_cleanrun(["/usr/bin/python3", "-X", "utf8", "-u", CLEANRUN, "run", "--out-dir", "o"]))

    def test_only_cleanrun_run_counts(self):
        self.assertTrue(fs.is_cleanrun(["python3", CLEANRUN, "run", "--out-dir", "o"]))
        self.assertFalse(fs.is_cleanrun(["python3", CLEANRUN, "plan", "--out-dir", "o"]))
        self.assertFalse(fs.is_cleanrun(["python3", CLEANRUN, "status", "--out-dir", "o"]))

    def test_the_log_keeps_only_the_last_run(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "log.txt")
            write(p, "[23:25:11] start a.js jobs=8\n[23:30:00] FAIL x:1: cleanrun exit 3: boom\n"
                     "[23:31:00] pipeline item 2 dropped: oops\n[23:56:55] cost (list price, ...)\n"
                     "[23:56:55] finished in 32 min -> r\n[23:57:49] start b.js jobs=8\n[23:58:00] done y:1 (11 s)\n")
            log = fs.read_log(p)
        self.assertEqual(log["events"], {"y:1": ("done", 11)})
        self.assertEqual((log["warnings"], log["finished"], log["cost_written"]), ([], False, False))
        self.assertEqual((log["script"], log["starts"], log["start_tod"]), ("b.js", 2, 23 * 3600 + 57 * 60 + 49))


class RuntimeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        self.addCleanup(self.tmp.cleanup)

    def test_a_live_runtime_shows_running_done_and_queued_calls(self):
        r = Runtime(self.root)
        r.started("gkc:A", "GKC")
        r.started("gkc:B", "GKC")
        r.started("denetle:A", "Denetle")
        r.result("gkc:A")
        r.log.append("done gkc:A (277 s)")
        r.call("gkc:A", {"state": "finished", "model": "claude-opus-5-5", "effort": "xhigh", "ran": 1},
               [attempt(1.26, 35905, 276.5)], output=True)
        live_dir = r.call("gkc:B", {"state": "running", "model": "claude-opus-5-5", "effort": "xhigh"})
        r.flush()
        procs = [node(100, r.out, etime=429), cleanrun(200, 100, live_dir, "claude-sonnet-5-5", "high", etime=28)]
        [f] = scan(procs)
        self.assertEqual((f["kind"], f["state"], f["alive"], f["pid"], f["script"]), ("runtime", "running", True, 100, "flow.js"))
        self.assertEqual(f["elapsed_s"], 429)
        self.assertEqual(f["phases"], ["GKC", "Denetle"])
        a = by_label(f)
        self.assertEqual((a["gkc:A"]["state"], a["gkc:A"]["cost_usd"], a["gkc:A"]["out_tokens"], a["gkc:A"]["elapsed_s"],
                          a["gkc:A"]["resumed"]), ("done", 1.26, 35905, 276, False))
        self.assertEqual((a["gkc:B"]["state"], a["gkc:B"]["model"], a["gkc:B"]["effort"], a["gkc:B"]["elapsed_s"]),
                         ("running", "claude-sonnet-5-5", "high", 28))
        self.assertEqual(a["denetle:A"]["state"], "queued")
        self.assertEqual(f["counts"], {"total": 3, "done": 1, "running": 1, "queued": 1, "failed": 0, "skipped": 0})
        self.assertEqual(f["cost_usd"], 1.26)
        self.assertEqual(f["last_log"], "done gkc:A (277 s)")

    def test_tokens_count_output_and_cache_like_the_workflow_view(self):
        r = Runtime(self.root)
        r.started("x:1", "P")
        r.started("x:2", "P")
        r.log += ["done x:1 (40 s)", "done x:2 (40 s)"]
        r.call("x:1", {"state": "finished", "ran": 1}, [attempt(tokens=1000, cache_write=20000, cache_read=10600)], output=True)
        r.call("x:2", {"state": "finished", "ran": 1}, [attempt(tokens=500)], output=True)
        r.flush()
        [f] = scan([node(100, r.out)])
        a = by_label(f)
        self.assertEqual((a["x:1"]["tokens"], a["x:1"]["out_tokens"], a["x:2"]["tokens"], f["tokens"]), (31600, 1000, 500, 32100))

    def test_a_fail_line_wins_over_an_old_output_and_names_the_ledger_problem(self):
        r = Runtime(self.root)
        r.started("denetle:T5:1", "Denetle")
        r.log.append('FAIL denetle:T5:1: cleanrun exit 3: {"event": "attempt"}')
        r.call("denetle:T5:1", {"state": "finished", "ran": 0},
               [attempt(valid=False, problems=["missing key 'items'"])], output=True)
        r.flush()
        [f] = scan([node(100, r.out)])
        a = by_label(f)["denetle:T5:1"]
        self.assertEqual((a["state"], a["error"]), ("failed", "missing key 'items'"))
        self.assertEqual(f["counts"]["failed"], 1)

    def test_a_failed_call_shows_cleanruns_own_stderr(self):
        r = Runtime(self.root)
        r.started("x:1", "P")
        r.log.append("FAIL x:1: cleanrun exit 2")
        r.call("x:1", tasks_at=NOW - 30, stderr="Traceback...\ncleanrun: usage check: window full (93% used)\n")
        r.flush()
        [f] = scan([node(100, r.out)])
        self.assertEqual(by_label(f)["x:1"]["error"], "cleanrun: usage check: window full (93% used)")

    def test_a_later_done_line_replaces_an_earlier_fail(self):
        r = Runtime(self.root)
        r.started("x:1", "P")
        r.log += ["FAIL x:1: cleanrun exit 3: boom", "done x:1 (40 s)"]
        r.call("x:1", {"state": "finished", "ran": 1}, output=True)
        r.flush()
        [f] = scan([node(100, r.out)])
        a = by_label(f)["x:1"]
        self.assertEqual((a["state"], a["elapsed_s"], a["resumed"]), ("done", None, True))

    def test_a_live_process_beats_an_output_left_by_an_earlier_run(self):
        r = Runtime(self.root)
        r.started("x:1", "P")
        r.log.append("done x:1 (40 s)")
        d = r.call("x:1", {"state": "running"}, output=True)
        r.flush()
        [f] = scan([node(100, r.out), cleanrun(200, 100, d)])
        self.assertEqual(by_label(f)["x:1"]["state"], "running")

    def test_a_finished_summary_without_output_is_a_failure(self):
        r = Runtime(self.root)
        r.started("x:1", "P")
        r.call("x:1", {"state": "stopped"}, [{"event": "not_started", "error": "usage over 90%"}])
        r.flush()
        [f] = scan([node(100, r.out)])
        a = by_label(f)["x:1"]
        self.assertEqual((a["state"], a["error"]), ("failed", "usage over 90%"))

    def test_ended_runs_without_a_start_line_read_their_state_from_files(self):
        cases = [("done", {"result.json": "{}", "cost.json": '{"total_usd": 49.52}'}),
                 ("failed", {"cost.json": '{"total_usd": 3.0}'}),
                 ("died", {})]
        for want, files in cases:
            with self.subTest(want=want):
                r = Runtime(self.root, name="run_" + want)
                r.started("x:1", "P")
                r.call("x:1", {"state": "finished", "ran": 1}, [attempt(2.0)], output=True)
                r.flush()
                for name, text in files.items():
                    write(os.path.join(r.out, name), text)
                [f] = scan([], known=[r.out])
                self.assertEqual((f["state"], f["alive"]), (want, False))
                self.assertIsNotNone(f["ended_at"])
                self.assertEqual(f["cost_usd"], 2.0)   # this run's ledgers, never a stale cost.json
                if want != "done":
                    self.assertTrue(f["problems"])

    def test_a_rerun_that_dies_is_not_done_although_the_first_run_left_result_json(self):
        r = Runtime(self.root)
        t1, t2 = NOW - 3600, NOW - 600     # first run, then the re-run
        r.log += [f"[{hms(t1)}] start flow.js jobs=6", f"[{hms(t1 + 60)}] FAIL x:2: cleanrun exit 3: boom",
                  f"[{hms(t1 + 120)}] done old:1 (50 s)", f"[{hms(t1 + 130)}] cost (list price, ...)",
                  f"[{hms(t1 + 130)}] finished in 2 min -> r", f"[{hms(t2)}] start flow.js jobs=6",
                  f"[{hms(t2 + 30)}] done x:1 (25 s)"]
        for label in ("old:1", "x:1", "x:2"):
            r.started(label, "P")
        r.call("old:1", {"state": "finished", "ran": 1}, [attempt(5.0, ts=t1 + 100)], output=True, tasks_at=t1 + 10)
        r.call("x:1", {"state": "finished", "ran": 1}, [attempt(9.0, ts=t1 + 50), attempt(0.5, ts=t2 + 25)],
               output=True, tasks_at=t2 + 5)
        r.call("x:2", None, [attempt(valid=False, ts=t1 + 55)], tasks_at=t2 + 40)
        write(os.path.join(r.out, "result.json"), "{}")
        write(os.path.join(r.out, "cost.json"), '{"total_usd": 14.5}')
        touch(os.path.join(r.out, "result.json"), t1 + 130)
        r.flush(log_at=t2 + 30)
        [f] = scan([], known=[r.out])
        self.assertEqual(f["state"], "died")
        self.assertEqual([a["label"] for a in f["agents"]], ["x:1", "x:2"])   # old:1 belongs to the first run
        a = by_label(f)
        self.assertEqual((a["x:1"]["state"], a["x:1"]["attempts"], a["x:1"]["cost_usd"]), ("done", 1, 0.5))
        self.assertEqual(a["x:2"]["state"], "skipped")     # its FAIL was in the first run
        self.assertEqual(f["cost_usd"], 0.5)
        self.assertEqual(f["started_at"], t2)
        self.assertIn("no process, and the last run never finished", f["problems"])

    def test_a_finished_rerun_is_timed_from_its_own_start_line_across_midnight(self):
        r = Runtime(self.root)
        day = (NOW // 86400) * 86400
        start, end = day - 120, day + 180    # 23:58:00 to 00:03:00
        r.log += [f"[{hms(start - 3000)}] start flow.js", f"[{hms(start - 100)}] finished in 48 min -> r",
                  f"[{hms(start)}] start flow.js", f"[{hms(end)}] cost (list price, ...)",
                  f"[{hms(end)}] finished in 5 min -> r"]
        r.flush(log_at=end)
        write(os.path.join(r.out, "result.json"), "{}")
        touch(os.path.join(r.out, "result.json"), end)
        [f] = scan([], known=[r.out], now=day + 600)
        self.assertEqual((f["state"], f["started_at"], f["ended_at"], f["elapsed_s"]), ("done", start, end, 300))

    def test_a_live_rerun_counts_only_its_own_cost(self):
        r = Runtime(self.root)
        r.started("x:1", "P")
        r.log += [f"[{hms(NOW - 7200)}] start flow.js", f"[{hms(NOW - 100)}] start flow.js"]
        d = r.call("x:1", {"state": "running"}, [attempt(20.0, ts=NOW - 7000), attempt(1.5, ts=NOW - 50)],
                   tasks_at=NOW - 90)
        write(os.path.join(r.out, "cost.json"), '{"total_usd": 20.0}')
        r.flush()
        [f] = scan([node(100, r.out, etime=100), cleanrun(200, 100, d)])
        self.assertEqual(f["cost_usd"], 1.5)

    def test_a_running_placeholder_under_a_dead_runtime_is_a_dead_call(self):
        r = Runtime(self.root)
        r.started("x:1", "P")
        r.started("x:2", "P")
        r.call("x:1", {"state": "running"})
        r.flush()
        [f] = scan([], known=[r.out])
        a = by_label(f)
        self.assertEqual((a["x:1"]["state"], a["x:1"]["error"]), ("died", "its process is gone"))
        self.assertEqual(a["x:2"]["state"], "skipped")
        self.assertEqual(f["state"], "died")

    def test_a_dead_runtime_ends_at_its_newest_file(self):
        r = Runtime(self.root)
        r.started("x:1", "P")
        r.log.append(f"[{hms(NOW - 900)}] start flow.js")
        r.call("x:1", {"state": "running"}, tasks_at=NOW - 800)
        r.flush(log_at=NOW - 800)
        touch(os.path.join(r.out, "journal.jsonl"), NOW - 800)
        touch(os.path.join(r.out, "calls", "x_1", "out", "summary.json"), NOW - 60)
        [f] = scan([], known=[r.out])
        self.assertEqual(f["ended_at"], NOW - 60)

    def test_an_orphaned_cleanrun_is_shown_under_its_runtime(self):
        r = Runtime(self.root)
        r.started("x:1", "P")
        d = r.call("x:1", {"state": "running"})
        r.flush()
        [f] = scan([cleanrun(200, 1, d)])
        self.assertEqual((f["kind"], f["dir"], f["state"]), ("runtime", r.out, "died"))
        self.assertEqual(by_label(f)["x:1"]["state"], "running")
        self.assertIn("calls still running with no runtime process to record them", f["problems"])

    def test_two_labels_on_one_call_folder_are_flagged_and_do_not_share_numbers(self):
        r = Runtime(self.root)
        r.started("kavram:şekil", "P")
        r.started("kavram:çekil", "P")
        r.log.append("FAIL kavram:çekil: cleanrun exit 2")
        d = r.call("kavram:şekil", {"state": "running"}, [attempt(0.3, ts=NOW - 5)])
        r.flush()
        [f] = scan([node(100, r.out), cleanrun(200, 100, d)])
        a = by_label(f)
        self.assertEqual(a["kavram:şekil"]["state"], "running")
        self.assertEqual((a["kavram:çekil"]["state"], a["kavram:çekil"]["error"], a["kavram:çekil"]["cost_usd"]),
                         ("failed", "shares calls/kavram__ekil with kavram:şekil", None))
        self.assertIn("labels kavram:şekil, kavram:çekil share calls/kavram__ekil: they ran as one call", f["problems"])

    def test_two_labels_on_one_call_folder_without_a_fail_count_its_numbers_once(self):
        r = Runtime(self.root)
        r.started("kavram:şekil", "P")
        r.started("kavram:çekil", "P")
        r.log += ["done kavram:şekil (30 s)", "done kavram:çekil (1 s)"]
        r.call("kavram:şekil", {"state": "finished", "ran": 1}, [attempt(0.3, tokens=1000, ts=NOW - 5)], output=True)
        r.flush()
        [f] = scan([node(100, r.out)])
        a = by_label(f)
        self.assertEqual((a["kavram:şekil"]["state"], a["kavram:çekil"]["state"]), ("done", "done"))
        self.assertEqual((a["kavram:çekil"]["cost_usd"], a["kavram:çekil"]["tokens"]), (None, None))
        self.assertEqual((f["cost_usd"], f["tokens"]), (0.3, 1000))
        self.assertIn("labels kavram:şekil, kavram:çekil share calls/kavram__ekil: they ran as one call", f["problems"])

    def test_a_path_with_spaces_is_joined_back(self):
        r = Runtime(self.root, name="My Runs")
        r.started("x:1", "P")
        d = r.call("x:1", {"state": "running"})
        r.flush()
        [f] = scan([node(100, r.out), cleanrun(200, 100, d)])
        self.assertEqual((f["dir"], f["name"]), (r.out, "My Runs"))
        self.assertEqual(by_label(f)["x:1"]["state"], "running")

    def test_a_relative_out_is_resolved_through_the_process_cwd_once(self):
        r = Runtime(self.root)
        r.started("x:1", "P")
        r.flush()
        asked = []

        def lookup(pid):
            asked.append(pid)
            return self.root

        resolver = fs.Resolver({}, lookup)
        [f], _ = fs.scan([node(100, "run1")], [], resolver, NOW)
        self.assertEqual(f["dir"], r.out)
        fs.scan([node(100, "run1")], [], resolver, NOW)
        self.assertEqual(asked, [100])
        self.assertEqual(resolver.cwds, {100: self.root})

    def test_a_cwd_handed_back_skips_the_lookup(self):
        r = Runtime(self.root)
        r.flush()
        [f], _ = fs.scan([node(100, "run1")], [], fs.Resolver({100: self.root}, no_lookup), NOW)
        self.assertEqual(f["dir"], r.out)

    def test_a_known_folder_a_process_may_hold_is_unknown_not_dead(self):
        r = Runtime(self.root)
        r.started("x:1", "P")
        r.flush()
        fanouts, unresolved = fs.scan([node(100, "run1")], [r.out], fs.Resolver({}, lambda pid: None), NOW)
        self.assertEqual(unresolved, ["run1"])
        self.assertEqual([(f["dir"], f["state"]) for f in fanouts], [(r.out, "unknown")])

    def test_a_live_fanouts_own_folder_given_back_is_not_listed_twice(self):
        r = Runtime(self.root)
        r.flush()
        fanouts = scan([node(100, r.out)], known=[r.out, r.out + "/"])
        self.assertEqual([f["state"] for f in fanouts], ["running"])

    def test_a_relabelled_call_follows_its_last_started_line(self):
        r = Runtime(self.root)
        r.started("x:1", "P", key="c1:old")
        r.result("x:1", key="c1:old")
        r.started("x:1", "P", key="c1:new")
        r.flush()
        [f] = scan([node(100, r.out)])
        self.assertEqual(len(f["agents"]), 1)
        self.assertEqual(f["agents"][0]["state"], "queued")   # the new prompt has not run yet

    def test_a_known_folder_that_was_deleted_is_skipped(self):
        self.assertEqual(scan([], known=[os.path.join(self.root, "gone")]), [])

    def test_running_fanouts_come_first(self):
        old = Runtime(self.root, "old")
        old.flush()
        write(os.path.join(old.out, "result.json"), "{}")
        live = Runtime(self.root, "live")
        live.flush()
        fanouts = scan([node(100, live.out)], known=[old.out])
        self.assertEqual([f["name"] for f in fanouts], ["live", "old"])


class RunScopeTest(unittest.TestCase):
    """What belongs to the current run of a folder used more than once."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        self.addCleanup(self.tmp.cleanup)

    def test_an_old_output_does_not_make_a_rerun_call_done(self):
        r = Runtime(self.root)
        r.started("x:1", "P")
        d = r.call("x:1", None, output=True, tasks_at=NOW - 30)
        touch(os.path.join(d, "outputs", "x_1.json"), NOW - 5000)
        r.flush()
        [f] = scan([node(100, r.out, etime=60)])
        self.assertEqual(by_label(f)["x:1"]["state"], "queued")

    def test_an_old_summary_does_not_make_a_rerun_call_failed(self):
        r = Runtime(self.root)
        r.started("x:1", "P")
        d = r.call("x:1", {"state": "finished", "ran": 0}, tasks_at=NOW - 30)
        touch(os.path.join(d, "summary.json"), NOW - 5000)
        r.flush()
        [f] = scan([node(100, r.out, etime=60)])
        self.assertEqual(by_label(f)["x:1"]["state"], "queued")

    def test_an_old_stderr_is_not_this_failures_reason(self):
        r = Runtime(self.root)
        r.started("x:1", "P")
        r.log.append("FAIL x:1: cleanrun exit 2")
        r.call("x:1", tasks_at=NOW - 30, stderr="old: usage window full\n")
        touch(os.path.join(r.out, "calls", "x_1", "stderr.txt"), NOW - 5000)
        r.flush()
        [f] = scan([node(100, r.out, etime=60)])
        self.assertEqual(by_label(f)["x:1"]["error"], "cleanrun exit 2")

    def test_a_summary_stop_reason_explains_a_failed_call(self):
        r = Runtime(self.root)
        r.started("x:1", "P")
        r.log.append("FAIL x:1: cleanrun exit 3")
        r.call("x:1", {"state": "stopped", "stopped": "max-usd 6 reached"}, tasks_at=NOW - 30)
        r.flush()
        [f] = scan([node(100, r.out, etime=60)])
        self.assertEqual(by_label(f)["x:1"]["error"], "max-usd 6 reached")

    def test_the_shared_ledger_counts_only_this_runs_attempts(self):
        r = Runtime(self.root)
        r.started("x:1", "P")
        r.log += [f"[{hms(NOW - 9000)}] start flow.js", f"[{hms(NOW - 100)}] start flow.js", "done x:1 (40 s)"]
        write(os.path.join(r.out, "ledger.jsonl"), jl({"id": "x_1", **attempt(9.0, ts=NOW - 8000)},
                                                      {"id": "x_1", **attempt(0.5, ts=NOW - 50)}))
        r.flush(log_at=NOW - 10)
        [f] = scan([], known=[r.out])
        self.assertEqual((by_label(f)["x:1"]["cost_usd"], f["cost_usd"]), (0.5, 0.5))

    def test_a_run_whose_script_threw_is_failed_by_its_log(self):
        r = Runtime(self.root)
        r.log += [f"[{hms(NOW - 300)}] start flow.js", f"[{hms(NOW - 20)}] cost (list price, this run's attempts): $1"]
        r.flush(log_at=NOW - 20)
        [f] = scan([], known=[r.out])
        self.assertEqual(f["state"], "failed")

    def test_a_finished_run_ignores_a_result_json_left_by_an_earlier_run(self):
        r = Runtime(self.root)
        r.log += [f"[{hms(NOW - 300)}] start flow.js", f"[{hms(NOW - 20)}] finished in 5 min -> r"]
        r.flush(log_at=NOW - 20)
        write(os.path.join(r.out, "result.json"), "{}")
        touch(os.path.join(r.out, "result.json"), NOW - 9000)
        [f] = scan([], known=[r.out])
        self.assertEqual((f["state"], f["ended_at"], f["elapsed_s"]), ("done", NOW - 20, 280))

    def test_a_finished_run_ends_at_its_result_json(self):
        r = Runtime(self.root)
        r.log += [f"[{hms(NOW - 300)}] start flow.js", f"[{hms(NOW - 20)}] finished in 5 min -> r"]
        r.flush(log_at=NOW - 10)
        write(os.path.join(r.out, "result.json"), "{}")
        touch(os.path.join(r.out, "result.json"), NOW - 20)
        [f] = scan([], known=[r.out])
        self.assertEqual(f["ended_at"], NOW - 20)

    def test_a_dead_run_from_days_ago_is_dated_by_its_log_not_today(self):
        r = Runtime(self.root)
        end = NOW - 3 * 86400
        r.log += [f"[{hms(end - 600)}] start flow.js"]
        r.flush(log_at=end)
        touch(os.path.join(r.out, "journal.jsonl"), end)
        [f] = scan([], known=[r.out])
        self.assertEqual((f["started_at"], f["ended_at"], f["elapsed_s"]), (end - 600, end, 600))

    def test_a_dead_run_ends_at_its_journal_when_that_is_newest(self):
        r = Runtime(self.root)
        r.log += [f"[{hms(NOW - 900)}] start flow.js"]
        r.flush(log_at=NOW - 800)
        touch(os.path.join(r.out, "journal.jsonl"), NOW - 70)
        [f] = scan([], known=[r.out])
        self.assertEqual(f["ended_at"], NOW - 70)

    def test_an_emoji_label_finds_the_folder_clean_runtime_made(self):
        self.assertEqual(fs.call_id("kavram:🙂A"), "kavram___A")
        self.assertEqual(len(fs.call_id("🙂" * 100)), 120)

    def test_a_trailing_word_after_a_spaced_path_is_not_part_of_it(self):
        r = Runtime(self.root, name="My Runs")
        r.flush()
        p = node(100, r.out)
        p["argv"] = p["argv"][:-2] + ["extra"]   # ... --out My Runs extra
        [f] = scan([p])
        self.assertEqual(f["dir"], r.out)

    def test_a_three_part_spaced_path_takes_the_longest_join(self):
        r = Runtime(self.root, name="a b c")
        os.makedirs(os.path.join(self.root, "a b"))
        r.flush()
        [f] = scan([node(100, r.out)])
        self.assertEqual(f["dir"], r.out)

    def test_an_unresolved_process_holds_only_the_folder_its_path_names(self):
        held = Runtime(self.root, "run1")
        held.flush()
        other = Runtime(self.root, "run2")
        other.flush()
        fanouts, _ = fs.scan([node(100, "run1")], [held.out, other.out], fs.Resolver({}, lambda pid: None), NOW)
        self.assertEqual(sorted((f["name"], f["state"]) for f in fanouts), [("run1", "unknown"), ("run2", "died")])

    def test_an_unresolved_dot_path_may_hold_any_known_folder(self):
        r = Runtime(self.root, "run1")
        r.flush()
        fanouts, _ = fs.scan([node(100, ".")], [r.out], fs.Resolver({}, lambda pid: None), NOW)
        self.assertEqual([f["state"] for f in fanouts], ["unknown"])

    def test_running_first_then_newest_first(self):
        old, newer = Runtime(self.root, "old"), Runtime(self.root, "newer")
        for rt, t in ((old, NOW - 9000), (newer, NOW - 3000)):
            rt.log.append(f"[{hms(t)}] start flow.js")
            rt.flush(log_at=t + 60)
            touch(os.path.join(rt.out, "journal.jsonl"), t + 60)
        live = Runtime(self.root, "live")
        live.flush()
        fanouts = scan([node(100, live.out)], known=[old.out, newer.out])
        self.assertEqual([f["name"] for f in fanouts], ["live", "newer", "old"])


class CleanrunTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        self.addCleanup(self.tmp.cleanup)
        self.out = os.path.join(self.root, "evalA", "out")
        os.makedirs(self.out)
        self.tasks = os.path.join(self.root, "evalA", "tasks.jsonl")
        write(self.tasks, jl({"id": "t1", "prompt": "p"}, {"id": "t2", "prompt": "p"}, {"id": "t3", "prompt": "p"}))

    def test_a_live_standalone_run_counts_its_claude_children_as_running(self):
        write(os.path.join(self.out, "outputs", "t1.json"), "{}")
        write(os.path.join(self.out, "ledger.jsonl"), jl({"id": "t1", **attempt(0.5, 800, 30, ts=NOW - 20)}))
        write(os.path.join(self.out, "summary.json"), json.dumps({"state": "running"}))
        procs = [{"pid": 50, "ppid": 1, "etime": 90, "argv": ["zsh"]},
                 cleanrun(300, 50, self.out, "claude-haiku-5-5", "medium", etime=90, tasks=self.tasks),
                 claude_child(301, 300), claude_child(302, 300)]
        [f] = scan(procs)
        self.assertEqual((f["kind"], f["name"], f["state"], f["elapsed_s"]), ("cleanrun", "evalA/out", "running", 90))
        self.assertEqual([a["id"] for a in f["agents"]], ["t1", "t2", "t3"])
        self.assertEqual([a["state"] for a in f["agents"]], ["done", "pending", "pending"])
        self.assertEqual(f["agents"][1]["model"], "claude-haiku-5-5")
        self.assertEqual((f["counts"]["running"], f["counts"]["queued"], f["counts"]["done"]), (2, 0, 1))
        self.assertEqual(f["cost_usd"], 0.5)

    def test_a_task_out_of_attempts_fails_while_the_run_goes_on(self):
        write(os.path.join(self.out, "ledger.jsonl"), jl(
            {"id": "t2", **attempt(valid=False, problems=["not JSON"], ts=NOW - 9000)},   # an earlier invocation
            {"id": "t1", **attempt(valid=False, problems=["bad"], ts=NOW - 50)},
            {"id": "t2", **attempt(valid=False, problems=["not JSON"], ts=NOW - 40)},
            {"id": "t2", **attempt(valid=False, problems=["still not JSON"], ts=NOW - 20)},
            {"id": "t3", "event": "not_started", "error": "per-run budget reached", "ts": iso(NOW - 10)}))
        [f] = scan([cleanrun(300, 50, self.out, etime=60, tasks=self.tasks, retries=1)])
        a = {x["id"]: x for x in f["agents"]}
        self.assertEqual((a["t1"]["state"], a["t1"]["attempts"]), ("pending", 1))
        self.assertEqual((a["t2"]["state"], a["t2"]["attempts"], a["t2"]["error"]), ("failed", 2, "still not JSON"))
        self.assertEqual((a["t3"]["state"], a["t3"]["error"]), ("failed", "per-run budget reached"))
        self.assertEqual(f["counts"]["failed"], 2)

    def test_a_finished_standalone_run_reads_failed_and_not_run_tasks(self):
        write(os.path.join(self.out, ".lock"), "300")
        write(os.path.join(self.out, "outputs", "t1.json"), "{}")
        write(os.path.join(self.out, "summary.json"), json.dumps({
            "state": "finished", "charged_usd": 1.234567, "model": "claude-sonnet-5-5", "effort": "high",
            "failed": [{"id": "t2", "problems": ["not JSON"]}], "crashed": [],
            "not_run": [{"id": "t3", "problems": ["interrupted"]}]}))
        [f] = scan([], [self.out])
        a = {x["id"]: x for x in f["agents"]}
        self.assertEqual((f["state"], f["cost_usd"]), ("done", 1.2346))
        self.assertEqual((a["t1"]["state"], a["t2"]["state"], a["t2"]["error"], a["t3"]["state"], a["t3"]["error"]),
                         ("done", "failed", "not JSON", "skipped", "interrupted"))
        self.assertEqual(a["t2"]["model"], "claude-sonnet-5-5")

    def test_a_killed_standalone_run_ends_at_its_newest_file(self):
        write(os.path.join(self.out, ".lock"), "300")
        touch(os.path.join(self.out, ".lock"), NOW - 3600)
        write(os.path.join(self.out, "summary.json"), json.dumps({"state": "running"}))
        touch(os.path.join(self.out, "summary.json"), NOW - 3600)
        write(os.path.join(self.out, "outputs", "t1.json"), "{}")
        touch(os.path.join(self.out, "outputs", "t1.json"), NOW - 100)
        [f] = scan([], [self.out])
        self.assertEqual((f["state"], f["started_at"], f["ended_at"], f["elapsed_s"]), ("died", NOW - 3600, NOW - 100, 3500))

    def test_a_stopped_standalone_run_says_why(self):
        write(os.path.join(self.out, "summary.json"), json.dumps({"state": "stopped", "stopped": "max-usd reached"}))
        [f] = scan([], [self.out])
        self.assertEqual((f["state"], f["problems"]), ("stopped", ["max-usd reached"]))


    def test_without_a_retries_flag_one_retry_is_allowed(self):
        write(os.path.join(self.out, "ledger.jsonl"), jl(
            {"id": "t1", **attempt(valid=False, ts=NOW - 30)},
            {"id": "t2", **attempt(valid=False, ts=NOW - 30)}, {"id": "t2", **attempt(valid=False, ts=NOW - 20)}))
        [f] = scan([cleanrun(300, 50, self.out, etime=60, tasks=self.tasks)])
        a = {x["id"]: x["state"] for x in f["agents"]}
        self.assertEqual((a["t1"], a["t2"]), ("pending", "failed"))

    def test_the_retries_flag_is_read(self):
        write(os.path.join(self.out, "ledger.jsonl"), jl(*[{"id": "t1", **attempt(valid=False, ts=NOW - 30)}] * 2))
        [f] = scan([cleanrun(300, 50, self.out, etime=60, tasks=self.tasks, retries=3)])
        self.assertEqual(f["agents"][0]["state"], "pending")

    def test_a_task_that_will_not_be_retried_fails_at_once(self):
        write(os.path.join(self.out, "ledger.jsonl"), jl(
            {"id": "t1", **attempt(valid=False, problems=["per-run budget reached (--per-run-usd 2.5); not retried"], ts=NOW - 30)},
            {"id": "t2", **attempt(valid=False, problems=["interrupted"], ts=NOW - 20)}))
        [f] = scan([cleanrun(300, 50, self.out, etime=60, tasks=self.tasks, retries=1)])
        a = {x["id"]: x for x in f["agents"]}
        self.assertEqual((a["t1"]["state"], a["t2"]["state"]), ("failed", "failed"))

    def test_an_old_output_with_attempts_now_is_being_redone_not_done(self):
        write(os.path.join(self.out, "outputs", "t1.json"), "{}")
        touch(os.path.join(self.out, "outputs", "t1.json"), NOW - 9000)
        write(os.path.join(self.out, "outputs", "t2.json"), "{}")
        touch(os.path.join(self.out, "outputs", "t2.json"), NOW - 9000)
        write(os.path.join(self.out, "ledger.jsonl"), jl({"id": "t1", **attempt(valid=False, ts=NOW - 30)}))
        [f] = scan([cleanrun(300, 50, self.out, etime=60, tasks=self.tasks)])
        a = {x["id"]: x for x in f["agents"]}
        self.assertEqual((a["t1"]["state"], a["t2"]["state"], a["t2"]["resumed"]), ("pending", "done", True))

    def test_a_reused_out_dir_counts_only_what_this_run_requested(self):
        write(os.path.join(self.out, ".lock"), "300")
        touch(os.path.join(self.out, ".lock"), NOW - 600)
        for n, t in (("old1", NOW - 9000), ("old2", NOW - 9000), ("old3", NOW - 9000), ("t1", NOW - 300)):
            write(os.path.join(self.out, "outputs", n + ".json"), "{}")
            touch(os.path.join(self.out, "outputs", n + ".json"), t)
        write(os.path.join(self.out, "ledger.jsonl"), jl({"id": "t1", **attempt(0.4, ts=NOW - 300)}))
        write(os.path.join(self.out, "summary.json"), json.dumps({"state": "finished", "requested": 2, "ran": 1, "resumed": 1}))
        [f] = scan([], [self.out])
        self.assertEqual(f["counts"]["total"], 2)
        a = {x["id"]: x for x in f["agents"]}
        self.assertEqual((a["t1"]["resumed"], sum(x["resumed"] for x in f["agents"])), (False, 1))

    def test_a_finished_standalone_run_ends_at_its_summary(self):
        write(os.path.join(self.out, ".lock"), "300")
        touch(os.path.join(self.out, ".lock"), NOW - 600)
        write(os.path.join(self.out, "outputs", "t1.json"), "{}")
        touch(os.path.join(self.out, "outputs", "t1.json"), NOW - 200)
        write(os.path.join(self.out, "summary.json"), json.dumps({"state": "finished", "requested": 1}))
        touch(os.path.join(self.out, "summary.json"), NOW - 100)
        [f] = scan([], [self.out])
        self.assertEqual((f["ended_at"], f["elapsed_s"]), (NOW - 100, 500))


class ChatScopeTest(unittest.TestCase):
    """2026-11-06: one chat's clean run showed in every other chat, because the scanner read the whole machine's
    process table. A run is listed for the chat (the claude process) it descends from or that its summary.json
    names as its owner."""

    ME, OTHER = 100, 200

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        self.addCleanup(self.tmp.cleanup)
        self.claude = [{"pid": 100, "ppid": 50, "etime": 5000, "argv": ["claude"]},
                       {"pid": 101, "ppid": 100, "etime": 4000, "argv": ["/bin/zsh", "-c", "run"]},
                       {"pid": 200, "ppid": 51, "etime": 5000, "argv": ["claude", "-c"]},
                       {"pid": 201, "ppid": 200, "etime": 4000, "argv": ["/bin/zsh", "-c", "run"]}]

    def run_dir(self, name, record=None, state="running"):
        out = os.path.join(self.root, name, "out")
        os.makedirs(out)
        write(os.path.join(self.root, name, "tasks.jsonl"), jl({"id": "t1", "prompt": "p"}))
        write(os.path.join(out, ".lock"), "1")
        summ = {"state": state, "requested": 1}
        if record is not None:
            summ["owner"] = {"pid": record, "session": "s"}
        write(os.path.join(out, "summary.json"), json.dumps(summ))
        return out

    def world(self):
        """Seven runs: two chats, runs that kept their parent and runs that lost it."""
        w = {"A": self.run_dir("a"), "B": self.run_dir("b"), "C": self.run_dir("c", record=self.ME),
             "D": self.run_dir("d", record=self.OTHER), "E": self.run_dir("e")}
        r1, r2 = Runtime(self.root, "r1"), Runtime(self.root, "r2")
        r1.flush()
        r2.flush()
        w["R1"], w["R2"] = r1.out, r2.out
        procs = self.claude + [
            cleanrun(110, 101, w["A"]), cleanrun(210, 201, w["B"]),
            cleanrun(120, 1, w["C"]), cleanrun(220, 1, w["D"]), cleanrun(130, 1, w["E"]),
            {**node(140, w["R1"]), "ppid": 101}, {**node(240, w["R2"]), "ppid": 201}]
        return w, procs

    def dirs(self, procs, owner, known=()):
        fanouts, _ = fs.scan(procs, list(known), fs.Resolver({}, no_lookup), NOW, owner)
        return {f["dir"] for f in fanouts}

    def test_a_chat_lists_the_runs_below_it_and_the_ones_that_name_it_and_no_others(self):
        w, procs = self.world()
        self.assertEqual(self.dirs(procs, self.ME), {w["A"], w["C"], w["R1"]})
        self.assertEqual(self.dirs(procs, self.OTHER), {w["B"], w["D"], w["R2"]})

    def test_without_an_owner_every_run_on_the_machine_is_listed_as_before(self):
        w, procs = self.world()
        self.assertEqual(self.dirs(procs, None), set(w.values()))

    def test_a_run_with_no_link_to_any_chat_is_listed_for_none(self):
        w, procs = self.world()
        self.assertNotIn(w["E"], self.dirs(procs, self.ME) | self.dirs(procs, self.OTHER))

    def test_a_foreign_run_whose_folder_cannot_be_resolved_is_not_reported_as_unresolved(self):
        mine = cleanrun(111, 101, "rel/out")
        theirs = {**mine, "pid": 211, "ppid": 201}
        _, unresolved = fs.scan(self.claude + [mine, theirs], [], fs.Resolver({}, lambda pid: None), NOW, self.ME)
        self.assertEqual(unresolved, ["rel/out"])        # one: the chat's own

    def test_a_known_folder_that_names_another_owner_is_dropped(self):
        w, procs = self.world()
        gone = self.run_dir("gone", record=self.ME, state="finished")
        foreign = self.run_dir("foreign", record=self.OTHER, state="finished")
        unrecorded = self.run_dir("old", state="finished")        # a run from before the field: cannot tell, kept
        shown = self.dirs(self.claude, self.ME, known=[gone, foreign, unrecorded])
        self.assertEqual(shown, {gone, unrecorded})
        self.assertEqual(self.dirs(self.claude, None, known=[gone, foreign, unrecorded]), {gone, foreign, unrecorded})

    def test_a_runtime_that_lost_its_parent_is_still_running_through_the_calls_that_name_the_chat(self):
        # `node clean_runtime.mjs ... &` re-parents to PID 1; its calls inherited the chat's CLAUDE_PID
        r = Runtime(self.root, "r3")
        r.started("x:1", "P")
        call = r.call("x:1", {"state": "running", "owner": {"pid": self.ME}})
        r.flush()
        procs = self.claude + [node(140, r.out), cleanrun(141, 140, call)]
        for owner, shown in ((self.ME, True), (self.OTHER, False)):
            with self.subTest(owner=owner):
                fanouts, _ = fs.scan(procs, [], fs.Resolver({}, no_lookup), NOW, owner)
                self.assertEqual([f["dir"] for f in fanouts], [r.out] if shown else [])
                for f in fanouts:
                    self.assertEqual(f["state"], "running")        # its node is alive: not "died"
                    self.assertNotIn("calls still running with no runtime process to record them", f["problems"])

    def test_the_scanner_works_for_the_nearest_claude_above_it(self):
        procs = self.claude + [{"pid": 150, "ppid": 101, "etime": 1, "argv": ["sh", "-c", "python3 fanout_scan.py"]}]
        self.assertEqual(fs.chat_pid(procs, 101), 100)           # a shell in between
        self.assertEqual(fs.chat_pid(procs, 150), 100)
        self.assertEqual(fs.chat_pid(procs, 100), 100)           # its direct parent is the claude process
        self.assertEqual(fs.chat_pid(procs, 999), 999)           # not in the table: its parent, as the last resort
        self.assertEqual(fs.chat_pid([{"pid": 7, "ppid": 1, "etime": 1, "argv": ["zsh"]}], 7), 7)

    def snapshot(self, procs, args, parent):
        ps_out = mock.Mock(stdout="".join(f"{p['pid']} {p['ppid']} 01:00 {' '.join(p['argv'])}\n" for p in procs),
                           returncode=0, stderr="")
        with mock.patch.object(fs.subprocess, "run", return_value=ps_out), mock.patch.object(fs.os, "getppid", return_value=parent):
            buf = io.StringIO()
            with redirect_stdout(buf):
                fs.main(args)
        return json.loads(buf.getvalue())

    def test_main_scopes_to_its_chat_unless_told_otherwise(self):
        w, procs = self.world()
        got = lambda snap: {f["dir"] for f in snap["fanouts"]}
        mine = self.snapshot(procs, [], parent=100)                    # as the module runs it
        self.assertEqual((mine["owner"], got(mine)), (100, {w["A"], w["C"], w["R1"]}))
        shell = self.snapshot(procs, [], parent=101)                   # through a shell
        self.assertEqual(shell["owner"], 100)
        named = self.snapshot(procs, ["--owner", "200"], parent=100)
        self.assertEqual((named["owner"], got(named)), (200, {w["B"], w["D"], w["R2"]}))
        every = self.snapshot(procs, ["--all"], parent=100)
        self.assertEqual((every["owner"], got(every)), (None, set(w.values())))
        bad = self.snapshot(procs, ["--owner", "x"], parent=100)       # a bad pid is reported and the default holds
        self.assertEqual(bad["owner"], 100)
        self.assertTrue(any("--owner" in q for q in bad["problems"]))


class MainTest(unittest.TestCase):
    def test_main_prints_a_degraded_v1_snapshot_when_ps_fails(self):
        with mock.patch.object(fs.subprocess, "run", side_effect=OSError("no ps")):
            buf = io.StringIO()
            with redirect_stdout(buf):
                self.assertEqual(fs.main(["--bogus"]), 0)
        snap = json.loads(buf.getvalue())
        self.assertEqual((snap["v"], snap["fanouts"], snap["degraded"]), (1, [], True))
        self.assertTrue(any("ps failed" in p for p in snap["problems"]))
        self.assertTrue(any("--bogus" in p for p in snap["problems"]))

    def test_main_hands_back_only_cwds_of_live_processes(self):
        ps_out = mock.Mock(stdout="  100 1 01:00 sleep 5\n", returncode=0, stderr="")
        with mock.patch.object(fs.subprocess, "run", return_value=ps_out):
            buf = io.StringIO()
            with redirect_stdout(buf):
                fs.main(["--cwd", "100=/a", "--cwd", "999=/gone"])
        snap = json.loads(buf.getvalue())
        self.assertEqual((snap["cwds"], snap["degraded"]), ({"100": "/a"}, False))

    def test_a_ps_that_exits_non_zero_or_prints_nothing_is_degraded(self):
        for out in (mock.Mock(stdout="", returncode=1, stderr="ps: Operation not permitted"),
                    mock.Mock(stdout="", returncode=0, stderr="")):
            with self.subTest(rc=out.returncode), mock.patch.object(fs.subprocess, "run", return_value=out):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    fs.main([])
                snap = json.loads(buf.getvalue())
                self.assertTrue(snap["degraded"])
                self.assertTrue(any(p.startswith("ps failed: exit") for p in snap["problems"]))


if __name__ == "__main__":
    unittest.main()
