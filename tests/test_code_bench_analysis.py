"""evals/probes/code_bench_analysis.py applies the rules of the 2026-11-14 coding pre-registration to the public
record of code_bench.py. These tests build synthetic record lines in memory (or in a temp file for the command
line); the real record and evals/private are never read. No model, no network."""

import contextlib
import importlib.util
import io
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
# Red-proof runs point this at a mutated copy, so the real file is never edited.
SRC = Path(os.environ.get("CODE_BENCH_ANALYSIS_UNDER_TEST") or ROOT / "evals" / "probes" / "code_bench_analysis.py")
_spec = importlib.util.spec_from_file_location("code_bench_analysis_under_test", SRC)
an = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = an
_spec.loader.exec_module(an)

TASKS = ("code-01", "code-02", "code-03", "code-04", "code-05", "code-06")
HM, HH, SL, SM, OH = "haiku-5-5@medium", "haiku-5-5@high", "sonnet-5-5@low", "sonnet-5-5@medium", "opus-5-5@high"
TS_H, TS_X, TO_M, TO_H = "sonnet-5-5@high", "sonnet-5-5@xhigh", "opus-5-5@medium", "opus-5-5@high"
# The rules' tables, typed here from the rules file (not from the code under test).
RULES_C_PLAN = {HM: ("AB", 4), HH: ("ABC", 4), SL: ("AB", 3), SM: ("B", 3), OH: ("B", 1)}
RULES_T_CELLS = (TS_H, TS_X, TO_M, TO_H)
TS = "2026-11-14T20:00:00Z"


class Rec:
    """Synthetic public lines, in the shapes code_bench.py writes."""

    def __init__(self):
        self.lines = []

    def model(self, step, task, cell, arm, run, try_, attempt=1, cost=0.25, infra=False, unknown=False, ms=1000):
        self.lines.append({"kind": "model", "step": step, "task": task, "cell": cell, "arm": arm, "run": run,
                           "try": try_, "attempt": attempt, "valid": not infra, "reason": "is_error" if infra else None,
                           "infra": infra, "cost_usd": None if unknown else cost, "cost_unknown": unknown,
                           "duration_ms": ms, "input_tokens": 1, "output_tokens": 1, "cache_read_tokens": 0,
                           "num_turns": 1, "denials": 0, "files_changed": 1, "files_dropped": 0,
                           "cli_version": "2.1.325", "ts": TS})

    def check(self, step, task, what, result, cell=None, arm=None, run=None, try_=None, suite=None):
        self.lines.append({"kind": "check", "step": step, "task": task, "cell": cell, "arm": arm, "run": run,
                           "try": try_, "what": what, "suite": suite, "result": result, "tests": 1, "failed": 0,
                           "seconds": 0.5, "ts": TS})

    # step T, fit, given
    def t_run(self, task, cell, run, words=("fail",), cost=1.0, ms=60000):
        for i, w in enumerate(words, 1):
            self.model("T", task, cell, None, run, i, cost=cost, ms=ms)
            self.check("T", task, "red_first", w, cell=cell, run=run, try_=i, suite=f"{cell}#{run}")

    def fit(self, task, cell, run, fit=True):
        sid = f"{cell}#{run}"
        self.check("fit", task, "fit_start", "fail" if fit else "pass", cell=cell, run=run, try_=1, suite=sid)
        if fit:
            for k in (1, 2):
                self.check("fit", task, "fit_reference", "pass", cell=cell, run=run, try_=k, suite=sid)

    def given(self, task, suite=TS_H + "#1"):
        cell, run = (suite.split("#")[0], int(suite.split("#")[1])) if suite else (None, None)
        self.check("fit", task, "given", "pass" if suite else "fail", cell=cell, run=run, suite=suite)

    # step C
    def c_run(self, task, cell, arm, run, kind="first", cost=0.25):
        """kind: arm A: "pass" | "fail"; arms B and C: "first" (check pass, hidden pass at try 1),
        "second" (fail/fail, then pass/pass), "escaped" (check pass, hidden fail), "unf" (three tries, check
        and hidden fail), "unf_ok" (three tries, check fail, hidden pass)."""
        if arm == "A":
            self.model("C", task, cell, "A", run, 1, cost=cost)
            self.check("C", task, "hidden", "pass" if kind == "pass" else "fail", cell=cell, arm="A", run=run, try_=1)
            return
        what = "given" if arm == "B" else "own"
        plan = {"first": [("pass", "pass")], "second": [("fail", "fail"), ("pass", "pass")],
                "escaped": [("pass", "fail")], "unf": [("fail", "fail")] * 3, "unf_ok": [("fail", "pass")] * 3}[kind]
        for i, (chk, hid) in enumerate(plan, 1):
            self.model("C", task, cell, arm, run, i, cost=cost)
            self.check("C", task, what, chk, cell=cell, arm=arm, run=run, try_=i)
            self.check("C", task, "hidden", hid, cell=cell, arm=arm, run=run, try_=i)

    def fill(self, cell, arm, kinds, tasks=TASKS, cost=0.25):
        """kinds: one kind for every run, or a list of kinds per task (each a list over the runs)."""
        runs = RULES_C_PLAN[cell][1]
        for ti, task in enumerate(tasks):
            for n in range(1, runs + 1):
                k = kinds if isinstance(kinds, str) else kinds[ti][n - 1]
                c = cost if not callable(cost) else cost(k)
                self.c_run(task, cell, arm, n, k, cost=c)

    def copy(self, task, cell, arm, run, word="changed"):
        self.check("cross", task, "copy", word, cell=cell, arm=arm, run=run)

    def cross(self, task, suite, cell, arm, run, result):
        self.check("cross", task, "cross", result, cell=cell, arm=arm, run=run, suite=suite)


def flat(per_task_counts, kind_yes, kind_no, runs):
    """Per task, `k` runs of kind_yes then runs - k of kind_no."""
    return [[kind_yes] * k + [kind_no] * (runs - k) for k in per_task_counts]


