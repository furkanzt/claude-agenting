"""evals/probes/think_first_analysis.py applies sections 2 and 3 of the 2026-11-13 think-first pre-registration to
stored runs and scores. These tests build synthetic runs.jsonl and scores.jsonl lines in memory (or in a temp
directory for the command-line cases); the real results files and evals/private are never read."""

import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("think_first_under_test", ROOT / "evals" / "probes" / "think_first_analysis.py")
tf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tf)

T1, T2 = "design-01", "design-02"
J1, J2 = "fable-5-1@high", "opus-5-5@high"
FL, FM, FH = "fable-5-2@low", "fable-5-2@medium", "fable-5-2@high"
OX, OH, SX = "opus-5-5@xhigh", "opus-5-5@high", "sonnet-5-5@xhigh"
ALL_CELLS = (FL, FM, FH, OX, OH, SX)
BOTH_FAIL = {J1: "fail", J2: "fail"}
ONLY_J1 = {J1: "fail", J2: "pass"}
RATE_LIMIT_LINE = {"invalid_reason": "is_error", "stop_reason": "end_turn", "safety_stops": 0,
                   "api_error_status": 429, "output_tokens": 0}
REFUSED = {"reason": "is_error", "stop_reason": "refusal"}          # the CLI's own marks of a classifier stop
SAFETY = {"reason": "is_error", "safety_stops": 1}
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
        """fields: extra run-line fields such as stop_reason and safety_stops."""
        self.runs.append({"run_id": self.rid(cell, task, repeat), "task_id": task, "cell_id": cell, "repeat": repeat,
                          "valid": valid, "invalid_reason": reason, "cost_usd": cost if valid else 0.5, **fields})

    def passes(self, cell, task, repeat, judge, results, rubric=None):
        """results: one bool (or None for 'not scored') per pass index."""
        for i, passed in enumerate(results):
            if passed is not None:
                self.scores.append({"run_id": self.rid(cell, task, repeat),
                                    "grader_id": f"judge:{judge}:{rubric or self.rubric}:{i}",
                                    "score": 1.0 if passed else 0.0, "passed": passed, "details": {}})

    def slot(self, cell, task, repeat, outcome="pass", cost=1.0, before=(), **fields):
        """A valid run (after `before` invalid attempts) judged by both judges. outcome: 'pass', 'fail' or
        'split', or a dict {judge: outcome}. `before`: an invalid_reason string, or a dict of run-line fields
        for the invalid attempt. `fields`: extra run-line fields on the valid run itself."""
        for earlier in before:
            self.attempt(cell, task, repeat, valid=False, **(earlier if isinstance(earlier, dict) else {"reason": earlier}))
        self.attempt(cell, task, repeat, cost=cost, **fields)
        for j in (J1, J2):
            o = outcome[j] if isinstance(outcome, dict) else outcome
            self.passes(cell, task, repeat, j, {"pass": (True, True), "fail": (False, False), "split": (True, False)}[o])

    def failed_slot(self, cell, task, repeat, reasons=("timeout", "timeout", "timeout")):
        for reason in reasons:
            self.attempt(cell, task, repeat, valid=False, reason=reason)


def full_world(fails=None, costs=None, cells=ALL_CELLS, repeats=range(1, 7), rubric="aaaaaaaa"):
    """Every listed cell on both tasks for the given repeats. fails: {(cell, task, repeat): outcome}."""
    w = World(rubric)
    for cell in cells:
        for task in (T1, T2):
            for rep in repeats:
                w.slot(cell, task, rep, (fails or {}).get((cell, task, rep), "pass"), cost=(costs or {}).get(cell, 1.0))
    return w


def lose(w, cell, task, repeat, attempts=3, **fields):
    """Replace the slot with `attempts` invalid attempts that are all API errors (a 429 by default)."""
    rid = w.rid(cell, task, repeat)
    w.runs = [r for r in w.runs if r["run_id"] != rid]
    w.scores = [x for x in w.scores if x["run_id"] != rid]
    for _ in range(attempts):
        w.attempt(cell, task, repeat, valid=False, **{**RATE_LIMIT, **fields})
    return w


