#!/usr/bin/env python3
"""Apply the rules of evals/results/PREREGISTERED-2026-11-14-coding.md (section "Rules") to the public
record that evals/probes/code_bench.py writes: who writes the tests and who writes the code.

    python3 evals/probes/code_bench_analysis.py
    python3 evals/probes/code_bench_analysis.py --json
    python3 evals/probes/code_bench_analysis.py --cut opus-5-5@high,sonnet-5-5@medium
    python3 evals/probes/code_bench_analysis.py --results /some/code-runs.jsonl

It reads ONE file, the public record (default <evals>/results/code-runs.jsonl). It never reads
evals/private/, never calls a model, and prints task codes, cells, arms, counts, shares, dollars and rule
words only. A missing record is an empty record: everything is pending.

Exit code: 0 when every planned run has ended (or is left out, cut or stopped by the spend stop) and cross
is complete; 3 when something is PENDING (the output says what); 2 when the record cannot be read (a line
that is not a JSON object of kind model or check) or an option is wrong.

--cut lists what the spend rule cut ("The spend is projected twice"): a cell (opus-5-5@high,
sonnet-5-5@medium), the arm C, or a smaller number of runs per task as <cell>:<n> (haiku-5-5@medium:3,
haiku-5-5@high:3, sonnet-5-5@low:2). The planned runs that a cut removes are not pending and are listed
as cut; runs of a cut cell that did end are still counted. Arm C cut makes question 3 "not measured".
--stop-usd (default 226) is the spend stop: once the record's spend total reaches it, every planned run
that has not ended was never started (or was cut half way) because of the spend stop: it is listed,
left out of every share, and not pending.

READINGS of the record (code_bench.py's docstring states the same from the writer's side):
  * A run's lines are its model lines (step T or C) and its check lines (red_first; given, own,
    hidden). Its FINAL incarnation starts at its last model line with try 1 and attempt 1; the lines
    before belong to cut incarnations (a spend stop, a check_infra stop or Ctrl-C cut the run, and the
    next invocation made it again from try 1). Only the final incarnation is read. The cost of cut
    incarnations counts in the spend total and is listed, but it is not part of any run's cost, so it is
    not in "cost per correct task" or "cost per fit suite" (rules: "A run's cost and time are the sum
    over its tries"; a cut incarnation's tries are not the run's tries). correct_first is read from the
    final incarnation only.
  * Check lines whose result is check_infra are ignored (the runner could not start; code_bench stops
    the unit and makes it again).
  * A try is complete when its hidden line exists (step C) or its red_first line exists (step T). A
    try whose attempts are all API or infrastructure errors (infra true), MAX_ATTEMPTS of them, ends the
    run on infra: in step C not correct and not finished, in step T its suite not fit; listed.
  * Step C, a run has ended when: arm A, try 1 is complete; arms B and C, the last complete try passed
    its check or is try 3. Correct = the hidden result of the last try is pass; correct at the first
    try = the hidden result of try 1 is pass; finished (B, C) = a try's check is pass; escaped =
    finished and not correct. A run that has not ended is not started (it is pending, or stopped).
  * Fit (rules, "A suite of step T"): from the suite's last fit_start line on: red on start and two
    fit_reference passes. A suite whose step-T run ended on infra is not fit.
  * The given suite of a task is its first given line (step fit); suite null = no fit suite: arms B
    and C of that task are left out, and every comparison between arms leaves the task out.
  * Cross: a pair (fit suite, copy) is the last cross line of that suite on that copy. The copies are
    the final copies of arms A and C whose run ended normally; a copy line says whether its source
    changed; "unchanged" copies are left out of both rates. A suite FAILS on a copy when its result
    there is anything but pass (fail, a load error, no tests, a time-out). It catches a copy that is not
    correct when it fails on it; it wrongly rejects a correct copy when it fails on it. Cross is
    complete when every such copy has its copy line and every changed copy a line for every fit suite
    of its task.
  * "Tasks that have both arms" (questions 2 and 3), per cell: the tasks with a given suite on which
    the cell has at least one ended run in each of the two arms. Shares are pooled over runs; "ahead on
    a task" compares the two arms' shares on that task.
  * Ties the rules do not break further fall to the plan order of the cells. Comparisons with a
    threshold allow 1e-9 for float rounding, so a value exactly on a line counts as on it ("at least",
    "at most").
  * Question 4, fallback "if no cell stays within 10%": the cell with the lowest rate of wrong
    rejections among the cells with a fit suite and a measured rate, the cheaper on a tie.
  * Question 4, "over fewer than 10 such pairs": each rate is counted over its own pairs. The catch
    rate's pairs are a fit suite with a copy that is not correct; the wrong-rejection rate's pairs
    are a fit suite with a correct copy. A rate with fewer than 10 pairs of its own is "too few to
    tell" and its bound is not applied, so it does not rule the cell out.
  * A step-C run that ended on infra errors is not correct and not finished (rules), but it still
    counts as correct at the first try when its try-1 hidden tests passed: that try was measured.
    So "what tries 2 and 3 add" can be negative for a cell with such a run; the run is listed.
  * A process whose cost is unknown is charged the $6 cap, in the spend and in every cost
    (UNKNOWN_COST_USD; code_bench.py charges the harness's per-process cap, which is $6).
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
EVALS = HERE.parent
DEFAULT_RESULTS = EVALS / "results" / "code-runs.jsonl"

# -- the plan (rules, "Tasks" and "Two steps") ---------------------------------------------------

TASKS = tuple(f"code-0{i}" for i in range(1, 7))
T_CELLS = ("sonnet-5-5@high", "sonnet-5-5@xhigh", "opus-5-5@medium", "opus-5-5@high")
T_RUNS = 2
GIVEN_ORDER = tuple((c, r) for c in T_CELLS for r in range(1, T_RUNS + 1))
C_PLAN = (("haiku-5-5@medium", ("A", "B"), 4),
          ("haiku-5-5@high", ("A", "B", "C"), 4),
          ("sonnet-5-5@low", ("A", "B"), 3),
          ("sonnet-5-5@medium", ("B",), 3),
          ("opus-5-5@high", ("B",), 1))
C_CELLS = tuple(c for c, _, _ in C_PLAN)
REFERENCE_CELL = "opus-5-5@high"                    # step C: a reference, in no verdict
MAX_TRIES = {"T": 3, "A": 1, "B": 3, "C": 3}
MAX_ATTEMPTS = 3
FIT_REFERENCE_RUNS = 2
UNKNOWN_COST_USD = 6.0
STOP_USD = 226.0
RED = frozenset({"fail", "timeout", "load_error_missing_name"})
INFRA_RESULT = "check_infra"

# -- the rules ------------------------------------------------------------------------------------

Q1_CELLS = ("haiku-5-5@medium", "haiku-5-5@high", "sonnet-5-5@low", "sonnet-5-5@medium")
Q1_USABLE_SHARE = 0.5
ESCAPED_MAX_SHARE = 0.1                             # escaped runs at most 1 in 10 of the finished runs
Q2_THRESHOLD = {"haiku-5-5@medium": 15.0, "haiku-5-5@high": 15.0, "sonnet-5-5@low": 30.0}
Q2_CELLS = tuple(Q2_THRESHOLD)
Q3_CELL = "haiku-5-5@high"
Q3_MIN_TASKS = 4
Q3_FINISHED_SHARE = 0.5
Q3_CORRECT_POINTS_BELOW = 10.0
Q3_MAX_TASKS_BEHIND = 2
Q4_MIN_PAIRS = 10
Q4_CATCH_MIN = 0.8
Q4_WRONG_MAX = 0.1
Q4_FAST_MIN_FIT = 10
Q4_BALANCED_FIT = len(TASKS) * T_RUNS               # 12
EPS = 1e-9

PENDING = "PENDING"
NOT_MEASURED = "not measured"
TOO_FEW = "too few to tell"
TOO_FEW_TASKS = "too few tasks to tell"
NO_CELL = "no cell from this experiment"
USABLE, NOT_USABLE = "usable for bulk coding", "not usable for bulk coding"
HELPS, HURTS, NO_EFFECT = "tests first helps", "tests first hurts", "no effect shown"
ACCEPTABLE = "acceptable"
STRONGER = "not acceptable: the tests must come from a stronger model"
TIP_TEXT = ("A long chat re-reads the whole conversation every turn, so the cheaper input price weighs "
            "more there than in these single tasks.")
DECIDED_STATUS, PENDING_STATUS = "DECIDED", "PENDING"


class AnalysisError(Exception):
    """The record or an option cannot be read."""


# -- reading ----------------------------------------------------------------------------------------

def read_record(path) -> list[dict]:
    """The public record's lines in file order. A missing file is an empty record."""
    path = Path(path)
    if not path.exists():
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        raise AnalysisError("the record cannot be read") from None
    out = []
    for n, raw in enumerate(text.splitlines(), 1):
        if not raw.strip():
            continue
        try:
            obj = json.loads(raw)
        except ValueError:
            raise AnalysisError(f"line {n} of the record is not JSON") from None
        if not isinstance(obj, dict) or obj.get("kind") not in ("model", "check"):
            raise AnalysisError(f"line {n} of the record is not a model or check line")
        out.append(obj)
    return out


