"""evals/probes/advisor_pairs_analysis.py applies the 2026-11-14 advisor-pairs pre-registration to stored runs
and scores. These tests build synthetic run lines, score lines and answer files, in memory or in a temp evals
directory for the command-line cases; the real results files and evals/private are never read."""

import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("advisor_pairs_under_test",
                                              ROOT / "evals" / "probes" / "advisor_pairs_analysis.py")
ap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ap)

D2 = "design-02"
S1, S2, S3 = "synthesize-01", "synthesize-02", "synthesize-03"
SYNTH_TASKS = (S1, S2, S3)
J1, J2 = "fable-5-1@high", "opus-5-5@high"
Q1C, Q1H = "opus-5-5@xhigh+fable-advisor", "opus-5-5@high+fable-advisor"
SXP, SHP = "sonnet-5-5@xhigh+opus-advisor", "sonnet-5-5@high+opus-advisor"
OX, OH, SX = "opus-5-5@xhigh", "opus-5-5@high", "sonnet-5-5@xhigh"
PAIRS = (Q1C, Q1H, SXP, SHP)
HASHES = {D2: "hash-d2", S1: "hash-s1", S2: "hash-s2", S3: "hash-s3"}
LIMITS = {"timeout_s": 1800.0, "cap_usd": 10.0}
SECRET = "ZEBRA-PLUM-7741 the answer text must never be printed"


class World:
    """Synthetic runs.jsonl and scores.jsonl lines and answer files."""

    def __init__(self):
        self.runs, self.scores, self.answers = [], [], {}

    @staticmethod
    def rid(cell, task, rep):
        return f"{cell}_{task}_{rep}"

    def attempt(self, cell, task, rep, valid=True, cost=1.0, secs=600, reason=None, advisor=True,
                advisor_cost=0.3, task_hash=None, **fields):
        line = {"run_id": self.rid(cell, task, rep), "task_id": task, "task_hash": task_hash or HASHES[task],
                "cell_id": cell, "repeat": rep, "valid": valid, "invalid_reason": reason,
                "cost_usd": cost, "duration_ms": None if secs is None else secs * 1000, **fields}
        if cell in PAIRS:
            line.update(advisor_called=bool(advisor) and valid, advisor_cost_usd=advisor_cost if advisor and valid else None)
        self.runs.append(line)

    def score(self, rid, judge, i, passed, rubric="r1", **details):
        self.scores.append({"run_id": rid, "grader_id": f"judge:{judge}:{rubric}:{i}", "score": 1.0 if passed else 0.0,
                            "passed": passed, "details": details})

    def design(self, cell, rep, handled=4, passed=False, violated=0, per_pass=None, rubric="r1", **run):
        """A valid design-02 run judged by both judges twice. per_pass: {(judge, i): {field: value}} overrides."""
        self.attempt(cell, D2, rep, **run)
        for j in (J1, J2):
            for i in (0, 1):
                f = {"handled": handled, "passed": passed, "violated": violated, **(per_pass or {}).get((j, i), {})}
                self.score(self.rid(cell, D2, rep), j, i, f["passed"], rubric=f.get("rubric", rubric),
                           handled=f["handled"], violated=f["violated"], n_P=6, n_C=5)

    def synth(self, cell, task, rep, found=(6, 6), of=6, passed=(True, True), fabricated=(0, 0), **run):
        self.attempt(cell, task, rep, **run)
        for i in (0, 1):
            self.score(self.rid(cell, task, rep), J1, i, passed[i], found=found[i], of=of, fabricated=fabricated[i])

    def answer(self, cell, task, rep, result, block="the answer"):
        self.answers[self.rid(cell, task, rep)] = {"result": result, "block": block}

    def drop(self, cell, task, rep):
        rid = self.rid(cell, task, rep)
        self.runs = [r for r in self.runs if r["run_id"] != rid]
        self.scores = [s for s in self.scores if s["run_id"] != rid]
        self.answers.pop(rid, None)
        return self

    def data(self):
        return {"runs": self.runs, "scores": self.scores, "hashes": dict(HASHES), "limits": dict(LIMITS),
                "answers": self.answers}


# Stored baselines with small made-up numbers. opus-5-5@xhigh on design-02 handles 4,4,4,4,4,5 (mean 25/6, which
# rounds to 4.17), runs 5 and 6 pass, costs 2.0 x5 and 2.6 (mean 2.1), 600 s each.
OX_HANDLED = (4, 4, 4, 4, 4, 5)
OX_MEAN = 25 / 6