def opus_fails(n, outcome="fail", split_tasks=True):
    """n failing opus-5-5@xhigh slots, alternating tasks when split_tasks (so both tasks have a fail from n = 2)."""
    slots = [(T1, 1), (T2, 1), (T1, 2), (T2, 2), (T1, 3), (T2, 3), (T1, 4), (T2, 4)] if split_tasks else \
            [(T1, r) for r in range(1, 7)]
    return {(OX, t, r): outcome for t, r in slots[:n]}


def analyse(w):
    return tf.analyse(w.runs, w.scores)


def decide(w):
    return tf.decide(analyse(w))


def cli(w, *flags):
    """(exit code, stdout, stderr) of main() on files written from the world."""
    with tempfile.TemporaryDirectory() as tmp:
        runs, scores = Path(tmp) / "runs.jsonl", Path(tmp) / "scores.jsonl"
        runs.write_text("".join(json.dumps(r) + "\n" for r in w.runs), encoding="utf-8")
        scores.write_text("".join(json.dumps(s) + "\n" for s in w.scores), encoding="utf-8")
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = tf.main(["--runs", str(runs), "--scores", str(scores), *flags])
        return code, out.getvalue(), err.getvalue()


class Constants(unittest.TestCase):
    def test_the_constants_name_the_tasks_judges_and_cells_of_the_pre_registration(self):
        self.assertEqual(tf.TASKS, ("design-01", "design-02"))
        self.assertEqual(tf.JUDGES, ("fable-5-1@high", "opus-5-5@high"))
        self.assertEqual(tf.PASS_INDEXES, (0, 1))
        self.assertEqual(set(tf.CELLS), set(ALL_CELLS))
        self.assertEqual(tf.FABLE_CELLS, (FL, FM, FH))
        self.assertEqual(tf.STAGE1_REPEATS, (1, 2, 3))
        self.assertEqual(tf.SLOTS_PER_CELL, 12)


class SolidFails(unittest.TestCase):
    def test_a_split_is_not_a_solid_fail(self):
        w = World()
        w.slot(OX, T1, 1, "split")
        s = analyse(w)["cells"][OX]
        self.assertEqual(s["solid"], {J1: 0, J2: 0})
        self.assertEqual(s["fails"], {J1: 0, J2: 0})

    def test_two_failing_passes_are_a_solid_fail_under_that_judge_only(self):
        w = World()
        w.slot(OX, T1, 1, ONLY_J1)
        s = analyse(w)["cells"][OX]
        self.assertEqual(s["solid"], {J1: 1, J2: 0})

    def test_a_run_with_no_answer_block_is_a_solid_fail_under_every_judge_without_judge_passes(self):
        w = World()
        w.attempt(OX, T1, 1)
        w.scores.append({"run_id": w.rid(OX, T1, 1), "grader_id": f"judge:{J1}:aaaaaaaa:0", "score": 0.0,
                         "passed": False, "details": {"no_block": True}})
        a = analyse(w)
        self.assertEqual(a["cells"][OX]["solid"], {J1: 1, J2: 1})
        self.assertEqual(a["missing"], [])                      # no judge passes are owed for it

    def test_the_latest_line_for_a_pass_index_wins(self):
        w = World()
        w.slot(OX, T1, 1, "fail")
        w.passes(OX, T1, 1, J1, (True, True))                  # a later grading under the same rubric
        self.assertEqual(analyse(w)["cells"][OX]["solid"], {J1: 0, J2: 1})