def givens(rec, tasks=TASKS, none=()):
    for t in TASKS:
        if t in tasks:
            rec.given(t, None if t in none else TS_H + "#1")


def analyse(rec, cut=None, stop=an.STOP_USD):
    return an.analyse(rec.lines, an.parse_cut(cut or []), stop)


def cli(tmp_path, lines, *args):
    path = tmp_path / "code-runs.jsonl"
    path.write_text("".join(json.dumps(x) + "\n" for x in lines), encoding="utf-8")
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = an.main(["--results", str(path), *args])
    return code, out.getvalue(), err.getvalue()


# -- the plan ----------------------------------------------------------------------------------------

def test_the_planned_runs_are_the_rules_tables():
    a = an.analyse([])
    assert a["planned"] == {"T": 48, "C": 180, "C_A": 66, "C_B": 90, "C_C": 24}
    assert an.T_CELLS == RULES_T_CELLS and an.TASKS == TASKS
    assert {c: ("".join(arms), n) for c, arms, n in an.C_PLAN} == RULES_C_PLAN
    assert an.Q1_CELLS == (HM, HH, SL, SM) and an.REFERENCE_CELL == OH and an.Q3_CELL == HH
    assert an.Q2_THRESHOLD == {HM: 15.0, HH: 15.0, SL: 30.0}
    assert (an.STOP_USD, an.UNKNOWN_COST_USD) == (224.0, 6.0)


def test_an_empty_record_runs_and_says_what_is_pending(tmp_path):
    code, out, err = cli(tmp_path, [])
    assert code == 3 and err == ""
    assert "step T: 48 run(s) not ended" in out and "step C: 180 run(s) not ended" in out
    assert "given suite not fixed for: code-01, code-02, code-03, code-04, code-05, code-06" in out
    assert "Spend: $0.00 over 0 model process(es)" in out and "Status: PENDING" in out
    for q in ("Question 1: PENDING", "Question 2: PENDING", "Question 4: PENDING"):
        assert q in out
    assert "Question 3, haiku-5-5@high: PENDING" in out
    missing = tmp_path / "none.jsonl"
    assert an.main(["--results", str(missing)]) == 3


def test_an_unreadable_record_exits_2_without_a_path(tmp_path):
    code, out, err = cli(tmp_path, [])
    (tmp_path / "code-runs.jsonl").write_text('{"kind": "model"}\nnot json\n', encoding="utf-8")
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = an.main(["--results", str(tmp_path / "code-runs.jsonl")])
    assert code == 2 and err.getvalue().strip() == "code_bench_analysis: error: line 2 of the record is not JSON"
    assert str(tmp_path) not in err.getvalue()
    (tmp_path / "code-runs.jsonl").write_text('[1, 2]\n', encoding="utf-8")
    assert an.main(["--results", str(tmp_path / "code-runs.jsonl")]) == 2


# -- a whole experiment ------------------------------------------------------------------------------

def full_world(t_spec=None, a_kind="fail", c_kind="first", b_kind="first", with_cross=True, none=()):
    """Every planned run ended. Step T: every suite fit unless t_spec says otherwise ({cell: [12 tuples of
    (fit, catches, rejects)]}). Step C: arm A copies not correct, arm C copies correct. Cross: every fit
    suite on every copy of arms A and C; a suite that catches fails on the wrong copies, one that rejects
    fails on the right ones."""
    r = Rec()
    spec = {c: (t_spec or {}).get(c, [(True, True, False)] * 12) for c in RULES_T_CELLS}
    for ti, t in enumerate(TASKS):
        for c in RULES_T_CELLS:
            for run in (1, 2):
                fit, _, _ = spec[c][ti * 2 + run - 1]
                r.t_run(t, c, run, words=("fail",))
                r.fit(t, c, run, fit=fit)
    givens(r, none=none)
    for cell, (arms, runs) in RULES_C_PLAN.items():
        for arm in arms:
            for t in TASKS:
                if arm != "A" and t in none:
                    continue
                for n in range(1, runs + 1):
                    r.c_run(t, cell, arm, n, a_kind if arm == "A" else (c_kind if arm == "C" else b_kind))
    if with_cross:
        for ti, t in enumerate(TASKS):
            copies = [(c, a, n) for c, (arms, runs) in RULES_C_PLAN.items() for a in arms if a in "AC"
                      for n in range(1, runs + 1) if not (a == "C" and t in none)]
            for c, a, n in copies:
                r.copy(t, c, a, n)
            for wc in RULES_T_CELLS:
                for run in (1, 2):
                    fit, catches, rejects = spec[wc][ti * 2 + run - 1]
                    if not fit:
                        continue
                    for c, a, n in copies:
                        correct = (a == "C" and c_kind in ("first", "second", "unf_ok")) or (a == "A" and a_kind == "pass")
                        fails = rejects if correct else catches
                        r.cross(t, f"{wc}#{run}", c, a, n, "fail" if fails else "pass")
    return r


def test_a_complete_record_is_decided_and_exits_0(tmp_path):
    code, out, err = cli(tmp_path, full_world().lines)
    assert code == 0 and "Status: DECIDED" in out and "PENDING" not in out
    code, out, _ = cli(tmp_path, full_world().lines, "--json")
    j = json.loads(out)
    assert code == 0 and j["status"] == "DECIDED" and j["q1"]["balanced"] == HM and j["q4"]["fast"] == TS_H


# -- in every question --------------------------------------------------------------------------------

def q1_world(spec, tasks=TASKS):
    """spec: {cell: (kinds, cost)} for arm B of the four cells; every task has a given suite."""
    r = Rec()
    givens(r)
    for cell, (kinds, cost) in spec.items():
        r.fill(cell, "B", kinds, tasks=tasks, cost=cost)
    return r