def parse_cut(values) -> dict:
    """--cut tokens -> {"cells": set, "arm_c": bool, "runs": {cell: n}}."""
    cut = {"cells": set(), "arm_c": False, "runs": {}}
    planned = {c: n for c, _, n in C_PLAN}
    for v in values or ():
        for tok in str(v).split(","):
            tok = tok.strip()
            if not tok:
                continue
            if tok == "C":
                cut["arm_c"] = True
            elif tok in planned:
                cut["cells"].add(tok)
            elif ":" in tok and tok.split(":")[0] in planned:
                cell, n = tok.split(":", 1)
                if not n.isdigit() or not 0 <= int(n) < planned[cell]:
                    raise AnalysisError(f"--cut {tok}: runs per task must be below {planned[cell]}")
                cut["runs"][cell] = int(n)
            else:
                raise AnalysisError(f"--cut {tok}: not a step-C cell, C, or <cell>:<runs>")
    return cut


def number(x):
    return float(x) if isinstance(x, (int, float)) and not isinstance(x, bool) else None


def line_cost(line: dict) -> float:
    if line.get("cost_unknown"):
        return UNKNOWN_COST_USD
    return number(line.get("cost_usd")) or 0.0


# -- runs and incarnations --------------------------------------------------------------------------

def incarnations(lines: list[dict]) -> list[list[dict]]:
    """Split a run's lines at every model line with try 1 and attempt 1; the last part is final."""
    starts = [i for i, x in enumerate(lines)
              if x.get("kind") == "model" and x.get("try") == 1 and x.get("attempt") == 1]
    if not starts:
        return [lines] if lines else []
    parts = [lines[:starts[0]]] if starts[0] else []
    for a, b in zip(starts, starts[1:] + [len(lines)]):
        parts.append(lines[a:b])
    return parts


def cost_of(lines: list[dict]) -> dict:
    models = [x for x in lines if x.get("kind") == "model"]
    return {"cost": sum(line_cost(x) for x in models), "unknown": sum(1 for x in models if x.get("cost_unknown")),
            "ms": sum(number(x.get("duration_ms")) or 0.0 for x in models), "processes": len(models)}