class FailedSlots(unittest.TestCase):
    def test_a_fable_attempt_with_stop_reason_refusal_fails_the_slot_even_after_a_valid_retry(self):
        w = World()
        w.slot(FL, T1, 1, "pass", before=(REFUSED,))
        a = analyse(w)["cells"][FL]
        self.assertEqual((a["failed"], a["fails"]), (1, {J1: 1, J2: 1}))

    def test_a_fable_attempt_with_safety_stops_fails_the_slot_valid_or_not(self):
        w = World()
        w.slot(FL, T1, 1, "pass", before=(SAFETY,))
        w.slot(FM, T1, 1, "pass", safety_stops=2)               # a valid run that was refused part-way
        w.slot(FH, T1, 1, "pass", before=({"reason": "refusal: classifier"},))   # a dedicated reason, should evalkit add one
        a = analyse(w)["cells"]
        self.assertEqual([a[c]["failed"] for c in (FL, FM, FH)], [1, 1, 1])

    def test_a_fable_attempt_that_is_only_an_error_such_as_a_rate_limit_does_not_fail_the_slot(self):
        w = World()
        w.slot(FL, T1, 1, "pass", before=(RATE_LIMIT,))
        w.slot(FM, T1, 1, "pass", before=({"reason": "exit_code=1", "stop_reason": "end_turn", "safety_stops": 0},))
        w.slot(FH, T1, 1, "pass", before=("is_error",))         # an old line with neither field
        a = analyse(w)["cells"]
        self.assertEqual([a[c]["failed"] for c in (FL, FM, FH)], [0, 0, 0])
        self.assertEqual(a[FL]["fails"], {J1: 0, J2: 0})

    def test_the_same_refusal_marks_on_an_opus_cell_do_not_fail_its_slot(self):
        w = World()
        w.slot(OX, T1, 1, "pass", before=(REFUSED,))
        w.slot(OX, T1, 2, "pass", before=(SAFETY,), safety_stops=1)
        w.slot(OH, T1, 1, "pass", stop_reason="refusal")
        a = analyse(w)["cells"]
        self.assertEqual((a[OX]["failed"], a[OX]["fails"], a[OH]["failed"]), (0, {J1: 0, J2: 0}, 0))

    def test_a_run_line_without_stop_reason_and_safety_stops_is_read_as_not_refused(self):
        w = World()
        w.slot(FL, T1, 1, "pass")                               # no extra fields at all
        w.slot(FM, T1, 1, "pass", stop_reason=None, safety_stops=0)
        a = analyse(w)["cells"]
        self.assertEqual((a[FL]["failed"], a[FM]["failed"]), (0, 0))
        self.assertEqual(analyse(w)["fable_invalid"][FL], {"refusal": 0, "wrong_model": 0, "other": 0})

    def test_a_different_model_answering_fails_a_fable_slot_but_a_timeout_does_not(self):
        w = World()
        w.slot(FL, T1, 1, "pass", before=("model_mismatch: observed ['claude-opus-4-8']",))
        w.slot(FM, T1, 1, "pass", before=("timeout",))
        w.slot(OX, T1, 1, "pass", before=("model_mismatch: observed ['claude-opus-4-8']",))
        a = analyse(w)["cells"]
        self.assertEqual((a[FL]["failed"], a[FM]["failed"], a[OX]["failed"]), (1, 0, 0))

    def test_a_slot_whose_attempts_are_all_invalid_is_failed_on_any_cell(self):
        w = World()
        w.failed_slot(OX, T1, 1)
        w.failed_slot(SX, T1, 1)
        a = analyse(w)["cells"]
        self.assertEqual((a[OX]["failed"], a[OX]["fails"][J1], a[SX]["failed"]), (1, 1, 1))
        self.assertEqual(a[OX]["decided"], 1)                   # decided without any judge pass

    def test_a_slot_with_no_attempt_is_not_decided(self):
        a = analyse(World())["cells"][OX]
        self.assertEqual((a["decided"], a["failed"]), (0, 0))