def test_a_cell_with_no_run_in_the_arm_is_never_named_and_a_cut_cell_is_not_pending():
    r = q1_world({HM: ("first", 1.0), HH: ("first", 1.0), SL: ("first", 1.0)})
    a = analyse(r, cut=["sonnet-5-5@medium"])
    q = a["q1"]
    assert q["verdict"] == "decided" and q["cells"][SM]["runs"] == 0
    assert SM not in (q["fast"], q["balanced"])
    assert len(a["left"]["cut"]) == 18 and all(k[1] == SM for k in a["left"]["cut"])
    assert "Question 1, sonnet-5-5@medium: no run in arm B; never named" in an.render(a)
    assert analyse(r)["q1"]["verdict"] == an.PENDING                    # not cut: its runs are pending


def test_a_cell_with_no_correct_run_is_never_named_and_the_report_says_no_cell():
    r = q1_world({HM: ("unf", 0.1), HH: ("escaped", 0.2), SL: ("unf", 0.3), SM: ("unf", 0.4)})
    q = analyse(r)["q1"]
    assert q["verdict"] == "decided" and q["fast"] is None and q["balanced"] is None
    text = an.render(analyse(r))
    assert "Question 1, fast: no cell from this experiment" in text
    assert "Question 1, balanced: no cell from this experiment" in text


def test_a_question_whose_set_of_tasks_is_empty_is_not_measured():
    r = full_world(none=TASKS)
    a = analyse(r)
    assert a["q1"]["verdict"] == an.NOT_MEASURED and a["q2"]["verdict"] == an.NOT_MEASURED
    assert a["q3"]["verdict"] == an.NOT_MEASURED
    assert len(a["left"]["left_out"]) == 6 * (15 + 4)                    # every B and C run of every task
    assert "Question 1: not measured" in an.render(a)


def test_runs_never_started_because_of_the_spend_stop_are_left_out_listed_and_not_counted():
    r = Rec()
    givens(r)
    r.t_run("code-01", TS_H, 1, cost=226.0)                              # the spend reaches the stop
    r.fill(HM, "B", flat([4, 4, 4, 0, 0, 0], "first", "first", 4))       # 12 runs ended, all correct
    r.lines = [x for x in r.lines if not (x["step"] == "C" and x["task"] in ("code-04", "code-05", "code-06"))]
    for c in (HH, SL, SM):
        r.fill(c, "B", "first")
    a = analyse(r)
    s = a["q1"]["cells"][HM]
    assert a["state"]["spend_stopped"] is True
    assert (s["runs"], s["correct"], s["share"]) == (12, 12, 1.0)        # the 12 never started are not "not correct"
    assert sum(1 for k in a["left"]["stopped"] if k[1] == HM and k[2] == "B") == 12
    assert a["q1"]["verdict"] == "decided" and not a["pending"]["C"]
    assert "never started or cut because of the spend stop" in an.render(a)
    assert analyse(r, stop=500.0)["q1"]["verdict"] == an.PENDING        # below the stop they are pending


# -- question 1 --------------------------------------------------------------------------------------

def test_q1_share_of_correct_runs_and_cost_per_correct_task():
    # haiku-5-5@medium: 12 correct at try 1 ($0.25), 12 not finished after three tries ($0.75): $12 / 12 correct
    r = q1_world({HM: (flat([2] * 6, "first", "unf", 4), 0.25), HH: ("first", 1.0), SL: ("first", 1.0),
                  SM: ("first", 1.0)})
    s = analyse(r)["q1"]["cells"][HM]
    assert (s["runs"], s["correct"], s["share"]) == (24, 12, 0.5)
    assert s["cost"] == pytest.approx(12.0) and s["cost_per_correct"] == pytest.approx(1.0)


def test_q1_a_cell_is_usable_when_at_least_half_of_its_arm_b_runs_are_correct():
    half = flat([2] * 6, "first", "unf", 4)                               # 12 of 24
    below = flat([2, 2, 2, 2, 2, 1], "first", "unf", 4)                   # 11 of 24
    r = q1_world({HM: (half, 0.25), HH: (below, 0.25), SL: ("first", 1.0), SM: ("first", 1.0)})
    q = analyse(r)["q1"]["cells"]
    assert q[HM]["usable"] is True and q[HH]["usable"] is False
    assert "Question 1, haiku-5-5@medium: usable for bulk coding" in an.render(analyse(r))
    assert "Question 1, haiku-5-5@high: not usable for bulk coding" in an.render(analyse(r))


def fast_world():
    """haiku-5-5@medium is cheapest but escapes 3 of 24 finished; haiku-5-5@high escapes exactly 2 of its 20
    finished (1 in 10); sonnet-5-5@low is clean at $0.50 a run, sonnet-5-5@medium clean at $1.00."""
    hm = [["first"] * 4] * 3 + [["first", "first", "first", "escaped"]] * 3
    hh = ([["first"] * 4] * 2 + [["first", "first", "first", "escaped"]] * 2
          + [["first", "first", "unf", "unf"]] * 2)
    return q1_world({HM: (hm, 0.1), HH: (hh, 0.2), SL: ("first", 0.5), SM: ("first", 1.0)})


def test_q1_fast_is_the_cheapest_usable_cell_whose_escaped_runs_are_at_most_one_in_ten_finished():
    q = analyse(fast_world())["q1"]
    hh = q["cells"][HH]
    assert (hh["finished"], hh["escaped"], hh["escaped_ok"]) == (20, 2, True)
    assert q["cells"][HM]["escaped_ok"] is False
    assert q["cells"][HM]["cost_per_correct"] < hh["cost_per_correct"] < q["cells"][SL]["cost_per_correct"]
    assert q["fast"] == HH


