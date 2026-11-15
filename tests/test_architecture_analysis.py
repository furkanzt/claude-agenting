"""evals/probes/architecture_analysis.py applies evals/results/PREREGISTERED-2026-11-15-architecture.md to stored
runs and scores of the design-decision row. These tests build synthetic runs.jsonl and scores.jsonl lines in
memory (or in a temp directory for the command-line cases); the real results files and evals/private are never
read."""

import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("architecture_under_test",
                                              ROOT / "evals" / "probes" / "architecture_analysis.py")
aa = importlib.util.module_from_spec(spec)
spec.loader.exec_module(aa)

T1, T2, T3 = "design-01", "design-02", "design-03"
J1, J2 = "fable-5-1@high", "opus-5-5@high"
OX, SX = "opus-5-5@xhigh", "sonnet-5-5@xhigh"
TARGET = {T1: 6, T2: 12, T3: 12}
RATE_LIMIT = {"reason": "is_error", "stop_reason": "end_turn", "safety_stops": 0, "api_error_status": 429,
              "output_tokens": 0}


class World:
    """Synthetic runs.jsonl and scores.jsonl lines."""

    def __init__(self, rubric="aaaaaaaa"):
        self.runs, self.scores, self.rubric = [], [], rubric

    @staticmethod
    def rid(cell, task, repeat):
        return f"{cell}|{task}|{repeat}"

    def attempt(self, cell, task, repeat, valid=True, reason=None, cost=1.0, **fields):
        self.runs.append({"run_id": self.rid(cell, task, repeat), "task_id": task, "cell_id": cell, "repeat": repeat,
                          "valid": valid, "invalid_reason": reason, "cost_usd": cost if valid else 0.5,
                          "duration_ms": 60000, **fields})

    def passes(self, cell, task, repeat, judge, results, handled=5, rubric=None):
        for i, passed in enumerate(results):
            if passed is not None:
                self.scores.append({"run_id": self.rid(cell, task, repeat),
                                    "grader_id": f"judge:{judge}:{rubric or self.rubric}:{i}",
                                    "score": 1.0 if passed else 0.0, "passed": passed,
                                    "details": {"handled": handled if passed else 3, "violated": 0}})

    def slot(self, cell, task, repeat, outcome="pass", cost=1.0, **fields):
        """A valid run judged by both judges. outcome: 'pass', 'fail' or 'split', or a dict {judge: outcome}."""
        self.attempt(cell, task, repeat, cost=cost, **fields)
        for j in (J1, J2):
            o = outcome[j] if isinstance(outcome, dict) else outcome
            self.passes(cell, task, repeat, j, {"pass": (True, True), "fail": (False, False), "split": (True, False)}[o])


def world(fails=None, skip=(), costs=None):
    """Both cells on all three tasks up to each task's target. fails: {cell: {task: n}} failing runs (the first n
    repeats fail under both judges) or {(cell, task, repeat): outcome}. skip: slots left out."""
    w = World()
    fails = fails or {}
    for cell in (OX, SX):
        for task, n in TARGET.items():
            for rep in range(1, n + 1):
                if (cell, task, rep) in skip:
                    continue
                if (cell, task, rep) in fails:
                    outcome = fails[(cell, task, rep)]
                else:
                    outcome = "fail" if rep <= fails.get(cell, {}).get(task, 0) else "pass"
                w.slot(cell, task, rep, outcome, cost=(costs or {}).get(cell, 1.0))
    return w


def verdict(w):
    an = aa.analyse(w.runs, w.scores)
    return an, aa.decide(an)


class Constants(unittest.TestCase):
    def test_the_constants_name_the_cells_the_tasks_and_30_slots_a_cell(self):
        self.assertEqual(aa.CELLS, (OX, SX))
        self.assertEqual(aa.TARGET, TARGET)
        self.assertEqual(aa.JUDGES, (J1, J2))
        self.assertEqual(sum(aa.TARGET.values()), 30)
        self.assertEqual((aa.FAST_MARGIN, aa.CLEARLY_WORSE_MARGIN), (2, 5))