class LostSlots(unittest.TestCase):
    """A slot whose attempts are all API errors measured nothing: not failed, not decided, cell PENDING."""

    def test_an_all_429_slot_is_lost_not_failed_and_keeps_its_cell_pending(self):
        w = lose(full_world(opus_fails(4), {FL: 3.0, FM: 2.0, FH: 5.0}), FL, T1, 1)
        a = analyse(w)["cells"][FL]
        self.assertEqual((a["lost"], a["failed"], a["decided"], a["fails"]), (1, 0, 11, {J1: 0, J2: 0}))
        d = decide(w)
        self.assertEqual(d["quality"]["status"], "pending")       # fable-5-2@low could still be the cheapest
        self.assertIn(FL, d["quality"]["why"])
        self.assertEqual(analyse(w)["missing"], [])                # and it owes no judge pass

    def test_a_slot_with_a_timeout_and_two_429s_and_no_valid_run_is_failed(self):
        w = World()
        w.attempt(OX, T1, 1, valid=False, reason="timeout")
        w.attempt(OX, T1, 1, valid=False, **RATE_LIMIT)
        w.attempt(OX, T1, 1, valid=False, **RATE_LIMIT)
        a = analyse(w)["cells"][OX]
        self.assertEqual((a["failed"], a["lost"], a["decided"], a["fails"]), (1, 0, 1, {J1: 1, J2: 1}))

    def test_429s_followed_by_a_valid_run_make_a_normal_decided_slot(self):
        w = World()
        w.slot(OX, T1, 1, "pass", before=(RATE_LIMIT, RATE_LIMIT))
        a = analyse(w)["cells"][OX]
        self.assertEqual((a["failed"], a["lost"], a["decided"], a["fails"]), (0, 0, 1, {J1: 0, J2: 0}))

    def test_a_lost_fable_slot_that_also_had_a_refusal_is_failed(self):
        w = World()
        w.attempt(FL, T1, 1, valid=False, **RATE_LIMIT)
        w.attempt(FL, T1, 1, valid=False, **REFUSED)
        a = analyse(w)["cells"][FL]
        self.assertEqual((a["failed"], a["lost"]), (1, 0))

    def test_the_text_and_json_show_the_lost_slots_and_a_command_to_run_them_again(self):
        w = lose(full_world(opus_fails(4), {FL: 2.0, FM: 2.0, FH: 5.0}), FL, T1, 2)
        code, out, _ = cli(w)
        self.assertEqual(code, 2)
        self.assertRegex(out, r"failed slots\s+lost to API errors\s+mean cost/run")
        row = next(l for l in out.splitlines() if l.startswith(FL + " "))
        self.assertRegex(row, r"\s1\s+\$")                      # one lost slot in the table row
        self.assertIn(f"python3 evals/evalkit.py run --phase all --rows design-decision --cells {FL} --repeats 2 --max-usd 3", out)
        js = json.loads(cli(w, "--json")[1])
        self.assertEqual((js["cells"][FL]["lost_to_api_errors"], js["cells"][FM]["lost_to_api_errors"]), (1, 0))

    def test_a_lost_stage_2_slot_of_a_warranted_cell_is_run_again_by_the_stage_2_line(self):
        w = lose(full_world(opus_fails(4), {c: 1.0 for c in ALL_CELLS}), FL, T1, 6)
        plan = tf.stage2_plan(analyse(w))
        self.assertEqual(plan["cells"], [FL])
        self.assertIn(f"--cells {FL} --repeats 6", plan["lines"][0][1])
        self.assertEqual(tf.lost_plan(analyse(w), skip=plan["cells"]), [])     # not listed a second time

    def test_the_infra_error_rule_agrees_with_evalkits_on_a_table_of_lines(self):
        spec = importlib.util.spec_from_file_location("evalkit_for_agreement", ROOT / "evals" / "evalkit.py")
        ek = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ek)
        refusal = {"stop_reason": "refusal", "safety_stops": 0, "output_tokens": 0}
        lines = [
            RATE_LIMIT_LINE, {"invalid_reason": "is_error", "api_error_status": 529, "output_tokens": 40},
            {"invalid_reason": "spawn failed: x"}, {"invalid_reason": "is_error", "stop_reason": "end_turn", "output_tokens": 0},
            {"invalid_reason": "exit_code=1", "stop_reason": "end_turn", "output_tokens": None},
            {"invalid_reason": "exit_code=1", "stop_reason": "end_turn"},
            {"invalid_reason": "is_error", "stop_reason": "end_turn", "output_tokens": 12},
            {"invalid_reason": "is_error"}, {"invalid_reason": "exit_code=1", "output_tokens": 0},
            {"invalid_reason": "is_error", **refusal},
            {"invalid_reason": "is_error", "stop_reason": "end_turn", "safety_stops": 2, "output_tokens": 0},
            {"invalid_reason": "refusal: classifier", "stop_reason": "end_turn", "output_tokens": 0},
            {"invalid_reason": "timeout", "stop_reason": None, "output_tokens": 0},
            {"invalid_reason": "json_parse", "stop_reason": None, "output_tokens": 0},
            {"invalid_reason": "model_mismatch: observed ['x']", "api_error_status": 529},
            {"valid": True, "api_error_status": 429}, {"valid": True},
        ]
        verdicts = []
        for fields in lines:
            line = {"valid": False, **fields}
            verdicts.append(tf.infra_error(line))
            self.assertEqual(tf.infra_error(line), ek.infra_error(line), fields)
        self.assertEqual(verdicts.count(True), 6)               # the table holds true and false cases


