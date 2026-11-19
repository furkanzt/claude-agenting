"""Tests for evals/probes/agy_bench.py and evals/agy/eval_hook.py: the Antigravity eval bench.

Every test works in a temporary evals directory (AGENTING_EVALS_DIR, built by test_evalkit's
EvalTestCase) with `agy` replaced by tests/fixtures/fake_agy.py. No test makes a model call. The
fake runs the real guard hook that `agy_bench setup` installs, so the hook log a run is judged by
is written by the production hook.

The bench's contract (what these tests pin):
- config <root>/agy/bench.json; templates <root>/agy/eval-runner.md and <root>/agy/eval_hook.py;
- `setup` installs <root>/private/work/.agents/{agents/eval-runner.md, evalhook/eval_hook.py,
  hooks.json}; the agent body is harness.json's runner system prompt;
- records go to <root>/results/agy-runs.jsonl and agy-scores.jsonl, answers to
  <root>/private/agy-answers/<run_id>.json; results/runs.jsonl and scores.jsonl (the Claude
  instrument) are never written;
- exit codes: 0 plan finished, 3 stopped early by a stop line or a quota error, 2 an error.
"""

import importlib.util
import json
import os
import shlex
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import test_evalkit as te  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
EVALS = ROOT / "evals"
BENCH = EVALS / "probes" / "agy_bench.py"
FAKE_AGY = Path(__file__).resolve().parent / "fixtures" / "fake_agy.py"
HOOK_SRC = EVALS / "agy" / "eval_hook.py"
AGENT_SRC = EVALS / "agy" / "eval-runner.md"

G, C = "agy:g@medium", "agy:c@medium"


def bench_config(**over):
    cfg = {
        "agy_bin": f"{shlex.quote(sys.executable)} {shlex.quote(str(FAKE_AGY))}",
        "agent": "eval-runner",
        "print_timeout_s": 30,
        "kill_grace_s": 5,
        "settings": {"allowNonWorkspaceAccess": False},
        "tools_files": ["read_file", "run_command"],
        "tools_inline": [],
        "usage_pools": {"Gemini Models": "gemini", "Claude and GPT models": "claude",
                        "Gemini 4 Argon": "argon"},
        "stop_lines": {"claude": 70, "gemini": 40, "argon": 40},
        "stages": {"1": {"phase": "screening", "repeats": {"claude": 1, "default": 2},
                         "cells": [G, C]}},
        "cells": {G: {"model_id": "gem-test-medium", "pools": ["gemini"]},
                  C: {"model_id": "claude-test-medium", "pools": ["claude"]}},
    }
    cfg.update(over)
    return cfg


