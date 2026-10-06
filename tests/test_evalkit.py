"""Tests for evals/evalkit.py.

Every test works in a temporary evals directory (AGENTING_EVALS_DIR) with
synthetic cells, rows and tasks, and `claude` replaced by tests/fixtures/
fake_claude.py. No test makes a model call, and a final test proves the real
evals/results and evals/private/{answers,work} were not touched.
"""

import contextlib
import fcntl
import hashlib
import io
import json
import os
import shlex
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
EVALS = ROOT / "evals"
EVALKIT = EVALS / "evalkit.py"
FAKE = Path(__file__).resolve().parent / "fixtures" / "fake_claude.py"
sys.path.insert(0, str(EVALS))

import evalkit as ev  # noqa: E402

GRADER_CODE = '''
def grade(answer, truth):
    ok = answer.strip() == str(truth["answer"])
    return {"score": 1.0 if ok else 0.0, "passed": ok, "details": {"checked": 1}}
'''
GRADER_JUDGE = '''
def score_judgment(judgment, truth):
    s = float(judgment["score"])
    return {"score": s, "passed": s >= 0.7, "details": {"points": judgment.get("points", 0)}}
'''
GRADER_RAISES = '''
def grade(answer, truth):
    raise RuntimeError("grader bug")
'''
GRADER_HANGS = '''
import time
def grade(answer, truth):
    time.sleep(120)
'''
GRADER_STRUCT = '''
def grade(answer, truth):
    ok = answer.strip() == str(truth["answer"])
    return {"score": 1.0 if ok else 0.0, "passed": ok, "details": {
        "checked": 1, "exact": ok, "ratio": 0.5, "label": "short", "long": "x" * 41, "nothing": None,
        "per_question": {"q1": True, "q7": False}, "missed": ["q7"], "findings": [{"id": "f2", "ok": False}]}}
'''
GRADER_JUDGE_STRUCT = '''
def score_judgment(judgment, truth):
    s = float(judgment["score"])
    return {"score": s, "passed": s >= 0.7, "details": {
        "points": judgment.get("points", 0), "verdicts": {"f1": "hit", "f2": "miss"}, "found": ["f1"]}}
'''
GRADER_BAD = '''
def grade(answer, truth):
    return {"score": 0.0, "passed": False, "details": {}}
'''
CELLS = {"cells": {
    "base": {"model_id": "claude-test-base", "effort": None, "price": {"input": 1.0, "output": 5.0}},
    "cheap": {"model_id": "claude-test-cheap", "effort": "low", "price": {"input": 0.1, "output": 0.5}},
    "up": {"model_id": "claude-test-up", "effort": "high", "price": {"input": 9.0, "output": 9.0}},
    "judge": {"model_id": "claude-test-judge", "effort": "high", "price": {"input": 1.0, "output": 1.0}}}}
GRID = [{"cell": "base", "role": "baseline"}, {"cell": "cheap", "role": "effort_down"},
        {"cell": "up", "role": "up_reference"}]
ROWS = {"rows": [
    {"id": "noticed-row", "plugin_row": "n", "tier": "noticed", "baseline": "base", "grid": GRID,
     "tasks": ["n-1"]},
    {"id": "silent-row", "plugin_row": "s", "tier": "silent_damage", "baseline": "base",
     "grid": GRID, "tasks": ["s-1"]},
    {"id": "judge-row", "plugin_row": "j", "tier": "noticed", "baseline": "base",
     "grid": GRID[:2], "tasks": ["j-1"]}]}