class Incomplete(unittest.TestCase):
    def test_a_missing_judge_pass_gives_incomplete_names_it_and_exits_2_without_a_verdict(self):
        w = full_world()
        w.scores = [s for s in w.scores if not (s["run_id"] == w.rid(FL, T2, 3) and s["grader_id"].startswith(f"judge:{J2}:")
                                                  and s["grader_id"].endswith(":1"))]
        a = analyse(w)
        self.assertEqual(a["missing"], [(FL, T2, 3, J2, 1)])
        code, out, _ = cli(w)
        self.assertEqual(code, 2)
        self.assertIn("INCOMPLETE", out)
        self.assertIn(f"{FL} {T2} repeat 3: {J2} pass 1", out)
        self.assertNotIn("Dispositions", out)
        self.assertEqual(json.loads(cli(w, "--json")[1])["status"], "INCOMPLETE")

    def test_a_failed_slot_needs_no_judge_passes(self):
        w = World()
        w.failed_slot(FL, T1, 1)
        w.attempt(FL, T1, 2, valid=False, reason="is_error", stop_reason="refusal")
        w.attempt(FL, T1, 2)                                    # refused once, then valid, but never judged
        self.assertEqual(analyse(w)["missing"], [])


class RuleQ(unittest.TestCase):
    COSTS = {FL: 3.0, FM: 2.0, FH: 5.0}

    def test_rule_q_fires_at_four_of_twelve_and_not_at_three(self):
        d = decide(full_world(opus_fails(4), self.COSTS))
        self.assertEqual((d["quality"]["cell"], d["quality"]["rule"]), (FM, "rule Q"))
        d = decide(full_world(opus_fails(3), self.COSTS))
        self.assertEqual((d["quality"]["cell"], d["quality"]["rule"]), (OX, "otherwise"))
        self.assertIn("not adopted", d["quality"]["why"])

    def test_rule_q_needs_both_judges_four_under_one_and_three_under_the_other_does_not_move(self):
        fails = {k: (BOTH_FAIL if i < 3 else ONLY_J1) for i, k in enumerate(opus_fails(4))}
        d = decide(full_world(fails, self.COSTS))
        self.assertEqual((d["quality"]["cell"], d["quality"]["rule"]), (OX, "otherwise"))

    def test_the_cheapest_qualifying_fable_effort_is_chosen_by_measured_cost_not_by_effort_name(self):
        d = decide(full_world(opus_fails(4), {FL: 3.0, FM: 2.0, FH: 5.0}))
        self.assertEqual(d["quality"]["cell"], FM)
        d = decide(full_world(opus_fails(4), {FL: 1.0, FM: 2.0, FH: 0.5}))
        self.assertEqual(d["quality"]["cell"], FH)

    def test_a_fable_cell_with_one_solid_fail_under_one_judge_cannot_qualify(self):
        fails = {**opus_fails(4), (FL, T1, 2): ONLY_J1}
        d = decide(full_world(fails, {FL: 0.1, FM: 2.0, FH: 5.0}))   # low is cheapest but has a fail
        self.assertEqual(d["quality"]["cell"], FM)
        every = {**opus_fails(4), (FL, T1, 2): ONLY_J1, (FM, T1, 2): ONLY_J1, (FH, T1, 2): ONLY_J1}
        d = decide(full_world(every, self.COSTS))
        self.assertEqual(d["quality"]["cell"], OX)

    def test_a_split_does_not_disqualify_a_fable_cell(self):
        fails = {**opus_fails(4), (FL, T1, 2): "split"}
        d = decide(full_world(fails, {FL: 0.1, FM: 2.0, FH: 5.0}))
        self.assertEqual(d["quality"]["cell"], FL)

    def test_a_failed_slot_counts_against_a_fable_cell(self):
        w = full_world(opus_fails(4), {FL: 0.1, FM: 2.0, FH: 5.0}, cells=(FM, FH, OX, OH, SX))
        for t in (T1, T2):
            for r in range(1, 7):
                if (t, r) != (T1, 2):
                    w.slot(FL, t, r, "pass", cost=0.1)
        w.failed_slot(FL, T1, 2)
        self.assertEqual(decide(w)["quality"]["cell"], FM)