def read_tries(inc: list[dict], check_whats) -> dict:
    tries: dict = {}
    for x in inc:
        slot = tries.setdefault(x.get("try"), {"models": [], "check": None, "hidden": None})
        if x.get("kind") == "model":
            slot["models"].append(x)
        elif x.get("what") == "hidden":
            slot["hidden"] = x.get("result")
        elif x.get("what") in check_whats:
            slot["check"] = x.get("result")
    return tries


def infra_try(slot: dict) -> bool:
    ms = slot["models"]
    return len(ms) >= MAX_ATTEMPTS and all(m.get("infra") for m in ms)


def c_outcome(lines: list[dict], arm: str) -> dict:
    """One step-C run from its lines: the final incarnation's tries, ended (None, "done", "infra"),
    finished, correct, correct_first, escaped, cost; and the cost of its cut incarnations."""
    parts = incarnations(lines)
    final = parts[-1] if parts else []
    tries = read_tries(final, ("given", "own"))
    ended, checks, hidden = None, [], []
    for n in sorted(k for k in tries if isinstance(k, int)):
        slot = tries[n]
        if infra_try(slot):
            ended = "infra"
            break
        if slot["hidden"] is None:
            break
        checks.append(slot["check"])
        hidden.append(slot["hidden"])
        if arm == "A" or slot["check"] == "pass" or n >= MAX_TRIES[arm]:
            ended = "done"
            break
    finished = None if arm == "A" else (ended == "done" and "pass" in checks)
    correct = ended == "done" and bool(hidden) and hidden[-1] == "pass"
    out = {"ended": ended, "tries": len(hidden), "checks": checks, "hidden": hidden, "finished": finished,
           "correct": correct, "correct_first": bool(hidden) and hidden[0] == "pass",
           "escaped": None if arm == "A" else bool(finished) and not correct,
           "cut_incarnations": len(parts) - 1 if parts else 0,
           "cut_cost": sum(cost_of(p)["cost"] for p in parts[:-1])}
    out.update(cost_of(final))
    return out


def t_outcome(lines: list[dict]) -> dict:
    """One step-T run: ended (None, "done", "infra"), its red_first words, cost."""
    parts = incarnations(lines)
    final = parts[-1] if parts else []
    tries = read_tries(final, ("red_first",))
    ended, words = None, []
    for n in sorted(k for k in tries if isinstance(k, int)):
        slot = tries[n]
        if infra_try(slot):
            ended = "infra"
            break
        if slot["check"] is None:
            break
        words.append(slot["check"])
        if slot["check"] in RED or n >= MAX_TRIES["T"]:
            ended = "done"
            break
    out = {"ended": ended, "tries": len(words), "red_first": words,
           "cut_incarnations": len(parts) - 1 if parts else 0,
           "cut_cost": sum(cost_of(p)["cost"] for p in parts[:-1])}
    out.update(cost_of(final))
    return out


def fit_of(lines: list[dict]) -> dict:
    """{"scored": bool, "fit": bool} from a suite's fit lines (from its last fit_start on)."""
    starts = [i for i, x in enumerate(lines) if x.get("what") == "fit_start"]
    if not starts:
        return {"scored": False, "fit": False}
    final = lines[starts[-1]:]
    start = final[0].get("result")
    refs = [x.get("result") for x in final[1:] if x.get("what") == "fit_reference"]
    if start not in RED:
        return {"scored": True, "fit": False}
    if any(r != "pass" for r in refs):
        return {"scored": True, "fit": False}
    if len(refs) >= FIT_REFERENCE_RUNS:
        return {"scored": True, "fit": True}
    return {"scored": False, "fit": False}


def group(lines: list[dict]) -> dict:
    g = {"T": defaultdict(list), "C": defaultdict(list), "fit": defaultdict(list), "given": {},
         "cross": {}, "copy": {}}
    for x in lines:
        kind, step, what = x.get("kind"), x.get("step"), x.get("what")
        if kind == "check" and x.get("result") == INFRA_RESULT:
            continue
        task = x.get("task")
        if step == "T":
            g["T"][(task, x.get("cell"), x.get("run"))].append(x)
        elif step == "C":
            g["C"][(task, x.get("cell"), x.get("arm"), x.get("run"))].append(x)
        elif step == "fit" and what in ("fit_start", "fit_reference"):
            g["fit"][(task, x.get("suite"))].append(x)
        elif step == "fit" and what == "given":
            g["given"].setdefault(task, x.get("suite"))
        elif step == "cross" and what == "cross":
            g["cross"][(task, x.get("suite"), x.get("cell"), x.get("arm"), x.get("run"))] = x.get("result")
        elif step == "cross" and what == "copy":
            g["copy"][(task, x.get("cell"), x.get("arm"), x.get("run"))] = x.get("result")
    return g


def spend_of(lines: list[dict]) -> dict:
    models = [x for x in lines if x.get("kind") == "model"]
    return {"total": sum(line_cost(x) for x in models), "processes": len(models),
            "unknown": sum(1 for x in models if x.get("cost_unknown"))}


# -- the state of every planned unit --------------------------------------------------------------

def suite_id(cell: str, run: int) -> str:
    return f"{cell}#{run}"