def test_q1_fast_on_a_tie_of_cost_per_correct_takes_the_higher_share():
    # both cost $0.50 per correct task: haiku-5-5@medium 18 of 24 correct, haiku-5-5@high 24 of 24
    hm = flat([3] * 6, "first", "unf", 4)
    r = q1_world({HM: (hm, 0.25), HH: ("first", 0.5), SL: ("first", 3.0), SM: ("first", 3.0)})
    q = analyse(r)["q1"]
    assert q["cells"][HM]["cost_per_correct"] == pytest.approx(q["cells"][HH]["cost_per_correct"])
    assert q["fast"] == HH


def test_q1_balanced_is_the_cheapest_cell_whose_arm_b_runs_are_all_correct():
    q = analyse(fast_world())["q1"]
    assert q["cells"][SL]["clean"] and q["cells"][SM]["clean"] and not q["cells"][HH]["clean"]
    assert q["balanced"] == SL and "no cell was clean" not in q["notes"]


def test_q1_balanced_with_no_clean_cell_takes_the_highest_share_then_the_lower_cost_and_says_so():
    two = flat([2] * 6, "first", "unf", 4)                                # 12 of 24, 50%
    sl = flat([1, 1, 1, 1, 2, 2], "first", "unf", 3)                      # 8 of 18, 44%
    r = q1_world({HM: (two, 0.5), HH: (two, 0.25), SL: (sl, 0.1), SM: (flat([1] * 6, "first", "unf", 3), 0.1)})
    q = analyse(r)["q1"]
    assert q["cells"][HM]["share"] == q["cells"][HH]["share"] == 0.5
    assert q["balanced"] == HH and "no cell was clean" in q["notes"]


def test_q1_when_no_cell_qualifies_for_fast_fast_takes_the_cell_of_balanced_and_says_so():
    below = flat([2, 2, 2, 2, 2, 1], "first", "unf", 4)                   # 11 of 24: not usable
    r = q1_world({HM: (below, 0.25), HH: (flat([2, 2, 2, 2, 1, 1], "first", "unf", 4), 0.25),
                  SL: (flat([1] * 6, "first", "unf", 3), 0.25), SM: (flat([1] * 6, "first", "unf", 3), 0.25)})
    q = analyse(r)["q1"]
    assert not any(q["cells"][c]["usable"] for c in (HM, HH, SL, SM))
    assert q["fast"] == q["balanced"] == HM
    assert "no cell qualifies for fast, so fast takes the cell of balanced" in q["notes"]


def test_q1_escaped_runs_are_reported_per_task():
    q = analyse(fast_world())["q1"]
    per = {t: sum(q["cells"][c]["escaped_per_task"][t] for c in (HM, HH, SL, SM)) for t in TASKS}
    assert per == {"code-01": 0, "code-02": 0, "code-03": 1, "code-04": 2, "code-05": 1, "code-06": 1}
    assert "escaped per task: code-01 0; code-02 0; code-03 1; code-04 2; code-05 1; code-06 1" in \
        an.render(analyse(fast_world()))


# -- question 2 --------------------------------------------------------------------------------------

def q2_world(cell, a_ok, b_first, runs=4, b_kind_ok="first", tasks=TASKS[:5], cut=()):
    """Arms A and B of one cell on `tasks` (the others have no given suite): per task a_ok correct arm-A runs
    and b_first arm-B runs correct at try 1."""
    r = Rec()
    givens(r, none=[t for t in TASKS if t not in tasks])
    for c in (HM, HH, SL):
        n = runs if c == cell else RULES_C_PLAN[c][1]
        for t in TASKS:
            for k in range(1, n + 1):
                ok = c == cell and k <= a_ok[TASKS.index(t)] if t in tasks else False
                r.c_run(t, c, "A", k, "pass" if ok else "fail")
                if t in tasks:
                    okb = c == cell and k <= b_first[TASKS.index(t)]
                    r.c_run(t, c, "B", k, b_kind_ok if okb else "unf")
    return r


def test_q2_difference_is_first_try_share_in_b_minus_share_in_a_over_tasks_with_both_arms():
    r = q2_world(HM, a_ok=[2, 2, 2, 2, 2], b_first=[3, 3, 3, 2, 2])
    s = analyse(r)["q2"]["cells"][HM]
    assert s["tasks"] == list(TASKS[:5])                                  # code-06 has no arm B: left out
    assert (s["runs_A"], s["runs_B"]) == (20, 20)
    assert s["share_A"] == 0.5 and s["share_B_first"] == 0.65 and s["difference"] == pytest.approx(15.0)
    s = analyse(q2_world(HM, a_ok=[2] * 5, b_first=[2] * 5, b_kind_ok="second"))["q2"]["cells"][HM]
    assert s["difference"] == pytest.approx(-50.0)                        # correct only at try 2: not first
    r = q2_world(HM, a_ok=[2, 2, 2, 2, 2, 4], b_first=[3, 3, 3, 2, 2, 0], tasks=TASKS)
    r.lines = [x for x in r.lines if not (x["task"] == "code-06" and x["cell"] == HM and x["arm"] == "B")]
    s = analyse(r)["q2"]["cells"][HM]                                     # code-06: no ended arm-B run of the cell
    assert s["tasks"] == list(TASKS[:5]) and s["runs_A"] == 20 and s["difference"] == pytest.approx(15.0)


def test_q2_tests_first_helps_a_haiku_cell_at_15_points_when_arm_b_is_ahead_on_more_tasks():
    s = analyse(q2_world(HM, a_ok=[2, 2, 2, 2, 2], b_first=[3, 3, 3, 2, 2]))["q2"]["cells"][HM]
    assert (s["ahead_B"], s["ahead_A"], s["verdict"]) == (3, 0, an.HELPS)
    s = analyse(q2_world(HM, a_ok=[0, 0, 4, 4, 2], b_first=[4, 4, 1, 2, 2]))["q2"]["cells"][HM]
    assert s["difference"] == pytest.approx(15.0) and (s["ahead_B"], s["ahead_A"]) == (2, 2)
    assert s["verdict"] == an.NO_EFFECT