def load_hook(work):
    """Import eval_hook.py as installed under <work>/.agents/evalhook (its WORK is derived
    from its own location)."""
    path = Path(work) / ".agents" / "evalhook" / "eval_hook.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(HOOK_SRC.read_text())
    spec = importlib.util.spec_from_file_location(f"eval_hook_{id(path)}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class AgyCase(te.EvalTestCase):
    """EvalTestCase's evals root plus the agy bench files. Screening tasks there: n-1 and s-1
    (code-graded, files) and j-1 (judge-graded); s-c1 and s-c2 are confirmation tasks."""

    def setUp(self):
        super().setUp()
        self.agy_log = Path(self._tmp.name) / "agy-calls.jsonl"
        self.set_bench(bench_config())
        te.write(self.root / "agy" / "eval-runner.md", AGENT_SRC.read_text())
        te.write(self.root / "agy" / "eval_hook.py", HOOK_SRC.read_text())

    def set_bench(self, cfg):
        te.write(self.root / "agy" / "bench.json", json.dumps(cfg))

    def bench(self, *args, mode="ok", check=True, **env):
        e = dict(os.environ, AGENTING_EVALS_DIR=str(self.root), FAKE_AGY_MODE=mode,
                 FAKE_AGY_LOG=str(self.agy_log))
        e.update({k: str(v) for k, v in env.items()})
        r = subprocess.run([sys.executable, str(BENCH), *args], capture_output=True, text=True,
                           timeout=180, env=e)
        if check:
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r

    def agy_calls(self):
        if not self.agy_log.exists():
            return []
        return [json.loads(x) for x in self.agy_log.read_text().splitlines()]

    def agy_runs(self):
        return te.ev.read_jsonl(self.root / "results" / "agy-runs.jsonl")

    def agy_scores(self):
        return te.ev.read_jsonl(self.root / "results" / "agy-scores.jsonl")

    def work(self):
        return self.root / "private" / "work"


# -- the guard hook ----------------------------------------------------------

class GuardHook(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        self.work = Path(self._tmp.name) / "work"
        self.wd = self.work / "run-abc"
        (self.wd / "src").mkdir(parents=True)
        self.hook = load_hook(self.work)

    def tearDown(self):
        self._tmp.cleanup()

    def policy(self, tools):
        p = self.work / "policy" / (self.wd.name + ".json")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"tools": tools}))

    def decide(self, name, args):
        return self.hook.decide({"hookEventName": "PreToolUse", "cwd": str(self.wd),
                                 "toolCall": {"name": name, "args": args}})["decision"]

    def test_no_policy_denies_every_tool(self):
        self.assertEqual(self.decide("read_file", {"Path": str(self.wd / "a.txt")}), "deny")

    def test_tool_outside_policy_is_denied(self):
        self.policy(["read_file", "run_command"])
        self.assertEqual(self.decide("manage_task", {}), "deny")
        self.policy([])
        self.assertEqual(self.decide("read_file", {"Path": str(self.wd / "a.txt")}), "deny")

    def test_read_file_inside_cwd_allowed_outside_denied(self):
        self.policy(["read_file", "run_command"])
        self.assertEqual(self.decide("read_file", {"Path": str(self.wd / "src" / "a.txt")}), "allow")
        self.assertEqual(self.decide("read_file", {"Path": str(self.work / "truth.json")}), "deny")
        self.assertEqual(self.decide("read_file", {"Path": "~/secrets"}), "deny")
        self.assertEqual(self.decide("read_file", {"Path": str(self.wd) + "/../x"}), "deny")

    def test_read_only_commands_inside_cwd_are_allowed(self):
        self.policy(["read_file", "run_command"])
        for line in ("find . -type f", "grep -rn needle . | wc -l",
                     "ls -la src && wc -l src/a.txt", f"cat {self.wd}/src/a.txt",
                     "find src -name '*.ts' | sort | uniq -c"):
            with self.subTest(line=line):
                self.assertEqual(self.decide("run_command", {"CommandLine": line}), "allow")

    def test_unsafe_commands_are_denied(self):
        self.policy(["read_file", "run_command"])
        for line in ("cat ../truth.json", "cat /etc/passwd", "cat $HOME/x", "ls > out.txt",
                     "curl http://example.com", "find . -exec rm {} ;", "ls\ncurl x",
                     "ls |& curl x", "python3 -c 'print(1)'", "FOO=1 ls", "cat `echo x`",
                     "ls ~", "sed -i s/a/b/ src/a.txt", "grep -r x /"):
            with self.subTest(line=line):
                self.assertEqual(self.decide("run_command", {"CommandLine": line}), "deny")

    def test_main_logs_every_event_and_answers_json(self):
        self.policy(["read_file"])
        hook = self.work / ".agents" / "evalhook" / "eval_hook.py"
        payload = {"hookEventName": "SessionStart", "conversationId": "conv-1",
                   "cwd": str(self.wd), "workspacePaths": [str(self.wd)], "modelName": "m"}
        r = subprocess.run([sys.executable, str(hook)], input=json.dumps(payload),
                           capture_output=True, text=True, timeout=30)
        self.assertEqual(json.loads(r.stdout), {})
        payload.update(hookEventName="PreToolUse",
                       toolCall={"name": "read_file", "args": {"Path": "/etc/passwd"}})
        r = subprocess.run([sys.executable, str(hook)], input=json.dumps(payload),
                           capture_output=True, text=True, timeout=30)
        self.assertEqual(json.loads(r.stdout)["decision"], "deny")
        lines = [json.loads(x) for x in
                 (self.work / "hooklogs" / "conv-1.jsonl").read_text().splitlines()]
        self.assertEqual([x["event"] for x in lines], ["SessionStart", "PreToolUse"])
        self.assertEqual(lines[1]["decision"], "deny")
        self.assertEqual(lines[0]["modelName"], "m")