def build(lines: list[dict], cut: dict, stop_usd: float) -> dict:
    g = group(lines)
    spend = spend_of(lines)
    stopped = spend["total"] >= stop_usd - EPS
    st = {"spend": spend, "spend_stopped": stopped, "stop_usd": stop_usd, "cut": cut,
          "T": {}, "C": {}, "given": {}, "fit": {}}
    for task in TASKS:
        for cell, run in GIVEN_ORDER:
            o = t_outcome(g["T"].get((task, cell, run), []))
            sid = suite_id(cell, run)
            if o["ended"] == "infra":
                f = {"scored": True, "fit": False}
            elif o["ended"] == "done":
                f = fit_of(g["fit"].get((task, sid), []))
            else:
                f = {"scored": False, "fit": False}
            o["state"] = "ended" if o["ended"] else ("stopped" if stopped else "pending")
            o.update(f)
            st["T"][(task, cell, run)] = o
        st["given"][task] = g["given"][task] if task in g["given"] else "pending"
        reduce = cut["runs"]
        for cell, arms, runs in C_PLAN:
            for arm in arms:
                for n in range(1, runs + 1):
                    o = c_outcome(g["C"].get((task, cell, arm, n), []), arm)
                    given = st["given"][task]
                    if o["ended"]:
                        o["state"] = "ended"
                    elif cell in cut["cells"] or (arm == "C" and cut["arm_c"]) or n > reduce.get(cell, runs):
                        o["state"] = "cut"
                    elif arm in ("B", "C") and given is None:
                        o["state"] = "left_out"
                    elif stopped:
                        o["state"] = "stopped"
                    else:
                        o["state"] = "pending"
                    st["C"][(task, cell, arm, n)] = o
    st["cross"] = cross_state(st, g)
    return st


def fit_suites(st: dict, task: str) -> list[str]:
    return [suite_id(c, r) for c, r in GIVEN_ORDER if st["T"][(task, c, r)]["fit"]]


def ended_copies(st: dict, task: str) -> list[tuple]:
    return [(cell, arm, n) for (t, cell, arm, n), o in st["C"].items()
            if t == task and arm in ("A", "C") and o["ended"] == "done"]


def cross_state(st: dict, g: dict) -> dict:
    """Pairs and what cross still has to do, per task."""
    pairs, missing = [], []
    for task in TASKS:
        suites = fit_suites(st, task)
        for cell, arm, n in ended_copies(st, task):
            word = g["copy"].get((task, cell, arm, n))
            if word is None:
                if suites:
                    missing.append((task, None, cell, arm, n))
                continue
            if word != "changed":
                continue
            correct = st["C"][(task, cell, arm, n)]["correct"]
            for sid in suites:
                res = g["cross"].get((task, sid, cell, arm, n))
                if res is None:
                    missing.append((task, sid, cell, arm, n))
                    continue
                pairs.append({"task": task, "suite": sid, "writer": sid.split("#")[0], "cell": cell, "arm": arm,
                              "run": n, "correct": correct, "fails": res != "pass"})
    return {"pairs": pairs, "missing": missing}


# -- shares and choices ----------------------------------------------------------------------------

def share(k, n):
    return k / n if n else None


def pick(cands: list[dict], key) -> dict | None:
    """The first of `cands` (plan order) with the smallest key; keys compare with EPS."""
    best = None
    for c in cands:
        if best is None or less(key(c), key(best)):
            best = c
    return best


def less(a: tuple, b: tuple) -> bool:
    for x, y in zip(a, b):
        if x < y - EPS:
            return True
        if x > y + EPS:
            return False
    return False


def runs_of(st: dict, cell: str, arm: str, tasks) -> list[dict]:
    return [dict(o, task=t) for (t, c, a, n), o in st["C"].items()
            if c == cell and a == arm and t in tasks and o["state"] == "ended"]


def pending_c(st: dict, cells, arms) -> list[tuple]:
    return [k for k, o in st["C"].items() if k[1] in cells and k[2] in arms and o["state"] == "pending"]


def given_tasks(st: dict) -> list[str]:
    return [t for t in TASKS if st["given"][t] not in (None, "pending")]


# -- question 1 ------------------------------------------------------------------------------------

def q1_cell(st: dict, cell: str, tasks) -> dict:
    runs = runs_of(st, cell, "B", tasks)
    n = len(runs)
    correct = sum(1 for r in runs if r["correct"])
    finished = sum(1 for r in runs if r["finished"])
    escaped = sum(1 for r in runs if r["escaped"])
    cost = sum(r["cost"] for r in runs)
    per_task = {t: sum(1 for r in runs if r["task"] == t and r["escaped"]) for t in tasks}
    return {"cell": cell, "runs": n, "correct": correct, "finished": finished, "escaped": escaped,
            "share": share(correct, n), "cost": cost, "cost_per_correct": cost / correct if correct else None,
            "usable": n > 0 and correct >= Q1_USABLE_SHARE * n - EPS,
            "escaped_ok": escaped <= ESCAPED_MAX_SHARE * finished + EPS,
            "clean": n > 0 and correct == n, "escaped_per_task": per_task}


def question1(st: dict) -> dict:
    out = {"cells": {}, "fast": None, "balanced": None, "notes": []}
    pend_given = [t for t in TASKS if st["given"][t] == "pending"]
    tasks = given_tasks(st)
    for cell in Q1_CELLS + (REFERENCE_CELL,):
        out["cells"][cell] = q1_cell(st, cell, tasks)
    pend = pending_c(st, Q1_CELLS, ("B",))
    if pend_given or pend:
        out["verdict"] = PENDING
        out["why"] = (f"{len(pend)} arm-B run(s) of the four cells not ended"
                      + (f"; no given suite fixed yet for {', '.join(pend_given)}" if pend_given else ""))
        return out
    if not tasks:
        out["verdict"] = NOT_MEASURED
        out["why"] = "no task has a given suite, so no task has arm B"
        return out
    out["verdict"] = "decided"
    cells = [out["cells"][c] for c in Q1_CELLS]
    named = [c for c in cells if c["runs"] > 0 and c["correct"] > 0]
    clean = [c for c in named if c["clean"]]
    if clean:
        bal = pick(clean, lambda c: (c["cost_per_correct"],))
        out["balanced"] = bal["cell"]
    elif named:
        bal = pick(named, lambda c: (-c["share"], c["cost_per_correct"]))
        out["balanced"] = bal["cell"]
        out["notes"].append("no cell was clean")
    else:
        out["notes"].append("balanced: " + NO_CELL)
    fast = [c for c in named if c["usable"] and c["escaped_ok"]]
    if fast:
        out["fast"] = pick(fast, lambda c: (c["cost_per_correct"], -c["share"]))["cell"]
    else:
        out["fast"] = out["balanced"]
        out["notes"].append("no cell qualifies for fast, so fast takes the cell of balanced"
                            if out["balanced"] else "fast: " + NO_CELL)
    out["why"] = f"over {len(tasks)} task(s) with arm B"
    return out