def baselines(w):
    for rep, h in enumerate(OX_HANDLED, 1):
        w.design(OX, rep, handled=h, passed=rep >= 5, cost=2.6 if rep == 6 else 2.0, secs=600)
    for rep, h in enumerate((3, 3, 4), 1):
        w.design(OH, rep, handled=h, cost=1.0, secs=300)
    for rep, h in enumerate((4, 4, 5), 1):
        w.design(SX, rep, handled=h, cost=1.0, secs=500)
    for cell, cost, secs, found in ((OX, 2.4, 500, 6), (OH, 2.0, 300, 6), (SX, 1.5, 550, 5)):
        for task in SYNTH_TASKS:
            for rep in (1, 2, 3):
                w.synth(cell, task, rep, found=(found, 6), cost=cost, secs=secs)
    return w


def q1_world(handled=(4,) * 6, passed=(False,) * 6, violated=(0,) * 6, answered=(True,) * 6):
    w = baselines(World())
    for rep in range(1, 7):
        w.design(Q1C, rep, handled=handled[rep - 1], passed=passed[rep - 1], violated=violated[rep - 1],
                 advisor=answered[rep - 1])
    return w


def q2_world(cell=SXP, row="both", cost=1.0, secs=300, answered=9, design=None, synth=None):
    """One Sonnet pair cell. Defaults: cheaper, faster and near on both rows, the advisor answered every time.
    design: {rep: kwargs for World.design}; synth: {(task, rep): kwargs for World.synth}."""
    w = baselines(World())
    if row in ("both", "synthesis"):
        n = 0
        for task in SYNTH_TASKS:
            for rep in (1, 2, 3):
                n += 1
                w.synth(cell, task, rep, **{"cost": cost, "secs": secs, "advisor": n <= answered,
                                            **(synth or {}).get((task, rep), {})})
    if row in ("both", "design"):
        for rep in (1, 2, 3):
            w.design(cell, rep, **{"handled": 4, "cost": cost, "secs": secs, "advisor": rep <= min(answered, 3),
                                   **(design or {}).get(rep, {})})
    return w


def full_world():
    """Every slot of the test run and scored."""
    w = baselines(World())
    for rep in range(1, 7):
        w.design(Q1C, rep)
    for rep in (1, 2, 3):
        w.design(Q1H, rep)
    for cell in (SXP, SHP):
        for task in SYNTH_TASKS:
            for rep in (1, 2, 3):
                w.synth(cell, task, rep, cost=1.0, secs=300)
        for rep in (1, 2, 3):
            w.design(cell, rep, cost=1.0, secs=300)
    return w


def analyse(w):
    return ap.analyse(w.data())


def write(w, tmp, answers=True):
    d = Path(tmp)
    (d / "results").mkdir(parents=True, exist_ok=True)
    (d / "results" / "runs.jsonl").write_text("".join(json.dumps(r) + "\n" for r in w.runs), encoding="utf-8")
    (d / "results" / "scores.jsonl").write_text("".join(json.dumps(s) + "\n" for s in w.scores), encoding="utf-8")
    (d / "tasks.json").write_text(json.dumps([{"id": t, "task_hash": h} for t, h in HASHES.items()]
                                             + [{"id": "design-01", "task_hash": "x"}]), encoding="utf-8")
    (d / "harness.json").write_text(json.dumps({"runner": {"timeout_s": 1800, "max_budget_usd_per_run": 10}}),
                                    encoding="utf-8")
    if answers and w.answers:
        (d / "private" / "answers").mkdir(parents=True)
        for rid, a in w.answers.items():
            (d / "private" / "answers" / f"{rid}.json").write_text(json.dumps({"run_id": rid, **a}), encoding="utf-8")
    return d


def cli(w, *flags, answers=True):
    """(exit code, stdout, stderr) of main() on a temp evals directory written from the world."""
    with tempfile.TemporaryDirectory() as tmp:
        d = write(w, tmp, answers)
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = ap.main(["--evals-dir", str(d), *flags])
        return code, out.getvalue(), err.getvalue()


class Constants(unittest.TestCase):
    def test_the_constants_name_the_cells_tasks_runs_and_judges_of_the_pre_registration(self):
        self.assertEqual(ap.PLAN, {(Q1C, "design-02"): 6, (Q1H, "design-02"): 3, (SXP, "design-02"): 3,
                                   (SXP, "synthesis"): 3, (SHP, "design-02"): 3, (SHP, "synthesis"): 3})
        self.assertEqual(ap.ROWS, {"design-02": (D2,), "synthesis": SYNTH_TASKS})
        self.assertEqual(sum(n * len(ap.ROWS[row]) for (_, row), n in ap.PLAN.items()), 33)
        self.assertEqual(ap.JUDGES, {"design-02": (J1, J2), "synthesis": (J1,)})
        self.assertEqual(ap.BASELINE_CELLS, (OX, OH, SX))