class RuleB(unittest.TestCase):
    COSTS = {FL: 3.0, FM: 2.0, FH: 5.0}

    def test_rule_b_needs_six_fails_with_one_on_each_task(self):
        d = decide(full_world(opus_fails(6), self.COSTS))
        self.assertEqual((d["balanced"]["cell"], d["balanced"]["rule"]), (FM, "rule B"))
        d = decide(full_world(opus_fails(5), self.COSTS))
        self.assertEqual((d["balanced"]["cell"], d["balanced"]["rule"]), (OX, "otherwise"))
        self.assertEqual(d["quality"]["cell"], FM)               # five is enough for quality

    def test_six_fails_on_one_task_only_do_not_move_balanced(self):
        d = decide(full_world(opus_fails(6, split_tasks=False), self.COSTS))
        self.assertEqual((d["balanced"]["cell"], d["balanced"]["rule"]), (OX, "otherwise"))
        self.assertEqual((d["quality"]["cell"], d["quality"]["rule"]), (FM, "rule Q"))

    def test_rule_b_needs_both_judges(self):
        fails = {k: (BOTH_FAIL if i < 5 else ONLY_J1) for i, k in enumerate(opus_fails(6))}
        d = decide(full_world(fails, self.COSTS))
        self.assertEqual(d["balanced"]["cell"], OX)


class BothFail(unittest.TestCase):
    def test_both_fail_when_opus_has_four_and_every_fable_cell_has_a_fail_under_both_judges(self):
        fails = {**opus_fails(4), (FL, T1, 1): "fail", (FM, T1, 1): "fail", (FH, T1, 1): "fail"}
        w = full_world(fails, cells=(FL, FM, FH, OX), repeats=range(1, 7))
        w2 = full_world(fails, cells=(OH, SX), repeats=range(1, 4))
        w.runs += w2.runs
        w.scores += w2.scores
        d = decide(w)
        for kind in ("quality", "balanced"):
            self.assertEqual((d[kind]["cell"], d[kind]["rule"], d[kind]["why"]), (OX, "both fail", tf.NO_CELL_PASSED))

    def test_a_fable_cell_with_zero_fails_under_one_judge_only_is_not_both_fail(self):
        fails = {**opus_fails(4), (FL, T1, 1): ONLY_J1, (FM, T1, 1): "fail", (FH, T1, 1): "fail"}
        d = decide(full_world(fails))
        self.assertEqual((d["quality"]["cell"], d["quality"]["rule"]), (OX, "otherwise"))


class Fast(unittest.TestCase):
    def test_fast_is_the_cheaper_candidate_with_zero_fails(self):
        self.assertEqual(decide(full_world(costs={OH: 2.0, SX: 1.0}))["fast"]["cell"], SX)
        self.assertEqual(decide(full_world(costs={OH: 1.0, SX: 2.0}))["fast"]["cell"], OH)

    def test_fast_skips_a_candidate_with_a_fail_even_when_it_is_cheaper(self):
        d = decide(full_world({(SX, T1, 2): "fail"}, costs={OH: 3.0, SX: 1.0}))
        self.assertEqual((d["fast"]["cell"], d["fast"]["rule"]), (OH, "rule fast"))

    def test_fast_falls_back_to_opus_xhigh_when_neither_candidate_has_zero_fails_and_is_never_fable(self):
        d = decide(full_world({(SX, T1, 2): "fail", (OH, T2, 5): ONLY_J1}, costs={FL: 0.01}))
        self.assertEqual(d["fast"]["cell"], OX)
        self.assertNotIn(d["fast"]["cell"], tf.FABLE_CELLS)