# -- setup, meters, plan -----------------------------------------------------

class SetupAndMeters(AgyCase):
    def test_setup_installs_agent_and_hook_above_the_run_dirs(self):
        self.bench("setup")
        agents = self.work() / ".agents"
        agent = (agents / "agents" / "eval-runner.md").read_text()
        self.assertIn("Be careful.", agent)                  # harness runner system prompt
        self.assertNotIn("{SYSTEM_PROMPT}", agent)
        self.assertIn("- read_file", agent)
        self.assertEqual((agents / "evalhook" / "eval_hook.py").read_text(), HOOK_SRC.read_text())
        hooks = json.loads((agents / "hooks.json").read_text())
        spec = next(iter(hooks.values()))
        self.assertEqual(spec["PreToolUse"][0]["matcher"], "*")
        self.assertIn("evalhook/eval_hook.py", spec["PreToolUse"][0]["hooks"][0]["command"])
        for event in ("SessionStart", "Stop"):
            self.assertIn("evalhook/eval_hook.py", spec[event][0]["command"])

    def test_meters_reads_the_three_pools(self):
        r = self.bench("meters", "--json",
                       FAKE_AGY_METERS=json.dumps({"claude": [81, 64], "gemini": [55, 90], "argon": 77}))
        m = json.loads(r.stdout)
        self.assertEqual(m["claude"], {"weekly": 81, "five_hour": 64})
        self.assertEqual(m["gemini"], {"weekly": 55, "five_hour": 90})
        self.assertEqual(m["argon"]["weekly"], 77)

    def test_unreadable_meters_are_an_error(self):
        r = self.bench("meters", "--json", mode="meters_fail", check=False)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)


class Planning(AgyCase):
    def plan(self):
        return json.loads(self.bench("plan", "--stage", "1", "--json").stdout)

    def test_stage_one_is_every_screening_task_times_cells_times_repeats(self):
        items = self.plan()
        got = sorted((i["task"], i["cell"], i["repeat"]) for i in items)
        want = sorted([(t, G, r) for t in ("n-1", "s-1", "j-1") for r in (1, 2)]
                      + [(t, C, 1) for t in ("n-1", "s-1", "j-1")])
        self.assertEqual(got, want)
        self.assertTrue(all(i["run_id"] for i in items))
        self.assertEqual(len({i["run_id"] for i in items}), len(items))

    def test_run_ids_differ_from_the_claude_instrument(self):
        ctx = self.ctx()
        task = te.ev.load_tasks(ctx)["n-1"]
        claude_ids = {te.ev.run_id_for(ctx, task, c, r) for c in ("base", "cheap", "up")
                      for r in (1, 2, 3)}
        self.assertFalse(claude_ids & {i["run_id"] for i in self.plan()})

    def test_unknown_stage_is_an_error(self):
        r = self.bench("plan", "--stage", "9", check=False)
        self.assertEqual(r.returncode, 2)


# -- runs --------------------------------------------------------------------