class Baselines(unittest.TestCase):
    def test_baselines_and_thresholds_come_from_the_stored_runs_and_use_the_unrounded_mean(self):
        an = analyse(baselines(World()))
        ox, oxs = an["summary"][(OX, "design-02")], an["summary"][(OX, "synthesis")]
        self.assertAlmostEqual(ox["handled"], 25 / 6)
        self.assertEqual((ox["passing"], ox["violating"], ox["scored"]), (2, 0, 6))
        self.assertAlmostEqual(ox["cost"], (5 * 2.0 + 2.6) / 6)
        self.assertAlmostEqual(ox["time_s"], 600)
        self.assertAlmostEqual(an["summary"][(OH, "design-02")]["handled"], 10 / 3)
        self.assertEqual(an["summary"][(SX, "synthesis")]["missed"], 9)
        th = an["thresholds"]
        self.assertAlmostEqual(th["q1"]["better_at_least"], 25 / 6 + 1)       # 5.1667, not 4.17 + 1 = 5.17
        self.assertAlmostEqual(th["q1"]["worse_at_most"], 25 / 6 - 1)
        self.assertAlmostEqual(th["q1"]["second_look_supports_at"], 10 / 3 + 1)
        self.assertAlmostEqual(th["q2"]["design-02"]["cheaper_at_most"], 2.1 * 0.75)
        self.assertAlmostEqual(th["q2"]["design-02"]["faster_at_most"], 540)
        self.assertAlmostEqual(th["q2"]["design-02"]["slower_above"], 660)
        self.assertAlmostEqual(th["q2"]["design-02"]["near_handled_at_least"], 25 / 6 - 0.5)
        self.assertAlmostEqual(th["q2"]["synthesis"]["cheaper_at_most"], 1.8)
        self.assertAlmostEqual(oxs["time_s"], 500)

    def test_before_any_run_of_the_four_cells_the_tool_prints_baselines_thresholds_and_pending(self):
        code, out, _ = cli(baselines(World()))
        self.assertEqual(code, 3)
        self.assertIn("handled 4.17; 2 of 6 pass", out)
        self.assertIn("Q1 better: mean handled >= 5.17 (stored 4.1667 + 1.0)", out)
        self.assertIn("PENDING", out)
        self.assertIn("python3 evals/evalkit.py run --rows design-decision --tasks design-02 "
                      f"--cells {Q1C} --repeats 6", out)
        self.assertIn("python3 evals/evalkit.py run --rows synthesize --tasks synthesize-01,synthesize-02,"
                      f"synthesize-03 --cells {SXP} --repeats 3", out)
        self.assertTrue(all("--tasks" in l for l in out.splitlines() if "evalkit.py run" in l or "evalkit.py judge" in l))

    def test_runs_with_an_old_task_hash_are_not_counted(self):
        w = baselines(World())
        w.design(OX, 7, handled=0, task_hash="old-hash")
        self.assertAlmostEqual(analyse(w)["summary"][(OX, "design-02")]["handled"], 25 / 6)