class Counting(unittest.TestCase):
    def test_fails_are_counted_per_cell_task_and_judge(self):
        an, _ = verdict(world({OX: {T2: 4, T3: 5}, SX: {T2: 6, T3: 3}}))
        for j in (J1, J2):
            self.assertEqual(an["fails"][OX][j], {T1: 0, T2: 4, T3: 5})
            self.assertEqual(an["fails"][SX][j], {T1: 0, T2: 6, T3: 3})
            self.assertEqual((an["total"][OX][j], an["total"][SX][j]), (9, 9))

    def test_a_split_is_not_a_fail(self):
        an, _ = verdict(world({(SX, T2, 1): "split"}))
        self.assertEqual(an["total"][SX], {J1: 0, J2: 0})

    def test_a_run_failed_by_one_judge_only_counts_under_that_judge_only(self):
        an, _ = verdict(world({(SX, T3, 2): {J1: "fail", J2: "pass"}}))
        self.assertEqual(an["total"][SX], {J1: 1, J2: 0})

    def test_a_slot_with_no_valid_answer_is_a_fail_under_both_judges(self):
        w = world(skip={(SX, T2, 3)})
        for _ in range(3):
            w.attempt(SX, T2, 3, valid=False, reason="timeout")
        an, d = verdict(w)
        self.assertEqual(an["total"][SX], {J1: 1, J2: 1})
        self.assertEqual(an["status"], "DECIDED")
        self.assertEqual(an["failed_slots"][SX], 1)

    def test_a_run_that_called_an_advisor_is_a_failed_slot_and_is_listed(self):
        w = world(skip={(OX, T3, 1)})
        w.slot(OX, T3, 1, "pass", advisor_called=True)
        an, _ = verdict(w)
        self.assertEqual(an["total"][OX], {J1: 1, J2: 1})
        self.assertEqual(an["advisor_runs"], [(OX, T3, 1)])

    def test_a_repeat_beyond_the_tasks_target_is_not_counted(self):
        w = world()
        w.slot(SX, T1, 7, "fail")
        w.slot(SX, T2, 13, "fail")
        an, _ = verdict(w)
        self.assertEqual(an["total"][SX], {J1: 0, J2: 0})

    def test_other_cells_and_other_tasks_are_ignored(self):
        w = world()
        w.slot("opus-5-5@high", T2, 1, "fail")
        w.slot(SX, "design-04", 1, "fail")
        an, _ = verdict(w)
        self.assertEqual(an["total"][SX], {J1: 0, J2: 0})
        self.assertEqual(an["status"], "DECIDED")


class Rules(unittest.TestCase):
    def test_equal_fails_give_sonnet_both_modes(self):
        _, d = verdict(world({OX: {T2: 6, T3: 4}, SX: {T2: 6, T3: 4}}))
        self.assertEqual((d["fast"]["cell"], d["balanced"]["cell"]), (SX, SX))

    def test_two_more_fails_in_total_keep_fast_and_lose_balanced(self):
        _, d = verdict(world({OX: {T2: 6, T3: 4}, SX: {T2: 7, T3: 5}}))
        self.assertEqual((d["fast"]["cell"], d["balanced"]["cell"]), (SX, OX))

    def test_one_more_fail_in_total_loses_balanced_even_when_behind_on_one_task_only(self):
        _, d = verdict(world({OX: {T2: 6, T3: 4}, SX: {T2: 6, T3: 5}}))
        self.assertEqual((d["fast"]["cell"], d["balanced"]["cell"]), (SX, OX))
        self.assertIn("11 fails against 10", d["balanced"]["why"])

    def test_three_more_fails_in_total_lose_fast(self):
        _, d = verdict(world({OX: {T2: 6, T3: 4}, SX: {T2: 8, T3: 5}}))
        self.assertEqual((d["fast"]["cell"], d["balanced"]["cell"]), (OX, OX))

    def test_three_more_fails_on_one_task_lose_fast_even_when_the_total_is_within_two(self):
        _, d = verdict(world({OX: {T2: 6, T3: 4}, SX: {T2: 3, T3: 7}}))
        self.assertEqual(d["fast"]["cell"], OX)
        self.assertIn("design-03", d["fast"]["why"])

    def test_no_more_fails_in_total_but_behind_on_two_tasks_loses_balanced(self):
        fails = {OX: {T1: 0, T2: 8, T3: 2}, SX: {T1: 1, T2: 5, T3: 3}}
        _, d = verdict(world(fails))
        self.assertEqual((d["fast"]["cell"], d["balanced"]["cell"]), (SX, OX))
        self.assertIn("2 task", d["balanced"]["why"])

    def test_behind_on_one_task_only_and_no_more_fails_in_total_takes_balanced(self):
        _, d = verdict(world({OX: {T2: 8, T3: 2}, SX: {T2: 6, T3: 3}}))
        self.assertEqual(d["balanced"]["cell"], SX)

    def test_a_rule_fires_only_when_it_fires_under_both_judges(self):
        fails = {OX: {T2: 4}, SX: {T2: 4}}
        w = world(fails)
        # three more Sonnet runs fail under the Opus judge only: equal under one judge, +3 under the other
        for rep in (5, 6, 7):
            w.scores = [s for s in w.scores if not (s["run_id"] == World.rid(SX, T2, rep) and J2 in s["grader_id"])]
            w.passes(SX, T2, rep, J2, (False, False))
        _, d = verdict(w)
        self.assertEqual((d["fast"]["cell"], d["balanced"]["cell"]), (OX, OX))

    def test_more_than_five_extra_fails_is_reported_as_clearly_worse(self):
        _, d = verdict(world({OX: {T2: 2}, SX: {T2: 5, T3: 3}}))
        self.assertTrue(d["clearly_worse"])
        _, d = verdict(world({OX: {T2: 2}, SX: {T2: 5, T3: 2}}))
        self.assertFalse(d["clearly_worse"])

    def test_critical_and_cheapest_are_never_moved(self):
        _, d = verdict(world({OX: {T2: 6}, SX: {T2: 6}}))
        self.assertEqual((d["critical"]["cell"], d["cheapest"]["cell"]), (OX, SX))


