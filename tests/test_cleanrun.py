"""Tests for scripts/cleanrun.py, run end to end against tests/fixtures/fake_claude_cleanrun.py.

Every test that can hang under a regression (process groups, timeouts, signals) waits
through its own deadline, so a regression fails the test instead of hanging the suite.
"""

import json
import os
import shlex
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "cleanrun.py"
FAKE = Path(__file__).resolve().parent / "fixtures" / "fake_claude_cleanrun.py"
MODEL = "claude-opus-5-5"
SCHEMA = {"type": "object", "properties": {"answer": {"type": "string"}}, "required": ["answer"]}
VALIDATOR = "def validate(output, task):\n    return [] if output.get('answer') == 'ok' else ['answer is not ok']\n"


def alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def wait_until(pred, deadline_s, step=0.1):
    end = time.time() + deadline_s
    while time.time() < end:
        if pred():
            return True
        time.sleep(step)
    return pred()


class Case(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.d = Path(self._tmp.name)
        self.out = self.d / "out"
        self.log = self.d / "fake.log"
        self.pids = self.d / "pids"
        self.pids.mkdir()
        (self.d / "state").mkdir()
        (self.d / "rules.md").write_bytes(b"RULES: answer ok.\r\nSecond line.\r\n")
        (self.d / "schema.json").write_text(json.dumps(SCHEMA), encoding="utf-8")
        (self.d / "check.py").write_text(VALIDATOR, encoding="utf-8")
        self.env = dict(os.environ, CLEANRUN_CLAUDE_BIN=f"{shlex.quote(sys.executable)} {shlex.quote(str(FAKE))}",
                        FAKE_LOG=str(self.log), FAKE_PIDS_DIR=str(self.pids), FAKE_STATE_DIR=str(self.d / "state"),
                        CLEANRUN_GATE_BACKOFF_S="0.05", CLEANRUN_GRACE_S="4")

    def tearDown(self):
        for f in self.pids.glob("*.pid"):            # never leave a sleeping grandchild or orphan behind
            try:
                os.kill(int(f.read_text()), signal.SIGKILL)
            except (ProcessLookupError, ValueError):
                pass
        self._tmp.cleanup()

    def tasks(self, prompts, files=None, ids=None):
        path = self.d / "tasks.jsonl"
        with open(path, "w", encoding="utf-8") as f:
            for i, p in enumerate(prompts):
                t = {"id": ids[i] if ids else f"t{i}", "prompt": p}
                if files and i in files:
                    t["files"] = files[i]
                f.write(json.dumps(t, ensure_ascii=False) + "\n")
        return path

    def args(self, *extra, cmd="run", validator=True, model=MODEL, effort="xhigh"):
        a = [cmd, "--tasks", str(self.d / "tasks.jsonl"), "--system-prompt", str(self.d / "rules.md"),
             "--schema", str(self.d / "schema.json"), "--model", model, "--effort", effort,
             "--out-dir", str(self.out), "--jobs", "2", "--retries", "0"]
        if validator:
            a += ["--validator", str(self.d / "check.py")]
        return a + list(extra)

    def run_cli(self, args, timeout=60):
        return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True,
                              env=self.env, timeout=timeout)

    def start_cli(self, args):
        return subprocess.Popen([sys.executable, str(SCRIPT), *args], env=self.env,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    def calls(self):
        if not self.log.exists():
            return []
        return [json.loads(l) for l in self.log.read_text(encoding="utf-8").splitlines() if l.strip()]

    def summary(self):
        return json.loads((self.out / "summary.json").read_text(encoding="utf-8"))

    def ledger(self):
        return [json.loads(l) for l in (self.out / "ledger.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]

    def attempts(self):
        return [l for l in self.ledger() if l["event"] == "attempt"]

    def grandchildren(self):
        return [int(f.read_text()) for f in self.pids.glob("*.pid")]


class HappyPath(Case):
    def test_every_task_runs_once_in_its_own_kit_with_the_pinned_flags(self):
        (self.d / "page.txt").write_text("data", encoding="utf-8")
        self.tasks(["first", "second", "third"], files={1: ["page.txt"]})
        r = self.run_cli(self.args("--tools", "Read"))
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        s = self.summary()
        self.assertEqual((s["state"], s["requested"], s["ran"], s["resumed"], s["failed"]), ("finished", 3, 3, 0, []))
        self.assertEqual(s["models_observed"], {MODEL: 3})
        calls = self.calls()
        self.assertEqual(sorted(c["prompt"] for c in calls), ["first", "second", "third"])   # prompt on stdin
        for c in calls:
            argv = c["argv"]
            for flag in ("--restricted", "--strict-mcp-config", "--no-session-persistence", "--disable-slash-commands"):
                self.assertIn(flag, argv)
            self.assertEqual(argv[argv.index("--model") + 1], MODEL)
            self.assertEqual(argv[argv.index("--effort") + 1], "xhigh")
            self.assertEqual(argv[argv.index("--tools") + 1], "Read")
            self.assertEqual(argv[argv.index("--output-format") + 1], "json")
            self.assertEqual(json.loads(argv[argv.index("--json-schema") + 1]), SCHEMA)
            self.assertNotIn("--system-prompt", argv)
            self.assertEqual(c["system"], "RULES: answer ok.\r\nSecond line.\r\n")   # byte for byte, CRLF kept
        by_prompt = {c["prompt"]: c["files"] for c in calls}
        self.assertEqual(by_prompt["second"], ["page.txt"])                        # only its own file
        self.assertEqual(by_prompt["first"], [])
        out = json.loads((self.out / "outputs" / "t1.json").read_text(encoding="utf-8"))
        self.assertEqual(out["output"]["files"], ["page.txt"])
        self.assertEqual(len(self.attempts()), 3)
        self.assertEqual(self.attempts()[0]["output_tokens"], 40)

    def test_plan_launches_nothing_and_bounds_overshoot_by_the_tasks_that_run(self):
        self.tasks(["a"])
        r = self.run_cli(self.args("--max-usd", "5", "--jobs", "4", cmd="plan"))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.calls(), [])
        self.assertIn("1 to run", r.stdout)
        self.assertIn("worst-case overshoot about 1 x $2.5", r.stdout)     # min(jobs, tasks), not jobs
        self.assertIn("soft cap", r.stdout)

    def test_the_banner_counts_only_the_tasks_that_will_run(self):
        self.tasks(["a", "b"])
        self.run_cli(self.args())
        r = self.run_cli(self.args())
        self.assertIn("2 resume, 0 to run", r.stdout)
        self.assertIn("0 task(s) x", r.stdout)

    def test_status_reports_the_last_run_and_all_ledger_attempts(self):
        self.tasks(["a"])
        self.run_cli(self.args())
        r = self.run_cli(["status", "--out-dir", str(self.out)])
        self.assertEqual(r.returncode, 0)
        self.assertIn("state finished", r.stdout)
        self.assertIn("all runs: 1 attempt(s), 1 valid", r.stdout)

    def test_unicode_line_separators_inside_a_prompt_are_one_line(self):
        self.tasks(["first second\u0085third"])
        r = self.run_cli(self.args())
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.calls()[0]["prompt"], "first second\u0085third")


class Routing(Case):
    def test_aliases_and_bad_efforts_are_refused_before_any_launch(self):
        self.tasks(["a"])
        for model, effort in (("opus", "xhigh"), ("sonnet", "high"), ("gpt-5", "high"), (MODEL, "extreme")):
            with self.subTest(model=model, effort=effort):
                r = self.run_cli(self.args(model=model, effort=effort))
                self.assertEqual(r.returncode, 2)
        self.assertEqual(self.calls(), [])

    def test_a_different_answering_model_invalidates_the_run(self):
        self.tasks(["@@mode:wrong_model@@"])
        r = self.run_cli(self.args())
        self.assertEqual(r.returncode, 1)
        s = self.summary()
        self.assertIn("model mismatch", s["failed"][0]["problems"][0])
        self.assertEqual(s["models_observed"], {"claude-haiku-4-5-20251001": 1})
        self.assertIn("claude-haiku-4-5-20251001", r.stdout)
        self.assertFalse((self.out / "outputs" / "t0.json").exists())

    def test_a_missing_claude_is_a_usage_error_and_nothing_is_charged(self):
        self.tasks(["a", "b"])
        r = self.run_cli(self.args("--claude-bin", str(self.d / "no-such-claude")))
        self.assertEqual(r.returncode, 2)
        self.assertIn("cannot find the claude executable", r.stderr)
        self.assertFalse((self.out / "ledger.jsonl").exists())

    def test_the_flag_wins_over_the_environment_variable(self):
        self.tasks(["a"])
        r = self.run_cli(self.args("--claude-bin", "/bin/definitely-not-claude"))
        self.assertEqual(r.returncode, 2)                  # the env var points at a working fake


class Validation(Case):
    def test_each_failure_kind_is_a_failed_task_never_a_saved_output(self):
        modes = ["invalid_output", "no_structured", "error", "bad_json", "error_exit0"]
        self.tasks([f"@@mode:{m}@@" for m in modes])
        r = self.run_cli(self.args())
        self.assertEqual(r.returncode, 1)
        self.assertEqual(len(self.summary()["failed"]), 5)
        self.assertFalse(any((self.out / "outputs").glob("*.json")) if (self.out / "outputs").exists() else False)

    def test_an_error_names_its_subtype_and_message(self):
        self.tasks(["@@mode:error@@"])
        self.run_cli(self.args())
        p = self.summary()["failed"][0]["problems"][0]
        self.assertIn("error_during_execution", p)
        self.assertIn("overloaded", p)

    def test_stderr_reaches_the_problem_text(self):
        self.tasks(["@@mode:stderr_fail@@"])
        self.run_cli(self.args())
        self.assertIn("auth failed: token expired", self.summary()["failed"][0]["problems"][0])

    def test_retry_turns_a_bad_first_answer_into_a_saved_one(self):
        self.tasks(["@@seq:invalid_output,ok@@"])
        r = self.run_cli(self.args("--retries", "1"))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual([a["valid"] for a in self.attempts()], [False, True])

    def test_a_crashing_validator_is_a_problem_not_a_crash(self):
        (self.d / "check.py").write_text("def validate(output, task):\n    raise KeyError('x')\n", encoding="utf-8")
        self.tasks(["a"])
        r = self.run_cli(self.args())
        self.assertEqual(r.returncode, 1)
        self.assertIn("validator raised KeyError", self.summary()["failed"][0]["problems"][0])

    def test_the_validator_sees_the_task_and_its_file_names(self):
        (self.d / "page.txt").write_text("x", encoding="utf-8")
        (self.d / "check.py").write_text(
            "def validate(output, task):\n    return [] if task['files'] == ['page.txt'] and task['id'] == 't0' else ['bad task view']\n",
            encoding="utf-8")
        self.tasks(["a"], files={0: ["page.txt"]})
        self.assertEqual(self.run_cli(self.args()).returncode, 0)


class Money(Case):
    def test_unknown_cost_is_charged_at_the_per_run_cap(self):
        self.tasks(["@@mode:no_cost@@"])
        self.run_cli(self.args("--per-run-usd", "1.5"))
        s = self.summary()
        self.assertEqual((s["unknown_cost_runs"], s["charged_usd"], s["observed_cost_usd"]), (1, 1.5, 0.0))

    def test_a_budget_stop_is_reported_plainly_and_not_retried(self):
        self.tasks(["@@mode:budget@@"])
        self.run_cli(self.args("--retries", "2"))
        self.assertEqual(len(self.attempts()), 1)
        self.assertIn("per-run budget reached", self.summary()["failed"][0]["problems"][0])
        self.assertEqual((self.attempts()[0]["output_tokens"], self.attempts()[0]["cache_write"]), (52, 1131))

    def test_max_usd_stops_new_launches_and_reports_what_did_not_run(self):
        self.tasks([f"task {i}" for i in range(6)])
        self.env["FAKE_COST"] = "0.6"
        r = self.run_cli(self.args("--max-usd", "1.0", "--jobs", "1"))
        self.assertEqual(r.returncode, 2)
        s = self.summary()
        self.assertIn("--max-usd", s["stopped"])
        self.assertEqual(s["state"], "stopped")
        self.assertEqual(s["launches"], 2)              # 0.6 < 1.0 launches a second run; 1.2 >= 1.0 stops
        self.assertEqual(len(s["not_run"]), 4)

    def test_max_usd_lets_runs_already_in_flight_finish(self):
        self.tasks(["fast", "@@mode:slow@@", "third"])
        self.env.update(FAKE_COST="0.6", FAKE_SLOW_S="3")
        r = self.run_cli(self.args("--max-usd", "0.5", "--jobs", "2"))
        self.assertEqual(r.returncode, 2)
        self.assertTrue((self.out / "outputs" / "t1.json").exists(), "the in-flight run was killed")
        self.assertEqual([a["valid"] for a in self.attempts()], [True, True])
        self.assertEqual([n["id"] for n in self.summary()["not_run"]], ["t2"])


class Resume(Case):
    def test_finished_tasks_are_skipped_and_changed_ones_rerun(self):
        self.tasks(["a", "b"])
        self.assertEqual(self.run_cli(self.args()).returncode, 0)
        self.assertEqual(len(self.calls()), 2)
        self.assertEqual(self.run_cli(self.args()).returncode, 0)
        self.assertEqual(len(self.calls()), 2)
        self.assertEqual(self.summary()["resumed"], 2)
        self.tasks(["a", "b changed"])
        self.run_cli(self.args())
        self.assertEqual(len(self.calls()), 3)
        (self.d / "rules.md").write_bytes(b"NEW RULES\n")
        self.run_cli(self.args())
        self.assertEqual(len(self.calls()), 5)

    def test_a_changed_file_reruns_its_task(self):
        (self.d / "page.txt").write_text("v1", encoding="utf-8")
        self.tasks(["a"], files={0: ["page.txt"]})
        self.run_cli(self.args())
        (self.d / "page.txt").write_text("v2", encoding="utf-8")
        self.run_cli(self.args())
        self.assertEqual(len(self.calls()), 2)

    def test_a_tightened_validator_reruns_its_tasks(self):
        self.tasks(["a"])
        self.run_cli(self.args())
        (self.d / "check.py").write_text(VALIDATOR + "# tightened\n", encoding="utf-8")
        self.run_cli(self.args())
        self.assertEqual(len(self.calls()), 2)

    def test_a_saved_output_that_no_longer_validates_is_rerun(self):
        self.tasks(["a"])
        self.run_cli(self.args())
        state = self.out / "outputs" / "t0.json"
        saved = json.loads(state.read_text(encoding="utf-8"))
        saved["output"] = {"answer": "tampered"}
        state.write_text(json.dumps(saved), encoding="utf-8")
        self.run_cli(self.args())
        self.assertEqual(len(self.calls()), 2)
        self.assertTrue(any(l["event"] == "resume_rejected" for l in self.ledger()))

    def test_a_corrupt_saved_output_is_rerun_not_a_crash(self):
        self.tasks(["a", "b"])
        self.run_cli(self.args())
        (self.out / "outputs" / "t0.json").write_text("[]", encoding="utf-8")
        (self.out / "outputs" / "t1.json").write_text("null", encoding="utf-8")
        self.assertEqual(self.run_cli(self.args(cmd="plan")).returncode, 0)
        r = self.run_cli(self.args())
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(len(self.calls()), 4)


class Inputs(Case):
    def test_bad_task_files_are_usage_errors(self):
        cases = {
            "dup": '{"id": "x", "prompt": "a"}\n{"id": "x", "prompt": "b"}\n',
            "case": '{"id": "Abc", "prompt": "a"}\n{"id": "abc", "prompt": "b"}\n',
            "badid": '{"id": "a/b", "prompt": "a"}\n',
            "noprompt": '{"id": "a", "prompt": ""}\n',
            "nofile": '{"id": "a", "prompt": "a", "files": ["missing.txt"]}\n',
            "notjson": "{oops\n",
            "empty": "\n",
        }
        for name, text in cases.items():
            with self.subTest(case=name):
                (self.d / "tasks.jsonl").write_text(text, encoding="utf-8")
                r = self.run_cli(self.args())
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                self.assertNotIn("Traceback", r.stderr)
        self.assertEqual(self.calls(), [])

    def test_unreadable_inputs_are_usage_errors_not_tracebacks(self):
        self.tasks(["a"])
        (self.d / "latin.md").write_bytes("kural: ş".encode("cp1254"))   # 0xFE, not valid UTF-8
        (self.d / "sdir").mkdir()
        (self.d / "afile").write_text("x", encoding="utf-8")
        cases = {"non-utf8 system prompt": ["--system-prompt", str(self.d / "latin.md")],
                 "schema is a directory": ["--schema", str(self.d / "sdir")],
                 "out-dir is a file": ["--out-dir", str(self.d / "afile")],
                 "non-finite max-usd": ["--max-usd", "nan"],
                 "infinite per-run": ["--per-run-usd", "inf"]}
        for name, extra in cases.items():
            with self.subTest(case=name):
                r = self.run_cli(self.args(*extra))
                self.assertEqual(r.returncode, 2, r.stderr)
                self.assertNotIn("Traceback", r.stderr)
                self.assertFalse((self.out / "summary.json").exists(), "refused input must not start a run")

    def test_a_tasks_file_with_a_bom_and_crlf_is_read(self):
        (self.d / "tasks.jsonl").write_bytes('﻿{"id": "a", "prompt": "x"}\r\n'.encode("utf-8"))
        self.assertEqual(self.run_cli(self.args()).returncode, 0)

    def test_two_files_with_the_same_name_are_refused(self):
        (self.d / "x").mkdir()
        (self.d / "page.txt").write_text("1", encoding="utf-8")
        (self.d / "x" / "page.txt").write_text("2", encoding="utf-8")
        self.tasks(["a"], files={0: ["page.txt", "x/page.txt"]})
        self.assertEqual(self.run_cli(self.args()).returncode, 2)

    def test_a_second_run_on_the_same_out_dir_is_refused_while_the_first_holds_the_lock(self):
        self.tasks(["@@mode:slow@@"])
        self.env["FAKE_SLOW_S"] = "3"
        first = self.start_cli(self.args())
        try:
            self.assertTrue(wait_until(lambda: self.calls(), 20))
            r = self.run_cli(self.args())
            self.assertEqual(r.returncode, 2)
            self.assertIn("another cleanrun", r.stderr)
        finally:
            first.wait(timeout=30)

    def test_status_survives_a_torn_ledger_and_a_missing_directory(self):
        self.tasks(["a"])
        self.run_cli(self.args())
        with open(self.out / "ledger.jsonl", "a", encoding="utf-8") as f:
            f.write('{"id": "t0", "event": "att')         # torn by a kill mid-append
        r = self.run_cli(["status", "--out-dir", str(self.out)])
        self.assertNotIn("Traceback", r.stderr)
        self.assertIn("1 unreadable line(s)", r.stdout)
        self.assertEqual(self.run_cli(["status", "--out-dir", str(self.d / "nowhere")]).returncode, 2)


class Processes(Case):
    def test_a_timeout_kills_the_whole_process_group(self):
        self.tasks(["@@mode:hang@@"])
        r = self.run_cli(self.args("--timeout", "2"), timeout=60)
        self.assertEqual(r.returncode, 1)
        self.assertIn("timeout", self.summary()["failed"][0]["problems"][0])
        kids = self.grandchildren()
        self.assertEqual(len(kids), 1)
        self.assertTrue(wait_until(lambda: not any(alive(p) for p in kids), 10), "grandchild survived the timeout")

    def test_an_orphan_holding_the_output_open_cannot_stall_the_run(self):
        self.tasks(["@@mode:orphan@@"])
        t0 = time.time()
        r = self.run_cli(self.args("--timeout", "30"), timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertLess(time.time() - t0, 20)
        self.assertTrue((self.out / "outputs" / "t0.json").exists())

    def stop_with(self, sig):
        self.tasks(["@@mode:hang@@"] * 5)
        proc = self.start_cli(self.args("--jobs", "2"))
        try:
            self.assertTrue(wait_until(lambda: len(self.grandchildren()) == 2, 20), "two runs never started")
            proc.send_signal(sig)
            proc.wait(timeout=30)
        finally:
            if proc.poll() is None:
                proc.kill()
        self.assertEqual(proc.returncode, 130)
        time.sleep(1)
        self.assertEqual(len(self.calls()), 2)           # nothing new after the signal
        kids = self.grandchildren()
        self.assertTrue(wait_until(lambda: not any(alive(p) for p in kids), 10), "a grandchild survived")
        s = self.summary()
        self.assertEqual((s["state"], s["stopped"]), ("interrupted", "interrupted"))
        self.assertEqual(len(s["not_run"]), 5)

    def test_ctrl_c(self):
        self.stop_with(signal.SIGINT)

    def test_sigterm(self):
        self.stop_with(signal.SIGTERM)

    def test_sighup_from_a_closed_terminal(self):
        self.stop_with(signal.SIGHUP)

    def test_repeated_ctrl_c_while_the_summary_is_written_cannot_deadlock(self):
        # the summary is written under the run lock; a handler that took that lock would hang forever
        self.env["CLEANRUN_TEST_HOLD_LOCK_S"] = "1"
        self.tasks(["@@mode:hang@@"] * 3)
        proc = self.start_cli(self.args("--jobs", "2"))
        try:
            self.assertTrue(wait_until(lambda: len(self.grandchildren()) == 2, 30), "runs never started")
            end = time.time() + 4
            while time.time() < end and proc.poll() is None:
                proc.send_signal(signal.SIGINT)
                time.sleep(0.05)
            proc.wait(timeout=20)
        finally:
            if proc.poll() is None:
                proc.kill()
        self.assertEqual(proc.returncode, 130)
        self.assertEqual(self.summary()["state"], "interrupted")

    def test_a_hanging_validator_cannot_block_an_interrupt(self):
        (self.d / "check.py").write_text("import time\ndef validate(output, task):\n    time.sleep(300)\n", encoding="utf-8")
        self.tasks(["a"])
        proc = self.start_cli(self.args())
        try:
            self.assertTrue(wait_until(lambda: self.calls(), 20))
            time.sleep(1)
            proc.send_signal(signal.SIGINT)
            proc.wait(timeout=30)                        # the grace period (4 s here) forces the exit
        finally:
            if proc.poll() is None:
                proc.kill()
        self.assertEqual(proc.returncode, 130)
        self.assertEqual(self.summary()["state"], "interrupted")

    def test_a_second_ctrl_c_leaves_at_once_even_with_a_long_grace(self):
        (self.d / "check.py").write_text("import time\ndef validate(output, task):\n    time.sleep(300)\n", encoding="utf-8")
        self.env["CLEANRUN_GRACE_S"] = "120"
        self.tasks(["a"])
        proc = self.start_cli(self.args())
        try:
            self.assertTrue(wait_until(lambda: self.calls(), 20))
            time.sleep(1)
            proc.send_signal(signal.SIGINT)
            time.sleep(1)
            proc.send_signal(signal.SIGINT)
            proc.wait(timeout=15)                        # well inside the 120 s grace
        finally:
            if proc.poll() is None:
                proc.kill()
        self.assertEqual(proc.returncode, 130)
        self.assertEqual(self.summary()["state"], "interrupted")

    def test_a_crash_inside_a_task_stops_new_launches_and_still_writes_the_summary(self):
        (self.d / "check.py").write_text("import sys\ndef validate(output, task):\n    sys.exit(3)\n", encoding="utf-8")
        self.tasks(["a", "b", "c", "d"])
        r = self.run_cli(self.args("--jobs", "1"))
        self.assertEqual(r.returncode, 3, r.stderr)
        s = self.summary()
        self.assertEqual(len(s["crashed"]), 1)
        self.assertIn("internal error", s["stopped"])
        self.assertEqual(s["launches"], 1)
        self.assertEqual(len(s["not_run"]), 3)


class UsageCheck(Case):
    def gate(self, rc):
        script = self.d / f"gate{rc}.py"
        script.write_text(f"import sys\nopen({str(self.d / 'gate.log')!r}, 'a').write('x')\nsys.exit({rc})\n", encoding="utf-8")
        return f"{shlex.quote(sys.executable)} {shlex.quote(str(script))}"

    def test_room_in_the_window_is_probed_once_for_many_jobs(self):
        self.tasks(["a", "b", "c", "d"])
        self.assertEqual(self.run_cli(self.args("--usage-check", self.gate(0), "--jobs", "4")).returncode, 0)
        self.assertEqual((self.d / "gate.log").read_text(), "x")      # single-flight, then cached

    def test_a_full_window_stops_before_any_launch(self):
        self.tasks(["a", "b"])
        r = self.run_cli(self.args("--usage-check", self.gate(2)))
        self.assertEqual(r.returncode, 2)
        self.assertEqual(self.summary()["stopped"], "usage check: window full")
        self.assertEqual(self.calls(), [])

    def test_an_unreadable_window_is_retried_then_stops_as_unreadable(self):
        self.tasks(["a"])
        r = self.run_cli(self.args("--usage-check", self.gate(1)))
        self.assertEqual(r.returncode, 2)
        self.assertEqual(self.summary()["stopped"], "usage check: unreadable")
        self.assertEqual((self.d / "gate.log").read_text(), "xxx")
        self.assertEqual(self.calls(), [])

    def test_without_the_flag_no_check_runs(self):
        self.tasks(["a"])
        self.assertEqual(self.run_cli(self.args()).returncode, 0)
        self.assertFalse((self.d / "gate.log").exists())


if __name__ == "__main__":
    unittest.main()
