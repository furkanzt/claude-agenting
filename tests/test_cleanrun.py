"""Tests for scripts/cleanrun.py, run end to end against tests/fixtures/fake_claude_cleanrun.py.

Every test that can hang under a regression (process groups, timeouts, signals) waits
through its own deadline, so a regression fails the test instead of hanging the suite.
"""

import hashlib
import importlib.util
import json
import os
import shlex
import signal
import subprocess
import sys
import tempfile
import time
import tracemalloc
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
                        CLEANRUN_GATE_BACKOFF_S="0.05", CLEANRUN_GRACE_S="4",
                        CLEANRUN_USAGE_CACHE=str(self.d / "usage_gate.json"))

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


class AllowedTools(Case):
    """--allowed-tools: permission for tools that claude -p could not ask about."""

    def saved_key(self, out):
        return json.loads((out / "outputs" / "t0.json").read_text(encoding="utf-8"))["key"]

    def test_the_list_is_passed_to_claude_as_its_allowed_tools_flag(self):
        self.tasks(["a"])
        cases = [("WebSearch,WebFetch", "WebSearch,WebFetch", "WebSearch,WebFetch"),
                 ("Bash,Read", "Bash(git status:*), Read", "Bash(git status:*),Read"),   # a pattern keeps its parentheses
                 ("Bash", "Bash(git log --format=%h,%s:*)", "Bash(git log --format=%h,%s:*)"),   # and a comma or space inside them
                 ("Read Glob", "Glob", "Glob")]     # --tools is split the way claude splits it too: a space separates
        for n, (tools, given, sent) in enumerate(cases):
            with self.subTest(allowed=given):
                r = self.run_cli(self.args("--tools", tools, "--allowed-tools", given, "--out-dir", str(self.d / f"out{n}")))
                self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
                argv = self.calls()[-1]["argv"]
                self.assertEqual(argv[argv.index("--allowed-tools") + 1], sent)
                self.assertEqual(argv[argv.index("--tools") + 1], tools)

    def test_without_the_option_claude_gets_no_allowed_tools_flag(self):
        self.tasks(["a", "b"])
        self.assertEqual(self.run_cli(self.args("--tools", "Read")).returncode, 0)
        for c in self.calls():
            for spelling in ("--allowed-tools", "--allowedTools"):
                self.assertNotIn(spelling, c["argv"])
            self.assertEqual(c["argv"][c["argv"].index("--tools") + 1], "Read")

    def test_a_name_that_tools_does_not_list_is_refused_by_run_and_by_plan(self):
        self.tasks(["a"])
        cases = {"a name tools lacks": ("Read", "WebFetch"),
                 "no tools at all": ("", "Read"),
                 "a pattern whose name tools lacks": ("Read", "Bash(git status:*)"),
                 "one name of two missing": ("WebSearch", "WebSearch,WebFetch"),
                 "an unclosed pattern": ("Bash", "Bash(git status"),
                 "an entry with no name, even in --tools": ("(git status)", "(git status)"),
                 # claude cuts a list with one inside/outside flag, not a depth count: these would be
                 # several grants there (a whole-tool Bash, an unchecked WebFetch), so they are refused
                 "a nested pattern that hides a whole-tool grant": ("Bash", "Bash(git (x),Bash,(y))"),
                 "a nested pattern that hides a name tools lacks": ("Bash", "Bash((a),WebFetch,(b))"),
                 "a shell substitution inside a pattern": ("Bash", "Bash(echo $(date) *)"),
                 "text glued after the closing parenthesis": ("Bash,Read", "Bash(a)Read"),
                 "a pattern with a parenthesis inside it": ("Bash", "Bash(a (b)"),
                 "a tab between names": ("Read,Glob", "Read\tGlob"),
                 "a tab that --tools has too": ("Read\tGlob", "Read\tGlob"),
                 "a closing parenthesis with no opening one": ("Read)", "Read)"),   # --tools has it too, so only this check refuses it
                 # claude reads these as withholding WebFetch, so the grant would do nothing
                 "an exclusion in --tools": ("Read,WebFetch,!WebFetch", "WebFetch"),
                 "a detached exclusion in --tools": ("Read,! WebFetch", "Read,WebFetch"),
                 "the default tool set": ("default", "WebFetch")}
        for name, (tools, allowed) in cases.items():
            for cmd in ("run", "plan"):
                with self.subTest(case=name, cmd=cmd):
                    r = self.run_cli(self.args("--tools", tools, "--allowed-tools", allowed, cmd=cmd))
                    self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                    self.assertIn("--allowed-tools", r.stderr)
                    self.assertNotIn("Traceback", r.stderr)
                    self.assertFalse(self.out.exists(), "a refused input must write nothing")
        self.assertEqual(self.calls(), [])

    def test_the_list_enters_the_run_key_only_when_it_is_given(self):
        # the inputs of test_a_flat_read_only_tasks_run_key_is_pinned, so "unchanged" is checked against
        # the key release 3.3.4 wrote and not against whatever the code under test computes today
        (self.d / "page.txt").write_text("data", encoding="utf-8")
        self.tasks(["first"], files={0: ["page.txt"]})
        keys = {}
        for label, extra in (("flat", []), ("allowed", ["--allowed-tools", "Read"])):
            out = self.d / f"out_{label}"
            r = self.run_cli(self.args("--tools", "Read", "--out-dir", str(out), *extra))
            self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
            keys[label] = self.saved_key(out)
        self.assertEqual(keys["flat"], "276e916802a89618a91fb043338e79ee870da432a7fb3c737b963cb2b8ef8e71")
        self.assertNotEqual(keys["allowed"], keys["flat"])

    def test_changing_the_list_reruns_a_finished_task(self):
        self.tasks(["a"])
        def run(*allowed):
            self.assertEqual(self.run_cli(self.args("--tools", "Read,Glob", *allowed)).returncode, 0)
            return len(self.calls())
        self.assertEqual(run("--allowed-tools", "Read"), 1)
        self.assertEqual(run("--allowed-tools", "Read"), 1)             # unchanged: resumed
        self.assertEqual(run("--allowed-tools", "Read,Glob"), 2)        # a wider list reruns
        self.assertEqual(run("--allowed-tools", "Glob,Read,Read"), 2)   # the same grant, reordered and repeated: resumed
        self.assertEqual(run(), 3)                                      # dropping it reruns