class Runs(AgyCase):
    def test_a_full_stage_records_valid_runs_and_code_scores(self):
        r = self.bench("run", "--stage", "1")
        runs = self.agy_runs()
        self.assertEqual(len(runs), 9, r.stdout + r.stderr)
        self.assertTrue(all(x["valid"] for x in runs))
        for x in runs:
            self.assertIsNone(x["invalid_reason"])
            self.assertEqual(x["agy_version"], "1.5.12")
            self.assertEqual(x["model_id"], bench_config()["cells"][x["cell"]]["model_id"])
            self.assertEqual(x["input_tokens"], 1000)
            self.assertEqual(x["output_tokens"], 50)
            self.assertIn(bench_config()["cells"][x["cell"]]["pools"][0], x["meters_before"])
            self.assertTrue((self.root / "private" / "agy-answers" / f"{x['run_id']}.json").is_file())
        scores = self.agy_scores()
        code_runs = {x["run_id"] for x in runs if x["task"] in ("n-1", "s-1")}
        self.assertEqual({s["run_id"] for s in scores}, code_runs)
        self.assertTrue(all(s["passed"] for s in scores))

    def test_the_claude_instrument_files_are_never_written(self):
        self.bench("run", "--stage", "1")
        self.assertFalse((self.root / "results" / "runs.jsonl").exists())
        self.assertFalse((self.root / "results" / "scores.jsonl").exists())
        self.assertFalse((self.root / "private" / "answers").exists())

    def test_the_run_dir_holds_only_the_material_and_is_removed(self):
        self.bench("run", "--stage", "1")
        calls = self.agy_calls()
        self.assertEqual(len(calls), 9)
        for c in calls:
            self.assertEqual(c["files"], ["data.txt"])
            self.assertFalse(Path(c["cwd"]).exists())
        self.assertEqual(list((self.work() / "policy").glob("*.json")), [])

    def test_the_command_line_selects_agent_model_and_settings(self):
        self.bench("run", "--stage", "1", "--max-runs", "1")
        argv = self.agy_calls()[0]["argv"]
        self.assertEqual(argv[argv.index("--agent") + 1], "eval-runner")
        self.assertIn(argv[argv.index("--model") + 1], ("gem-test-medium", "claude-test-medium"))
        self.assertEqual(json.loads(argv[argv.index("--settings") + 1]),
                         {"allowNonWorkspaceAccess": False})
        self.assertEqual(argv[argv.index("--output-format") + 1], "json")
        self.assertTrue(any(a.startswith("-p=Do task") for a in argv))

    def test_a_finished_plan_runs_nothing_again(self):
        self.bench("run", "--stage", "1")
        n = len(self.agy_calls())
        self.assertEqual(json.loads(self.bench("plan", "--stage", "1", "--json").stdout), [])
        self.bench("run", "--stage", "1")
        self.assertEqual(len(self.agy_calls()), n)

    def test_max_runs_bounds_the_invocation(self):
        self.bench("run", "--stage", "1", "--max-runs", "2")
        self.assertEqual(len(self.agy_calls()), 2)

    def test_denied_tool_calls_are_counted_and_the_run_stays_valid(self):
        tool = json.dumps({"name": "run_command", "args": {"CommandLine": "cat ../truth.json"}})
        self.bench("run", "--stage", "1", "--max-runs", "1", FAKE_AGY_TOOL=tool)
        self.assertEqual(self.agy_calls()[0]["decision"], "deny")
        x = self.agy_runs()[0]
        self.assertTrue(x["valid"])
        self.assertEqual(x["tool_calls"], 1)
        self.assertEqual(x["denied_tool_calls"], 1)


class InvalidRuns(AgyCase):
    def one(self, mode, **env):
        self.bench("run", "--stage", "1", "--max-runs", "1", mode=mode, check=False, **env)
        runs = self.agy_runs()
        self.assertEqual(len(runs), 1)
        self.assertFalse(runs[0]["valid"])
        self.assertFalse((self.root / "private" / "agy-answers" / f"{runs[0]['run_id']}.json").exists())
        self.assertEqual(self.agy_scores(), [])
        return runs[0]["invalid_reason"]

    def test_wrong_model_in_the_hook_log(self):
        self.assertEqual(self.one("wrong_model"), "model_mismatch")

    def test_a_helper_conversation(self):
        self.assertEqual(self.one("helper"), "helper_spawned")

    def test_a_foreign_workspace(self):
        self.assertEqual(self.one("workspace"), "workspace_mismatch")

    def test_no_hook_log(self):
        self.assertEqual(self.one("no_hook"), "no_hook_log")

    def test_status_error(self):
        self.assertEqual(self.one("status_error"), "status_error")

    def test_empty_response(self):
        self.assertEqual(self.one("empty"), "no_output")

    def test_output_that_is_not_json(self):
        self.assertEqual(self.one("bad_json"), "json_parse")

    def test_a_hung_run_is_killed(self):
        self.set_bench(bench_config(print_timeout_s=1, kill_grace_s=1))
        self.assertEqual(self.one("timeout"), "timeout")