class Pending(unittest.TestCase):
    def test_rules_that_need_twelve_slots_are_pending_until_all_twelve_are_decided(self):
        w = full_world(opus_fails(4), repeats=range(1, 4))      # stage 1 only; opus xhigh has 6 of 12
        d = decide(w)
        self.assertEqual((d["quality"]["status"], d["balanced"]["status"]), ("pending", "pending"))
        w.runs += full_world(opus_fails(4), cells=(OX,), repeats=range(4, 7)).runs
        w.scores += full_world(opus_fails(4), cells=(OX,), repeats=range(4, 7)).scores
        d = decide(w)                                           # opus has its 12; the clean Fable cells have 6
        self.assertEqual(d["quality"]["status"], "pending")
        self.assertEqual(d["fast"]["status"], "pending")        # candidates are clean at 6 of 12
        code, out, _ = cli(w)
        self.assertEqual(code, 2)
        self.assertIn("PENDING", out)

    def test_opus_xhigh_counts_stay_pending_until_its_own_twelve_slots_are_decided(self):
        every_fable_fails = {(c, T1, 1): "fail" for c in (FL, FM, FH)}
        w = full_world({**opus_fails(4), **every_fable_fails}, repeats=range(1, 4))
        d = decide(w)                                           # opus has 6 of 12 slots, 4 of them failing
        self.assertEqual((d["quality"]["status"], d["balanced"]["status"]), ("pending", "pending"))
        self.assertIn(f"{OX} has 6/12", d["quality"]["why"])

    def test_a_complete_world_exits_0_and_prints_one_line_per_disposition(self):
        code, out, _ = cli(full_world(opus_fails(4), {FL: 3.0, FM: 2.0, FH: 5.0}))
        self.assertEqual(code, 0)
        for line in (f"quality: {FM}", f"balanced: {OX}", f"fast: "):
            self.assertIn(line, out)
        self.assertIn("rule Q", out)


class Stage2(unittest.TestCase):
    def stage1(self, fails, costs):
        w = full_world(fails, costs, cells=(FL, FM, FH, OH, SX), repeats=range(1, 4))
        o = full_world(fails, costs, cells=(OX,))
        w.runs += o.runs
        w.scores += o.scores
        return w

    def test_stage_2_lines_are_printed_only_for_the_cells_the_rules_warrant(self):
        fails = {**opus_fails(4), (FM, T1, 1): "fail", (SX, T2, 1): "fail"}
        costs = {FL: 2.0, FM: 9.0, FH: 4.0, OH: 1.0, SX: 1.0}
        plan = tf.stage2_plan(analyse(self.stage1(fails, costs)))
        cmds = [c for _, c in plan["lines"]]
        self.assertEqual(cmds, [
            f"python3 evals/evalkit.py run --phase all --rows design-decision --cells {FL},{FH} --repeats 6 --max-usd 54",
            f"python3 evals/evalkit.py run --phase all --rows design-decision --cells {OH} --repeats 6 --max-usd 9"])
        self.assertEqual(plan["cells"], [FL, FH, OH])
        self.assertTrue(any(n.startswith(f"{FM}: stage 2 not warranted") for n in plan["notes"]))
        self.assertTrue(any(n.startswith(f"{SX}: stage 2 not warranted") for n in plan["notes"]))

    def test_no_fable_stage_2_when_opus_xhigh_has_fewer_than_four_fails_and_none_when_nothing_is_warranted(self):
        costs = {FL: 2.0, FM: 2.0, FH: 2.0, OH: 1.0, SX: 1.0}
        plan = tf.stage2_plan(analyse(self.stage1(opus_fails(3), costs)))
        self.assertEqual(plan["cells"], [OH, SX])                # only the cheaper candidates
        fails = {**opus_fails(3), (OH, T1, 1): "fail", (SX, T1, 1): "fail"}
        plan = tf.stage2_plan(analyse(self.stage1(fails, costs)))
        self.assertEqual(plan["lines"], [])
        code, out, _ = cli(self.stage1(fails, costs))
        self.assertIn("none are warranted", out)
        self.assertNotIn("evalkit.py run", out)

    def test_a_cell_with_a_stage_1_fail_under_either_judge_gets_no_stage_2(self):
        fails = {**opus_fails(4), (FL, T1, 1): ONLY_J1}
        plan = tf.stage2_plan(analyse(self.stage1(fails, {c: 1.0 for c in ALL_CELLS})))
        self.assertNotIn(FL, plan["cells"])

    def test_stage_2_that_has_already_been_run_prints_no_line(self):
        w = full_world(opus_fails(4))
        plan = tf.stage2_plan(analyse(w))
        self.assertEqual(plan["lines"], [])
        self.assertTrue(any("already run" in n for n in plan["notes"]))