def test_q2_the_sonnet_cell_needs_30_points():
    cut = ["sonnet-5-5@low:2"]                                            # 2 runs a task on 5 tasks: 10 runs
    r = q2_world(SL, a_ok=[1, 1, 0, 0, 0], b_first=[2, 2, 0, 0, 0], runs=2)
    s = analyse(r, cut=cut)["q2"]["cells"][SL]
    assert s["difference"] == pytest.approx(20.0) and s["verdict"] == an.NO_EFFECT
    r = q2_world(SL, a_ok=[1, 1, 0, 0, 0], b_first=[2, 2, 1, 0, 0], runs=2)
    s = analyse(r, cut=cut)["q2"]["cells"][SL]
    assert s["difference"] == pytest.approx(30.0) and s["verdict"] == an.HELPS


def test_q2_tests_first_hurts_at_minus_15_when_arm_a_is_ahead_on_more_tasks():
    s = analyse(q2_world(HH, a_ok=[3, 3, 3, 2, 2], b_first=[2, 2, 2, 2, 2]))["q2"]["cells"][HH]
    assert s["difference"] == pytest.approx(-15.0) and s["ahead_A"] == 3 and s["verdict"] == an.HURTS


def test_q2_otherwise_no_effect_shown():
    s = analyse(q2_world(HM, a_ok=[2, 2, 2, 2, 2], b_first=[3, 3, 2, 2, 2]))["q2"]["cells"][HM]
    assert s["difference"] == pytest.approx(10.0) and s["verdict"] == an.NO_EFFECT


def test_q2_what_tries_2_and_3_add_in_arm_b_is_reported():
    s = analyse(q2_world(HM, a_ok=[2] * 5, b_first=[2] * 5, b_kind_ok="second"))["q2"]["cells"][HM]
    assert s["share_B_first"] == 0.0 and s["share_B_end"] == 0.5 and s["later_tries"] == pytest.approx(50.0)
    text = an.render(analyse(q2_world(HM, a_ok=[2] * 5, b_first=[2] * 5, b_kind_ok="second")))
    assert "tries 2 and 3 in arm B add +50.0 points" in text


# -- question 3 --------------------------------------------------------------------------------------

def q3_world(b, c, tasks=TASKS[:5]):
    """haiku-5-5@high arms B and C on `tasks`; b and c: per task, a list of 4 kinds."""
    r = Rec()
    givens(r, none=[t for t in TASKS if t not in tasks])
    for i, t in enumerate(tasks):
        for n in range(1, 5):
            r.c_run(t, HH, "B", n, b[i][n - 1])
            r.c_run(t, HH, "C", n, c[i][n - 1])
    return r


ALL_OK = [["first"] * 4] * 5


def test_q3_arm_c_is_acceptable_when_every_condition_holds_at_its_bound():
    # C: 18 first and 2 escaped (20 finished, 2 escaped = 1 in 10); correct 90% against B's 100% (exactly
    # 10 points below); behind on exactly two tasks
    c = [["first"] * 4, ["first"] * 4, ["first"] * 4, ["first"] * 3 + ["escaped"], ["first"] * 3 + ["escaped"]]
    q = analyse(q3_world(ALL_OK, c))["q3"]
    assert (q["finished_C"], q["escaped_C"], q["share_C"], len(q["behind"])) == (20, 2, 0.9, 2)
    assert q["verdict"] == an.ACCEPTABLE


def test_q3_fewer_than_half_of_arm_c_runs_finished_is_not_acceptable():
    ok = [["first"] * 4, ["first"] * 4, ["unf_ok"] * 4, ["unf_ok"] * 4, ["unf_ok"] * 4]
    q = analyse(q3_world(ALL_OK, ok))["q3"]
    assert q["finished_C"] == 8 and q["verdict"] == an.STRONGER and q["conditions"]["finished"] is False
    ok[2] = ["first", "first", "unf_ok", "unf_ok"]
    assert analyse(q3_world(ALL_OK, ok))["q3"]["verdict"] == an.ACCEPTABLE   # 10 of 20 finished


def test_q3_a_share_correct_more_than_10_points_below_arm_b_is_not_acceptable():
    b = [["first"] * 4] * 3 + [["first"] * 3 + ["unf"]] * 2               # 18 of 20
    c = [["first"] * 3 + ["unf"]] * 2 + [["first"] * 4] + [["first"] * 3 + ["unf"]] * 2   # 16 of 20: 10 below
    q = analyse(q3_world(b, c))["q3"]
    assert q["conditions"]["correct"] is True
    c[2] = ["first"] * 3 + ["unf"]                                        # 15 of 20: 15 points below
    q = analyse(q3_world(b, c))["q3"]
    assert q["conditions"]["correct"] is False and q["verdict"] == an.STRONGER


def test_q3_escaped_runs_above_one_in_ten_finished_are_not_acceptable():
    b = [["first"] * 4] * 2 + [["first"] * 3 + ["unf"]] * 3               # 17 of 20
    c = [["first"] * 4] * 2 + [["first"] * 3 + ["escaped"]] * 3           # 17 correct, 3 of 20 escaped
    q = analyse(q3_world(b, c))["q3"]
    assert q["behind"] == [] and q["conditions"]["correct"] is True
    assert q["conditions"]["escaped"] is False and q["verdict"] == an.STRONGER


def test_q3_behind_arm_b_on_more_than_two_tasks_is_not_acceptable():
    b = [["first"] * 4] * 3 + [["first", "first", "unf", "unf"]] * 2      # 16 of 20
    c = [["first"] * 3 + ["unf"]] * 3 + [["first"] * 4] * 2               # 17 of 20, behind on 3 tasks
    q = analyse(q3_world(b, c))["q3"]
    assert len(q["behind"]) == 3 and q["verdict"] == an.STRONGER
    assert [k for k, v in q["conditions"].items() if not v] == ["behind"]
    c[2] = ["first"] * 4
    assert analyse(q3_world(b, c))["q3"]["verdict"] == an.ACCEPTABLE