class StopLines(AgyCase):
    def test_a_quota_error_stops_that_pool_only(self):
        r = self.bench("run", "--stage", "1", check=False, FAKE_AGY_QUOTA_MODELS="claude-test-medium")
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        runs = self.agy_runs()
        claude = [x for x in runs if x["cell"] == C]
        self.assertEqual(len(claude), 1)
        self.assertEqual(claude[0]["invalid_reason"], "quota")
        self.assertEqual(len([x for x in runs if x["cell"] == G and x["valid"]]), 6)

    def test_a_weekly_meter_under_its_stop_line_starts_no_run_in_that_pool(self):
        r = self.bench("run", "--stage", "1", check=False,
                       FAKE_AGY_METERS=json.dumps({"claude": [65, 90]}))
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertIn("stop line", r.stdout + r.stderr)
        models = [c["argv"][c["argv"].index("--model") + 1] for c in self.agy_calls()]
        self.assertNotIn("claude-test-medium", models)
        self.assertEqual(models.count("gem-test-medium"), 6)

    def test_unreadable_meters_start_no_run(self):
        r = self.bench("run", "--stage", "1", mode="meters_fail", check=False)
        self.assertEqual(r.returncode, 2)
        self.assertEqual(self.agy_calls(), [])

    def test_a_held_lock_is_an_error(self):
        import fcntl
        lock = self.root / "results" / ".agy-bench.lock"
        lock.parent.mkdir(parents=True, exist_ok=True)
        with open(lock, "w") as f:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            r = self.bench("run", "--stage", "1", check=False)
        self.assertEqual(r.returncode, 2)
        self.assertEqual(self.agy_calls(), [])


class JudgeAndReport(AgyCase):
    JUDGMENT = '===ANSWER===\n{"score": 0.9, "points": 2}\n===END==='

    def judge(self):
        return self.bench("judge", FAKE_CLAUDE_ANSWER=self.JUDGMENT, FAKE_CLAUDE_LOG=str(self.log))

    def test_judge_scores_the_judge_task_runs_into_the_agy_scores_only(self):
        self.bench("run", "--stage", "1")
        self.judge()
        j_runs = {x["run_id"] for x in self.agy_runs() if x["task"] == "j-1"}
        self.assertEqual(len(j_runs), 3)
        judged = [s for s in self.agy_scores() if s["run_id"] in j_runs]
        self.assertEqual(len(judged), 3 * 2)                      # harness judge repeats: 2
        self.assertTrue(all(s["grader_id"].startswith("judge:judge:") for s in judged))
        self.assertEqual({c["model"] for c in self.calls()}, {"claude-test-judge"})
        self.assertFalse((self.root / "results" / "scores.jsonl").exists())
        self.log.unlink()
        self.judge()
        self.assertEqual(self.calls(), [])                         # nothing left to judge

    def test_report_counts_passes_and_tokens_per_task_and_cell(self):
        self.bench("run", "--stage", "1")
        self.judge()
        rep = json.loads(self.bench("report", "--stage", "1", "--json").stdout)
        rows = {(r["task"], r["cell"]): r for r in rep["rows"]}
        self.assertEqual(len(rows), 6)
        n = rows[("n-1", G)]
        self.assertEqual((n["valid"], n["scored"], n["passed"]), (2, 2, 2))
        self.assertEqual(n["median_input_tokens"], 1000)
        self.assertEqual(n["median_output_tokens"], 50)
        j = rows[("j-1", C)]
        self.assertEqual((j["valid"], j["scored"], j["passed"]), (1, 1, 1))
        self.assertAlmostEqual(j["mean_score"], 0.9)
        self.assertEqual(rep["meters"]["claude"], {"first": 100, "last": 100, "runs": 3})


if __name__ == "__main__":
    unittest.main()