# -- question 2 ------------------------------------------------------------------------------------

def both_arm_tasks(st: dict, cell: str, arm1: str, arm2: str) -> list[str]:
    tasks = given_tasks(st)
    return [t for t in tasks if runs_of(st, cell, arm1, [t]) and runs_of(st, cell, arm2, [t])]


def q2_cell(st: dict, cell: str) -> dict:
    tasks = both_arm_tasks(st, cell, "A", "B")
    a, b = runs_of(st, cell, "A", tasks), runs_of(st, cell, "B", tasks)
    out = {"cell": cell, "tasks": tasks, "threshold": Q2_THRESHOLD[cell], "runs_A": len(a), "runs_B": len(b)}
    if not tasks:
        out.update(verdict=NOT_MEASURED, why="no task with ended runs in both arms")
        return out
    a_ok = sum(1 for r in a if r["correct"])
    b_first = sum(1 for r in b if r["correct_first"])
    b_end = sum(1 for r in b if r["correct"])
    diff = 100.0 * (b_first / len(b) - a_ok / len(a))
    ahead_b = ahead_a = 0
    for t in tasks:
        ta, tb = [r for r in a if r["task"] == t], [r for r in b if r["task"] == t]
        sa = sum(1 for r in ta if r["correct"]) / len(ta)
        sb = sum(1 for r in tb if r["correct_first"]) / len(tb)
        ahead_b += sb > sa + EPS
        ahead_a += sa > sb + EPS
    thr = Q2_THRESHOLD[cell]
    if diff >= thr - EPS and ahead_b > ahead_a:
        verdict = HELPS
    elif diff <= -thr + EPS and ahead_a > ahead_b:
        verdict = HURTS
    else:
        verdict = NO_EFFECT
    out.update(share_A=a_ok / len(a), share_B_first=b_first / len(b), share_B_end=b_end / len(b),
               difference=diff, ahead_B=ahead_b, ahead_A=ahead_a,
               later_tries=100.0 * (b_end - b_first) / len(b), verdict=verdict,
               why=f"{diff:+.1f} points over {len(tasks)} task(s); arm B ahead on {ahead_b}, arm A on {ahead_a}")
    return out


def question2(st: dict) -> dict:
    pend_given = [t for t in TASKS if st["given"][t] == "pending"]
    pend = pending_c(st, Q2_CELLS, ("A", "B"))
    cells = {c: q2_cell(st, c) for c in Q2_CELLS}
    if pend_given or pend:
        return {"verdict": PENDING, "cells": cells,
                "why": f"{len(pend)} arm-A or arm-B run(s) of the three cells not ended"
                       + (f"; no given suite fixed yet for {', '.join(pend_given)}" if pend_given else "")}
    if not given_tasks(st):
        return {"verdict": NOT_MEASURED, "cells": cells, "why": "no task has both arms"}
    return {"verdict": "decided", "cells": cells, "why": ""}


# -- question 3 ------------------------------------------------------------------------------------

def question3(st: dict) -> dict:
    cut = st["cut"]
    if cut["arm_c"] or Q3_CELL in cut["cells"]:
        return {"verdict": NOT_MEASURED, "why": "arm C was cut by the spend rule"}
    pend_given = [t for t in TASKS if st["given"][t] == "pending"]
    pend = pending_c(st, (Q3_CELL,), ("B", "C"))
    if pend_given or pend:
        return {"verdict": PENDING, "why": f"{len(pend)} arm-B or arm-C run(s) of {Q3_CELL} not ended"
                + (f"; no given suite fixed yet for {', '.join(pend_given)}" if pend_given else "")}
    tasks = both_arm_tasks(st, Q3_CELL, "B", "C")
    if not tasks:
        return {"verdict": NOT_MEASURED, "why": "no task has arms B and C", "tasks": []}
    b, c = runs_of(st, Q3_CELL, "B", tasks), runs_of(st, Q3_CELL, "C", tasks)
    b_ok = sum(1 for r in b if r["correct"])
    c_ok = sum(1 for r in c if r["correct"])
    c_fin = sum(1 for r in c if r["finished"])
    c_esc = sum(1 for r in c if r["escaped"])
    behind = []
    for t in tasks:
        tb, tc = [r for r in b if r["task"] == t], [r for r in c if r["task"] == t]
        if sum(1 for r in tc if r["correct"]) / len(tc) < sum(1 for r in tb if r["correct"]) / len(tb) - EPS:
            behind.append(t)
    out = {"tasks": tasks, "runs_B": len(b), "runs_C": len(c), "share_B": b_ok / len(b), "share_C": c_ok / len(c),
           "finished_C": c_fin, "escaped_C": c_esc, "behind": behind}
    if len(tasks) < Q3_MIN_TASKS:
        out.update(verdict=TOO_FEW_TASKS, why=f"{len(tasks)} task(s) have both arms (needs {Q3_MIN_TASKS})")
        return out
    conds = {"finished": c_fin >= Q3_FINISHED_SHARE * len(c) - EPS,
             "correct": 100.0 * out["share_C"] >= 100.0 * out["share_B"] - Q3_CORRECT_POINTS_BELOW - EPS,
             "escaped": c_esc <= ESCAPED_MAX_SHARE * c_fin + EPS,
             "behind": len(behind) <= Q3_MAX_TASKS_BEHIND}
    out["conditions"] = conds
    out["verdict"] = ACCEPTABLE if all(conds.values()) else STRONGER
    out["why"] = (f"finished {c_fin} of {len(c)}; correct {100 * out['share_C']:.0f}% against arm B "
                  f"{100 * out['share_B']:.0f}%; escaped {c_esc} of {c_fin} finished; behind on {len(behind)} task(s)")
    return out