def test_q3_with_fewer_than_four_tasks_with_both_arms_is_too_few_tasks_to_tell():
    q = analyse(q3_world(ALL_OK[:3], ALL_OK[:3], tasks=TASKS[:3]))["q3"]
    assert q["verdict"] == an.TOO_FEW_TASKS
    assert analyse(q3_world(ALL_OK[:4], ALL_OK[:4], tasks=TASKS[:4]))["q3"]["verdict"] == an.ACCEPTABLE


def test_q3_is_not_measured_when_arm_c_was_cut():
    q = analyse(q3_world(ALL_OK, ALL_OK), cut=["C"])["q3"]
    assert q["verdict"] == an.NOT_MEASURED and "cut" in q["why"]


# -- question 4 --------------------------------------------------------------------------------------

def suites(fit, catches=None, rejects=0):
    """12 suites: the first `fit` fit; the first `catches` of the fit ones catch (default all); the first
    `rejects` of the fit ones wrongly reject."""
    catches = fit if catches is None else catches
    return [(i < fit, i < catches, i < rejects) for i in range(12)]


def q4(spec, **kw):
    return analyse(full_world(t_spec=spec, **kw))["q4"]


def test_q4_per_cell_fit_suites_mean_cost_and_time_and_cost_per_fit_suite():
    r = full_world(t_spec={TS_H: suites(10)})
    s = analyse(r)["q4"]["cells"][TS_H]
    assert (s["suites"], s["fit"]) == (12, 10)
    assert s["mean_cost"] == pytest.approx(1.0) and s["mean_time_s"] == pytest.approx(60.0)
    assert s["cost_per_fit"] == pytest.approx(12.0 / 10)


def test_q4_a_suite_catches_a_wrong_copy_it_fails_on_and_wrongly_rejects_a_right_one():
    # per fit suite: 11 arm-A copies that are not correct, 4 arm-C copies that are correct
    s = q4({TS_H: suites(12, catches=9, rejects=3)})["cells"][TS_H]
    assert (s["catch"]["k"], s["catch"]["n"]) == (9 * 11, 12 * 11)
    assert (s["wrong"]["k"], s["wrong"]["n"]) == (3 * 4, 12 * 4)
    assert s["catch"]["rate"] == pytest.approx(0.75) and s["wrong"]["rate"] == pytest.approx(0.25)


def test_q4_a_load_error_on_a_copy_counts_as_failing_and_unchanged_or_arm_b_copies_are_left_out():
    r = full_world(t_spec={TS_H: suites(1)}, )
    pairs_before = len([p for p in analyse(r)["state"]["cross"]["pairs"] if p["writer"] == TS_H])
    for x in r.lines:
        if x.get("what") == "cross" and x["suite"] == TS_H + "#1" and x["result"] == "fail":
            x["result"] = "load_error"
    r.cross("code-01", TS_H + "#1", HM, "B", 1, "fail")                  # an arm-B line is never read
    for x in r.lines:                                                     # one copy left out: source unchanged
        if x.get("what") == "copy" and (x["task"], x["cell"], x["arm"], x["run"]) == ("code-01", HM, "A", 1):
            x["result"] = "unchanged"
    s = analyse(r)["q4"]["cells"][TS_H]
    assert s["catch"]["n"] == 10 and s["catch"]["k"] == 10 and pairs_before == 15
    assert s["wrong"]["n"] == 4


def test_q4_a_rate_over_fewer_than_10_pairs_is_too_few_to_tell_and_its_bound_is_not_applied():
    s = q4({TS_H: suites(2, rejects=2)})["cells"][TS_H]                    # 8 right copies, all rejected
    assert s["wrong"]["n"] == 8 and s["wrong"]["too_few"] is True and s["wrong_ok"] is True
    s = q4({TS_H: suites(3, rejects=3)})["cells"][TS_H]                    # 12 pairs: measured
    assert s["wrong"]["too_few"] is False and s["wrong_ok"] is False
    assert "8/8 too few to tell" in an.render(analyse(full_world(t_spec={TS_H: suites(2, rejects=2)})))


def test_q4_fast_is_the_cheapest_cell_with_10_fit_suites_that_catches_80_and_rejects_at_most_10():
    # sonnet-5-5@high: 10 fit, 8 catch (80%), 1 rejects (4 of 40 = 10%), $12 / 10; sonnet-5-5@xhigh 12 fit at
    # $12 / 12 is cheaper per fit suite but catches 75%; opus-5-5@medium 9 fit; opus-5-5@high rejects 25%
    spec = {TS_H: suites(10, catches=8, rejects=1), TS_X: suites(12, catches=9), TO_M: suites(9),
            TO_H: suites(12, rejects=3)}
    q = q4(spec)
    assert q["cells"][TS_H]["catch"]["rate"] == pytest.approx(0.8) and q["cells"][TS_H]["wrong"]["rate"] == pytest.approx(0.1)
    assert q["fast"] == TS_H


def test_q4_fast_when_no_cell_qualifies_takes_the_most_fit_suites_within_10_percent_cheaper_on_a_tie():
    spec = {TS_H: suites(9), TS_X: suites(8), TO_M: suites(9), TO_H: suites(11, rejects=11)}
    r = full_world(t_spec=spec)
    for x in r.lines:                                                     # opus-5-5@medium is cheaper per suite
        if x["kind"] == "model" and x["step"] == "T" and x["cell"] == TO_M:
            x["cost_usd"] = 0.5
    q = analyse(r)["q4"]
    assert q["fast"] == TO_M and any("most fit suites among those that wrongly reject" in n for n in q["notes"])


def test_q4_fast_when_no_cell_stays_within_10_percent_takes_the_lowest_rate_of_wrong_rejections():
    spec = {TS_H: suites(12, rejects=6), TS_X: suites(12, rejects=3), TO_M: suites(12, rejects=4),
            TO_H: suites(12, rejects=12)}
    q = q4(spec)
    assert q["fast"] == TS_X and any("lowest rate of wrong rejections" in n for n in q["notes"])