HAIKU = "claude-haiku-4-5-20251001"
SONNET = "claude-sonnet-4-5-20250929"
PIN = "276e916802a89618a91fb043338e79ee870da432a7fb3c737b963cb2b8ef8e71"   # test_a_flat_read_only_tasks_run_key_is_pinned


class AlsoModels(Case):
    """--also-models: helper models a tool calls on its own (WebFetch's summariser) beside the routed one."""

    def saved_key(self, out):
        return json.loads((out / "outputs" / "t0.json").read_text(encoding="utf-8"))["key"]

    def test_without_also_models_a_helper_beside_the_routed_model_is_still_a_mismatch(self):
        self.tasks(["@@mode:helper_model@@"])
        r = self.run_cli(self.args())
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        s = self.summary()
        # the literal message the exact check has always written
        self.assertEqual(s["failed"][0]["problems"], [f"model mismatch: answered by {[HAIKU, MODEL]}, routed to {MODEL}"])
        self.assertFalse((self.out / "outputs" / "t0.json").exists())

    def test_a_helper_on_the_list_is_accepted_and_the_summary_lists_both_models(self):
        self.tasks(["@@mode:helper_model@@"])
        r = self.run_cli(self.args("--also-models", HAIKU))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.summary()["models_observed"], {MODEL: 1, HAIKU: 1})
        self.assertIn(HAIKU, r.stdout)
        self.assertEqual(self.attempts()[0]["model_observed"], [HAIKU, MODEL])
        self.assertTrue((self.out / "outputs" / "t0.json").exists())
        self.assertNotIn("--also-models", self.calls()[0]["argv"])     # a check on the answer, not a claude flag

    def test_a_model_not_on_the_list_is_rejected_and_named(self):
        self.tasks(["@@mode:helper_model@@"])
        self.env["FAKE_HELPER_MODEL"] = SONNET
        r = self.run_cli(self.args("--also-models", HAIKU))
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        (problem,) = self.summary()["failed"][0]["problems"]
        self.assertTrue(problem.startswith(f"model mismatch: answered by {[MODEL, SONNET]}, routed to {MODEL}"), problem)
        self.assertIn(f"not on --also-models: {SONNET}", problem)
        self.assertFalse((self.out / "outputs" / "t0.json").exists())

    def test_the_routed_model_missing_is_rejected_even_when_a_listed_helper_answered(self):
        self.tasks(["@@mode:helper_only@@"])
        r = self.run_cli(self.args("--also-models", HAIKU))
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        (problem,) = self.summary()["failed"][0]["problems"]
        self.assertTrue(problem.startswith(f"model mismatch: answered by {[HAIKU]}, routed to {MODEL}"), problem)
        self.assertIn(f"{MODEL} is not among them", problem)
        self.assertEqual(self.summary()["models_observed"], {HAIKU: 1})
        self.assertFalse((self.out / "outputs" / "t0.json").exists())

    def test_an_alias_in_also_models_is_refused_by_run_and_by_plan(self):
        self.tasks(["a"])
        for given in ("haiku", "Sonnet", f"{HAIKU},opus", "gpt-5", f"{HAIKU}, default"):
            for cmd in ("run", "plan"):
                with self.subTest(given=given, cmd=cmd):
                    r = self.run_cli(self.args("--also-models", given, cmd=cmd))
                    self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                    self.assertIn("--also-models must be a full model id", r.stderr)
                    self.assertNotIn("Traceback", r.stderr)
                    self.assertFalse(self.out.exists(), "a refused input must write nothing")
        self.assertEqual(self.calls(), [])

    def test_a_space_separated_list_or_the_routed_model_in_another_case_is_refused_by_run_and_by_plan(self):
        self.tasks(["@@mode:helper_model@@"])
        for given, says in ((f"{HAIKU} {SONNET}", "a model id has no space"),
                            (f"{SONNET}, {HAIKU} {SONNET}", "a model id has no space"),
                            ("claude-OPUS-5-5", "names --model 'claude-opus-5-5' in another case"),
                            (f"{HAIKU},claude-Opus-5-5", "names --model 'claude-opus-5-5' in another case")):
            for cmd in ("run", "plan"):
                with self.subTest(given=given, cmd=cmd):
                    r = self.run_cli(self.args("--also-models", given, cmd=cmd))
                    self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                    self.assertIn(says, r.stderr)
                    self.assertNotIn("Traceback", r.stderr)
                    self.assertFalse(self.out.exists(), "a refused input must write nothing")
        self.assertEqual(self.calls(), [])

    def test_an_id_a_run_could_never_report_is_refused_by_run_and_by_plan(self):
        # each would pass the full-id check, then be paid for and rejected (or churn the key) on every run
        self.tasks(["@@mode:helper_model@@"])
        for name, given in (("a ';' list", f"{HAIKU};{SONNET}"),
                            ("a partial id", "claude-haiku"),
                            ("a bare prefix", "claude-"),
                            ("another case", "claude-Haiku-4-5-20251001"),
                            ("a fullwidth look-alike", "claude-\uff48aiku-4-5-20251001"),
                            ("a zero-width character", HAIKU + "\u200b"),
                            ("a soft hyphen", "claude-haiku-4-5\u00ad-20251001")):
            for cmd in ("run", "plan"):
                with self.subTest(case=name, cmd=cmd):
                    r = self.run_cli(self.args("--also-models", given, cmd=cmd))
                    self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                    self.assertIn("written as claude reports them", r.stderr)
                    self.assertNotIn("Traceback", r.stderr)
                    self.assertFalse(self.out.exists(), "a refused input must write nothing")
        self.assertEqual(self.calls(), [])

    def test_the_weaker_check_is_recorded_where_the_result_is_read(self):
        self.tasks(["@@mode:helper_model@@"])
        plan = self.run_cli(self.args("--also-models", HAIKU, cmd="plan"))
        self.assertIn(f"also models {HAIKU} (weaker model check)", plan.stdout)
        r = self.run_cli(self.args("--also-models", HAIKU))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("(weaker model check)", r.stdout.splitlines()[0])
        self.assertEqual(self.summary()["also_models"], [HAIKU])
        self.assertEqual(json.loads((self.out / "outputs" / "t0.json").read_text(encoding="utf-8"))["also_models"], [HAIKU])

    def test_a_default_run_mentions_neither_the_weaker_check_nor_a_grant(self):
        self.tasks(["a"])
        plan = self.run_cli(self.args(cmd="plan"))
        self.assertNotIn("also", plan.stdout)
        self.assertNotIn("allowed", plan.stdout)
        r = self.run_cli(self.args())
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("also_models", self.summary())
        self.assertNotIn("also_models", json.loads((self.out / "outputs" / "t0.json").read_text(encoding="utf-8")))
        grant = self.run_cli(self.args("--tools", "Read", "--allowed-tools", "Read", "--out-dir", str(self.d / "g"), cmd="plan"))
        self.assertIn("allowed 'Read'", grant.stdout)       # the plan shows the grant before anything is paid for

    def test_also_models_enter_the_run_key_only_when_they_add_a_model(self):
        # the pinned task's inputs, so "unchanged" is checked against the key release 3.3.4 wrote
        (self.d / "page.txt").write_text("data", encoding="utf-8")
        self.tasks(["first"], files={0: ["page.txt"]})
        keys = {}
        for label, extra in (("flat", []), ("helper", ["--also-models", HAIKU]),
                             ("routed model only", ["--also-models", MODEL])):
            out = self.d / f"out_{label.replace(' ', '_')}"
            r = self.run_cli(self.args("--tools", "Read", "--out-dir", str(out), *extra))
            self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
            keys[label] = self.saved_key(out)
        self.assertEqual(keys["flat"], PIN)
        self.assertEqual(keys["routed model only"], PIN)       # naming --model itself is the default check
        self.assertNotEqual(keys["helper"], PIN)

    def test_a_changed_also_models_set_reruns_a_finished_task_and_a_reordered_one_resumes(self):
        self.tasks(["@@mode:helper_model@@"])
        def run(given):
            self.assertEqual(self.run_cli(self.args("--also-models", given)).returncode, 0)
            return len(self.calls())
        self.assertEqual(run(HAIKU), 1)
        self.assertEqual(run(HAIKU), 1)                             # unchanged: resumed
        self.assertEqual(run(f"{HAIKU}, {SONNET}"), 2)              # a wider set reruns
        self.assertEqual(run(f"{SONNET},{HAIKU},{HAIKU}"), 2)       # the same set, reordered and repeated: resumed
        self.assertEqual(run(f"{SONNET},{HAIKU},{MODEL}"), 2)       # --model itself in the list: resumed