# -- question 4 ------------------------------------------------------------------------------------

def rate(k, n):
    return {"k": k, "n": n, "rate": share(k, n), "too_few": n < Q4_MIN_PAIRS}


def q4_cell(st: dict, cell: str) -> dict:
    suites = [st["T"][(t, cell, r)] for t in TASKS for r in range(1, T_RUNS + 1)]
    ended = [s for s in suites if s["state"] == "ended"]
    fit = sum(1 for s in ended if s["fit"])
    cost = sum(s["cost"] for s in ended)
    ms = sum(s["ms"] for s in ended)
    pairs = [p for p in st["cross"]["pairs"] if p["writer"] == cell]
    bad = [p for p in pairs if not p["correct"]]
    good = [p for p in pairs if p["correct"]]
    catch = rate(sum(1 for p in bad if p["fails"]), len(bad))
    wrong = rate(sum(1 for p in good if p["fails"]), len(good))
    return {"cell": cell, "suites": len(ended), "fit": fit, "infra": sum(1 for s in ended if s["ended"] == "infra"),
            "cost": cost, "mean_cost": share(cost, len(ended)), "mean_time_s": share(ms / 1000.0, len(ended)),
            "cost_per_fit": cost / fit if fit else None, "catch": catch, "wrong": wrong,
            "catch_ok": catch["too_few"] or catch["rate"] >= Q4_CATCH_MIN - EPS,
            "wrong_ok": wrong["too_few"] or wrong["rate"] <= Q4_WRONG_MAX + EPS}


def question4(st: dict) -> dict:
    cells = {c: q4_cell(st, c) for c in T_CELLS}
    pend_t = [k for k, o in st["T"].items() if o["state"] == "pending"]
    pend_fit = [k for k, o in st["T"].items() if o["state"] == "ended" and not o["scored"]]
    pend_given = [t for t in TASKS if st["given"][t] == "pending"]
    pend_cross = st["cross"]["missing"]
    out = {"cells": cells, "fast": None, "balanced": None, "notes": []}
    if pend_t or pend_fit or pend_given or pend_cross or pending_c(st, C_CELLS, ("A", "C")):
        out["verdict"] = PENDING
        out["why"] = (f"{len(pend_t)} step-T run(s) not ended, {len(pend_fit)} suite(s) not scored, "
                      f"{len(pend_cross)} cross item(s) missing, arm A or C runs not ended")
        return out
    if not any(s["suites"] for s in cells.values()):
        out["verdict"] = NOT_MEASURED
        out["why"] = "no step-T run ended"
        return out
    out["verdict"] = "decided"
    order = [cells[c] for c in T_CELLS]
    named = [c for c in order if c["fit"] > 0]
    fast = [c for c in named if c["fit"] >= Q4_FAST_MIN_FIT and c["catch_ok"] and c["wrong_ok"]]
    if fast:
        out["fast"] = pick(fast, lambda c: (c["cost_per_fit"],))["cell"]
    else:
        within = [c for c in named if c["wrong_ok"]]
        if within:
            out["fast"] = pick(within, lambda c: (-c["fit"], c["cost_per_fit"]))["cell"]
            out["notes"].append("fast: no cell qualifies; the most fit suites among those that wrongly reject "
                                "at most 10%")
        else:
            measured = [c for c in named if c["wrong"]["rate"] is not None]
            if measured:
                out["fast"] = pick(measured, lambda c: (c["wrong"]["rate"], c["cost_per_fit"]))["cell"]
                out["notes"].append("fast: no cell stays within 10%; the lowest rate of wrong rejections")
            else:
                out["notes"].append("fast: " + NO_CELL)
    bal = [c for c in named if c["fit"] >= Q4_BALANCED_FIT and c["catch_ok"] and c["wrong_ok"]]
    if bal:
        out["balanced"] = pick(bal, lambda c: (c["cost_per_fit"],))["cell"]
    else:
        both = [c for c in named if c["catch_ok"] and c["wrong_ok"]]
        if both:
            out["balanced"] = pick(both, lambda c: (-c["fit"], c["cost_per_fit"]))["cell"]
            out["notes"].append("balanced: no cell qualifies; the most fit suites among those that meet both bounds")
        elif named:
            out["balanced"] = pick(named, lambda c: (-c["fit"], c["cost_per_fit"]))["cell"]
            out["notes"].append("balanced: no cell meets both bounds; the most fit suites")
        else:
            out["notes"].append("balanced: " + NO_CELL)
    out["tip"] = (f"The tip for the main chat of a $20 plan names {out['fast']}. {TIP_TEXT}" if out["fast"]
                  else f"The tip for the main chat of a $20 plan: {NO_CELL}.")
    out["why"] = f"{len(st['cross']['pairs'])} pair(s) of a fit suite and a copy"
    return out


# -- the whole analysis ----------------------------------------------------------------------------

def missing_and_invalid(st: dict) -> dict:
    return {"T_infra": sorted(k for k, o in st["T"].items() if o["ended"] == "infra"),
            "C_infra": sorted(k for k, o in st["C"].items() if o["ended"] == "infra"),
            "cut_cost": sum(o["cut_cost"] for o in list(st["T"].values()) + list(st["C"].values())),
            "cut_incarnations": sum(o["cut_incarnations"] for o in list(st["T"].values()) + list(st["C"].values()))}