class Pending(unittest.TestCase):
    def test_a_slot_that_was_never_run_keeps_every_rule_pending(self):
        an, d = verdict(world(skip={(SX, T3, 12)}))
        self.assertEqual(an["status"], "PENDING")
        self.assertIsNone(d)
        self.assertEqual(an["missing_runs"][SX][T3], 1)

    def test_a_missing_judge_pass_is_incomplete(self):
        w = world()
        w.scores = [s for s in w.scores if not (s["run_id"] == World.rid(OX, T2, 4) and s["grader_id"].endswith(":1")
                                                and J2 in s["grader_id"])]
        an, d = verdict(w)
        self.assertEqual(an["status"], "INCOMPLETE")
        self.assertIsNone(d)
        self.assertEqual(an["missing_passes"], 1)

    def test_a_slot_lost_to_api_errors_is_pending_not_failed(self):
        w = world(skip={(SX, T2, 2)})
        w.attempt(SX, T2, 2, valid=False, **RATE_LIMIT)
        an, d = verdict(w)
        self.assertEqual(an["status"], "PENDING")
        self.assertEqual(an["total"][SX], {J1: 0, J2: 0})

    def test_two_rubric_hashes_for_one_task_and_judge_are_an_error(self):
        w = world()
        w.passes(SX, T2, 1, J1, (True, True), rubric="bbbbbbbb")
        with self.assertRaises(aa.AnalysisError):
            aa.analyse(w.runs, w.scores)


class CommandLine(unittest.TestCase):
    def run_cli(self, w, *args):
        with tempfile.TemporaryDirectory() as d:
            runs, scores = Path(d) / "runs.jsonl", Path(d) / "scores.jsonl"
            runs.write_text("".join(json.dumps(r) + "\n" for r in w.runs), encoding="utf-8")
            scores.write_text("".join(json.dumps(s) + "\n" for s in w.scores), encoding="utf-8")
            out = io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
                code = aa.main(["--runs", str(runs), "--scores", str(scores), *args])
            return code, out.getvalue()

    def test_a_decided_record_prints_the_table_and_the_verdicts_and_exits_0(self):
        code, text = self.run_cli(world({OX: {T2: 6, T3: 4}, SX: {T2: 7, T3: 5}}, costs={OX: 2.0, SX: 1.0}))
        self.assertEqual(code, 0)
        self.assertIn("fast: sonnet-5-5@xhigh", text)
        self.assertIn("balanced: opus-5-5@xhigh", text)
        self.assertIn("Status: DECIDED", text)
        self.assertIn("design-03 alone", text)
        self.assertIn("$2.00", text)

    def test_a_pending_record_names_what_is_missing_and_exits_2(self):
        code, text = self.run_cli(world(skip={(SX, T3, 11), (SX, T3, 12)}))
        self.assertEqual(code, 2)
        self.assertIn("Status: PENDING", text)
        self.assertIn("sonnet-5-5@xhigh design-03: 2 run(s) missing", text)
        self.assertNotIn("fast:", text)

    def test_json_output_carries_counts_and_cell_ids_only(self):
        code, text = self.run_cli(world({OX: {T2: 1}, SX: {T2: 1}}), "--json")
        self.assertEqual(code, 0)
        data = json.loads(text)
        self.assertEqual(data["status"], "DECIDED")
        self.assertEqual(data["verdicts"]["fast"]["cell"], SX)
        self.assertNotIn("answer", text)

    def test_an_unreadable_file_exits_2(self):
        with tempfile.TemporaryDirectory() as d:
            out = io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
                code = aa.main(["--runs", str(Path(d) / "none.jsonl"), "--scores", str(Path(d) / "none2.jsonl")])
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