class InputHashing(Case):
    """How the run key reads a task's files: in chunks, and fresh every time."""

    @classmethod
    def module(cls):
        spec = importlib.util.spec_from_file_location("cleanrun_hashing_under_test", SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_the_digest_equals_an_independent_sha256(self):
        cleanrun = self.module()
        chunk = cleanrun.HASH_CHUNK
        for size in (0, 1, chunk - 1, chunk, chunk + 1, 2 * chunk + 12345):
            with self.subTest(size=size):
                data = bytes(range(256)) * (size // 256) + bytes(size % 256)
                p = self.d / f"f{size}.bin"
                p.write_bytes(data)
                self.assertEqual(cleanrun.file_sha(p), hashlib.sha256(data).hexdigest())

    def test_a_large_file_is_hashed_in_chunks_not_read_whole(self):
        cleanrun = self.module()
        size = 16 * cleanrun.HASH_CHUNK
        p = self.d / "big.bin"
        p.write_bytes(b"x" * size)
        tracemalloc.start()
        try:
            digest = cleanrun.file_sha(p)
            peak = tracemalloc.get_traced_memory()[1]
        finally:
            tracemalloc.stop()
        self.assertEqual(digest, hashlib.sha256(b"x" * size).hexdigest())
        self.assertLess(peak, 4 * cleanrun.HASH_CHUNK)      # read whole it would be 16 chunks

    def test_a_file_shared_by_several_tasks_resumes_and_reruns_them_all_when_it_changes(self):
        (self.d / "shared.pdf").write_text("v1", encoding="utf-8")
        self.tasks(["a", "b", "c"], files={i: ["shared.pdf"] for i in range(3)})
        self.assertEqual(self.run_cli(self.args()).returncode, 0)
        self.assertEqual(self.run_cli(self.args()).returncode, 0)
        self.assertEqual(len(self.calls()), 3)                     # unchanged: all three resumed
        (self.d / "shared.pdf").write_text("v2", encoding="utf-8")
        self.assertEqual(self.run_cli(self.args()).returncode, 0)
        self.assertEqual(len(self.calls()), 6)                     # changed: all three rerun

    def test_a_rewrite_with_the_mtime_put_back_during_a_run_is_seen_when_the_task_is_picked_up(self):
        # t0 holds the single worker; while it runs, t1's input is rewritten in place at the same size
        # and its mtime put back. A digest remembered from before would call the file unchanged.
        sh = self.d / "shared.txt"
        sh.write_bytes(b"v1v1")
        self.tasks(["slow one @@mode:slow@@", "reads shared"], files={1: ["shared.txt"]})
        self.env["FAKE_SLOW_S"] = "0"
        self.assertEqual(self.run_cli(self.args("--jobs", "1")).returncode, 0)
        (self.out / "outputs" / "t0.json").unlink()           # only t0 reruns, and it is the slow one
        self.env["FAKE_SLOW_S"] = "3"
        before = len(self.calls())
        proc = self.start_cli(self.args("--jobs", "1"))
        try:
            self.assertTrue(wait_until(lambda: len(self.calls()) > before, 20))
            st = os.stat(sh)
            with open(sh, "r+b") as f:
                f.write(b"v2v2")
            os.utime(sh, ns=(st.st_atime_ns, st.st_mtime_ns))
        finally:
            proc.communicate(timeout=60)
        reruns = [c for c in self.calls()[before:] if c["prompt"] == "reads shared"]
        self.assertEqual(len(reruns), 1)                       # not resumed from the v1 output
        self.assertEqual(reruns[0]["tree"]["shared.txt"], hashlib.sha256(b"v2v2").hexdigest())
        self.assertEqual(self.summary()["resumed"], 0)


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

    def test_a_flat_read_only_tasks_run_key_is_pinned(self):
        # Release 3.3.4 wrote this key for these inputs, and finished out-dirs on disk carry it. A change
        # that moves it makes every resumable task rerun at full price, so a new input may enter the key
        # only when a run uses it, and KEY_VERSION stays put.
        (self.d / "page.txt").write_text("data", encoding="utf-8")
        self.tasks(["first"], files={0: ["page.txt"]})
        r = self.run_cli(self.args("--tools", "Read"))
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        saved = json.loads((self.out / "outputs" / "t0.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["key"], "276e916802a89618a91fb043338e79ee870da432a7fb3c737b963cb2b8ef8e71")

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


def sha256(data):
    return hashlib.sha256(data.encode("utf-8") if isinstance(data, str) else data).hexdigest()


class KitPathEntries(Case):
    """files entries of the form {"path": ..., "as": "sub/dir/name"}: a directory structure inside the kit."""

    PIN = "276e916802a89618a91fb043338e79ee870da432a7fb3c737b963cb2b8ef8e71"   # test_a_flat_read_only_tasks_run_key_is_pinned

    def setUp(self):
        super().setUp()
        (self.d / "page.txt").write_text("1", encoding="utf-8")
        (self.d / "other.txt").write_text("2", encoding="utf-8")

    def saved_key(self, out, tid="t0"):
        return json.loads((out / "outputs" / f"{tid}.json").read_text(encoding="utf-8"))["key"]

    def assert_refused(self, files, *needles, validator=True):
        for cmd in ("run", "plan"):
            with self.subTest(files=files, cmd=cmd):
                self.tasks(["a"], files={0: files})
                r = self.run_cli(self.args(cmd=cmd, validator=validator))
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                self.assertNotIn("Traceback", r.stderr)
                for needle in ("t0", *needles):          # the message names the task, the entry and the defect
                    self.assertIn(needle, r.stderr)
                self.assertFalse(self.out.exists(), "a refused input must write nothing")
        self.assertEqual(self.calls(), [])

    def test_an_object_entry_lands_at_its_kit_path_and_claude_sees_it_there(self):
        (self.d / "src").mkdir()
        (self.d / "src" / "report.bin").write_bytes(b"%PDF-1.7 bytes")
        self.tasks(["a"], files={0: [{"path": "src/report.bin", "as": "sub/dir/name.pdf"}, "page.txt"]})
        r = self.run_cli(self.args())
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        (call,) = self.calls()
        self.assertEqual(call["tree"], {"sub/dir/name.pdf": sha256(b"%PDF-1.7 bytes"), "page.txt": sha256("1")})
        self.assertEqual(call["files"], ["page.txt", "sub"])

    def test_the_validator_sees_the_kit_path_of_an_object_entry(self):
        (self.d / "check.py").write_text(
            "def validate(output, task):\n"
            "    return [] if task['files'] == ['sub/name.md', 'page.txt'] else ['bad view: %r' % task['files']]\n",
            encoding="utf-8")
        self.tasks(["a"], files={0: [{"path": "other.txt", "as": "sub/name.md"}, "page.txt"]})
        r = self.run_cli(self.args())
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)

    def test_two_files_with_the_same_base_name_are_accepted_at_different_kit_paths(self):
        (self.d / "x").mkdir()
        (self.d / "x" / "page.txt").write_text("from x", encoding="utf-8")
        self.tasks(["both objects", "string and object"],
                   files={0: [{"path": "page.txt", "as": "a/page.txt"}, {"path": "x/page.txt", "as": "b/page.txt"}],
                          1: ["page.txt", {"path": "x/page.txt", "as": "x/page.txt"}]})
        r = self.run_cli(self.args())
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        trees = {c["prompt"]: c["tree"] for c in self.calls()}
        self.assertEqual(trees["both objects"], {"a/page.txt": sha256("1"), "b/page.txt": sha256("from x")})
        self.assertEqual(trees["string and object"], {"page.txt": sha256("1"), "x/page.txt": sha256("from x")})

    def test_an_invalid_kit_path_is_refused_by_run_and_by_plan(self):
        cases = {"an empty string": ("", "non-empty string"),
                 "a number": (5, "non-empty string"),
                 "null": (None, "non-empty string"),
                 "an absolute path": ("/etc/page.txt", "absolute"),
                 "a '..' segment": ("../page.txt", "'..' segment"),
                 "a '..' after a directory": ("sub/../page.txt", "'..' segment"),
                 "a '.' segment": ("./page.txt", "'.'"),
                 "a '.' inside": ("a/./page.txt", "'.'"),
                 "a lone dot": (".", "'.'"),
                 "a double slash": ("a//page.txt", "empty"),
                 "a trailing slash": ("a/", "empty"),
                 "a backslash": ("a\\page.txt", "backslash"),
                 "a NUL": ("a\x00page.txt", "NUL"),
                 "a path over 512 bytes": ("d/" * 256 + "x", "longer than 512 bytes"),
                 "a path of 383 characters but 764 bytes": ("/".join(["\u015f" * 127] * 3), "longer than 512 bytes"),
                 "a segment over 255 bytes": ("d/" + "x" * 256, "255 bytes"),
                 "a segment of 128 characters but 256 bytes": ("ş" * 128, "255 bytes"),
                 # a disk follows a newer Unicode than this Python: it folds letters Python does not know as
                 # one name, and refuses others outright, so any unassigned code point is refused up front
                 "a noncharacter": ("x\uffff", "unassigned"),
                 "an astral noncharacter": ("d/\U0010ffff", "unassigned"),
                 "a fork segment": ("x/..namedfork/rsrc", "..namedfork"),
                 "a fork segment in other case": ("..NamedFork", "..namedfork")}
        for name, (kit_path, needle) in cases.items():
            with self.subTest(case=name):
                entry = {"path": "page.txt", "as": kit_path}
                self.assert_refused([entry], needle, json.dumps(entry))

    def test_a_lone_surrogate_in_as_is_a_usage_error_not_a_traceback(self):
        # legal JSON, but no file name: it used to escape as a UnicodeEncodeError and exit 1 ("some failed")
        line = json.dumps({"id": "t0", "prompt": "a", "files": [{"path": "page.txt", "as": "\ud800"}]})
        for cmd in ("run", "plan"):
            with self.subTest(cmd=cmd):
                (self.d / "tasks.jsonl").write_text(line + "\n", encoding="utf-8")
                r = self.run_cli(self.args(cmd=cmd))
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                self.assertNotIn("Traceback", r.stderr)
                self.assertIn("lone surrogate", r.stderr)
                self.assertFalse(self.out.exists(), "a refused input must write nothing")
        self.assertEqual(self.calls(), [])

    def test_a_kit_that_cannot_be_built_fails_its_task_and_not_the_fan_out(self):
        # plan accepted the task; the copy then fails at run time (the disk's own rules, a full disk). The
        # copy is made to fail for one file here, in the process that runs cleanrun, since no input does it
        (self.d / "boom.txt").write_text("x", encoding="utf-8")
        self.tasks(["a", "b"], files={0: [{"path": "boom.txt", "as": "d/boom.txt"}]})
        wrapper = ("import runpy, shutil, sys\n"
                   "real = shutil.copy2\n"
                   "def copy2(src, dst, **kw):\n"
                   "    if str(src).endswith('boom.txt'):\n"
                   "        raise PermissionError(13, 'denied by the test')\n"
                   "    return real(src, dst, **kw)\n"
                   "shutil.copy2 = copy2\n"
                   "sys.argv = sys.argv[1:]\n"
                   "runpy.run_path(sys.argv[0], run_name='__main__')\n")
        r = subprocess.run([sys.executable, "-c", wrapper, str(SCRIPT), *self.args()], capture_output=True,
                           text=True, env=self.env, timeout=60)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)          # "some failed", not an internal error
        self.assertNotIn("STOPPED", r.stdout + r.stderr)
        failed = self.summary()["failed"]
        self.assertEqual([f["id"] for f in failed], ["t0"])
        self.assertIn("could not build the task's kit", failed[0]["problems"][0])
        self.assertEqual(len(self.calls()), 1)                           # the other task ran

    def test_a_malformed_object_entry_is_refused_by_run_and_by_plan(self):
        cases = {"no as": ({"path": "page.txt"}, 'exactly a non-empty "path"'),
                 "no path": ({"as": "x.txt"}, 'exactly a non-empty "path"'),
                 "an empty path": ({"path": "", "as": "x.txt"}, 'exactly a non-empty "path"'),
                 "a path that is not a string": ({"path": 5, "as": "x.txt"}, 'exactly a non-empty "path"'),
                 "an extra key": ({"path": "page.txt", "as": "x.txt", "mode": "ro"}, 'exactly a non-empty "path"'),
                 "a missing source file": ({"path": "missing.txt", "as": "x.txt"}, "no such file missing.txt")}
        for name, (entry, needle) in cases.items():
            with self.subTest(case=name):
                self.assert_refused([entry], needle, json.dumps(entry) if "no such file" not in needle else "missing.txt")

    def test_a_traversal_in_as_creates_nothing_outside_the_kit(self):
        tmp = self.d / "tmp"                 # the kit is made under TMPDIR, so everything around it is in self.d
        tmp.mkdir()
        self.env["TMPDIR"] = str(tmp)
        tag = self.d.name
        def snapshot():                      # every path and its bytes, the tasks file the test rewrites aside
            return sorted((str(p.relative_to(self.d)), p.is_dir() or p.read_bytes())
                          for p in self.d.rglob("*") if p.name != "tasks.jsonl")
        before = snapshot()
        attempts = [f"../escape-{tag}-1.txt", f"../../escape-{tag}-2.txt", f"../../../escape-{tag}-3.txt",
                    f"sub/../../escape-{tag}-4.txt", str(self.d / f"escape-{tag}-5.txt")]
        for kit_path in attempts:
            self.assert_refused([{"path": "page.txt", "as": kit_path}], "\"as\"", validator=False)
        self.assertEqual(snapshot(), before)
        self.assertEqual(list(tmp.iterdir()), [])
        for where in (self.d.parent, self.d.parent.parent):
            self.assertEqual(list(where.glob(f"escape-{tag}-*")), [])

    def test_kit_paths_that_are_equal_ignoring_case_are_refused(self):
        cases = {"the same kit path twice": [{"path": "page.txt", "as": "d/page.txt"}, {"path": "other.txt", "as": "d/page.txt"}],
                 "a case-only difference": [{"path": "page.txt", "as": "Docs/Page.txt"}, {"path": "other.txt", "as": "docs/page.txt"}],
                 "a string entry and an object entry": ["page.txt", {"path": "other.txt", "as": "page.txt"}],
                 "an object entry and a string entry, case apart": [{"path": "other.txt", "as": "PAGE.txt"}, "page.txt"],
                 # macOS compares names after Unicode normalisation too: a composed and a decomposed s-cedilla
                 "a normalisation-only difference": [{"path": "page.txt", "as": "ş.md"}, {"path": "other.txt", "as": "ş.md"}],
                 # U+0390 against U+03AA U+0301: equal only when the casefolded name is normalised again
                 "a case and normalisation difference": [{"path": "page.txt", "as": "\u0390"}, {"path": "other.txt", "as": "\u03aa\u0301"}]}
        for name, files in cases.items():
            with self.subTest(case=name):
                self.assert_refused(files, "same kit path", json.dumps(files[1]))

    def test_a_file_where_another_entry_needs_a_directory_is_refused(self):
        cases = {"a file, then a file under it": [{"path": "page.txt", "as": "a"}, {"path": "other.txt", "as": "a/b.txt"}],
                 "a file under it, then the file": [{"path": "other.txt", "as": "a/b.txt"}, {"path": "page.txt", "as": "a"}],
                 "a deeper directory": [{"path": "other.txt", "as": "a/b/c.txt"}, {"path": "page.txt", "as": "a/b"}],
                 "a string entry under which an object entry goes": ["page.txt", {"path": "other.txt", "as": "page.txt/in.txt"}],
                 "an object entry over which a string entry lands": [{"path": "other.txt", "as": "page.txt/in.txt"}, "page.txt"],
                 "the same, case apart": [{"path": "page.txt", "as": "A"}, {"path": "other.txt", "as": "a/b.txt"}],
                 "the same, case and normalisation apart": [{"path": "page.txt", "as": "\u0390"}, {"path": "other.txt", "as": "\u03aa\u0301/b.txt"}],
                 "a directory, then a file on it, case and normalisation apart": [{"path": "other.txt", "as": "\u03aa\u0301/b.txt"}, {"path": "page.txt", "as": "\u0390"}]}
        for name, files in cases.items():
            with self.subTest(case=name):
                self.assert_refused(files, "directory", json.dumps(files[1]))

    def test_an_object_entry_with_no_directory_keys_like_the_string_entry(self):
        # The pinned task's inputs, with page.txt reached through an object entry whose source has another
        # name: the key holds the kit path and the bytes, so it equals the key release 3.3.4 wrote
        (self.d / "src").mkdir()
        (self.d / "src" / "page-v1.txt").write_text("data", encoding="utf-8")
        (self.d / "page.txt").write_text("data", encoding="utf-8")
        for label, entry in (("string", "page.txt"), ("object", {"path": "src/page-v1.txt", "as": "page.txt"})):
            with self.subTest(entry=label):
                out = self.d / f"out_{label}"
                self.tasks(["first"], files={0: [entry]})
                r = self.run_cli(self.args("--tools", "Read", "--out-dir", str(out)))
                self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
                self.assertEqual(self.saved_key(out), self.PIN)

    def test_the_kit_path_of_an_object_entry_is_part_of_the_run_key(self):
        (self.d / "page.txt").write_text("data", encoding="utf-8")
        keys = {}
        for kit_path in ("docs/page.txt", "other/page.txt"):
            out = self.d / f"out_{kit_path.split('/')[0]}"
            self.tasks(["first"], files={0: [{"path": "page.txt", "as": kit_path}]})
            self.assertEqual(self.run_cli(self.args("--tools", "Read", "--out-dir", str(out))).returncode, 0)
            keys[kit_path] = self.saved_key(out)
        self.assertNotEqual(keys["docs/page.txt"], keys["other/page.txt"])
        self.assertNotIn(self.PIN, keys.values())
        def run(kit_path):
            self.tasks(["first"], files={0: [{"path": "page.txt", "as": kit_path}]})
            self.assertEqual(self.run_cli(self.args("--tools", "Read")).returncode, 0)
            return len(self.calls())
        before = len(self.calls())
        self.assertEqual(run("docs/page.txt"), before + 1)
        self.assertEqual(run("docs/page.txt"), before + 1)        # unchanged: resumed
        self.assertEqual(run("other/page.txt"), before + 2)       # moved in the kit: reruns

    def test_a_changed_file_under_an_object_entry_reruns_its_task(self):
        self.tasks(["a"], files={0: [{"path": "page.txt", "as": "in/page.txt"}]})
        self.assertEqual(self.run_cli(self.args()).returncode, 0)
        self.assertEqual(self.run_cli(self.args()).returncode, 0)
        self.assertEqual(len(self.calls()), 1)                     # unchanged: resumed
        (self.d / "page.txt").write_text("changed", encoding="utf-8")
        self.assertEqual(self.run_cli(self.args()).returncode, 0)
        self.assertEqual(len(self.calls()), 2)

    def test_the_copy_refuses_a_destination_outside_the_kit(self):
        # load_tasks refuses these first; this is the second line, reached only if that check were bypassed
        spec = importlib.util.spec_from_file_location("cleanrun_under_test", SCRIPT)
        cleanrun = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cleanrun)
        kit = self.d / "kit"
        kit.mkdir()
        before = sorted(str(p) for p in self.d.rglob("*"))
        for rel in ("../escape.txt", "a/../../escape.txt", str(self.d / "escape.txt"), "", "."):
            with self.subTest(rel=rel):
                with self.assertRaises(RuntimeError):
                    cleanrun.place(kit, rel)
        self.assertEqual(sorted(str(p) for p in self.d.rglob("*")), before)
        self.assertEqual(cleanrun.place(kit, "a/b/c.txt"), kit.resolve() / "a" / "b" / "c.txt")
        self.assertTrue((kit / "a" / "b").is_dir())
        with self.assertRaises(RuntimeError):      # copy2 would write inside it, under the source's name
            cleanrun.place(kit, "a/b")


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

    def test_one_reading_is_shared_by_runs_in_other_processes(self):
        self.tasks(["a"])
        gate = self.gate(0)
        self.assertEqual(self.run_cli(self.args("--usage-check", gate)).returncode, 0)
        self.assertEqual(self.run_cli(self.args("--usage-check", gate, "--out-dir", str(self.d / "out2"))).returncode, 0)
        self.assertEqual((self.d / "gate.log").read_text(), "x")      # the second process read the first one's verdict

    def test_a_shared_reading_expires(self):
        rc_file = self.d / "gate.rc"
        script = self.d / "gate_var.py"
        script.write_text(f"import sys\nopen({str(self.d / 'gate.log')!r}, 'a').write('x')\n"
                          f"sys.exit(int(open({str(rc_file)!r}).read()))\n", encoding="utf-8")
        gate = f"{shlex.quote(sys.executable)} {shlex.quote(str(script))}"
        self.tasks(["a"])
        rc_file.write_text("2", encoding="utf-8")
        self.assertEqual(self.run_cli(self.args("--usage-check", gate)).returncode, 2)       # "window full" is shared
        cache = self.d / "usage_gate.json"
        data = json.loads(cache.read_text(encoding="utf-8"))
        for entry in data.values():
            entry["ts"] -= 120                                                              # two minutes old
        cache.write_text(json.dumps(data), encoding="utf-8")
        rc_file.write_text("0", encoding="utf-8")
        r = self.run_cli(self.args("--usage-check", gate, "--out-dir", str(self.d / "out2")))
        self.assertEqual(r.returncode, 0, r.stdout)                                          # a stale reading is not reused
        self.assertEqual((self.d / "gate.log").read_text(), "xx")

    def test_an_unreadable_window_is_never_shared(self):
        self.tasks(["a"])
        gate = self.gate(1)
        self.run_cli(self.args("--usage-check", gate))
        self.run_cli(self.args("--usage-check", gate, "--out-dir", str(self.d / "out2")))
        self.assertEqual((self.d / "gate.log").read_text(), "xxxxxx")  # each run probed for itself, 3 times

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