class Question1(unittest.TestCase):
    def test_q1_is_better_when_handled_is_at_least_one_above_the_unrounded_mean_four_pass_and_none_violates(self):
        # mean 31/6 = exactly the stored 25/6 + 1.0; it would miss a threshold built from the rounded 4.17
        w = q1_world(handled=(5, 5, 5, 5, 5, 6), passed=(True,) * 4 + (False,) * 2)
        self.assertEqual(analyse(w)["q1"]["verdict"], "better, cause not separated")

    def test_q1_is_no_difference_just_under_plus_one_or_with_three_passing_or_one_violation(self):
        just_under = q1_world(handled=(5, 5, 5, 5, 5, 5.9), passed=(True,) * 6)
        three_pass = q1_world(handled=(6,) * 6, passed=(True,) * 3 + (False,) * 3)
        one_violates = q1_world(handled=(6,) * 6, passed=(True,) * 6, violated=(1,) + (0,) * 5)
        for w in (just_under, three_pass, one_violates):
            self.assertEqual(analyse(w)["q1"]["verdict"], "no difference shown")

    def test_q1_is_worse_at_exactly_one_below_the_stored_mean_and_not_just_above_it(self):
        # mean 19/6 = exactly 25/6 - 1.0
        self.assertEqual(analyse(q1_world(handled=(3, 3, 3, 3, 3, 4)))["q1"]["verdict"], "worse")
        self.assertEqual(analyse(q1_world(handled=(3, 3, 3, 3, 3, 4.1)))["q1"]["verdict"], "no difference shown")
        # the same tie on means that are exact in binary, so float rounding cannot decide it
        six = {"complete": True, "slots": 6, "scored": 6, "answered": 6, "passing": 0, "violating": 0}
        self.assertEqual(ap.q1_verdict({**six, "handled": 3.0}, 4.0)["verdict"], "worse")
        self.assertEqual(ap.q1_verdict({**six, "handled": 3.25}, 4.0)["verdict"], "no difference shown")

    def test_q1_is_worse_with_two_violating_runs_and_not_with_one(self):
        two = q1_world(handled=(6,) * 6, passed=(True,) * 6, violated=(1, 1, 0, 0, 0, 0))
        self.assertEqual(analyse(two)["q1"]["verdict"], "worse")
        one = q1_world(violated=(1, 0, 0, 0, 0, 0))
        self.assertEqual(analyse(one)["q1"]["verdict"], "no difference shown")

    def test_q1_is_not_decided_when_the_advisor_answered_in_three_of_six_even_when_better_holds(self):
        w = q1_world(handled=(6,) * 6, passed=(True,) * 6, answered=(True,) * 3 + (False,) * 3)
        q1 = analyse(w)["q1"]
        self.assertEqual(q1["verdict"], "not decided")
        self.assertIn("3 of 6", q1["why"])
        w4 = q1_world(handled=(6,) * 6, passed=(True,) * 6, answered=(True,) * 4 + (False,) * 2)
        self.assertEqual(analyse(w4)["q1"]["verdict"], "better, cause not separated")

    def test_the_second_look_supports_a_better_at_the_stored_high_mean_plus_one_and_changes_no_verdict(self):
        w = q1_world()
        for rep, h in enumerate((4, 4, 5), 1):          # 13/3 = exactly the stored 10/3 + 1.0
            w.design(Q1H, rep, handled=h)
        an = analyse(w)
        self.assertIs(an["second_look"]["supports"], True)
        self.assertEqual(an["q1"]["verdict"], "no difference shown")
        w2 = q1_world()
        for rep, h in enumerate((4, 4, 4.9), 1):
            w2.design(Q1H, rep, handled=h)
        self.assertIs(analyse(w2)["second_look"]["supports"], False)


class Scoring(unittest.TestCase):
    def test_a_violation_counts_only_when_one_judge_says_so_in_both_of_its_passes(self):
        w = World()
        w.design(OX, 1, per_pass={(J1, 0): {"violated": 1}, (J2, 1): {"violated": 1}})   # split under each judge
        w.design(OX, 2, per_pass={(J2, 0): {"violated": 1}, (J2, 1): {"violated": 2}})   # one judge, both passes
        s = analyse(w)["summary"][(OX, "design-02")]
        self.assertEqual(s["violating"], 1)

    def test_a_design_run_passes_unless_one_judge_fails_it_in_both_passes_and_handled_is_the_mean_of_four(self):
        w = World()
        w.design(OX, 1, passed=True, per_pass={(J1, 0): {"passed": False}, (J2, 1): {"passed": False}})
        w.design(OX, 2, passed=True, per_pass={(J2, 0): {"passed": False}, (J2, 1): {"passed": False}})
        w.design(OX, 3, handled=3, per_pass={(J1, 0): {"handled": 6}, (J2, 1): {"handled": 4}})
        an = analyse(w)
        units = {u["repeat"]: u["score"] for u in an["units"][(OX, "design-02")]}
        self.assertEqual((units[1]["passes"], units[2]["passes"], units[3]["passes"]), (True, False, False))
        self.assertAlmostEqual(units[3]["handled"], (6 + 3 + 3 + 4) / 4)
        self.assertAlmostEqual(units[3]["handled_by_judge"][J1], 4.5)

    def test_a_synthesis_run_passes_when_both_passes_pass_misses_by_the_lower_found_and_invents_on_either_pass(self):
        w = World()
        w.synth(OX, S1, 1, found=(6, 4), passed=(True, False))
        w.synth(OX, S1, 2, fabricated=(0, 1))
        s = analyse(w)["summary"][(OX, "synthesis")]
        self.assertEqual((s["passing"], s["missed"], s["inventing"]), (1, 2, 1))