class StoredData(unittest.TestCase):
    def test_mixed_rubric_hashes_for_one_task_and_judge_stop_with_an_error_naming_the_task(self):
        w = full_world(cells=(OX,), repeats=(1,))
        w.passes(OX, T2, 1, J1, (True, True), rubric="bbbbbbbb")
        with self.assertRaises(tf.AnalysisError) as cm:
            analyse(w)
        self.assertIn(T2, str(cm.exception))
        self.assertNotIn(T1, str(cm.exception))
        code, out, err = cli(w)
        self.assertEqual(code, 2)
        self.assertIn(T2, err)
        self.assertEqual(out, "")

    def test_two_judges_with_different_rubric_hashes_are_not_mixed_gradings(self):
        w = full_world(cells=(OX,), repeats=(1,), rubric="aaaaaaaa")
        for s in w.scores:
            if s["grader_id"].startswith(f"judge:{J2}:"):
                s["grader_id"] = s["grader_id"].replace("aaaaaaaa", "bbbbbbbb")
        self.assertEqual(analyse(w)["missing"], [])             # one hash per judge and task: no error

    def test_attempts_outside_the_counted_cells_tasks_and_repeats_are_ignored(self):
        w = World()
        w.slot("fable-5-3@high", T1, 1, "pass", before=(REFUSED,))
        w.slot(FL, "other-task", 1, "pass", before=(REFUSED,))
        w.slot(FL, T1, 7, "pass", before=(REFUSED,))
        w.slot(OX, T1, 1, "fail")
        a = analyse(w)
        self.assertEqual(a["fable_invalid"][FL], {"refusal": 0, "wrong_model": 0, "other": 0})
        self.assertEqual((a["cells"][FL]["decided"], a["cells"][OX]["fails"]), (0, {J1: 1, J2: 1}))

    def test_a_missing_results_file_is_an_error_exit_2(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = tf.main(["--runs", "/nonexistent/runs.jsonl", "--scores", "/nonexistent/scores.jsonl"])
        self.assertEqual(code, 2)
        self.assertIn("does not exist", err.getvalue())


class JsonOutput(unittest.TestCase):
    ALLOWED = set(ALL_CELLS) | {"rule Q", "rule B", "rule fast", "otherwise", "both fail",
                                "VERDICT", "PENDING", "INCOMPLETE", "decided", "pending"}

    @staticmethod
    def strings(obj):
        if isinstance(obj, str):
            yield obj
        elif isinstance(obj, dict):
            for v in obj.values():
                yield from JsonOutput.strings(v)
        elif isinstance(obj, list):
            for v in obj:
                yield from JsonOutput.strings(v)

    def test_json_holds_no_strings_beyond_cell_ids_rule_names_and_status_words(self):
        worlds = [full_world(opus_fails(6), {FL: 3.0, FM: 2.0, FH: 5.0}),
                  full_world(opus_fails(4), repeats=range(1, 4)),
                  full_world({**opus_fails(4), (FL, T1, 1): "fail", (FM, T1, 1): "fail", (FH, T1, 1): "fail"}),
                  lose(full_world(opus_fails(4)), FL, T1, 1),
                  World()]
        for w in worlds:
            obj = json.loads(cli(w, "--json")[1])
            self.assertLessEqual(set(self.strings(obj)), self.ALLOWED)
        full = json.loads(cli(worlds[0], "--json")[1])
        self.assertEqual((full["status"], full["quality"]["cell"], full["balanced"]["rule"]), ("VERDICT", FM, "rule B"))
        self.assertEqual(full["cells"][OX]["solid_fails"], {J1: 6, J2: 6})


if __name__ == "__main__":
    unittest.main()