def pending_items(st: dict) -> dict:
    return {"T": sorted(k for k, o in st["T"].items() if o["state"] == "pending"),
            "fit": sorted(k for k, o in st["T"].items() if o["state"] == "ended" and not o["scored"]),
            "given": [t for t in TASKS if st["given"][t] == "pending"],
            "C": sorted(k for k, o in st["C"].items() if o["state"] == "pending"),
            "cross": sorted(st["cross"]["missing"], key=lambda x: tuple(str(v) for v in x))}


def analyse(lines: list[dict], cut: dict | None = None, stop_usd: float = STOP_USD) -> dict:
    """Pure: the record's lines in, the whole analysis out."""
    cut = cut or {"cells": set(), "arm_c": False, "runs": {}}
    st = build(lines, cut, stop_usd)
    pend = pending_items(st)
    pending = any(pend.values())
    left = {w: sorted(k for k, o in st["C"].items() if o["state"] == w) for w in ("left_out", "cut", "stopped")}
    left["T_stopped"] = sorted(k for k, o in st["T"].items() if o["state"] == "stopped")
    return {"state": st, "q1": question1(st), "q2": question2(st), "q3": question3(st), "q4": question4(st),
            "pending": pend, "status": PENDING_STATUS if pending else DECIDED_STATUS, "left": left,
            "missing": missing_and_invalid(st),
            "planned": {"T": len(st["T"]), "C": len(st["C"]),
                        **{f"C_{a}": sum(1 for k in st["C"] if k[2] == a) for a in "ABC"}}}


# -- output ----------------------------------------------------------------------------------------

def money(x):
    return "n/a" if x is None else f"${x:.2f}"


def pct(x):
    return "n/a" if x is None else f"{100 * x:.0f}%"


def table(rows: list[list[str]]) -> list[str]:
    widths = [max(len(r[i]) for r in rows) for i in range(len(rows[0]))]
    return ["  " + "  ".join(v.ljust(w) for v, w in zip(r, widths)).rstrip() for r in rows]


def rate_text(r: dict) -> str:
    base = f"{r['k']}/{r['n']}"
    return f"{base} {TOO_FEW}" if r["too_few"] else f"{base} {pct(r['rate'])}"


def key_text(k) -> str:
    return " ".join(str(x) for x in k if x is not None)