class Question2(unittest.TestCase):
    def q2(self, w, cell=SXP, row="synthesis"):
        return analyse(w)["q2"][(cell, row)]

    def test_cost_is_cheaper_at_75_percent_cheaper_by_less_than_a_quarter_up_to_100_and_not_cheaper_above(self):
        # Opus synthesis mean cost is 2.4: 75% is 1.8, 100% is 2.4
        self.assertEqual(self.q2(q2_world(cost=1.8))["cost"], "cheaper")
        self.assertEqual(self.q2(q2_world(cost=1.81))["cost"], "cheaper by less than a quarter")
        self.assertEqual(self.q2(q2_world(cost=2.4))["cost"], "cheaper by less than a quarter")
        self.assertEqual(self.q2(q2_world(cost=2.41))["cost"], "not cheaper")

    def test_time_is_faster_at_90_percent_about_the_same_up_to_110_and_slower_above(self):
        # Opus synthesis mean time is 500 s: 90% is 450 s, 110% is 550 s
        self.assertEqual(self.q2(q2_world(secs=450))["time"], "faster")
        self.assertEqual(self.q2(q2_world(secs=451))["time"], "about the same")
        self.assertEqual(self.q2(q2_world(secs=550))["time"], "about the same")
        self.assertEqual(self.q2(q2_world(secs=551))["time"], "slower")

    def test_near_on_synthesis_needs_every_run_to_pass_no_invention_and_at_most_one_missed(self):
        self.assertIs(self.q2(q2_world(synth={(S1, 1): {"found": (5, 6)}}))["near"], True)
        self.assertIs(self.q2(q2_world(synth={(S1, 1): {"found": (5, 6)}, (S2, 1): {"found": (6, 5)}}))["near"], False)
        self.assertIs(self.q2(q2_world(synth={(S1, 1): {"fabricated": (0, 1)}}))["near"], False)
        self.assertIs(self.q2(q2_world(synth={(S1, 1): {"passed": (True, False)}}))["near"], False)

    def test_near_on_design_needs_handled_at_most_half_below_the_unrounded_mean_and_no_violation(self):
        # stored 25/6; near from 25/6 - 0.5 = 11/3 on
        self.assertIs(self.q2(q2_world(design={1: {"handled": 3}, 2: {"handled": 4}, 3: {"handled": 4}}),
                              row="design-02")["near"], True)
        self.assertIs(self.q2(q2_world(design={1: {"handled": 2.9}, 2: {"handled": 4}, 3: {"handled": 4}}),
                              row="design-02")["near"], False)
        self.assertIs(self.q2(q2_world(design={1: {"handled": 6, "violated": 1}}), row="design-02")["near"], False)

    def test_a_row_is_not_decided_below_two_thirds_answered_and_its_statements_are_still_reported(self):
        q = self.q2(q2_world(answered=5))
        self.assertEqual((q["verdict"], q["decided"], q["cost"], q["time"], q["near"]),
                         ("not decided", False, "cheaper", "faster", True))
        self.assertIs(q["asked"], False)
        self.assertEqual(self.q2(q2_world(answered=6))["verdict"], "does what the owner asked")
        d = self.q2(q2_world(answered=1), row="design-02")
        self.assertEqual(d["verdict"], "not decided")
        self.assertEqual(self.q2(q2_world(answered=2), row="design-02")["verdict"], "does what the owner asked")

    def test_the_pair_does_what_the_owner_asked_only_when_cheaper_faster_and_near_all_hold(self):
        self.assertIs(self.q2(q2_world())["asked"], True)
        for w in (q2_world(cost=2.0), q2_world(secs=460), q2_world(synth={(S1, 1): {"fabricated": (1, 1)}})):
            q = self.q2(w)
            self.assertIs(q["asked"], False)
            self.assertEqual(q["verdict"], "does not do what the owner asked")

    def test_the_sonnet_high_cell_is_judged_on_its_own_rows(self):
        q = analyse(q2_world(cell=SHP, cost=3.0))["q2"][(SHP, "design-02")]
        self.assertEqual(q["cost"], "not cheaper")