def test_q4_balanced_is_the_cheapest_cell_with_12_fit_suites_and_both_bounds():
    # sonnet-5-5@high is the cheapest per fit suite but has 11; opus-5-5@high has 12 but catches 75%
    spec = {TS_H: suites(11), TS_X: suites(12), TO_M: suites(12), TO_H: suites(12, catches=9)}
    r = full_world(t_spec=spec)
    for x in r.lines:
        if x["kind"] == "model" and x["step"] == "T" and x["cell"] in (TO_M, TS_H, TO_H):
            x["cost_usd"] = {TO_M: 0.9, TS_H: 0.5, TO_H: 0.1}[x["cell"]]
    q = analyse(r)["q4"]
    assert q["balanced"] == TO_M and q["fast"] == TS_H


def test_q4_balanced_fallbacks_most_fit_within_both_bounds_then_most_fit_cheaper_on_a_tie():
    spec = {TS_H: suites(11), TS_X: suites(10), TO_M: suites(12, catches=9), TO_H: suites(11)}
    r = full_world(t_spec=spec)
    for x in r.lines:
        if x["kind"] == "model" and x["step"] == "T" and x["cell"] == TO_H:
            x["cost_usd"] = 0.5
    q = analyse(r)["q4"]
    assert q["balanced"] == TO_H and any("among those that meet both bounds" in n for n in q["notes"])
    spec = {TS_H: suites(11, catches=5), TS_X: suites(10, catches=5), TO_M: suites(11, catches=5),
            TO_H: suites(9, catches=5)}
    r = full_world(t_spec=spec)
    for x in r.lines:
        if x["kind"] == "model" and x["step"] == "T" and x["cell"] == TO_M:
            x["cost_usd"] = 0.5
    q = analyse(r)["q4"]
    assert q["balanced"] == TO_M and any("no cell meets both bounds; the most fit suites" in n for n in q["notes"])


def test_q4_a_cell_with_no_fit_suite_is_never_named():
    spec = {c: suites(0) for c in RULES_T_CELLS}
    q = q4(spec)
    assert q["verdict"] == "decided" and q["fast"] is None and q["balanced"] is None
    text = an.render(analyse(full_world(t_spec=spec)))
    assert "Question 4, fast: no cell from this experiment" in text
    assert "The tip for the main chat of a $20 plan: no cell from this experiment." in text


def test_q4_the_tip_names_the_fast_cell_and_says_a_long_chat_rereads_the_conversation():
    text = an.render(analyse(full_world(t_spec={TS_H: suites(9)})))
    assert ("The tip for the main chat of a $20 plan names sonnet-5-5@xhigh. A long chat re-reads the whole "
            "conversation every turn, so the cheaper input price weighs more there than in these single tasks.") in text


def test_q4_waits_for_every_copy_line_and_every_pair_of_cross():
    r = full_world()
    r.lines = [x for x in r.lines if not (x.get("what") == "copy" and x["task"] == "code-02" and x["cell"] == SL)]
    a = analyse(r)
    assert a["q4"]["verdict"] == an.PENDING and len(a["pending"]["cross"]) == 3
    r = full_world()
    drop = next(i for i, x in enumerate(r.lines) if x.get("what") == "cross")
    del r.lines[drop]
    a = analyse(r)
    assert a["q4"]["verdict"] == an.PENDING and len(a["pending"]["cross"]) == 1 and a["status"] == "PENDING"


# -- missing and invalid runs ---------------------------------------------------------------------------

def test_an_api_error_is_an_attempt_not_a_try():
    r = Rec()
    r.model("C", "code-01", HH, "B", 1, 1, attempt=1, infra=True, cost=0.0)
    r.model("C", "code-01", HH, "B", 1, 1, attempt=2, infra=True, cost=0.0)
    r.model("C", "code-01", HH, "B", 1, 1, attempt=3, cost=0.3)
    r.check("C", "code-01", "given", "pass", cell=HH, arm="B", run=1, try_=1)
    r.check("C", "code-01", "hidden", "pass", cell=HH, arm="B", run=1, try_=1)
    o = an.c_outcome(r.lines, "B")
    assert (o["ended"], o["tries"], o["correct"], o["correct_first"], o["finished"]) == ("done", 1, True, True, True)
    assert o["processes"] == 3 and o["cost"] == pytest.approx(0.3)


def test_after_three_failed_attempts_a_step_c_run_ends_not_correct_not_finished_and_is_listed():
    r = Rec()
    givens(r)
    r.model("C", "code-01", HH, "B", 1, 1)
    r.check("C", "code-01", "given", "fail", cell=HH, arm="B", run=1, try_=1)
    r.check("C", "code-01", "hidden", "pass", cell=HH, arm="B", run=1, try_=1)
    for k in (1, 2, 3):
        r.model("C", "code-01", HH, "B", 1, 2, attempt=k, infra=True, cost=0.0)
    o = an.c_outcome(r.lines[6:], "B")
    assert (o["ended"], o["correct"], o["finished"], o["correct_first"]) == ("infra", False, False, True)
    a = analyse(r)
    assert ("code-01", HH, "B", 1) in a["missing"]["C_infra"] and a["state"]["C"][("code-01", HH, "B", 1)]["state"] == "ended"
    assert "step C runs ended after three API or infrastructure errors (not correct, not finished): code-01 haiku-5-5@high B 1" in an.render(a)


def test_after_three_failed_attempts_a_step_t_suite_is_not_fit_and_is_listed():
    r = Rec()
    for k in (1, 2, 3):
        r.model("T", "code-01", TS_H, None, 1, 1, attempt=k, infra=True, cost=0.0)
    a = analyse(r)
    o = a["state"]["T"][("code-01", TS_H, 1)]
    assert (o["ended"], o["scored"], o["fit"], o["state"]) == ("infra", True, False, "ended")
    assert ("code-01", TS_H, 1) not in a["pending"]["fit"] and ("code-01", TS_H, 1) in a["missing"]["T_infra"]