def harness(claude_bin, timeout_s=30):
    return {"harness_version": 1, "repeats_default": 3, "max_retries_invalid": 2,
            "runner": {"claude_bin": claude_bin, "flags": ["--restricted", "--output-format", "json"],
                       "tools_files": "Read,Grep,Glob", "tools_inline": "", "timeout_s": timeout_s,
                       "max_budget_usd_per_run": 1, "jobs": 2, "system_prompt": "Be careful."},
            "answer_markers": ["===ANSWER===", "===END==="],
            "judge": {"cell": "judge", "repeats": 2, "system_prompt": "You are a strict grader."},
            "decision": {"noticed_extra_misses": 1, "confirmation_tasks_min": 2}}


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class EvalTestCase(unittest.TestCase):
    """A fresh evals directory per test, wired to the fake claude."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "evals"
        self.root.mkdir()
        self.log = Path(self._tmp.name) / "calls.jsonl"
        self.set_harness(harness(f"{shlex.quote(sys.executable)} {shlex.quote(str(FAKE))}"))
        write(self.root / "cells.json", json.dumps(CELLS))
        write(self.root / "rows.json", json.dumps(ROWS))
        self.make_task("n-1", "noticed-row")
        self.make_task("s-1", "silent-row")
        self.make_task("s-c1", "silent-row", phase="confirmation")
        self.make_task("s-c2", "silent-row", phase="confirmation")
        self.make_task("j-1", "judge-row", grading="judge")

    def tearDown(self):
        self._tmp.cleanup()

    # -- fixtures -----------------------------------------------------------

    def set_harness(self, h):
        write(self.root / "harness.json", json.dumps(h))

    def edit_harness(self, **changes):
        h = json.loads((self.root / "harness.json").read_text())
        h.update(changes)
        self.set_harness(h)

    def make_task(self, tid, row, phase="screening", grading="code", delivery="files"):
        d = self.root / "private" / "tasks" / tid
        write(d / "task.json", json.dumps({
            "id": tid, "row": row, "phase": phase, "title": f"Task {tid}", "delivery": delivery,
            "pass_threshold": 0.7, "pass_rule": "score >= 0.7",
            "grading": {"type": grading, "rubric": "rubric.md" if grading == "judge" else None}}))
        write(d / "prompt.md", f"Do task {tid} using data.txt.\n===ANSWER===\n===END===\n")
        if delivery == "files":
            write(d / "material" / "data.txt", "forty two\n")
        write(d / "truth.json", json.dumps({"answer": 42}))
        if grading == "judge":
            write(d / "rubric.md", "Key points: A, B. Reply with {\"score\": 0..1}.\n")
            write(d / "grader.py", GRADER_JUDGE)
            write(d / "fixtures" / "judgment_perfect.json", '{"score": 1.0}')
            write(d / "fixtures" / "judgment_flawed_a.json", '{"score": 0.2}')
        else:
            write(d / "grader.py", GRADER_CODE)
            write(d / "fixtures" / "perfect.txt", "42")
            write(d / "fixtures" / "flawed_a.txt", "41")
        return d

    def ctx(self):
        return ev.Ctx(self.root)

    def cli(self, *args, mode="ok", check=True, **env):
        e = dict(os.environ, AGENTING_EVALS_DIR=str(self.root), FAKE_CLAUDE_MODE=mode,
                 FAKE_CLAUDE_LOG=str(self.log))
        e.update({k: str(v) for k, v in env.items()})
        r = subprocess.run([sys.executable, str(EVALKIT), *args], capture_output=True,
                           text=True, timeout=60, env=e)
        if check:
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r

    def calls(self):
        if not self.log.exists():
            return []
        return [json.loads(x) for x in self.log.read_text().splitlines()]

    def runs(self):
        return ev.read_jsonl(self.root / "results" / "runs.jsonl")

    def scores(self):
        return ev.read_jsonl(self.root / "results" / "scores.jsonl")

    def seed(self, task_id, cell_id, passes, cost=0.01, thinking=50):
        """Write synthetic valid runs (repeat 1..n) straight into results/. `passes` holds
        True/False for a scored run and None for a valid run left ungraded."""
        ctx = self.ctx()
        task = ev.load_tasks(ctx)[task_id]
        for i, ok in enumerate(passes, 1):
            rid = ev.run_id_for(ctx, task, cell_id, i)
            ev.append_jsonl(ctx.runs_path, {
                "run_id": rid, "task_id": task_id, "cell_id": cell_id, "repeat": i, "valid": True,
                "cell_hash": ctx.cell_hash(cell_id), "model_id_expected": ctx.model_id(cell_id),
                "cost_usd": cost, "thinking_tokens": thinking})
            if ok is not None:
                ev.append_jsonl(ctx.scores_path, ev.score_line(
                    rid, ev.grader_prefix(ctx, task),
                    {"score": 1.0 if ok else 0.0, "passed": ok, "details": {}}))

    def set_cells(self, mutate):
        cells = json.loads(json.dumps(CELLS))
        mutate(cells["cells"])
        write(self.root / "cells.json", json.dumps(cells))

    def decide(self, row_id):
        out = json.loads(self.cli("decide", "--json").stdout)
        return next(r for r in out if r["row"] == row_id)


class RunIdAndHash(EvalTestCase):
    def test_run_id_is_stable(self):
        a = ev.compute_run_id(1, "t", "h", "abcd1234", 1)
        self.assertEqual(a, ev.compute_run_id(1, "t", "h", "abcd1234", 1))
        self.assertEqual(len(a), 16)
        self.assertEqual(a, hashlib.sha1(b"1|t|h|abcd1234|1").hexdigest()[:16])

    def test_run_id_changes_with_each_input(self):
        base = ev.compute_run_id(1, "t", "h", "c", 1)
        for changed in (ev.compute_run_id(2, "t", "h", "c", 1),
                        ev.compute_run_id(1, "t2", "h", "c", 1),
                        ev.compute_run_id(1, "t", "h2", "c", 1),
                        ev.compute_run_id(1, "t", "h", "c2", 1),
                        ev.compute_run_id(1, "t", "h", "c", 2)):
            self.assertNotEqual(base, changed)

    def test_cell_hash_is_sha8_of_the_canonical_identity(self):
        cell = {"model_id": "m", "effort": "low", "price": {"input": 1}, "why": "ignored"}
        want = hashlib.sha256(ev.canon({"cell_id": "c", "model_id": "m", "effort": "low",
                                        "system_append": ""}).encode()).hexdigest()[:8]
        self.assertEqual(ev.compute_cell_hash("c", cell), want)
        self.assertEqual(ev.compute_cell_hash("c", {**cell, "system_append": ""}), want)   # missing == ""
        self.assertEqual(ev.compute_cell_hash("c", {**cell, "price": {"input": 99}}), want)  # price is not identity
        for changed in ({**cell, "effort": "high"}, {**cell, "effort": None}, {**cell, "model_id": "m2"},
                        {**cell, "system_append": "Think."}):
            self.assertNotEqual(ev.compute_cell_hash("c", changed), want)
        self.assertNotEqual(ev.compute_cell_hash("c2", cell), want)
        self.assertEqual(len(want), 8)
    def test_task_hash_follows_prompt_and_material(self):
        d = self.root / "private" / "tasks" / "n-1"
        h0 = ev.compute_task_hash(d, "files")
        self.assertEqual(h0, ev.compute_task_hash(d, "files"))
        self.assertNotEqual(h0, ev.compute_task_hash(d, "inline"))
        write(d / "material" / "data.txt", "forty three\n")
        h1 = ev.compute_task_hash(d, "files")
        self.assertNotEqual(h0, h1)
        write(d / "prompt.md", "A different prompt.\n")
        self.assertNotEqual(h1, ev.compute_task_hash(d, "files"))

    def test_manifest_is_sorted_and_deterministic(self):
        self.cli("manifest")
        first = (self.root / "tasks.json").read_text()
        self.cli("manifest")
        self.assertEqual(first, (self.root / "tasks.json").read_text())
        entries = json.loads(first)
        self.assertEqual([e["id"] for e in entries], sorted(e["id"] for e in entries))
        self.assertEqual(list(entries[0]), ["id", "row", "phase", "title", "delivery", "grading_type",
                                            "pass_rule", "pass_threshold", "task_hash"])


class Planning(EvalTestCase):
    def plan(self, *args):
        return json.loads(self.cli("plan", "--json", *args).stdout)

    def test_fresh_plan_expands_grid_tasks_repeats(self):
        p = self.plan("--rows", "noticed-row")
        self.assertEqual(len(p["items"]), 3 * 3)       # 3 cells x 1 screening task x 3 repeats
        self.assertEqual(p["counts"], {"base": 3, "cheap": 3, "up": 3})
        self.assertTrue(all(i["reason"] == "missing" for i in p["items"]))
        self.assertEqual(p["items"], sorted(p["items"], key=lambda i: (i["row"], i["task"], i["cell"], i["repeat"])))

    def test_confirmation_tasks_only_with_phase_or_task_filter(self):
        self.assertEqual(len(self.plan("--rows", "silent-row")["items"]), 9)
        self.assertEqual(len(self.plan("--rows", "silent-row", "--phase", "all")["items"]), 27)
        self.assertEqual(len(self.plan("--tasks", "s-c1", "--cells", "base")["items"]), 3)

    def test_plan_skips_valid_runs(self):
        self.cli("run", "--rows", "noticed-row", "--cells", "cheap", "--repeats", "2")
        p = self.plan("--rows", "noticed-row", "--cells", "cheap", "--repeats", "3")
        self.assertEqual([i["repeat"] for i in p["items"]], [3])

    def test_plan_replans_when_task_changes(self):
        self.cli("run", "--rows", "noticed-row", "--cells", "base", "--repeats", "1")
        self.assertEqual(self.plan("--rows", "noticed-row", "--cells", "base", "--repeats", "1")["items"], [])
        write(self.root / "private" / "tasks" / "n-1" / "prompt.md", "Reworded prompt.\n")
        self.assertEqual(len(self.plan("--rows", "noticed-row", "--cells", "base", "--repeats", "1")["items"]), 1)

    def test_plan_replans_when_model_id_or_harness_changes(self):
        self.cli("run", "--rows", "noticed-row", "--cells", "base", "--repeats", "1")
        args = ("--rows", "noticed-row", "--cells", "base", "--repeats", "1")
        cells = json.loads((self.root / "cells.json").read_text())
        cells["cells"]["base"]["model_id"] = "claude-test-base-2"
        write(self.root / "cells.json", json.dumps(cells))
        self.assertEqual(len(self.plan(*args)["items"]), 1)
        write(self.root / "cells.json", json.dumps(CELLS))
        self.assertEqual(self.plan(*args)["items"], [])
        self.edit_harness(harness_version=2)
        self.assertEqual(len(self.plan(*args)["items"]), 1)

    def test_cell_identity_change_replans_that_cell_only(self):
        self.cli("run", "--rows", "noticed-row", "--repeats", "1")
        args = ("--rows", "noticed-row", "--repeats", "1")
        self.assertEqual(self.plan(*args)["items"], [])
        for mutate in (lambda c: c["cheap"].update(effort="medium"),
                       lambda c: c["cheap"].update(model_id="claude-test-cheap-2"),
                       lambda c: c["cheap"].update(system_append="Think first.")):
            self.set_cells(mutate)
            self.assertEqual([(i["cell"], i["repeat"]) for i in self.plan(*args)["items"]],
                             [("cheap", 1)])
        write(self.root / "cells.json", json.dumps(CELLS))
        self.assertEqual(self.plan(*args)["items"], [])        # reverting reuses the stored runs

    def test_cell_identity_change_gives_a_new_run_id(self):
        ctx, task = self.ctx(), ev.load_tasks(self.ctx())["n-1"]
        before = {c: ev.run_id_for(ctx, task, c, 1) for c in ("base", "cheap", "up")}
        for mutate in (lambda c: c["cheap"].update(effort="medium"),
                       lambda c: c["cheap"].update(model_id="claude-test-cheap-2"),
                       lambda c: c["cheap"].update(system_append="Think first.")):
            self.set_cells(mutate)
            ctx = self.ctx()
            after = {c: ev.run_id_for(ctx, task, c, 1) for c in before}
            self.assertNotEqual(after["cheap"], before["cheap"])
            self.assertEqual((after["base"], after["up"]), (before["base"], before["up"]))

    def test_invalid_runs_retry_up_to_the_cap(self):
        args = ("--rows", "noticed-row", "--cells", "base", "--repeats", "1")
        for attempt in range(1, 5):
            self.cli("run", *args, mode="error")
            p = self.plan(*args)
            if attempt <= 2:
                self.assertEqual([i["reason"] for i in p["items"]], ["retry"])
            elif attempt == 3:       # initial attempt + 2 retries used: nothing more is planned
                self.assertEqual((p["items"], p["exhausted"]), ([], 1))
        self.assertEqual(len(self.runs()), 3)             # attempt 4 never launched

    def test_unknown_filters_fail_clearly(self):
        r = self.cli("plan", "--cells", "nope", check=False)
        self.assertEqual(r.returncode, 2)
        self.assertIn("unknown cell: nope", r.stderr)

    def test_missing_private_is_tolerated_with_manifest_and_explained_without(self):
        self.cli("manifest")
        import shutil
        shutil.rmtree(self.root / "private")
        self.assertEqual(len(self.plan("--rows", "noticed-row")["items"]), 9)
        r = self.cli("run", "--rows", "noticed-row", check=False)
        self.assertEqual(r.returncode, 2)
        self.assertIn("private", r.stderr)
        (self.root / "tasks.json").unlink()
        self.assertIn("no tasks", self.cli("plan", check=False).stderr)


class RunExecution(EvalTestCase):
    def one(self, mode="ok", cell="cheap", row="noticed-row", **env):
        return self.cli("run", "--rows", row, "--cells", cell, "--repeats", "1", mode=mode, **env)

    def test_command_shape_stdin_cwd_and_cleanup(self):
        self.one(cell="cheap")
        self.one(cell="base")
        c_cheap, c_base = self.calls()
        self.assertEqual((c_cheap["model"], c_cheap["effort"]), ("claude-test-cheap", "low"))
        self.assertNotIn("--effort", c_base["argv"])               # effort null: flag omitted
        self.assertEqual(c_cheap["tools"], ["Read,Grep,Glob"])
        self.assertIn("Do task n-1", c_cheap["prompt"])            # prompt arrived on stdin
        self.assertEqual(c_cheap["files"], ["data.txt"])           # material copy only
        self.assertEqual(c_cheap["system_prompt"], "Be careful.")
        self.assertNotIn("Do task", " ".join(c_cheap["argv"]))
        self.assertEqual(os.listdir(self.root / "private" / "work"), [])

    def test_system_append_goes_after_the_harness_prompt_with_two_newlines(self):
        self.set_cells(lambda c: c["cheap"].update(system_append="Think the problem through."))
        self.one(cell="cheap")
        self.one(cell="base")
        c_cheap, c_base = self.calls()
        self.assertEqual(c_cheap["system_prompt"], "Be careful.\n\nThink the problem through.")
        self.assertEqual(c_base["system_prompt"], "Be careful.")

    def test_run_record_carries_the_cell_hash_and_run_id_uses_it(self):
        self.set_cells(lambda c: c["cheap"].update(system_append="Think."))
        self.one(cell="cheap")
        (r,) = self.runs()
        ctx = self.ctx()
        self.assertEqual(r["cell_hash"], ctx.cell_hash("cheap"))
        want = hashlib.sha1(f"1|n-1|{r['task_hash']}|{r['cell_hash']}|1".encode()).hexdigest()[:16]
        self.assertEqual(r["run_id"], want)

    def test_valid_run_record_answer_file_and_code_score(self):
        self.one(FAKE_CLAUDE_COST="0.02", FAKE_CLAUDE_THINKING="77")
        (r,) = self.runs()
        self.assertTrue(r["valid"])
        self.assertEqual((r["model_id_expected"], r["model_id_observed"]), ("claude-test-cheap",) * 2)
        self.assertEqual((r["cost_usd"], r["thinking_tokens"], r["effort"]), (0.02, 77, "low"))
        for key in ("run_id", "harness_version", "task_id", "task_hash", "cell_id", "cell_hash", "repeat", "input_tokens",
                    "output_tokens", "cache_read_tokens", "duration_ms", "num_turns", "ts"):
            self.assertIn(key, r)
        ans = json.loads((self.root / "private" / "answers" / f"{r['run_id']}.json").read_text())
        self.assertEqual(ans["block"], "42")
        (s,) = self.scores()
        self.assertEqual((s["run_id"], s["score"], s["passed"]), (r["run_id"], 1.0, True))
        self.assertTrue(s["grader_id"].startswith("code:"))

    def test_wrong_model_is_invalid_and_not_graded(self):
        self.one(mode="wrong_model")
        (r,) = self.runs()
        self.assertFalse(r["valid"])
        self.assertIn("model_mismatch", r["invalid_reason"])
        self.assertEqual(self.scores(), [])
        self.assertFalse((self.root / "private" / "answers").exists())

    def test_alias_drift_is_invalid(self):
        self.one(mode="alias_drift")
        (r,) = self.runs()
        self.assertFalse(r["valid"])
        self.assertIn("claude-test-cheap-next", r["model_id_observed"])

    def test_error_and_bad_json_are_invalid(self):
        self.one(mode="error")
        self.one(mode="bad_json")
        self.assertEqual([r["invalid_reason"] for r in self.runs()], ["exit_code=1", "json_parse"])

    def test_timeout_kills_and_is_invalid(self):
        self.edit_harness(runner={**harness("x")["runner"], "timeout_s": 1,
                                  "claude_bin": f"{shlex.quote(sys.executable)} {shlex.quote(str(FAKE))}"})
        t0 = time.time()
        self.one(mode="timeout")
        self.assertLess(time.time() - t0, 20)
        (r,) = self.runs()
        self.assertEqual((r["valid"], r["invalid_reason"]), (False, "timeout"))
        self.assertEqual(os.listdir(self.root / "private" / "work"), [])

    def test_missing_block_is_a_graded_failure_not_invalid(self):
        self.one(mode="no_block")
        (r,) = self.runs()
        self.assertTrue(r["valid"])
        (s,) = self.scores()
        self.assertEqual((s["score"], s["passed"], s["details"]["no_block"]), (0.0, False, True))

    def test_extract_block_last_wins_and_requires_both_markers(self):
        m = ("===ANSWER===", "===END===")
        text = "===ANSWER===\nA\n===END===\nmore\nnote ===ANSWER=== inline\n===ANSWER===\n B \n===END==="
        self.assertEqual(ev.extract_block(text, m), "B")
        self.assertIsNone(ev.extract_block("===ANSWER===\nno end", m))
        self.assertIsNone(ev.extract_block("", m))

    def test_wrong_answer_is_scored_failed(self):
        self.one(FAKE_CLAUDE_ANSWER="===ANSWER===\n41\n===END===")
        self.assertEqual([s["passed"] for s in self.scores()], [False])

    def test_inline_delivery_gets_no_tools_and_empty_cwd(self):
        self.make_task("n-2", "noticed-row", delivery="inline")
        self.cli("run", "--tasks", "n-2", "--cells", "cheap", "--repeats", "1")
        (c,) = self.calls()
        self.assertEqual((c["tools"], c["files"]), ([""], []))

    def test_budget_cap_stops_launching(self):
        self.cli("run", "--rows", "noticed-row", "--max-usd", "0.025", "--jobs", "1", FAKE_CLAUDE_COST="0.01")
        self.assertEqual(len(self.runs()), 3)               # 0.01, 0.02, 0.03 >= cap: the rest skipped
        self.assertEqual(len(self.plan_items()), 6)

    def test_invalid_run_cost_counts_toward_budget(self):
        self.cli("run", "--rows", "noticed-row", "--max-usd", "0.015", "--jobs", "1",
                 mode="wrong_model", FAKE_CLAUDE_COST="0.01")
        self.assertEqual(len(self.runs()), 2)

    def plan_items(self):
        return json.loads(self.cli("plan", "--json", "--rows", "noticed-row").stdout)["items"]

    def test_dry_run_calls_nothing(self):
        r = self.cli("run", "--rows", "noticed-row", "--dry-run")
        self.assertIn("9 run(s) planned", r.stdout)
        self.assertEqual((self.calls(), self.runs()), ([], []))

    def test_concurrent_appends_never_interleave(self):
        path = self.root / "results" / "x.jsonl"
        threads = [threading.Thread(target=lambda n=n: [ev.append_jsonl(path, {"n": n, "pad": "é" * 500})
                                                        for _ in range(40)]) for n in range(8)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        self.assertEqual(len(ev.read_jsonl(path)), 320)

    def test_sigint_exits_130_without_half_written_lines(self):
        env = dict(os.environ, AGENTING_EVALS_DIR=str(self.root), FAKE_CLAUDE_MODE="timeout",
                   FAKE_CLAUDE_LOG=str(self.log))
        p = subprocess.Popen([sys.executable, str(EVALKIT), "run", "--rows", "noticed-row", "--jobs", "2"],
                             env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        for _ in range(100):
            if len(self.calls()) >= 2:
                break
            time.sleep(0.1)
        p.send_signal(signal.SIGINT)
        p.communicate(timeout=20)
        self.assertEqual(p.returncode, 130)
        self.assertEqual(self.runs(), [])


class Judging(EvalTestCase):
    JUDGMENT = '===ANSWER===\n{"score": 0.9, "points": 2}\n===END==='

    def subject(self):
        self.cli("run", "--tasks", "j-1", "--cells", "cheap", "--repeats", "1")
        return self.runs()[0]["run_id"]

    def test_judge_flow_scores_every_pass_blind_to_the_cell(self):
        rid = self.subject()
        self.log.unlink()
        self.cli("judge", FAKE_CLAUDE_ANSWER=self.JUDGMENT, FAKE_CLAUDE_COST="0.03")
        calls = self.calls()
        self.assertEqual(len(calls), 2)                         # judge.repeats passes
        for c in calls:
            self.assertEqual((c["model"], c["tools"]), ("claude-test-judge", [""]))
            self.assertEqual(c["system_prompt"], "You are a strict grader.")
            self.assertEqual(c["files"], [])
            self.assertIn("Do task j-1", c["prompt"])           # task prompt for context
            self.assertIn("Key points", c["prompt"])            # rubric
            self.assertIn("42", c["prompt"])                    # the answer block
            self.assertNotIn("cheap", c["prompt"] + c["cwd"])   # no cell identity leaks
        judged = [s for s in self.scores() if s["run_id"] == rid]
        rubric = (self.root / "private" / "tasks" / "j-1" / "rubric.md").read_bytes()
        prefix = f"judge:judge:{hashlib.sha256(rubric).hexdigest()[:8]}:"
        self.assertEqual(sorted(s["grader_id"] for s in judged), [prefix + "0", prefix + "1"])
        self.assertEqual({s["details"]["judge_cost_usd"] for s in judged}, {0.03})
        self.assertEqual(self.judge_again(), 0)                 # nothing left to judge

    def judge_again(self):
        self.log.unlink()
        self.cli("judge", FAKE_CLAUDE_ANSWER=self.JUDGMENT)
        return len(self.calls())

    def test_rubric_change_triggers_rejudging_not_rerunning(self):
        self.subject()
        self.cli("judge", FAKE_CLAUDE_ANSWER=self.JUDGMENT)
        write(self.root / "private" / "tasks" / "j-1" / "rubric.md", "A new rubric.\n")
        self.cli("judge", FAKE_CLAUDE_ANSWER=self.JUDGMENT)
        self.assertEqual(len(self.runs()), 1)
        self.assertEqual(len(self.scores()), 4)

    def test_effective_judge_score_is_mean_and_majority_vote(self):
        ctx, task = self.ctx(), ev.load_tasks(self.ctx())["j-1"]
        prefix = ev.grader_prefix(ctx, task)
        def put(k, score, passed):
            ev.append_jsonl(ctx.scores_path, ev.score_line(
                "r1", f"{prefix}{k}", {"score": score, "passed": passed, "details": {}}))
        put(0, 0.8, True)
        self.assertIsNone(ev.effective(ctx, task, "r1", ev.scores_by_run(ctx)))   # one pass of two
        put(1, 0.4, False)
        score, passed = ev.effective(ctx, task, "r1", ev.scores_by_run(ctx))
        self.assertAlmostEqual(score, 0.6)
        self.assertFalse(passed)                                # 1 of 2 is not a majority

    def test_unusable_judge_reply_records_nothing(self):
        self.subject()
        self.cli("judge", FAKE_CLAUDE_ANSWER="no markers here")
        self.assertEqual(self.scores(), [])

    GOOD = '===ANSWER===\n{"score": 0.9, "points": 2}\n===END==='

    def seq(self, answers):
        return {"FAKE_CLAUDE_SEQ": json.dumps(answers), "FAKE_CLAUDE_STATE": str(Path(self._tmp.name) / "seq")}

    def judge_serially(self, answers, **env):
        self.subject()
        self.log.unlink()
        return self.cli("judge", "--jobs", "1", **self.seq(answers), **env)

    def test_unparseable_judge_reply_is_retried_then_scored(self):
        garbage = "===ANSWER===\n{not json\n===END==="
        r = self.judge_serially(["no markers at all", garbage, self.GOOD], FAKE_CLAUDE_COST="0.02")
        self.assertEqual(len(self.calls()), 4)                  # pass 0: bad, bad, good; pass 1: good
        judged = self.scores()
        self.assertEqual(len(judged), 2)
        self.assertEqual(sorted(s["details"]["judge_attempts"] for s in judged), [1, 3])
        retried = next(s for s in judged if s["details"]["judge_attempts"] == 3)
        self.assertAlmostEqual(retried["details"]["judge_cost_usd"], 0.06)   # failed attempts still cost money
        self.assertNotIn("left missing", r.stdout)
        self.assertTrue(all(s["passed"] for s in judged))      # no failing score from a format fault

    def test_rejected_judgment_shape_is_retried(self):
        wrong_shape = '===ANSWER===\n{"verdict": "fine"}\n===END==='     # grader raises KeyError on it
        self.judge_serially([wrong_shape, self.GOOD])
        self.assertEqual(len(self.calls()), 3)
        self.assertEqual(len(self.scores()), 2)

    def test_judge_format_fault_after_retries_leaves_the_pass_missing_and_reports_it(self):
        r = self.judge_serially(["no markers here"])
        self.assertEqual(len(self.calls()), 2 * 3)             # two passes x (1 try + 2 retries)
        self.assertEqual(self.scores(), [])                    # never a failing score for a format fault
        self.assertIn("2 judge pass(es) left missing", r.stdout)
        self.assertIn("left missing after 3 attempt(s)", r.stderr)
        out = self.cli("status").stdout
        self.assertRegex(out, r"judge-row\s+1/1\s+2\s+1\s+0\s+0\s+1")      # the run is ungraded
        self.assertEqual(self.decide("judge-row")["recommendation"], "INSUFFICIENT_DATA")

    def test_partial_judge_failure_keeps_the_good_pass_and_the_run_ungraded(self):
        # pass 0 gets 3 unusable replies, pass 1 then gets the good one
        self.judge_serially(["bad", "bad", "bad", self.GOOD])
        self.assertEqual(len(self.scores()), 1)
        ctx = self.ctx()
        task = ev.load_tasks(ctx)["j-1"]
        self.assertIsNone(ev.effective(ctx, task, self.runs()[0]["run_id"], ev.scores_by_run(ctx)))
        self.log.unlink()
        self.cli("judge", FAKE_CLAUDE_ANSWER=self.GOOD)         # a later judge run fills only the gap
        self.assertEqual(len(self.calls()), 1)
        self.assertEqual(len(self.scores()), 2)

    def test_invalid_judge_call_is_not_a_format_fault_and_not_retried(self):
        self.subject()
        self.log.unlink()
        r = self.cli("judge", mode="wrong_model", FAKE_CLAUDE_ANSWER=self.GOOD)
        self.assertEqual(len(self.calls()), 2)                  # one call per pass
        self.assertEqual(self.scores(), [])
        self.assertIn("judge call invalid", r.stderr)

    def test_answer_without_block_scores_zero_without_a_model_call(self):
        self.cli("run", "--tasks", "j-1", "--cells", "cheap", "--repeats", "1", mode="no_block")
        self.log.unlink()
        self.cli("judge")
        self.assertEqual(self.calls(), [])
        self.assertEqual([s["score"] for s in self.scores()], [0.0, 0.0])


class ReportAndStatus(EvalTestCase):
    def test_report_numbers_on_a_synthetic_dataset(self):
        self.seed("n-1", "base", [True, True, False], cost=0.10, thinking=300)
        self.seed("n-1", "cheap", [True, True, True], cost=0.04, thinking=60)
        out = self.cli("report", "--rows", "noticed-row").stdout
        line = {ln.split()[0]: ln.split() for ln in out.splitlines() if ln.split()[:1] in (["base"], ["cheap"], ["up"])}
        self.assertEqual(line["base"][2:], ["3", "3", "2", "66.7%", "0.667", "$0.1000", "300", "1"])
        self.assertEqual(line["cheap"][2:], ["3", "3", "3", "100.0%", "1.000", "$0.0400", "60", "1"])
        self.assertEqual(line["up"][2:], ["0", "0", "0", "n/a", "n/a", "$n/a", "n/a", "0"])

    def test_report_markdown_and_stale_runs_ignored(self):
        self.seed("n-1", "base", [True])
        write(self.root / "private" / "tasks" / "n-1" / "prompt.md", "changed\n")   # task hash moves on
        out = self.cli("report", "--md", "--rows", "noticed-row").stdout
        self.assertIn("| cell | role | runs |", out)
        self.assertIn("| base | baseline | 0 | 0 |", out)

    def test_status_counts_and_total_cost(self):
        self.seed("n-1", "base", [True, True], cost=0.5)
        ev.append_jsonl(self.root / "results" / "scores.jsonl", {
            "run_id": "z", "grader_id": "judge:x:y:0", "score": 1, "passed": True,
            "details": {"judge_cost_usd": 0.25}, "ts": "t"})
        out = self.cli("status").stdout
        self.assertRegex(out, r"noticed-row\s+1/1\s+3\s+2\s+0\s+2\s+0")
        self.assertIn("total cost so far: $1.2500", out)


class UngradedRuns(EvalTestCase):
    def test_status_counts_ungraded_and_report_excludes_them(self):
        self.seed("n-1", "base", [True, None, None], cost=0.10)
        out = self.cli("status").stdout
        self.assertIn("ungraded", out.splitlines()[0])
        self.assertRegex(out, r"noticed-row\s+1/1\s+3\s+3\s+0\s+1\s+2")
        rep = self.cli("report", "--rows", "noticed-row").stdout
        base = next(ln.split() for ln in rep.splitlines() if ln.startswith("base"))
        self.assertEqual(base[2:6], ["3", "3", "1", "100.0%"])      # pass rate over the graded run only
        self.assertIn("2 ungraded run(s) excluded", rep)


class Decisions(EvalTestCase):
    def fill(self, row_tasks, base, cand, cand_cost=0.05, base_cost=0.10, cell="cheap"):
        for t in row_tasks:
            self.seed(t, "base", base, cost=base_cost)
            self.seed(t, cell, cand, cost=cand_cost)

    def test_noticed_moves_to_cheaper_within_one_extra_miss(self):
        self.fill(["n-1"], [True, True, True], [True, True, False])
        d = self.decide("noticed-row")
        self.assertEqual((d["recommendation"], d["cell"]), ("MOVE_TO", "cheap"))

    def test_noticed_two_extra_misses_keeps_baseline(self):
        self.fill(["n-1"], [True, True, True], [True, False, False])
        d = self.decide("noticed-row")
        self.assertEqual(d["recommendation"], "KEEP")
        cand = next(c for c in d["candidates"] if c["cell"] == "cheap")
        self.assertIn("2 failures vs baseline 0 + 1", cand["reason"])

    def test_saving_below_the_materiality_threshold_keeps_baseline(self):
        self.edit_harness(decision={"noticed_extra_misses": 1, "confirmation_tasks_min": 2,
                                    "min_saving_fraction": 0.25})
        self.fill(["n-1"], [True] * 3, [True] * 3, cand_cost=0.09)        # 10% cheaper
        d = self.decide("noticed-row")
        self.assertEqual(d["recommendation"], "KEEP")
        self.assertIn("cheaper by only 10%", d["candidates"][0]["reason"])

    def test_saving_at_or_above_the_threshold_still_moves(self):
        self.edit_harness(decision={"noticed_extra_misses": 1, "confirmation_tasks_min": 2,
                                    "min_saving_fraction": 0.25})
        self.fill(["n-1"], [True] * 3, [True] * 3, cand_cost=0.07)        # 30% cheaper
        d = self.decide("noticed-row")
        self.assertEqual((d["recommendation"], d["cell"]), ("MOVE_TO", "cheap"))

    def test_materiality_does_not_apply_when_the_baseline_fails_its_row(self):
        self.edit_harness(decision={"noticed_extra_misses": 1, "confirmation_tasks_min": 2,
                                    "min_saving_fraction": 0.25})
        self.fill(["n-1"], [False] * 3, [True] * 3, cand_cost=0.095)      # only 5% cheaper
        d = self.decide("noticed-row")
        self.assertEqual((d["recommendation"], d["cell"]), ("MOVE_TO", "cheap"))

    def test_tie_on_measured_cost_keeps_baseline(self):
        self.fill(["n-1"], [True] * 3, [True] * 3, cand_cost=0.10)
        d = self.decide("noticed-row")
        self.assertEqual(d["recommendation"], "KEEP")
        self.assertIn("not cheaper", d["candidates"][0]["reason"])

    def test_cheaper_is_measured_cost_not_list_price(self):
        # "cheap" has the lowest list price in cells.json but burned more money per run
        self.fill(["n-1"], [True] * 3, [True] * 3, cand_cost=0.30)
        d = self.decide("noticed-row")
        self.assertEqual(d["recommendation"], "KEEP")
        self.assertIn("$0.3000 vs baseline $0.1000", d["candidates"][0]["reason"])

    def test_cheapest_qualifying_candidate_wins(self):
        self.fill(["n-1"], [True] * 3, [True] * 3, cand_cost=0.06)
        self.seed("n-1", "up", [True] * 3, cost=0.04)
        self.assertEqual(self.decide("noticed-row")["cell"], "up")

    def test_silent_clean_candidate_needs_confirmation_with_exact_missing_runs(self):
        self.fill(["s-1"], [True] * 3, [True] * 3)
        d = self.decide("silent-row")
        self.assertEqual((d["recommendation"], d["cell"]), ("NEEDS_CONFIRMATION", "cheap"))
        want = [{"task": t, "cell": "cheap", "repeat": r} for t in ("s-c1", "s-c2") for r in (1, 2, 3)]
        self.assertEqual(sorted(map(json.dumps, d["missing_runs"])), sorted(map(json.dumps, want)))

    def test_silent_needs_enough_confirmation_tasks_authored(self):
        import shutil
        shutil.rmtree(self.root / "private" / "tasks" / "s-c2")
        self.fill(["s-1", "s-c1"], [True] * 3, [True] * 3)
        d = self.decide("silent-row")
        self.assertEqual(d["recommendation"], "NEEDS_CONFIRMATION")
        self.assertTrue(any("1 more confirmation task" in n for n in d["notes"]))

    def test_silent_confirmed_candidate_moves(self):
        self.fill(["s-1", "s-c1", "s-c2"], [True] * 3, [True] * 3)
        d = self.decide("silent-row")
        self.assertEqual((d["recommendation"], d["cell"]), ("MOVE_TO", "cheap"))

    def test_silent_candidate_failing_confirmation_is_dropped(self):
        self.fill(["s-1", "s-c1"], [True] * 3, [True] * 3)
        self.fill(["s-c2"], [True] * 3, [True, True, False])
        d = self.decide("silent-row")
        self.assertEqual(d["recommendation"], "KEEP")
        self.assertIn("failed 1 confirmation", d["candidates"][0]["reason"])

    def test_silent_one_screening_miss_disqualifies(self):
        self.fill(["s-1"], [True] * 3, [True, True, False])
        d = self.decide("silent-row")
        self.assertEqual(d["recommendation"], "KEEP")
        self.assertIn("silent-damage needs every run", d["candidates"][0]["reason"])

    def test_silent_candidate_needs_confirmation_even_when_the_baseline_missed_a_run(self):
        self.fill(["s-1"], [True, True, False], [True] * 3)
        d = self.decide("silent-row")
        self.assertEqual((d["recommendation"], d["cell"]), ("NEEDS_CONFIRMATION", "cheap"))
        self.assertEqual({(m["cell"], m["task"]) for m in d["missing_runs"]},
                         {("cheap", "s-c1"), ("cheap", "s-c2")})      # the candidate's runs only
        self.assertEqual(len(d["missing_runs"]), 6)

    def test_silent_missed_baseline_candidate_moves_once_it_passes_confirmation(self):
        self.fill(["s-1"], [True, True, False], [True] * 3)
        for t in ("s-c1", "s-c2"):
            self.seed(t, "cheap", [True] * 3, cost=0.05)       # no baseline confirmation runs at all
        d = self.decide("silent-row")
        self.assertEqual((d["recommendation"], d["cell"], d["missing_runs"]), ("MOVE_TO", "cheap", []))

    def test_silent_clean_baseline_needs_no_baseline_confirmation_runs(self):
        self.fill(["s-1"], [True] * 3, [True] * 3)
        for t in ("s-c1", "s-c2"):
            self.seed(t, "cheap", [True] * 3, cost=0.05)
        self.assertEqual(self.decide("silent-row")["recommendation"], "MOVE_TO")

    def test_silent_partial_confirmation_lists_only_the_remaining_candidate_runs(self):
        self.fill(["s-1"], [True] * 3, [True] * 3)
        self.seed("s-c1", "cheap", [True] * 3, cost=0.05)
        self.seed("s-c2", "cheap", [True, True], cost=0.05)
        d = self.decide("silent-row")
        self.assertEqual(d["recommendation"], "NEEDS_CONFIRMATION")
        self.assertEqual(d["missing_runs"], [{"task": "s-c2", "cell": "cheap", "repeat": 3}])

    def test_silent_one_failed_confirmation_run_is_final_even_if_others_are_missing(self):
        self.fill(["s-1"], [True] * 3, [True] * 3)
        self.seed("s-c1", "cheap", [True, False, True], cost=0.05)
        d = self.decide("silent-row")
        self.assertEqual(d["recommendation"], "KEEP")
        self.assertIn("failed 1 confirmation", d["candidates"][0]["reason"])

    def test_silent_failed_baseline_candidate_still_needs_confirmation(self):
        self.fill(["s-1"], [False, False, False], [True] * 3)
        d = self.decide("silent-row")
        self.assertEqual((d["recommendation"], d["cell"]), ("NEEDS_CONFIRMATION", "cheap"))
        for t in ("s-c1", "s-c2"):
            self.seed(t, "cheap", [True] * 3, cost=0.05)
        self.assertEqual(self.decide("silent-row")["recommendation"], "MOVE_TO")

    def test_silent_failed_baseline_and_failed_confirmation_falls_back_to_the_up_cell(self):
        self.fill(["s-1"], [False, True, True], [True] * 3)
        self.seed("s-1", "up", [True] * 3, cost=0.30)
        self.seed("s-c1", "cheap", [True, True, False], cost=0.05)
        d = self.decide("silent-row")
        self.assertEqual((d["recommendation"], d["cell"]), ("BASELINE_FAILS", "up"))

    def test_baseline_fails_names_cheapest_passing_up_cell(self):
        self.fill(["s-1"], [True, False, False], [True, False, False], cand_cost=0.20)
        self.seed("s-1", "up", [True] * 3, cost=0.30)
        d = self.decide("silent-row")
        self.assertEqual((d["recommendation"], d["cell"]), ("BASELINE_FAILS", "up"))

    def test_baseline_fails_and_no_up_cell_passes(self):
        self.fill(["s-1"], [False] * 3, [False] * 3, cand_cost=0.20)
        self.seed("s-1", "up", [True, False, True], cost=0.30)
        d = self.decide("silent-row")
        self.assertEqual((d["recommendation"], d["cell"]), ("BASELINE_FAILS", None))

    def test_incomplete_data_is_insufficient(self):
        self.seed("s-1", "base", [True, True])               # two of three baseline runs
        d = self.decide("silent-row")
        self.assertEqual(d["recommendation"], "INSUFFICIENT_DATA")
        self.assertEqual([m["repeat"] for m in d["missing_runs"]], [3])
        self.seed("s-1", "base", [True] * 3)
        self.assertEqual(self.decide("silent-row")["recommendation"], "INSUFFICIENT_DATA")  # no candidates yet

    def test_ungraded_baseline_run_is_insufficient_data(self):
        self.seed("n-1", "base", [True, True, None], cost=0.10)
        self.seed("n-1", "cheap", [True] * 3, cost=0.05)
        d = self.decide("noticed-row")
        self.assertEqual(d["recommendation"], "INSUFFICIENT_DATA")
        self.assertEqual(d["missing_runs"], [{"task": "n-1", "cell": "base", "repeat": 3, "ungraded": True}])
        self.assertTrue(any("ungraded" in n for n in d["notes"]))

    def test_ungraded_candidate_run_makes_the_row_insufficient_even_if_another_candidate_is_complete(self):
        self.seed("n-1", "base", [True] * 3, cost=0.10)
        self.seed("n-1", "cheap", [True, None, None], cost=0.05)       # would qualify if it were graded
        d = self.decide("noticed-row")
        self.assertEqual(d["recommendation"], "INSUFFICIENT_DATA")
        self.assertIn("incomplete", d["candidates"][0]["reason"])
        self.assertEqual([m["repeat"] for m in d["missing_runs"]], [2, 3])
        self.seed("n-1", "up", [True] * 3, cost=0.07)                   # a complete, cheaper-than-base cell
        d = self.decide("noticed-row")                                  # must not let the fault decide the row
        self.assertEqual((d["recommendation"], d["cell"]), ("INSUFFICIENT_DATA", None))
        self.assertTrue(all(m["ungraded"] for m in d["missing_runs"]))

    def test_a_run_that_was_never_made_is_missing_not_ungraded(self):
        self.seed("n-1", "base", [True] * 3, cost=0.10)
        self.seed("n-1", "cheap", [True, True], cost=0.05)              # third run never executed
        self.seed("n-1", "up", [True] * 3, cost=0.07)
        d = self.decide("noticed-row")
        self.assertEqual((d["recommendation"], d["cell"]), ("MOVE_TO", "up"))   # README: a complete candidate decides

    def test_ungraded_confirmation_run_makes_the_row_insufficient(self):
        self.fill(["s-1"], [True] * 3, [True] * 3)
        self.seed("s-c1", "cheap", [True] * 3, cost=0.05)
        self.seed("s-c2", "cheap", [True, True, None], cost=0.05)
        d = self.decide("silent-row")
        self.assertEqual((d["recommendation"], d["missing_runs"]),
                         ("INSUFFICIENT_DATA", [{"task": "s-c2", "cell": "cheap", "repeat": 3, "ungraded": True}]))
        self.assertTrue(any("ungraded" in n for n in d["notes"]))

    def test_decide_text_output_lists_reasons(self):
        self.fill(["n-1"], [True] * 3, [True] * 3, cand_cost=0.10)
        out = self.cli("decide").stdout
        self.assertIn("noticed-row", out)
        self.assertIn("KEEP", out)
        self.assertIn("not cheaper", out)


class SelfCheck(EvalTestCase):
    def test_clean_tasks_pass(self):
        r = self.cli("selfcheck")
        self.assertIn("5 task(s), 0 problem(s)", r.stdout)

    def test_bad_grader_is_caught(self):
        write(self.root / "private" / "tasks" / "n-1" / "grader.py", GRADER_BAD)
        r = self.cli("selfcheck", check=False)
        self.assertEqual(r.returncode, 1)
        self.assertIn("perfect.txt scored 0.0", r.stdout)

    def test_grader_that_passes_a_flawed_fixture_is_caught(self):
        write(self.root / "private" / "tasks" / "n-1" / "grader.py",
              'def grade(a, t):\n    return {"score": 1.0, "passed": True, "details": {}}\n')
        r = self.cli("selfcheck", check=False)
        self.assertIn("flawed_a.txt passed but is flawed", r.stdout)

    def test_planted_fake_secret_is_caught(self):
        write(self.root / "private" / "tasks" / "n-1" / "material" / "notes.txt",
              "token = sk-ant-api03-" + "FAKEFAKEFAKE" * 3 + "\n")
        r = self.cli("selfcheck", check=False)
        self.assertEqual(r.returncode, 1)
        self.assertIn("notes.txt matches secret pattern", r.stdout)

    def test_env_file_and_private_key_are_caught(self):
        write(self.root / "private" / "tasks" / "n-1" / "material" / ".env.local", "A=1\n")
        write(self.root / "private" / "tasks" / "s-1" / "material" / "k.pem", "-----BEGIN RSA PRIVATE KEY-----\n")
        out = self.cli("selfcheck", check=False).stdout
        self.assertIn(".env.local is an env file", out)
        self.assertIn("k.pem matches secret pattern", out)

    def test_missing_task_fields_are_caught(self):
        write(self.root / "private" / "tasks" / "n-1" / "task.json", '{"id": "n-1"}')
        out = self.cli("selfcheck", check=False).stdout
        self.assertIn("missing fields", out)


class GraderSafety(EvalTestCase):
    def grader(self, code, task="n-1"):
        write(self.root / "private" / "tasks" / task / "grader.py", code)

    def grade_directly(self, answer="42", timeout=None):
        ctx = self.ctx()
        task = ev.load_tasks(ctx)["n-1"]
        old = ev.GRADER_TIMEOUT_S
        ev.GRADER_TIMEOUT_S = timeout or old
        err = io.StringIO()
        try:
            with contextlib.redirect_stderr(err):
                graded = ev.grade_code(ctx, task, "rid1", answer)
        finally:
            ev.GRADER_TIMEOUT_S = old
        return graded, err.getvalue()

    def cli_fast(self, *args, timeout=1, **env):
        """Run evalkit with the grader timeout cut to `timeout` s (the real default is 30)."""
        code = ("import sys, evalkit; evalkit.GRADER_TIMEOUT_S = %r; sys.exit(evalkit.main(sys.argv[1:]))"
                % timeout)
        e = dict(os.environ, AGENTING_EVALS_DIR=str(self.root), FAKE_CLAUDE_MODE="ok",
                 FAKE_CLAUDE_LOG=str(self.log), PYTHONPATH=str(EVALS))
        e.update({k: str(v) for k, v in env.items()})
        r = subprocess.run([sys.executable, "-c", code, *args], capture_output=True, text=True,
                           timeout=60, env=e)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r

    def test_default_timeout_is_thirty_seconds(self):
        self.assertEqual(ev.GRADER_TIMEOUT_S, 30)

    def test_grader_runs_in_a_child_process(self):
        self.grader('import os\ndef grade(a, t):\n    return {"score": 1.0, "passed": True, "details": {"pid": os.getpid()}}\n')
        self.assertTrue(self.grade_directly()[0])
        (s,) = self.scores()
        self.assertNotEqual(s["details"]["pid"], os.getpid())
        self.assertEqual((s["run_id"], s["score"], s["passed"]), ("rid1", 1.0, True))

    def test_grader_that_prints_does_not_corrupt_the_result(self):
        self.grader('import sys\ndef grade(a, t):\n    print("noise"); sys.stdout.write("@@RESULT@@x\\n")\n'
                    '    return {"score": 0.5, "passed": False, "details": {}}\n')
        self.assertTrue(self.grade_directly()[0])
        self.assertEqual([s["score"] for s in self.scores()], [0.5])

    def test_hanging_grader_times_out_and_leaves_the_run_ungraded(self):
        self.grader(GRADER_HANGS)
        t0 = time.time()
        graded, err = self.grade_directly(timeout=1)
        self.assertLess(time.time() - t0, 15)
        self.assertFalse(graded)
        self.assertEqual(self.scores(), [])
        self.assertIn("warning", err)
        self.assertIn("exceeded 1 s", err)

    def test_raising_grader_leaves_the_run_ungraded(self):
        self.grader(GRADER_RAISES)
        graded, err = self.grade_directly()
        self.assertFalse(graded)
        self.assertEqual(self.scores(), [])
        self.assertIn("grader bug", err)

    def test_invalid_return_values_leave_the_run_ungraded(self):
        for body in ('return "pass"', 'return {"score": 0.5}', 'return {"score": 2.0, "passed": True}',
                     'return {"score": "high", "passed": True}', 'return {"score": float("nan"), "passed": True}',
                     'return {"score": 1.0, "passed": "yes"}', 'return {"score": True, "passed": True}',
                     'return {"score": 1.0, "passed": True, "details": "x"}', 'return {"score": 1.0, "passed": True, "details": {"s": {1, 2}}}',
                     'return None'):
            self.grader(f"def grade(a, t):\n    {body}\n")
            self.assertFalse(self.grade_directly()[0], body)
        self.assertEqual(self.scores(), [])

    def test_grader_reporting_its_own_error_is_a_fault_not_a_zero(self):
        self.grader('def grade(a, t):\n    return {"score": 0.0, "passed": False, "details": {"error": "bad_truth:KeyError"}}\n')
        graded, err = self.grade_directly()
        self.assertFalse(graded)
        self.assertEqual(self.scores(), [])
        self.assertIn("internal error", err)

    def test_grader_without_the_function_is_a_fault(self):
        self.grader("x = 1\n")
        self.assertFalse(self.grade_directly()[0])

    def test_missing_answer_block_is_still_a_scored_failure(self):
        self.grader(GRADER_RAISES)                     # never consulted without a block
        self.assertTrue(self.grade_directly(answer=None)[0])
        self.assertEqual([(s["score"], s["passed"]) for s in self.scores()], [(0.0, False)])

    def test_run_with_a_raising_grader_stays_ungraded_end_to_end(self):
        self.grader(GRADER_RAISES)
        r = self.cli("run", "--rows", "noticed-row", "--cells", "base", "--repeats", "3")
        self.assertEqual(len(self.runs()), 3)
        self.assertTrue(all(x["valid"] for x in self.runs()))
        self.assertEqual(self.scores(), [])
        self.assertIn("UNGRADED", r.stdout)
        self.assertIn("left ungraded", r.stderr)
        self.assertRegex(self.cli("status").stdout, r"noticed-row\s+1/1\s+3\s+3\s+0\s+0\s+3")
        self.assertIn("3 ungraded run(s) excluded", self.cli("report", "--rows", "noticed-row").stdout)
        self.assertEqual(self.decide("noticed-row")["recommendation"], "INSUFFICIENT_DATA")

    def test_hanging_grader_end_to_end_and_regrade_after_a_fix(self):
        self.grader(GRADER_HANGS)
        self.cli_fast("run", "--rows", "noticed-row", "--cells", "base", "--repeats", "1", timeout=1)
        self.assertEqual((len(self.runs()), self.scores()), (1, []))
        self.grader(GRADER_CODE)                       # fix the grader, then grade stored answers: no model call
        self.log.unlink()
        out = self.cli("grade").stdout
        self.assertIn("graded 1 run(s)", out)
        self.assertEqual(self.calls(), [])
        self.assertEqual(len(self.runs()), 1)
        self.assertEqual([s["passed"] for s in self.scores()], [True])

    def test_grade_command_reports_runs_that_stay_ungraded(self):
        self.cli("run", "--rows", "noticed-row", "--cells", "base", "--repeats", "1")
        self.grader(GRADER_RAISES)
        out = self.cli("grade").stdout
        self.assertIn("graded 0 run(s); 1 left ungraded", out)
        self.assertEqual(len(self.scores()), 1)        # only the original, under the old grader id

    def test_selfcheck_reports_a_crashing_grader_instead_of_dying(self):
        self.grader(GRADER_RAISES)
        r = self.cli("selfcheck", check=False)
        self.assertEqual(r.returncode, 1)
        self.assertIn("grader failed on fixtures", r.stdout)


class SelfCheckExtras(EvalTestCase):
    def test_judge_grader_may_reject_a_malformed_flawed_fixture(self):
        d = self.root / "private" / "tasks" / "j-1"
        write(d / "grader.py", GRADER_JUDGE.replace(
            "    s = float", '    if "score" not in judgment:\n        return {"score": 0.0, "passed": False, "details": {"error": "no score"}}\n    s = float'))
        write(d / "fixtures" / "judgment_flawed_malformed.json", "{}")
        self.assertIn("0 problem(s)", self.cli("selfcheck").stdout)

    def test_code_grader_rejecting_a_flawed_fixture_is_still_a_problem(self):
        write(self.root / "private" / "tasks" / "n-1" / "grader.py", GRADER_CODE.replace(
            "ok = answer", 'if answer.strip() == "41":\n        return {"score": 0.0, "passed": False, "details": {"error": "x"}}\n    ok = answer'))
        r = self.cli("selfcheck", check=False)
        self.assertEqual(r.returncode, 1)
        self.assertIn("grader failed on fixtures", r.stdout)

    def test_ok_fixture_that_fails_is_caught(self):
        d = self.root / "private" / "tasks" / "n-1" / "fixtures"
        write(d / "ok_a.txt", "  42  ")
        self.assertIn("0 problem(s)", self.cli("selfcheck").stdout)
        write(d / "ok_b.txt", "41")
        r = self.cli("selfcheck", check=False)
        self.assertEqual(r.returncode, 1)
        self.assertIn("n-1: ok_b.txt is an ok fixture but did not pass", r.stdout)
        self.assertNotIn("ok_a.txt", r.stdout)

    def test_judge_ok_fixtures_are_checked(self):
        d = self.root / "private" / "tasks" / "j-1" / "fixtures"
        write(d / "ok_a.json", '{"score": 0.8}')
        self.assertIn("0 problem(s)", self.cli("selfcheck").stdout)
        write(d / "ok_b.json", '{"score": 0.3}')
        self.assertIn("j-1: ok_b.json is an ok fixture but did not pass", self.cli("selfcheck", check=False).stdout)

    def test_pass_threshold_must_match_truth_when_truth_has_one(self):
        truth = self.root / "private" / "tasks" / "n-1" / "truth.json"
        write(truth, json.dumps({"answer": 42}))                     # no key: nothing to compare
        self.assertIn("0 problem(s)", self.cli("selfcheck").stdout)
        write(truth, json.dumps({"answer": 42, "pass_threshold": 0.7}))
        self.assertIn("0 problem(s)", self.cli("selfcheck").stdout)
        write(truth, json.dumps({"answer": 42, "pass_threshold": 0.9}))
        r = self.cli("selfcheck", check=False)
        self.assertEqual(r.returncode, 1)
        self.assertIn("n-1: task.json pass_threshold 0.7 != truth.json pass_threshold 0.9", r.stdout)


class Provisional(EvalTestCase):
    """Item 1: a recommendation resting on an incomplete candidate is provisional."""

    def invalid_line(self, task_id, cell_id, repeat):
        ctx = self.ctx()
        task = ev.load_tasks(ctx)[task_id]
        ev.append_jsonl(ctx.runs_path, {
            "run_id": ev.run_id_for(ctx, task, cell_id, repeat), "task_id": task_id, "cell_id": cell_id,
            "repeat": repeat, "valid": False, "invalid_reason": "timeout", "cost_usd": None,
            "cost_unknown": True})

    def test_missing_candidate_runs_make_the_recommendation_provisional(self):
        self.seed("n-1", "base", [True] * 3, cost=0.10)
        self.seed("n-1", "cheap", [True] * 3, cost=0.04)
        self.seed("n-1", "up", [True, True], cost=0.20)                 # one run never made
        d = self.decide("noticed-row")
        self.assertEqual((d["recommendation"], d["cell"], d["provisional"]), ("MOVE_TO", "cheap", True))
        self.assertIn("provisional: candidate up has 1 missing run(s)", d["notes"])
        out = self.cli("decide").stdout
        self.assertRegex(out, r"noticed-row .*: MOVE_TO cheap \(provisional\)")

    def test_unmeasured_candidate_is_provisional_too(self):
        self.seed("n-1", "base", [True] * 3, cost=0.10)
        self.seed("n-1", "cheap", [True] * 3, cost=0.04)                # up has no runs at all
        d = self.decide("noticed-row")
        self.assertEqual((d["recommendation"], d["provisional"]), ("MOVE_TO", True))
        self.assertIn("provisional: candidate up has 3 missing run(s)", d["notes"])

    def test_complete_grid_is_not_provisional(self):
        for cell, cost in (("base", 0.10), ("cheap", 0.04), ("up", 0.20)):
            self.seed("n-1", cell, [True] * 3, cost=cost)
        d = self.decide("noticed-row")
        self.assertEqual((d["recommendation"], d["cell"], d["provisional"]), ("MOVE_TO", "cheap", False))
        self.assertFalse(any("provisional" in n for n in d["notes"]))
        self.assertNotIn("(provisional)", self.cli("decide").stdout.split("silent-row")[0])

    def test_every_result_carries_the_provisional_flag(self):
        for d in json.loads(self.cli("decide", "--json").stdout):
            self.assertIs(d["provisional"], False)                      # no data at all: nothing to qualify

    def test_exhausted_candidate_runs_are_listed_in_the_notes(self):
        self.seed("n-1", "base", [True] * 3, cost=0.10)
        self.seed("n-1", "cheap", [True] * 3, cost=0.04)
        self.seed("n-1", "up", [True, True], cost=0.20)
        for _ in range(3):                                              # initial attempt + 2 retries, all invalid
            self.invalid_line("n-1", "up", 3)
        d = self.decide("noticed-row")
        self.assertTrue(any("candidate up: run n-1 #3 exhausted its retries (3 invalid attempts)" in n
                            for n in d["notes"]), d["notes"])
        self.assertTrue(d["provisional"])
        self.assertEqual(next(c for c in d["candidates"] if c["cell"] == "up")["exhausted"], 1)
        self.assertIn("never complete", self.cli("decide").stdout)

    def test_a_run_still_retryable_is_not_listed_as_exhausted(self):
        self.seed("n-1", "base", [True] * 3, cost=0.10)
        self.seed("n-1", "cheap", [True] * 3, cost=0.04)
        self.seed("n-1", "up", [True, True], cost=0.20)
        for _ in range(2):                                              # plan would still retry this one
            self.invalid_line("n-1", "up", 3)
        d = self.decide("noticed-row")
        self.assertFalse(any("exhausted" in n for n in d["notes"]))


class ReportPhases(EvalTestCase):
    """Item 2: report separates screening from confirmation and says which tasks it covers."""

    def rows_of(self, out):
        return {ln.split()[0]: ln.split() for ln in out.splitlines()
                if ln.split()[:1] in (["base"], ["cheap"], ["up"])}

    def setUp(self):
        super().setUp()
        self.seed("s-1", "base", [True] * 3, cost=0.10)
        self.seed("s-c1", "base", [True] * 3, cost=0.50)
        self.seed("s-c2", "base", [True] * 3, cost=0.50)

    def test_default_phase_is_screening_only(self):
        out = self.cli("report", "--rows", "silent-row").stdout
        self.assertIn("phase: screening; tasks: s-1", out)
        base = self.rows_of(out)["base"]
        self.assertEqual((base[2:5], base[7], base[9]), (["3", "3", "3"], "$0.1000", "1"))

    def test_confirmation_phase_and_tasks_column(self):
        out = self.cli("report", "--rows", "silent-row", "--phase", "confirmation").stdout
        self.assertIn("phase: confirmation; tasks: s-c1, s-c2", out)
        base = self.rows_of(out)["base"]
        self.assertEqual((base[2], base[7], base[9]), ("6", "$0.5000", "2"))
        self.assertNotIn("warning", out)

    def test_all_phase_mixes_and_warns_once(self):
        out = self.cli("report", "--phase", "all").stdout
        self.assertEqual(out.count("cells may cover different task sets"), 1)
        self.assertEqual(out.splitlines()[0].split(":")[0], "warning")
        self.assertIn("phase: all; tasks: s-1, s-c1, s-c2", out)
        silent = out[out.index("silent-row"):out.index("judge-row")]
        base = self.rows_of(silent)["base"]
        self.assertEqual((base[2], base[9]), ("9", "3"))

    def test_report_header_names_none_when_a_phase_has_no_tasks(self):
        out = self.cli("report", "--rows", "noticed-row", "--phase", "confirmation").stdout
        self.assertIn("phase: confirmation; tasks: none", out)


class Concurrency(EvalTestCase):
    """Item 3: one writer at a time, private work directories, no second valid line."""

    @contextlib.contextmanager
    def lock_held(self):
        path = self.root / "results" / ".evalkit.lock"
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
        fcntl.flock(fd, fcntl.LOCK_EX)
        try:
            yield
        finally:
            os.close(fd)

    def test_writers_refuse_while_the_lock_is_held_and_do_nothing(self):
        self.seed("n-1", "base", [True])
        before = (self.runs(), self.scores())
        with self.lock_held():
            for args in (("run", "--rows", "noticed-row"), ("judge",), ("grade",), ("sanitize",)):
                r = self.cli(*args, check=False)
                self.assertEqual(r.returncode, 2, args)
                self.assertIn("already writing results", r.stderr)
        self.assertEqual((self.calls(), self.runs(), self.scores()), ([], before[0], before[1]))

    def test_read_only_commands_and_dry_run_do_not_lock(self):
        with self.lock_held():
            for args in (("status",), ("plan",), ("report",), ("decide",), ("selfcheck",),
                         ("run", "--rows", "noticed-row", "--dry-run")):
                self.cli(*args)

    def test_lock_is_released_when_the_invocation_ends(self):
        self.cli("run", "--rows", "noticed-row", "--cells", "base", "--repeats", "1")
        self.assertTrue((self.root / "results" / ".evalkit.lock").exists())
        self.cli("run", "--rows", "noticed-row", "--cells", "cheap", "--repeats", "1")   # not refused
        self.cli("sanitize")

    def test_a_second_live_invocation_is_refused(self):
        env = dict(os.environ, AGENTING_EVALS_DIR=str(self.root), FAKE_CLAUDE_MODE="timeout",
                   FAKE_CLAUDE_LOG=str(self.log))
        first = subprocess.Popen([sys.executable, str(EVALKIT), "run", "--rows", "noticed-row",
                                  "--cells", "base", "--repeats", "1", "--jobs", "1"],
                                 env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            for _ in range(100):
                if self.calls():
                    break
                time.sleep(0.1)
            self.assertEqual(len(self.calls()), 1)
            second = self.cli("run", "--rows", "noticed-row", "--cells", "cheap", "--repeats", "1", check=False)
            self.assertEqual(second.returncode, 2)
            self.assertIn("already writing results", second.stderr)
            self.assertEqual(len(self.calls()), 1)                       # the loser launched nothing
        finally:
            first.send_signal(signal.SIGINT)
            first.communicate(timeout=20)

    def test_every_run_gets_its_own_work_directory(self):
        ctx, task = self.ctx(), ev.load_tasks(self.ctx())["n-1"]
        a = ev.prepare_workdir(ctx, task, "abc123")
        b = ev.prepare_workdir(ctx, task, "abc123")
        self.assertNotEqual(a, b)
        self.assertTrue(a.name.startswith("abc123") and b.name.startswith("abc123"))
        self.assertEqual(a.parent, ctx.work_dir)
        self.assertEqual((a / "data.txt").read_text(), "forty two\n")
        import shutil
        shutil.rmtree(a)                                                 # one run cleaning up...
        self.assertEqual((b / "data.txt").read_text(), "forty two\n")    # ...never touches the other

    def test_a_second_valid_line_for_a_run_id_is_never_appended(self):
        self.seed("n-1", "cheap", [True])
        ctx, task = self.ctx(), ev.load_tasks(self.ctx())["n-1"]
        rid = ev.run_id_for(ctx, task, "cheap", 1)
        item = {"run_id": rid, "row": "noticed-row", "task": "n-1", "cell": "cheap", "repeat": 1}
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            rec, graded, duplicate = ev.execute_one(ctx, task, item, ev.Budget(None, 1.0), ev.Stop())
        self.assertTrue(rec["valid"] and duplicate)
        self.assertIn("already has a valid line", err.getvalue())
        self.assertEqual([r["run_id"] for r in self.runs()], [rid])      # still the one seeded line
        self.assertEqual(len(self.scores()), 1)                          # no second score either
        self.assertFalse((self.root / "private" / "answers" / f"{rid}.json").exists())
        self.assertEqual(os.listdir(self.root / "private" / "work"), [])

    def test_plan_still_skips_a_valid_run(self):
        self.seed("n-1", "cheap", [True])
        p = json.loads(self.cli("plan", "--json", "--rows", "noticed-row", "--cells", "cheap",
                                "--repeats", "1").stdout)
        self.assertEqual(p["items"], [])


class CostAccounting(EvalTestCase):
    """Item 4: unknown cost is null, flagged, charged at the cap, never treated as free."""

    FINISHED = json.dumps({
        "type": "result", "is_error": False, "result": "===ANSWER===\n42\n===END===",
        "total_cost_usd": 0.02, "duration_ms": 5, "num_turns": 1,
        "usage": {"input_tokens": 1, "output_tokens": 4, "output_tokens_details": {"thinking_tokens": 2}},
        "modelUsage": {"claude-test-cheap": {}}})

    def item(self):
        ctx, task = self.ctx(), ev.load_tasks(self.ctx())["n-1"]
        rid = ev.run_id_for(ctx, task, "cheap", 1)
        return ctx, task, {"run_id": rid, "row": "noticed-row", "task": "n-1", "cell": "cheap", "repeat": 1}

    def test_unparseable_output_logs_null_cost_and_charges_the_cap(self):
        r = self.cli("run", "--rows", "noticed-row", "--max-usd", "1.5", "--jobs", "1", mode="bad_json")
        runs = self.runs()
        self.assertEqual(len(runs), 2)                      # cap 1 per run: 1.0 < 1.5, 2.0 >= 1.5 stops
        for rec in runs:
            self.assertIs(rec["cost_usd"], None)
            self.assertIs(rec["cost_unknown"], True)
            self.assertFalse(rec["valid"])
        self.assertIn("cost unknown", r.stdout)
        self.assertIn("spent $2.0000 of $1.5 (2 run(s) with unknown cost", r.stdout)

    def test_a_timeout_logs_null_cost(self):
        self.edit_harness(runner={**harness("x")["runner"], "timeout_s": 1,
                                  "claude_bin": f"{shlex.quote(sys.executable)} {shlex.quote(str(FAKE))}"})
        self.cli("run", "--rows", "noticed-row", "--cells", "cheap", "--repeats", "1", mode="timeout")
        (r,) = self.runs()
        self.assertEqual((r["invalid_reason"], r["cost_usd"], r["cost_unknown"]), ("timeout", None, True))

    def test_a_known_cost_stays_a_number_without_the_flag(self):
        self.cli("run", "--rows", "noticed-row", "--cells", "cheap", "--repeats", "1", mode="error")
        (r,) = self.runs()
        self.assertEqual((r["valid"], r["cost_usd"]), (False, 0.0))      # the CLI reported $0: that is known
        self.assertNotIn("cost_unknown", r)

    def test_status_sums_known_costs_and_counts_unknown_runs(self):
        self.seed("n-1", "base", [True, True], cost=0.5)
        self.seed("n-1", "cheap", [True], cost=None)
        out = self.cli("status").stdout
        self.assertIn("total cost so far: $1.0000", out)
        self.assertIn("1 run(s) with unknown cost", out)

    def test_status_without_unknown_costs_prints_no_unknown_line(self):
        self.seed("n-1", "base", [True], cost=0.5)
        self.assertNotIn("unknown cost", self.cli("status").stdout)

    def test_unknown_cost_is_not_free_in_report_or_decide(self):
        self.seed("n-1", "base", [True] * 3, cost=0.10)
        self.seed("n-1", "cheap", [True] * 3, cost=None)
        rep = self.cli("report", "--rows", "noticed-row").stdout
        cheap = next(ln.split() for ln in rep.splitlines() if ln.startswith("cheap"))
        self.assertEqual(cheap[7], "$n/a")
        d = self.decide("noticed-row")
        self.assertNotEqual(d["recommendation"], "MOVE_TO")
        self.assertIn("cost unknown for 3 run(s)", next(c for c in d["candidates"] if c["cell"] == "cheap")["reason"])

    def test_a_run_that_finishes_as_ctrl_c_lands_is_still_logged(self):
        ctx, task, item = self.item()
        stop = ev.Stop()

        def finishes_then_stop(ctx_, cell, prompt, cwd, tools, system_prompt, stop_):
            stop_.event.set()                               # Ctrl-C arrives while the process exits
            return {"stdout": self.FINISHED, "returncode": 0, "timeout": False, "error": None}

        with mock.patch.object(ev, "call_claude", finishes_then_stop):
            done = ev.execute_one(ctx, task, item, ev.Budget(None, 1.0), stop)
        self.assertIsNotNone(done)
        (r,) = self.runs()
        self.assertTrue(r["valid"])
        self.assertEqual([s["passed"] for s in self.scores()], [True])
        self.assertTrue((self.root / "private" / "answers" / f"{item['run_id']}.json").exists())

    def test_a_run_killed_by_the_stop_is_not_logged(self):
        ctx, task, item = self.item()
        stop = ev.Stop()

        def killed(ctx_, cell, prompt, cwd, tools, system_prompt, stop_):
            stop_.event.set()
            return {"stdout": "", "returncode": -9, "timeout": False, "error": None}

        with mock.patch.object(ev, "call_claude", killed):
            self.assertIsNone(ev.execute_one(ctx, task, item, ev.Budget(None, 1.0), stop))
        self.assertEqual((self.runs(), self.scores()), ([], []))

    def test_budget_charges_the_cap_for_unknown_cost(self):
        b = ev.Budget(10.0, 6.0)
        b.add(0.25)
        b.add(None)
        self.assertEqual((b.spent, b.unknown), (6.25, 1))


class CliVersion(EvalTestCase):
    """Item 5: the Claude CLI version is recorded, and is never part of an id."""

    def test_runs_record_the_version_and_it_is_fetched_once_per_invocation(self):
        vlog = Path(self._tmp.name) / "version.log"
        self.cli("run", "--rows", "noticed-row", "--cells", "cheap", FAKE_CLAUDE_VERSION_LOG=vlog)
        self.assertEqual(vlog.read_text().count("version"), 1)           # 3 runs, one --version call
        self.assertEqual({r["cli_version"] for r in self.runs()}, {"9.9.9 (Fake)"})
        self.assertEqual(len(self.runs()), 3)
        self.assertEqual(len(self.calls()), 3)                           # --version is not a model call

    def test_invalid_runs_carry_the_version_too(self):
        self.cli("run", "--rows", "noticed-row", "--cells", "cheap", "--repeats", "1", mode="error")
        self.assertEqual([r["cli_version"] for r in self.runs()], ["9.9.9 (Fake)"])

    def test_version_does_not_change_run_id_or_cell_hash(self):
        self.cli("run", "--rows", "noticed-row", "--cells", "cheap", "--repeats", "1")
        ctx, task = self.ctx(), ev.load_tasks(self.ctx())["n-1"]
        (r,) = self.runs()
        self.assertEqual((r["run_id"], r["cell_hash"]), (ev.run_id_for(ctx, task, "cheap", 1), ctx.cell_hash("cheap")))
        self.cli("run", "--rows", "noticed-row", "--cells", "cheap", "--repeats", "2", FAKE_CLAUDE_VERSION="10.0.0")
        self.assertEqual([x["cli_version"] for x in self.runs()], ["9.9.9 (Fake)", "10.0.0"])
        plan = json.loads(self.cli("plan", "--json", "--rows", "noticed-row", "--cells", "cheap",
                                   "--repeats", "2", FAKE_CLAUDE_VERSION="11.0.0").stdout)
        self.assertEqual(plan["items"], [])                              # a new CLI version re-plans nothing

    def test_judge_scores_carry_the_version(self):
        self.cli("run", "--tasks", "j-1", "--cells", "cheap", "--repeats", "1")
        self.cli("judge", FAKE_CLAUDE_ANSWER=Judging.JUDGMENT)
        judged = self.scores()
        self.assertEqual(len(judged), 2)
        self.assertEqual({s["details"]["cli_version"] for s in judged}, {"9.9.9 (Fake)"})

    def test_dry_run_and_empty_plan_do_not_ask_for_the_version(self):
        vlog = Path(self._tmp.name) / "version.log"
        self.cli("run", "--rows", "noticed-row", "--dry-run", FAKE_CLAUDE_VERSION_LOG=vlog)
        self.assertFalse(vlog.exists())

    def test_a_long_version_string_is_capped_for_the_public_record(self):
        self.cli("run", "--rows", "noticed-row", "--cells", "cheap", "--repeats", "1",
                 FAKE_CLAUDE_VERSION="1.2.3 " + "x" * 80)
        (r,) = self.runs()
        self.assertEqual(len(r["cli_version"]), 40)


class PublicDetails(EvalTestCase):
    """Item 6: scores.jsonl never carries per-item structure."""

    def test_score_line_keeps_only_short_scalars(self):
        res = {"score": 1.0, "passed": True, "details": {
            "n": 3, "ratio": 0.5, "ok": True, "label": "x" * 40, "long": "x" * 41, "nothing": None,
            "nan": float("nan"), "inf": float("inf"), "per_q": {"q1": True}, "ids": ["q2"], "t": (1, 2)}}
        line = ev.score_line("r", "code:x", res, {"extra": 1, "extra_map": {"a": 1}})
        self.assertEqual(line["details"], {"n": 3, "ratio": 0.5, "ok": True, "label": "x" * 40, "extra": 1})

    def test_code_grader_details_are_reduced_end_to_end(self):
        write(self.root / "private" / "tasks" / "n-1" / "grader.py", GRADER_STRUCT)
        self.cli("run", "--rows", "noticed-row", "--cells", "base", "--repeats", "1")
        (s,) = self.scores()
        self.assertEqual(s["details"], {"checked": 1, "exact": True, "ratio": 0.5, "label": "short"})
        write(self.root / "private" / "tasks" / "n-1" / "grader.py", GRADER_STRUCT + "# regrade\n")
        self.cli("grade")                                    # a changed grader appends through score_line too
        regraded = self.scores()[1:]
        self.assertEqual(len(regraded), 1)
        self.assertEqual(regraded[0]["details"], s["details"])
        self.assertNotIn("q7", (self.root / "results" / "scores.jsonl").read_text())

    def test_judge_details_are_reduced_end_to_end(self):
        write(self.root / "private" / "tasks" / "j-1" / "grader.py", GRADER_JUDGE_STRUCT)
        self.cli("run", "--tasks", "j-1", "--cells", "cheap", "--repeats", "1")
        self.cli("judge", FAKE_CLAUDE_ANSWER=Judging.JUDGMENT)
        for s in self.scores():
            self.assertTrue(all(isinstance(v, (int, float, bool, str)) for v in s["details"].values()), s)
            self.assertEqual(s["details"]["points"], 2)
            self.assertIn("judge_cost_usd", s["details"])
        self.assertNotIn("verdicts", (self.root / "results" / "scores.jsonl").read_text())

    def leaky_scores(self):
        clean = ('{"run_id": "b", "grader_id": "code:x", "score": 1.0, "passed": true, '
                 '"details": {"a": 1, "u": " "}, "ts": "t"}')
        leaky = ('{"run_id":"a","grader_id":"code:x","score":0.5,"passed":false,"details":{"checked":1,'
                 '"per_q":{"q1":true,"q7":false},"ids":["q2"],"long":"%s","ok":"short","none":null},"ts":"t"}'
                 % ("x" * 41))
        as_list = '{"run_id":"c","grader_id":"code:x","score":0,"passed":false,"details":["q7"],"ts":"t"}'
        return [leaky, clean, "{torn line", as_list]

    def test_sanitize_rewrites_existing_lines_and_is_idempotent(self):
        path = self.root / "results" / "scores.jsonl"
        lines = self.leaky_scores()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        out = self.cli("sanitize").stdout
        self.assertIn("sanitize: 2 line(s) changed", out)
        new = path.read_text(encoding="utf-8").split("\n")
        self.assertEqual(json.loads(new[0])["details"], {"checked": 1, "ok": "short"})
        self.assertEqual(new[1], lines[1])                       # clean line byte for byte (incl. U+2028)
        self.assertEqual(new[2], lines[2])                       # a torn line is kept verbatim
        self.assertEqual(json.loads(new[3])["details"], {})
        self.assertEqual(new[-1], "")                            # trailing newline kept
        self.assertNotIn("q7", path.read_text(encoding="utf-8"))
        again = path.read_bytes()
        self.assertIn("sanitize: 0 line(s) changed", self.cli("sanitize").stdout)
        self.assertEqual(path.read_bytes(), again)               # idempotent, byte for byte
        self.assertEqual([p.name for p in path.parent.iterdir() if p.name.endswith(".tmp")], [])
        self.assertEqual(oct(path.stat().st_mode & 0o777), oct(0o644))

    def test_sanitize_without_a_scores_file_is_a_no_op(self):
        self.assertIn("0 line(s) changed", self.cli("sanitize").stdout)
        self.assertFalse((self.root / "results" / "scores.jsonl").exists())

    def test_sanitize_keeps_scores_usable(self):
        self.seed("n-1", "base", [True, False])
        path = self.root / "results" / "scores.jsonl"
        raw = [json.loads(x) for x in path.read_text().splitlines()]
        raw[0]["details"] = {"per_q": {"q1": True}, "n": 1}
        path.write_text("\n".join(json.dumps(x) for x in raw) + "\n")
        self.cli("sanitize")
        self.assertEqual([s["passed"] for s in self.scores()], [True, False])
        self.assertEqual(self.scores()[0]["details"], {"n": 1})


class PublicManifest(EvalTestCase):
    """Item 7: tasks.json is public; the private pass_rule text must never reach it."""

    SECRET = "zero invented answers AND at least 11 of 12 correct (items q3, q7 are traps)"

    def set_task(self, tid, **fields):
        path = self.root / "private" / "tasks" / tid / "task.json"
        t = json.loads(path.read_text())
        t.update(fields)
        write(path, json.dumps(t))

    def entry(self, tid):
        return next(e for e in json.loads((self.root / "tasks.json").read_text()) if e["id"] == tid)

    def test_pass_rule_public_is_used_when_present(self):
        self.set_task("n-1", pass_rule=self.SECRET, pass_rule_public="no invented answers, at most one miss")
        self.cli("manifest")
        e = self.entry("n-1")
        self.assertEqual(e["pass_rule"], "no invented answers, at most one miss")
        self.assertEqual(e["title"], "Task n-1")
        self.assertNotIn("pass_rule_public", e)                  # the key list stays exactly as documented

    def test_generic_rule_replaces_the_private_text_when_there_is_no_public_one(self):
        self.set_task("n-1", pass_rule=self.SECRET, pass_threshold=0.85)
        self.set_task("s-1", pass_rule=self.SECRET)
        self.cli("manifest")
        self.assertEqual(self.entry("n-1")["pass_rule"], "score >= 0.85")
        self.assertEqual(self.entry("s-1")["pass_rule"], "score >= 0.7")
        self.assertNotIn("q7", (self.root / "tasks.json").read_text())
        self.assertNotIn("invented", (self.root / "tasks.json").read_text())

    def test_blank_public_rule_falls_back_to_the_generic_one(self):
        self.set_task("n-1", pass_rule=self.SECRET, pass_rule_public="   ")
        self.cli("manifest")
        self.assertEqual(self.entry("n-1")["pass_rule"], "score >= 0.7")

    def test_task_hash_is_not_affected_by_the_pass_rule(self):
        before = ev.load_tasks(self.ctx())["n-1"]["task_hash"]
        self.set_task("n-1", pass_rule=self.SECRET, pass_rule_public="x")
        self.assertEqual(ev.load_tasks(self.ctx())["n-1"]["task_hash"], before)


class RealStateUntouched(unittest.TestCase):
    def fingerprint(self):
        files = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in sorted((EVALS / "results").glob("*")) if p.is_file()}
        return (files, (EVALS / "tasks.json").exists(), (EVALS / "private" / "answers").exists(),
                (EVALS / "private" / "work").exists())

    def test_a_full_cycle_in_a_temp_dir_leaves_the_real_evals_alone(self):
        before = self.fingerprint()
        case = Planning("test_fresh_plan_expands_grid_tasks_repeats")
        case.setUp()
        try:
            case.cli("manifest")
            case.cli("run", "--rows", "noticed-row", "--cells", "cheap", "--repeats", "1")
            case.cli("report")
            case.cli("decide")
            self.assertTrue((case.root / "results" / "runs.jsonl").exists())
        finally:
            case.tearDown()
        self.assertEqual(self.fingerprint(), before)

    def test_real_help_runs_without_touching_anything(self):
        before = self.fingerprint()
        r = subprocess.run([sys.executable, str(EVALKIT), "--help"], capture_output=True, text=True, timeout=20)
        self.assertEqual(r.returncode, 0)
        for cmd in ("manifest", "status", "plan", "run", "judge", "report", "decide", "selfcheck"):
            self.assertIn(cmd, r.stdout)
        self.assertEqual(self.fingerprint(), before)


if __name__ == "__main__":
    unittest.main()