class Slots(unittest.TestCase):
    def test_a_slot_with_three_invalid_attempts_is_a_failed_run_at_the_time_limit_with_cost_left_out(self):
        w = q2_world(row="design")
        w.drop(SXP, D2, 3)
        for _ in range(3):
            w.attempt(SXP, D2, 3, valid=False, reason="timeout", cost=None, secs=None)
        an = analyse(w)
        s = an["summary"][(SXP, "design-02")]
        self.assertEqual((s["failed_slots"], s["decided"], s["passing"], s["answered"], s["cost_n"]), (1, 3, 0, 2, 2))
        self.assertAlmostEqual(s["handled"], (4 + 4 + 0) / 3)
        self.assertAlmostEqual(s["time_s"], (300 + 300 + 1800) / 3)
        self.assertAlmostEqual(s["cost"], 1.0)
        self.assertEqual(an["q2"][(SXP, "design-02")]["verdict"], "does not do what the owner asked")

    def test_a_failed_synthesis_slot_misses_every_reference_item_of_its_task(self):
        w = q2_world(row="synthesis")
        w.drop(SXP, S2, 1)
        for _ in range(3):
            w.attempt(SXP, S2, 1, valid=False, reason="timeout", cost=None, secs=None)
        s = analyse(w)["summary"][(SXP, "synthesis")]
        self.assertEqual((s["missed"], s["passing"]), (6, 8))

    def test_a_slot_with_two_invalid_attempts_is_not_run_yet_and_makes_the_result_pending_exit_3(self):
        w = full_world()
        w.drop(SHP, S3, 2)
        w.attempt(SHP, S3, 2, valid=False, reason="timeout", cost=None)
        w.attempt(SHP, S3, 2, valid=False, reason="timeout", cost=None)
        for _ in range(3):                               # API errors never use up a retry
            w.attempt(SHP, S3, 2, valid=False, reason="is_error", api_error_status=429, cost=0.0)
        an = analyse(w)
        self.assertEqual(an["status"], "PENDING")
        self.assertEqual(an["q2"][(SHP, "synthesis")]["verdict"], "PENDING")
        self.assertEqual(an["q2"][(SXP, "synthesis")]["verdict"], "does what the owner asked")
        code, out, _ = cli(w)
        self.assertEqual(code, 3)
        self.assertIn(f"{SHP} synthesis: 1 slot(s) not run yet: {S3} #2", out)
        self.assertIn("python3 evals/evalkit.py run --rows synthesize --tasks synthesize-01,synthesize-02,"
                      f"synthesize-03 --cells {SHP} --repeats 3", out)

    def test_a_complete_world_exits_0_with_one_verdict_line_per_rule(self):
        code, out, _ = cli(full_world())
        self.assertEqual(code, 0)
        self.assertNotIn("PENDING", out)
        self.assertIn(f"Question 1, {Q1C}: no difference shown", out)
        self.assertIn(f"Question 2, {SXP}, synthesis: does what the owner asked; cheaper; faster; near in quality", out)
        self.assertEqual(sum(1 for l in out.splitlines() if l.startswith("  Question ")), 6)

    def test_a_missing_judge_pass_makes_the_result_pending_names_it_and_prints_the_second_judge_command(self):
        w = full_world()
        w.scores = [s for s in w.scores if s["grader_id"] != f"judge:{J2}:r1:1" or s["run_id"] != w.rid(Q1C, D2, 4)]
        an = analyse(w)
        self.assertEqual((an["status"], an["q1"]["verdict"]), ("PENDING", "PENDING"))
        code, out, _ = cli(w)
        self.assertEqual(code, 3)
        self.assertIn(f"{Q1C} {D2} #4: judge {J2} pass 1 missing", out)
        self.assertIn(f"python3 evals/evalkit.py judge --rows design-decision --tasks design-02 --cells {Q1C} "
                      f"--judge-cell {J2}", out)

    def test_scores_of_one_judge_under_two_rubric_hashes_make_the_result_pending(self):
        w = full_world()
        w.score(w.rid(SXP, D2, 2), J1, 0, False, rubric="r2", handled=1, violated=0)
        an = analyse(w)
        self.assertEqual(an["status"], "PENDING")
        self.assertEqual(an["q2"][(SXP, "design-02")]["verdict"], "PENDING")
        self.assertEqual(an["pending"]["mixed"], [(SXP, D2, 2, J1)])
        code, out, _ = cli(w)
        self.assertEqual(code, 3)
        self.assertIn("more than one rubric hash", out)

    def test_a_failed_slot_takes_the_tests_own_time_limit_and_cap_whatever_harness_json_says_now(self):
        w = q2_world(row="design")
        w.drop(SXP, D2, 3)
        for _ in range(3):
            w.attempt(SXP, D2, 3, valid=False, reason="timeout", cost=None, secs=None)
        data = w.data()
        data["limits"] = {"timeout_s": 1200.0, "cap_usd": 6.0}        # harness.json after the limits went back
        an = ap.analyse(data)
        self.assertAlmostEqual(an["summary"][(SXP, "design-02")]["time_s"], (300 + 300 + 1800) / 3)
        self.assertAlmostEqual(an["spend"]["bound_usd"], an["spend"]["known_usd"] + 3 * 10.0)
        self.assertEqual((an["limits"], an["harness_limits"]),
                         ({"timeout_s": 1800.0, "cap_usd": 10.0}, {"timeout_s": 1200.0, "cap_usd": 6.0}))
        text = ap.render(an)
        self.assertIn("harness.json now has 1200 s and $6 a run", text)
        self.assertIn("1800 s and $10", text)
        self.assertNotIn("harness.json now has", ap.render(analyse(w)))    # same limits: no note

    def test_a_failed_slot_lists_the_time_and_reason_of_each_counted_attempt(self):
        w = q2_world(row="design")
        w.drop(SXP, D2, 3)
        w.attempt(SXP, D2, 3, valid=False, reason="timeout", cost=None, secs=None, ts="2026-11-14T16:00:00Z")
        w.attempt(SXP, D2, 3, valid=False, reason="is_error", cost=None, secs=None, ts="2026-11-14T16:10:00Z",
                  api_error_status=529)                                  # an API error: not counted, not listed
        w.attempt(SXP, D2, 3, valid=False, reason="json_parse", cost=0.4, secs=100, ts="2026-11-14T16:20:00Z")
        w.attempt(SXP, D2, 3, valid=False, reason="timeout", cost=None, secs=None, ts="2026-11-14T16:50:00Z")
        an = analyse(w)
        self.assertEqual(an["failed_slots"], [{"cell": SXP, "task": D2, "repeat": 3, "attempts": [
            {"ts": "2026-11-14T16:00:00Z", "reason": "timeout"},
            {"ts": "2026-11-14T16:20:00Z", "reason": "json_parse"},
            {"ts": "2026-11-14T16:50:00Z", "reason": "timeout"}]}])
        text = ap.render(an)
        self.assertIn(f"{SXP} {D2} #3: timeout at 2026-11-14T16:00:00Z; json_parse at 2026-11-14T16:20:00Z; "
                      "timeout at 2026-11-14T16:50:00Z", text)
        self.assertIn("connection log", text)
        self.assertEqual(analyse(full_world())["failed_slots"], [])
        self.assertNotIn("Failed slots.", ap.render(analyse(full_world())))

    def test_a_pair_run_judged_under_another_rubric_than_the_stored_baselines_makes_the_result_pending(self):
        w = full_world()
        rid = w.rid(SXP, D2, 2)
        w.scores = [s for s in w.scores if s["run_id"] != rid]
        for j in (J1, J2):
            for i in (0, 1):
                w.score(rid, j, i, False, rubric="r2" if j == J2 else "r1", handled=4, violated=0)
        an = analyse(w)
        self.assertEqual(an["pending"]["other_rubric"], [(SXP, D2, 2, J2)])   # only the judge whose hash differs
        self.assertEqual(an["pending"]["mixed"], [])
        self.assertEqual(an["status"], "PENDING")
        code, out, _ = cli(w)
        self.assertEqual(code, 3)
        self.assertIn(f"{SXP} {D2} #2: judge {J2} scored it under another rubric than the stored baselines", out)
        self.assertEqual(analyse(full_world())["pending"]["other_rubric"], [])
        self.assertEqual(analyse(full_world())["status"], "DECIDED")

    def test_an_unreadable_input_exits_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = write(baselines(World()), tmp)
            (d / "results" / "runs.jsonl").write_text("{not json\n", encoding="utf-8")
            err = io.StringIO()
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
                self.assertEqual(ap.main(["--evals-dir", str(d)]), 2)
            self.assertIn("not JSON", err.getvalue())