def render(an: dict) -> str:
    st = an["state"]
    out = ["Who writes the tests and who writes the code (PREREGISTERED-2026-11-14-coding.md)", ""]
    sp = st["spend"]
    out.append(f"Spend: {money(sp['total'])} over {sp['processes']} model process(es), {sp['unknown']} of unknown "
               f"cost charged ${UNKNOWN_COST_USD:.0f} each; spend stop ${st['stop_usd']:.2f} "
               + ("REACHED" if st["spend_stopped"] else "not reached"))
    mi = an["missing"]
    out.append(f"Cut incarnations (a run cut half way and made again): {mi['cut_incarnations']}, "
               f"{money(mi['cut_cost'])}; counted in the spend, not in any run's cost")
    cut = st["cut"]
    cuts = sorted(cut["cells"]) + (["arm C"] if cut["arm_c"] else []) + [f"{c} to {n} runs per task"
                                                                         for c, n in sorted(cut["runs"].items())]
    out.append("Cut by the spend rule: " + (", ".join(cuts) if cuts else "nothing"))
    p = an["planned"]
    out.append(f"Planned: {p['T']} step-T runs; {p['C']} step-C runs (A {p['C_A']}, B {p['C_B']}, C {p['C_C']})")

    q1 = an["q1"]
    out += ["", "Question 1, bulk coding (arm B):"]
    rows = [["cell", "runs", "correct", "share", "cost", "cost per correct", "finished", "escaped"]]
    for c in Q1_CELLS + (REFERENCE_CELL,):
        s = q1["cells"][c]
        rows.append([c + (" (reference)" if c == REFERENCE_CELL else ""), str(s["runs"]), str(s["correct"]),
                     pct(s["share"]), money(s["cost"]), money(s["cost_per_correct"]), str(s["finished"]),
                     str(s["escaped"])])
    out += table(rows)
    esc = {t: {c: q1["cells"][c]["escaped_per_task"].get(t, 0) for c in Q1_CELLS} for t in TASKS}
    out.append("  escaped per task: " + "; ".join(f"{t} {sum(v.values())}" for t, v in esc.items()))

    q2 = an["q2"]
    out += ["", "Question 2, tests first (correct at the first try in arm B minus correct in arm A):"]
    rows = [["cell", "tasks", "A correct", "B first try", "difference", "B ahead", "A ahead", "tries 2 and 3 add"]]
    for c, s in q2["cells"].items():
        if "difference" in s:
            rows.append([c, str(len(s["tasks"])), pct(s["share_A"]), pct(s["share_B_first"]),
                         f"{s['difference']:+.1f}", str(s["ahead_B"]), str(s["ahead_A"]), f"{s['later_tries']:+.1f}"])
        else:
            rows.append([c, "0", "n/a", "n/a", "n/a", "-", "-", "n/a"])
    out += table(rows)

    q3 = an["q3"]
    out += ["", f"Question 3, who writes the tests ({Q3_CELL}, arms B and C):"]
    if "share_C" in q3:
        out.append(f"  {len(q3['tasks'])} task(s); arm B correct {pct(q3['share_B'])} of {q3['runs_B']}; arm C correct "
                   f"{pct(q3['share_C'])} of {q3['runs_C']}, finished {q3['finished_C']}, escaped {q3['escaped_C']}, "
                   f"behind arm B on {len(q3['behind'])} task(s)")
    else:
        out.append("  no runs to compare")

    q4 = an["q4"]
    out += ["", "Question 4, plan and tests (step T):"]
    rows = [["cell", "fit of suites", "mean cost", "mean time", "cost per fit suite", "catches", "wrongly rejects"]]
    for c in T_CELLS:
        s = q4["cells"][c]
        rows.append([c, f"{s['fit']}/{s['suites']}", money(s["mean_cost"]),
                     "n/a" if s["mean_time_s"] is None else f"{s['mean_time_s']:.0f} s", money(s["cost_per_fit"]),
                     rate_text(s["catch"]), rate_text(s["wrong"])])
    out += table(rows)

    left = an["left"]
    if any(left.values()) or mi["T_infra"] or mi["C_infra"]:
        out += ["", "Left out of every share (listed, never counted as not correct):"]
        for w, label in (("left_out", "no fit suite for the task"), ("cut", "cut by the spend rule"),
                         ("stopped", "never started or cut because of the spend stop")):
            if left[w]:
                out.append(f"  step C, {label}: {len(left[w])}: " + ", ".join(key_text(k) for k in left[w]))
        if left["T_stopped"]:
            out.append(f"  step T, never started because of the spend stop: {len(left['T_stopped'])}: "
                       + ", ".join(key_text(k) for k in left["T_stopped"]))
        if mi["T_infra"]:
            out.append(f"  step T runs ended after three API or infrastructure errors (suite not fit): "
                       + ", ".join(key_text(k) for k in mi["T_infra"]))
        if mi["C_infra"]:
            out.append(f"  step C runs ended after three API or infrastructure errors (not correct, not finished): "
                       + ", ".join(key_text(k) for k in mi["C_infra"]))

    pend = an["pending"]
    if an["status"] == PENDING_STATUS:
        out += ["", "PENDING:"]
        if pend["T"]:
            out.append(f"  step T: {len(pend['T'])} run(s) not ended (write-tests)")
        if pend["fit"]:
            out.append(f"  fix-suites: {len(pend['fit'])} suite(s) not scored")
        if pend["given"]:
            out.append(f"  given suite not fixed for: {', '.join(pend['given'])}")
        if pend["C"]:
            by = defaultdict(int)
            for k in pend["C"]:
                by[(k[1], k[2])] += 1
            out.append(f"  step C: {len(pend['C'])} run(s) not ended (code): "
                       + ", ".join(f"{c} {a} {n}" for (c, a), n in sorted(by.items())))
        if pend["cross"]:
            out.append(f"  cross: {len(pend['cross'])} copy or pair line(s) missing (cross)")

    out += ["", "Verdicts:"]
    if q1["verdict"] in (PENDING, NOT_MEASURED):
        out.append(f"  Question 1: {q1['verdict']} ({q1['why']})")
    else:
        for c in Q1_CELLS:
            s = q1["cells"][c]
            if s["runs"]:
                out.append(f"  Question 1, {c}: {USABLE if s['usable'] else NOT_USABLE} "
                           f"({s['correct']} of {s['runs']} correct)")
            else:
                out.append(f"  Question 1, {c}: no run in arm B; never named")
        out.append(f"  Question 1, fast: {q1['fast'] or NO_CELL}")
        out.append(f"  Question 1, balanced: {q1['balanced'] or NO_CELL}")
        for n in q1["notes"]:
            out.append(f"  Question 1: {n}")
    if q2["verdict"] in (PENDING, NOT_MEASURED):
        out.append(f"  Question 2: {q2['verdict']} ({q2['why']})")
    else:
        for c, s in q2["cells"].items():
            extra = f"; tries 2 and 3 in arm B add {s['later_tries']:+.1f} points" if "later_tries" in s else ""
            out.append(f"  Question 2, {c}: {s['verdict']} ({s['why']}){extra}")
    out.append(f"  Question 3, {Q3_CELL}: {q3['verdict']} ({q3['why']})")
    if q4["verdict"] in (PENDING, NOT_MEASURED):
        out.append(f"  Question 4: {q4['verdict']} ({q4['why']})")
    else:
        out.append(f"  Question 4, fast: {q4['fast'] or NO_CELL}")
        out.append(f"  Question 4, balanced: {q4['balanced'] or NO_CELL}")
        for n in q4["notes"]:
            out.append(f"  Question 4: {n}")
        out.append(f"  {q4['tip']}")
    out.append(f"  Status: {an['status']}")
    return "\n".join(out)


def _keys(obj):
    """JSON-safe: tuple keys become 'a|b|c' strings, sets become sorted lists."""
    if isinstance(obj, dict):
        return {("|".join(str(x) for x in k) if isinstance(k, tuple) else k): _keys(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_keys(v) for v in obj]
    if isinstance(obj, set):
        return sorted(obj)
    return obj


def to_json(an: dict) -> dict:
    st = an["state"]
    return _keys({"status": an["status"], "spend": st["spend"], "spend_stopped": st["spend_stopped"],
                  "stop_usd": st["stop_usd"], "cut": st["cut"], "planned": an["planned"],
                  "given": st["given"], "q1": an["q1"], "q2": an["q2"], "q3": an["q3"], "q4": an["q4"],
                  "pending": an["pending"], "left": an["left"], "missing": an["missing"]})


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--results", default=str(DEFAULT_RESULTS), help="the public record")
    ap.add_argument("--json", action="store_true", help="the same result as one JSON object")
    ap.add_argument("--cut", action="append", default=[],
                    help="what the spend rule cut: a cell, C, or <cell>:<runs per task> (comma-separated)")
    ap.add_argument("--stop-usd", type=float, default=STOP_USD, help=f"the spend stop (default {STOP_USD:g})")
    args = ap.parse_args(argv)
    try:
        an = analyse(read_record(args.results), parse_cut(args.cut), args.stop_usd)
    except AnalysisError as e:
        print(f"code_bench_analysis: error: {e}", file=sys.stderr)
        return 2
    print(json.dumps(to_json(an), sort_keys=True) if args.json else render(an))
    return 0 if an["status"] == DECIDED_STATUS else 3


if __name__ == "__main__":
    sys.exit(main())