def test_a_process_whose_cost_is_unknown_is_charged_6_dollars():
    r = q1_world({HM: ("first", 0.25), HH: ("first", 0.25), SL: ("first", 0.25), SM: ("first", 0.25)})
    x = next(x for x in r.lines if x["kind"] == "model" and x["cell"] == HM)
    x.update(cost_usd=None, cost_unknown=True)
    a = analyse(r)
    assert a["state"]["spend"]["total"] == pytest.approx(0.25 * (24 * 2 + 18 * 2) - 0.25 + 6.0)
    assert a["q1"]["cells"][HM]["cost"] == pytest.approx(0.25 * 23 + 6.0)


# -- incarnations and repeated lines ------------------------------------------------------------------

def test_a_run_cut_by_the_spend_stop_and_made_again_is_read_from_its_final_incarnation():
    # S5: try 1 and try 2 of an arm-B run, then the stop; the next invocation makes it again from try 1
    r = Rec()
    for i in (1, 2):
        r.model("C", "code-01", HH, "B", 1, i, cost=1.0)
        r.check("C", "code-01", "given", "fail", cell=HH, arm="B", run=1, try_=i)
        r.check("C", "code-01", "hidden", "fail", cell=HH, arm="B", run=1, try_=i)
    r.c_run("code-01", HH, "B", 1, "first", cost=1.0)
    o = an.c_outcome(r.lines, "B")
    assert (o["tries"], o["correct_first"], o["correct"]) == (1, True, True)
    assert o["cost"] == pytest.approx(1.0) and o["cut_cost"] == pytest.approx(2.0) and o["cut_incarnations"] == 1
    a = analyse(r)
    assert a["state"]["spend"]["total"] == pytest.approx(3.0) and a["missing"]["cut_cost"] == pytest.approx(2.0)


def test_a_run_interrupted_between_its_model_line_and_its_hidden_line_is_read_from_its_final_incarnation():
    # S6: Ctrl-C after the model line of try 1; the restart writes try 1 again and goes on
    r = Rec()
    r.model("C", "code-01", HM, "A", 1, 1, cost=0.5)
    r.c_run("code-01", HM, "A", 1, "pass", cost=0.25)
    o = an.c_outcome(r.lines, "A")
    assert (o["ended"], o["tries"], o["correct"], o["cost"]) == ("done", 1, True, 0.25)
    o = an.c_outcome(r.lines[:1], "A")
    assert o["ended"] is None                                             # the cut one alone has not ended


def test_check_infra_lines_are_ignored():
    r = Rec()
    r.model("C", "code-01", HM, "A", 1, 1)
    r.check("C", "code-01", "hidden", "check_infra", cell=HM, arm="A", run=1, try_=1)
    assert an.c_outcome(an.group(r.lines)["C"][("code-01", HM, "A", 1)], "A")["ended"] is None
    r.lines = []
    r.check("fit", "code-01", "fit_start", "check_infra", cell=TS_H, run=1, try_=1, suite=TS_H + "#1")
    assert an.group(r.lines)["fit"] == {}


def test_a_repeated_fit_scoring_or_cross_pair_is_read_from_its_last_lines():
    r = Rec()
    r.check("fit", "code-01", "fit_start", "fail", cell=TS_H, run=1, try_=1, suite=TS_H + "#1")
    r.check("fit", "code-01", "fit_reference", "fail", cell=TS_H, run=1, try_=1, suite=TS_H + "#1")
    r.fit("code-01", TS_H, 1, fit=True)
    assert an.fit_of(an.group(r.lines)["fit"][("code-01", TS_H + "#1")]) == {"scored": True, "fit": True}
    r.cross("code-01", TS_H + "#1", HM, "A", 1, "pass")
    r.cross("code-01", TS_H + "#1", HM, "A", 1, "fail")
    assert an.group(r.lines)["cross"][("code-01", TS_H + "#1", HM, "A", 1)] == "fail"


# -- --cut and --json --------------------------------------------------------------------------------

def test_cut_lists_what_the_spend_rule_cut_and_refuses_anything_else(tmp_path):
    cut = an.parse_cut(["opus-5-5@high,sonnet-5-5@medium", "C", "haiku-5-5@medium:3", "sonnet-5-5@low:2"])
    assert cut == {"cells": {OH, SM}, "arm_c": True, "runs": {HM: 3, SL: 2}}
    a = an.analyse([], cut)
    keys = a["left"]["cut"]
    assert sum(1 for k in keys if k[1] == OH) == 6 and sum(1 for k in keys if k[1] == SM) == 18
    assert sum(1 for k in keys if k[2] == "C") == 24 and sum(1 for k in keys if k[1] == HM) == 12
    assert sum(1 for k in keys if k[1] == SL) == 12
    assert not any(k in a["pending"]["C"] for k in keys)
    for bad in ("fable-5-1@high", "haiku-5-5@medium:4", "D"):
        code, out, err = cli(tmp_path, [], "--cut", bad)
        assert code == 2 and err.startswith("code_bench_analysis: error: --cut")
    code, out, _ = cli(tmp_path, [], "--cut", "C")
    assert "Cut by the spend rule: arm C" in out


def test_json_gives_the_same_verdicts_as_the_text(tmp_path):
    lines = fast_world().lines
    code, out, _ = cli(tmp_path, lines, "--json")
    j = json.loads(out)
    assert code == 3 and j["status"] == "PENDING"
    assert j["q1"]["fast"] == HH and j["q1"]["balanced"] == SL and j["q2"]["verdict"] == "PENDING"
    code, text, _ = cli(tmp_path, lines)
    assert "Question 1, fast: haiku-5-5@high" in text and "Question 1, balanced: sonnet-5-5@low" in text