class AdvisorStatus(unittest.TestCase):
    RUN = {"run_id": "r", "advisor_called": False}

    def status(self, result=None, block="the answer", called=False, file=True):
        answers = {"r": {"result": result, "block": block}} if file else {}
        return ap.advisor_status({"run_id": "r", "advisor_called": called}, answers)

    def test_the_advisor_answered_when_its_model_shows_in_the_run_usage_whatever_the_text_says(self):
        self.assertEqual(self.status("ADVISOR: failed\n===ANSWER===\nx\n===END===", called=True)["status"], "answered")
        self.assertEqual(self.status(called=True, file=False)["status"], "answered")

    def test_each_status_line_before_the_answer_block_gives_its_status(self):
        self.assertEqual(self.status("Done.\nADVISOR: failed\n===ANSWER===\nx\n===END===")["status"], "failed")
        self.assertEqual(self.status("Done.\nADVISOR: not called\n===ANSWER===\nx")["status"], "not called")
        line_after = self.status("ADVISOR: not called\n===ANSWER===\nADVISOR: failed\n===END===")
        self.assertEqual(line_after["status"], "not called")          # only text before the block counts

    def test_answered_in_the_status_line_without_advisor_usage_is_failed_and_counted_as_claimed(self):
        s = self.status("ADVISOR: answered\n===ANSWER===\nx")
        self.assertEqual((s["status"], s["claimed"]), ("failed", True))
        w = q2_world(row="design", answered=2)
        w.answer(SXP, D2, 3, "**ADVISOR: answered**\n===ANSWER===\nx\n===END===")
        s = analyse(w)["summary"][(SXP, "design-02")]
        self.assertEqual((s["claimed"], s["statuses"]["failed"], s["statuses"]["answered"]), (1, 1, 2))

    def test_free_text_naming_the_advisor_with_a_failure_word_gives_failed_and_otherwise_not_called(self):
        for text in ("The advisor call timed out, so I went on alone.", "advisor: error 529",
                     "Danışman çağrısı zaman aşımına uğradı.", "The Advisor was unavailable."):
            self.assertEqual(self.status(text + "\n===ANSWER===\nx")["status"], "failed", text)
        for text in ("I asked the advisor and agreed with it.", "The build failed twice.", "", None):
            self.assertEqual(self.status(text and text + "\n===ANSWER===\nx")["status"], "not called", text)

    def test_with_no_answer_file_the_status_is_unknown_even_with_no_answers_folder(self):
        self.assertEqual(self.status(file=False)["status"], "unknown")
        w = q2_world(row="design", answered=1)
        w.answer(SXP, D2, 2, "ADVISOR: failed\n===ANSWER===\nx")
        s = analyse(w)["summary"][(SXP, "design-02")]["statuses"]
        self.assertEqual((s["answered"], s["failed"], s["unknown"]), (1, 1, 1))
        code, out, _ = cli(w, answers=False)
        self.assertIn("answered 1, failed 0, not called 0, unknown 2", out)

    def test_a_status_line_inside_the_answer_block_is_counted(self):
        s = self.status("ADVISOR: not called\n===ANSWER===\nADVISOR: answered\nx", block="ADVISOR: answered\nx")
        self.assertIs(s["in_block"], True)
        self.assertIs(self.status("ADVISOR: not called\n===ANSWER===\nx", block="x\nno status here")["in_block"], False)
        w = q2_world(row="design", answered=3)
        w.answer(SXP, D2, 1, "===ANSWER===\n  ADVISOR: answered\nx\n===END===", block="ADVISOR: answered\nx")
        self.assertEqual(analyse(w)["summary"][(SXP, "design-02")]["in_block"], 1)


class Reporting(unittest.TestCase):
    def test_the_report_never_contains_text_from_an_answer_file(self):
        w = q2_world(answered=0)
        for task in SYNTH_TASKS:
            for rep in (1, 2, 3):
                w.answer(SXP, task, rep, f"{SECRET}\nADVISOR: failed\n===ANSWER===\n{SECRET}\n===END===",
                         block=f"ADVISOR: failed\n{SECRET}")
        w.answer(SXP, D2, 1, f"The advisor timed out. {SECRET}\n===ANSWER===\n{SECRET}", block=SECRET)
        for flags in ((), ("--json",)):
            code, out, err = cli(w, *flags)
            self.assertNotIn("ZEBRA", out + err)
            self.assertNotIn("PLUM", out + err)
        js = json.loads(cli(w, "--json")[1])
        self.assertEqual(js["summary"][f"{SXP}|synthesis"]["statuses"]["failed"], 9)

    def test_the_advisor_share_of_cost_the_status_counts_and_the_spend_are_reported(self):
        w = q2_world(row="design", answered=2)
        w.attempt(SXP, S1, 1, valid=False, reason="timeout", cost=None, secs=None)
        w.attempt(SXP, S1, 1, valid=False, reason="is_error", cost=0.5)
        an = analyse(w)
        self.assertAlmostEqual(an["advisor_cost"]["mean_usd"], 0.3)
        self.assertAlmostEqual(an["advisor_cost"]["share"], 0.3)
        self.assertEqual((an["spend"]["attempts"], an["spend"]["unknown_cost_attempts"]), (5, 1))
        self.assertAlmostEqual(an["spend"]["known_usd"], 3.5)
        self.assertAlmostEqual(an["spend"]["bound_usd"], 13.5)
        js = json.loads(cli(w, "--json")[1])
        self.assertEqual(js["status"], "PENDING")
        self.assertAlmostEqual(js["spend"]["known_usd"], 3.5)


if __name__ == "__main__":
    unittest.main()
