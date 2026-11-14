#!/usr/bin/env python3
"""Apply the rules of evals/results/PREREGISTERED-2026-11-14-advisor-pairs.md: does Opus 5.5 with a Fable 5.2
advisor judge `design-02` better than Opus alone (question 1), and is Sonnet 5.5 with an Opus 5.5 advisor cheaper
and faster than Opus alone while coming near it in quality (question 2)?

    python3 evals/probes/advisor_pairs_analysis.py
    python3 evals/probes/advisor_pairs_analysis.py --json
    python3 evals/probes/advisor_pairs_analysis.py --evals-dir /some/evals

It reads, under the evals directory (default: the folder above this file): results/runs.jsonl,
results/scores.jsonl, tasks.json (the current task hash of each task), harness.json (only to say when its
limits differ from the test's own) and, when they exist, private/answers/<run_id>.json, only to find the advisor
status of a run. It prints cell ids, task ids, counts, means and rule words. It never prints text from an answer
file and never calls a model.

Exit code: 0 when every slot of the test is decided and every counted run is scored; 3 when something is PENDING
(a slot not run yet, a judge pass missing, scores of one judge under more than one rubric hash, a run of the
four cells judged under another rubric than the stored baselines of its task); 2 when an input cannot be read.

Readings fixed here, where the pre-registration leaves room (each is stated again beside the code):
  * A slot is (cell, task, repeat) for the repeats the rules plan. Only run lines with the task's current hash
    count. The slot's run is its latest valid line. With no valid line, the slot is FAILED once it has three
    invalid attempts that are not API or infrastructure errors (the rule evalkit's plan uses to stop retrying,
    max_retries_invalid 2); otherwise it is NOT RUN YET.
  * Baselines are every valid run (current task hash) of the stored cell on the task, whatever its repeat.
  * A synthesis run "invents an item" when either of its two passes reports fabricated above 0.
  * "Between 75% and 100%" includes 100%: a mean cost equal to Opus's is "cheaper by less than a quarter",
    only above it is "not cheaper". "About the same" includes exactly 110%.
  * Advisor status from free text needs the advisor and a failure word on the same line.
  * A status line "ADVISOR: answered" on a run whose usage shows no advisor is read as a failed call, and
    counted on its own. Only "answered" from the usage enters a rule, so this changes no verdict.
  * The limits of the test are fixed here (1,800 s and $10 a run, as pre-registered): a failed slot takes
    1,800 s whatever harness.json says when the analysis runs, because the rules put the old limits back
    after the test.
  * A failed slot is listed with the time and reason of each counted attempt, so that each can be checked
    against the connection log before the verdict is accepted (the rules set aside an attempt whose window
    holds outage evidence; this tool cannot see that log).
  * Comparisons with a threshold allow 1e-9 for float rounding, so a mean exactly on the line counts as on it.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
EVALS = HERE.parent

# -- the plan of the test (section "What is fixed") ---------------------------

Q1_CELL = "opus-5-5@xhigh+fable-advisor"
Q1_SECOND = "opus-5-5@high+fable-advisor"
SONNET_XHIGH_PAIR = "sonnet-5-5@xhigh+opus-advisor"
SONNET_HIGH_PAIR = "sonnet-5-5@high+opus-advisor"
PAIR_CELLS = (Q1_CELL, Q1_SECOND, SONNET_XHIGH_PAIR, SONNET_HIGH_PAIR)
SONNET_PAIRS = (SONNET_XHIGH_PAIR, SONNET_HIGH_PAIR)

OPUS_XHIGH, OPUS_HIGH, SONNET_XHIGH = "opus-5-5@xhigh", "opus-5-5@high", "sonnet-5-5@xhigh"
BASELINE_CELLS = (OPUS_XHIGH, OPUS_HIGH, SONNET_XHIGH)

DESIGN, SYNTH = "design-02", "synthesis"
ROWS = {DESIGN: ("design-02",), SYNTH: ("synthesize-01", "synthesize-02", "synthesize-03")}
EVALKIT_ROW = {DESIGN: "design-decision", SYNTH: "synthesize"}
TASK_ROW = {t: row for row, tasks in ROWS.items() for t in tasks}

# (cell, row): repeats per task
PLAN = {(Q1_CELL, DESIGN): 6, (Q1_SECOND, DESIGN): 3,
        (SONNET_XHIGH_PAIR, DESIGN): 3, (SONNET_XHIGH_PAIR, SYNTH): 3,
        (SONNET_HIGH_PAIR, DESIGN): 3, (SONNET_HIGH_PAIR, SYNTH): 3}
BASELINE_ROWS = {(c, row) for c in BASELINE_CELLS for row in ROWS}

# -- scoring (section "How a run is scored") ----------------------------------

JUDGES = {DESIGN: ("fable-5-1@high", "opus-5-5@high"), SYNTH: ("fable-5-1@high",)}
SECOND_JUDGE = "opus-5-5@high"
PASS_INDEXES = (0, 1)
FAILED_SLOT_ATTEMPTS = 3
# "How the runs are made": the limits of this test. harness.json goes back to 1,200 s and $6 afterwards.
TEST_LIMITS = {"timeout_s": 1800.0, "cap_usd": 10.0}

# -- rules --------------------------------------------------------------------

Q1_MIN_ANSWERED = 4             # of the 6 runs
Q1_MARGIN = 1.0                 # handled, above or below the stored mean
Q1_MIN_PASSING = 4
Q1_WORSE_VIOLATING = 2
Q2_ANSWERED_NUM, Q2_ANSWERED_DEN = 2, 3     # two thirds of the runs
CHEAPER_AT, NOT_CHEAPER_ABOVE = 0.75, 1.00
FASTER_AT, SLOWER_ABOVE = 0.90, 1.10
NEAR_HANDLED_BELOW = 0.5
NEAR_MAX_MISSED = 1
EPS = 1e-9

BETTER = "better, cause not separated"
WORSE, NO_DIFFERENCE, NOT_DECIDED, PENDING = "worse", "no difference shown", "not decided", "PENDING"
CHEAPER, CHEAPER_LITTLE, NOT_CHEAPER = "cheaper", "cheaper by less than a quarter", "not cheaper"
FASTER, SAME_TIME, SLOWER = "faster", "about the same", "slower"
UNKNOWN = "unknown"
DECIDED_STATUS, PENDING_STATUS = "DECIDED", "PENDING"

# advisor status of a run
ANSWERED, FAILED, NOT_CALLED, NO_FILE, NO_RUN = "answered", "failed", "not called", "unknown", "no valid run"
STATUSES = (ANSWERED, FAILED, NOT_CALLED, NO_FILE, NO_RUN)
ANSWER_MARKER = "===ANSWER==="
STATUS_LINE = re.compile(r"^[\s*_`>]*ADVISOR\s*:\s*(answered|failed|not called)\b", re.IGNORECASE)
STATUS_PREFIX = re.compile(r"^[\s*_`>]*ADVISOR\s*:", re.IGNORECASE)
ADVISOR_WORD = re.compile(r"advisor|danışman", re.IGNORECASE)
FAILURE_WORD = re.compile(r"timed out|timeout|failed|error|unavailable|zaman aş[ıi]m[ıi]", re.IGNORECASE)


class AnalysisError(Exception):
    """An input cannot be read (a missing or broken file)."""


# -- reading -----------------------------------------------------------------

def read_jsonl(path) -> list[dict]:
    path = Path(path)
    if not path.exists():
        raise AnalysisError(f"{path} does not exist")
    out = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            raise AnalysisError(f"{path} line {n} is not JSON") from None
        if isinstance(obj, dict):
            out.append(obj)
    return out


def read_json(path):
    path = Path(path)
    if not path.exists():
        raise AnalysisError(f"{path} does not exist")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        raise AnalysisError(f"{path} is not JSON") from None


def task_hashes(tasks) -> dict:
    """{task id: current task hash} for the tasks of this test; every one must be listed."""
    listed = {t.get("id"): t.get("task_hash") for t in tasks if isinstance(t, dict)} if isinstance(tasks, list) else {}
    missing = [t for t in TASK_ROW if not listed.get(t)]
    if missing:
        raise AnalysisError("tasks.json has no task hash for " + ", ".join(missing))
    return {t: listed[t] for t in TASK_ROW}


def runner_limits(harness) -> dict:
    runner = harness.get("runner") if isinstance(harness, dict) else None
    try:
        return {"timeout_s": float(runner["timeout_s"]), "cap_usd": float(runner["max_budget_usd_per_run"])}
    except (TypeError, KeyError, ValueError):
        raise AnalysisError("harness.json has no runner.timeout_s and runner.max_budget_usd_per_run") from None


class Answers:
    """Reads private/answers/<run_id>.json on demand. Returns None when the folder or the file is missing."""

    def __init__(self, folder):
        self.folder = Path(folder) if folder else None

    def get(self, run_id):
        if not self.folder or not run_id:
            return None
        path = self.folder / f"{run_id}.json"
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            raise AnalysisError(f"answer file {path.name} is not JSON") from None
        return data if isinstance(data, dict) else None


def load(evals_dir) -> dict:
    d = Path(evals_dir)
    return {"runs": read_jsonl(d / "results" / "runs.jsonl"), "scores": read_jsonl(d / "results" / "scores.jsonl"),
            "hashes": task_hashes(read_json(d / "tasks.json")), "limits": runner_limits(read_json(d / "harness.json")),
            "answers": Answers(d / "private" / "answers")}


# -- attempts and slots ------------------------------------------------------

def is_refusal(line: dict) -> bool:
    stops = line.get("safety_stops")
    return (line.get("stop_reason") == "refusal" or str(line.get("invalid_reason") or "").startswith("refusal")
            or (isinstance(stops, (int, float)) and not isinstance(stops, bool) and stops > 0))


def infra_error(line: dict) -> bool:
    """An invalid attempt that is an API or infrastructure fault; it does not use up a retry. Mirrors
    infra_error() in evals/evalkit.py (and think_first_analysis.py)."""
    if line.get("valid") or is_refusal(line):
        return False
    reason = str(line.get("invalid_reason") or "")
    if reason.startswith(("timeout", "json_parse", "model_mismatch")):
        return False
    status = line.get("api_error_status")
    if isinstance(status, int) and not isinstance(status, bool):
        return True
    if reason.startswith("spawn failed"):
        return True
    return (reason == "is_error" or reason.startswith("exit_code=")) and "stop_reason" in line \
        and not line.get("output_tokens")


def number(x):
    return float(x) if isinstance(x, (int, float)) and not isinstance(x, bool) else None


def current_lines(runs: list[dict], hashes: dict) -> list[dict]:
    """Run lines of this test's tasks that carry the task's current hash."""
    return [r for r in runs if r.get("task_id") in hashes and r.get("task_hash") == hashes[r.get("task_id")]]


def slot_state(attempts: list[dict]) -> tuple[str, dict | None, int]:
    """('run', latest valid line, n) or ('failed', None, n) or ('not_run', None, n); n = counted invalid attempts.
    FAILED needs three invalid attempts that are not API errors (evalkit stops retrying there)."""
    valid = [a for a in attempts if a.get("valid")]
    counted = sum(1 for a in attempts if not a.get("valid") and not infra_error(a))
    if valid:
        return "run", valid[-1], counted
    if counted >= FAILED_SLOT_ATTEMPTS:
        return "failed", None, counted
    return "not_run", None, counted


def counted_attempts(attempts: list[dict]) -> list[dict]:
    """[{'ts', 'reason'}] of the invalid attempts that count toward a failed slot, in file order."""
    return [{"ts": a.get("ts"), "reason": str(a.get("invalid_reason") or "invalid")}
            for a in attempts if not a.get("valid") and not infra_error(a)]


# -- scores ------------------------------------------------------------------

def judge_parts(grader_id) -> tuple | None:
    """(judge cell, rubric hash, pass index) of 'judge:<cell>:<hash>:<k>', else None."""
    parts = str(grader_id).split(":")
    if len(parts) != 4 or parts[0] != "judge":
        return None
    try:
        return parts[1], parts[2], int(parts[3])
    except ValueError:
        return None


def judge_passes(lines: list[dict], judge: str) -> tuple[dict, set]:
    """({pass index: latest score line}, rubric hashes seen) of one run under one judge."""
    passes, hashes = {}, set()
    for s in lines:
        parts = judge_parts(s.get("grader_id"))
        if parts and parts[0] == judge and parts[2] in PASS_INDEXES:
            passes[parts[2]] = s
            hashes.add(parts[1])
    return passes, hashes


def detail(line: dict, key: str):
    d = line.get("details")
    return number(d.get(key)) if isinstance(d, dict) else None


def failed_both(passes: dict, test) -> bool:
    """True when both passes of a judge exist and `test` holds for both."""
    return all(i in passes and test(passes[i]) for i in PASS_INDEXES)


def score_design(by_judge: dict) -> dict:
    """design-02: handled = mean over the four passes; passes = no judge fails it in both of its passes;
    violates = one judge says so (violated above 0) in both of its passes."""
    values = [detail(p, "handled") for passes in by_judge.values() for p in passes.values()]
    if any(v is None for v in values):
        return {"error": "a design-02 pass has no handled count"}
    return {"handled": sum(values) / len(values),
            "handled_by_judge": {j: sum(detail(p, "handled") for p in ps.values()) / len(ps) for j, ps in by_judge.items()},
            "passes": not any(failed_both(ps, lambda s: not s.get("passed")) for ps in by_judge.values()),
            "violates": any(failed_both(ps, lambda s: (detail(s, "violated") or 0) > 0) for ps in by_judge.values())}


def score_synth(by_judge: dict) -> dict:
    """Synthesis: passes when both passes pass; missed = reference count - the lower found of the two passes;
    invents an item when either pass reports fabricated above 0."""
    (passes,) = by_judge.values()
    found = [detail(p, "found") for p in passes.values()]
    of = [detail(p, "of") for p in passes.values()]
    if any(v is None for v in found + of):
        return {"error": "a synthesis pass has no found or of count"}
    return {"passes": all(bool(p.get("passed")) for p in passes.values()),
            "missed": max(of) - min(found), "of": max(of),
            "invents": any((detail(p, "fabricated") or 0) > 0 for p in passes.values())}


def score_run(row: str, lines: list[dict]) -> dict:
    """{'score': dict or None, 'missing': [(judge, pass)], 'mixed': [judge], 'rubrics': {judge: set of
    hashes}} for one valid run."""
    by_judge, missing, mixed, rubrics = {}, [], [], {}
    for j in JUDGES[row]:
        passes, hashes = judge_passes(lines, j)
        rubrics[j] = hashes
        if len(hashes) > 1:
            mixed.append(j)
        missing += [(j, i) for i in PASS_INDEXES if i not in passes]
        by_judge[j] = passes
    if missing or mixed:
        return {"score": None, "missing": missing, "mixed": mixed, "rubrics": rubrics}
    score = score_design(by_judge) if row == DESIGN else score_synth(by_judge)
    if "error" in score:
        raise AnalysisError(score["error"])
    return {"score": score, "missing": [], "mixed": [], "rubrics": rubrics}


def reference_counts(runs: list[dict], scores: list[dict]) -> dict:
    """{synthesis task: reference item count} from any score line of that task (largest 'of')."""
    task_of = {r.get("run_id"): r.get("task_id") for r in runs}
    out = {}
    for s in scores:
        task = task_of.get(s.get("run_id"))
        of = detail(s, "of")
        if TASK_ROW.get(task) == SYNTH and of is not None:
            out[task] = max(out.get(task, 0.0), of)
    return out


def failed_slot_score(row: str, task: str, refs: dict) -> dict:
    """A slot with no valid run after three attempts: does not pass, handled 0, misses every reference item."""
    if row == DESIGN:
        return {"handled": 0.0, "handled_by_judge": {j: 0.0 for j in JUDGES[DESIGN]}, "passes": False,
                "violates": False}
    return {"passes": False, "missed": refs.get(task), "of": refs.get(task), "invents": False}


# -- advisor status ----------------------------------------------------------

def text_before_block(result: str) -> str:
    cut = result.rfind(ANSWER_MARKER)
    return result if cut < 0 else result[:cut]


def status_from_text(before: str) -> tuple[str, bool]:
    """(status, claimed answered) from the text before the answer block, for a run whose usage does not show
    the advisor. The last status line counts. 'answered' without usage is a failed call that was claimed."""
    found = [m.group(1).lower() for m in map(STATUS_LINE.match, before.splitlines()) if m]
    if found:
        last = found[-1]
        if last == "answered":
            return FAILED, True
        return (FAILED if last == "failed" else NOT_CALLED), False
    for line in before.splitlines():
        if ADVISOR_WORD.search(line) and FAILURE_WORD.search(line):
            return FAILED, False
    return NOT_CALLED, False


def advisor_status(run: dict, answers) -> dict:
    """{'status', 'claimed' (answered without usage), 'in_block' (a status line inside the answer block)}."""
    data = answers.get(run.get("run_id")) if answers else None
    block = data.get("block") if isinstance(data, dict) else None
    in_block = isinstance(block, str) and any(STATUS_PREFIX.match(l) for l in block.splitlines())
    if run.get("advisor_called") is True:
        return {"status": ANSWERED, "claimed": False, "in_block": in_block}
    if data is None:
        return {"status": NO_FILE, "claimed": False, "in_block": False}
    result = data.get("result") if isinstance(data.get("result"), str) else ""
    status, claimed = status_from_text(text_before_block(result))
    return {"status": status, "claimed": claimed, "in_block": in_block}


# -- units: one per slot or baseline run --------------------------------------

def make_unit(kind, cell, task, repeat, run, by_run, answers, limits, refs):
    row = TASK_ROW[task]
    unit = {"cell": cell, "task": task, "row": row, "repeat": repeat, "kind": kind, "cost": None, "time_s": None,
            "advisor_cost": None, "status": NO_RUN, "claimed": False, "in_block": False, "score": None,
            "missing": [], "mixed": [], "rubrics": {}, "other_rubric": [], "attempts": []}
    if kind == "failed":
        unit.update(time_s=TEST_LIMITS["timeout_s"], score=failed_slot_score(row, task, refs))
        return unit
    if kind == "not_run":
        return unit
    ms = number(run.get("duration_ms"))
    unit.update(cost=number(run.get("cost_usd")), time_s=None if ms is None else ms / 1000.0,
                advisor_cost=number(run.get("advisor_cost_usd")), run_id=run.get("run_id"))
    unit.update(score_run(row, by_run.get(run.get("run_id"), [])))
    if cell in PAIR_CELLS:
        unit.update(advisor_status(run, answers))
    return unit


def build_units(data: dict) -> dict:
    """{(cell, row): [unit]} for the planned slots of the four cells and the stored baseline runs."""
    lines = current_lines(data["runs"], data["hashes"])
    by_run = defaultdict(list)
    for s in data["scores"]:
        by_run[s.get("run_id")].append(s)
    refs = reference_counts(data["runs"], data["scores"])
    attempts = defaultdict(list)
    for r in lines:
        attempts[(r.get("cell_id"), r.get("task_id"), r.get("repeat"))].append(r)
    units = {}
    for (cell, row), repeats in PLAN.items():
        units[(cell, row)] = []
        for task in ROWS[row]:
            for rep in range(1, repeats + 1):
                kind, run, n = slot_state(attempts.get((cell, task, rep), []))
                u = make_unit(kind, cell, task, rep, run, by_run, data["answers"], data["limits"], refs)
                u["invalid_attempts"] = n
                if kind == "failed":
                    u["attempts"] = counted_attempts(attempts.get((cell, task, rep), []))
                units[(cell, row)].append(u)
    for cell, row in sorted(BASELINE_ROWS):
        latest = {}
        for r in lines:
            if r.get("cell_id") == cell and TASK_ROW[r["task_id"]] == row and r.get("valid"):
                latest[r.get("run_id")] = r
        units[(cell, row)] = [make_unit("run", cell, r["task_id"], r.get("repeat"), r, by_run, None, data["limits"], refs)
                              for r in latest.values()]
    mark_other_rubrics(units)
    return units


def mark_other_rubrics(units: dict) -> None:
    """The rules compare a pair with stored runs under "the same graders and judges". A run of the four cells
    whose judge passes carry a rubric hash that no stored baseline run of the same task carries for that judge
    is marked in unit['other_rubric'] (a list of judges); the result is then PENDING."""
    stored = defaultdict(set)
    for key in BASELINE_ROWS:
        for u in units[key]:
            for j, hashes in u["rubrics"].items():
                stored[(u["task"], j)] |= hashes
    for key in PLAN:
        for u in units[key]:
            for j, hashes in u["rubrics"].items():
                known = stored.get((u["task"], j))
                if known and hashes and not hashes <= known:
                    u["other_rubric"].append(j)


# -- summaries ---------------------------------------------------------------

def mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def summarise(row: str, units: list[dict]) -> dict:
    """Means and counts over the slots that are decided (a valid run or a failed slot). Cost leaves out the
    failed slots (cost unknown); time counts them at the time limit."""
    done = [u for u in units if u["kind"] != "not_run"]
    scored = [u for u in done if u["score"] is not None]
    s = {"slots": len(units), "decided": len(done), "not_run": len(units) - len(done),
         "failed_slots": sum(1 for u in done if u["kind"] == "failed"), "scored": len(scored),
         "complete": len(scored) == len(units) and len(units) > 0,
         "answered": sum(1 for u in done if u["status"] == ANSWERED),
         "statuses": {st: sum(1 for u in done if u["status"] == st) for st in STATUSES},
         "claimed": sum(1 for u in done if u["claimed"]), "in_block": sum(1 for u in done if u["in_block"]),
         "cost": mean(u["cost"] for u in done), "cost_n": sum(1 for u in done if u["cost"] is not None),
         "time_s": mean(u["time_s"] for u in done), "time_n": sum(1 for u in done if u["time_s"] is not None),
         "passing": sum(1 for u in scored if u["score"]["passes"])}
    if row == DESIGN:
        s["handled"] = mean(u["score"]["handled"] for u in scored)
        s["violating"] = sum(1 for u in scored if u["score"]["violates"])
        s["handled_by_judge"] = {j: mean(u["score"]["handled_by_judge"][j] for u in scored) for j in JUDGES[DESIGN]}
    else:
        missed = [u["score"]["missed"] for u in scored]
        s["missed"] = None if any(m is None for m in missed) else sum(missed)
        s["of"] = sum(u["score"]["of"] for u in scored if u["score"]["of"] is not None)
        s["inventing"] = sum(1 for u in scored if u["score"]["invents"])
    return s


# -- question 1 --------------------------------------------------------------

def q1_verdict(s: dict, stored_handled: float) -> dict:
    """The rules of question 1 on the summary of the six runs. Not decided comes first and overrides the rest."""
    if not s["complete"] or stored_handled is None:
        return {"verdict": PENDING, "why": f"{s['scored']} of {s['slots']} runs decided and scored"}
    if s["answered"] < Q1_MIN_ANSWERED:
        return {"verdict": NOT_DECIDED, "why": f"the advisor answered in {s['answered']} of {s['slots']} runs "
                                                f"(needs {Q1_MIN_ANSWERED})"}
    diff = s["handled"] - stored_handled
    if diff >= Q1_MARGIN - EPS and s["passing"] >= Q1_MIN_PASSING and s["violating"] == 0:
        return {"verdict": BETTER, "why": f"handled {diff:+.2f}, {s['passing']} of {s['slots']} pass, none violates"}
    if diff <= -Q1_MARGIN + EPS or s["violating"] >= Q1_WORSE_VIOLATING:
        return {"verdict": WORSE, "why": f"handled {diff:+.2f}, {s['violating']} run(s) violate a constraint"}
    return {"verdict": NO_DIFFERENCE, "why": f"handled {diff:+.2f}, {s['passing']} of {s['slots']} pass, "
                                             f"{s['violating']} violate"}


def second_look(s: dict, stored_high: float) -> dict:
    if not s["complete"] or stored_high is None:
        return {"supports": None, "why": f"{s['scored']} of {s['slots']} runs decided and scored"}
    return {"supports": s["handled"] >= stored_high + Q1_MARGIN - EPS,
            "why": f"mean handled {s['handled']:.2f} against stored {stored_high:.2f}"}


# -- question 2 --------------------------------------------------------------

def cost_label(cost, opus_cost):
    if cost is None or not opus_cost:
        return UNKNOWN
    ratio = cost / opus_cost
    if ratio <= CHEAPER_AT + EPS:
        return CHEAPER
    return CHEAPER_LITTLE if ratio <= NOT_CHEAPER_ABOVE + EPS else NOT_CHEAPER


def time_label(time_s, opus_time):
    if time_s is None or not opus_time:
        return UNKNOWN
    ratio = time_s / opus_time
    if ratio <= FASTER_AT + EPS:
        return FASTER
    return SAME_TIME if ratio <= SLOWER_ABOVE + EPS else SLOWER


def near(row: str, s: dict, opus: dict) -> bool:
    if row == SYNTH:
        return (s["passing"] == s["slots"] and s["inventing"] == 0 and s["missed"] is not None
                and s["missed"] <= NEAR_MAX_MISSED)
    return s["handled"] >= opus["handled"] - NEAR_HANDLED_BELOW - EPS and s["violating"] == 0


def q2_verdict(row: str, s: dict, opus: dict) -> dict:
    """Not decided, cheaper, faster, near and 'does what the owner asked' for one Sonnet cell and row."""
    if not s["complete"] or not opus["complete"]:
        return {"verdict": PENDING, "why": f"{s['scored']} of {s['slots']} runs decided and scored"}
    decided = s["answered"] * Q2_ANSWERED_DEN >= s["slots"] * Q2_ANSWERED_NUM
    out = {"decided": decided, "cost": cost_label(s["cost"], opus["cost"]),
           "time": time_label(s["time_s"], opus["time_s"]), "near": near(row, s, opus)}
    out["asked"] = decided and out["cost"] == CHEAPER and out["time"] == FASTER and out["near"]
    out["verdict"] = NOT_DECIDED if not decided else ("does what the owner asked" if out["asked"]
                                                       else "does not do what the owner asked")
    out["why"] = f"the advisor answered in {s['answered']} of {s['slots']} runs"
    return out


# -- the whole analysis ------------------------------------------------------

def thresholds(base: dict) -> dict:
    ox_d, oh_d, ox_s = base[(OPUS_XHIGH, DESIGN)], base[(OPUS_HIGH, DESIGN)], base[(OPUS_XHIGH, SYNTH)]

    def scaled(x, f):
        return None if x is None else x * f

    def shifted(x, d):
        return None if x is None else x + d
    out = {"q1": {"stored_handled": ox_d["handled"],
                  "better_at_least": shifted(ox_d["handled"], Q1_MARGIN),
                  "worse_at_most": shifted(ox_d["handled"], -Q1_MARGIN),
                  "second_look_stored": oh_d["handled"],
                  "second_look_supports_at": shifted(oh_d["handled"], Q1_MARGIN)},
           "q2": {}}
    for row, o in ((SYNTH, ox_s), (DESIGN, ox_d)):
        out["q2"][row] = {"opus_cost": o["cost"], "opus_time_s": o["time_s"],
                          "cheaper_at_most": scaled(o["cost"], CHEAPER_AT), "not_cheaper_above": scaled(o["cost"], NOT_CHEAPER_ABOVE),
                          "faster_at_most": scaled(o["time_s"], FASTER_AT), "slower_above": scaled(o["time_s"], SLOWER_ABOVE)}
        if row == DESIGN:
            out["q2"][row]["near_handled_at_least"] = shifted(o["handled"], -NEAR_HANDLED_BELOW)
        else:
            out["q2"][row]["near_missed_at_most"] = NEAR_MAX_MISSED
    return out


def pending_items(units: dict) -> dict:
    """What is missing: slots not run (per cell and row), judge passes (per row, judge and cell), mixed hashes."""
    not_run, passes, mixed, other = defaultdict(list), defaultdict(set), [], []
    for (cell, row), us in units.items():
        for u in us:
            if u["kind"] == "not_run":
                not_run[(cell, row)].append((u["task"], u["repeat"]))
            for j, i in u["missing"]:
                passes[(row, j)].add(cell)
            for j in u["mixed"]:
                mixed.append((cell, u["task"], u["repeat"], j))
            for j in u["other_rubric"]:
                other.append((cell, u["task"], u["repeat"], j))
    return {"not_run": dict(not_run), "passes": {k: sorted(v) for k, v in passes.items()}, "mixed": mixed,
            "other_rubric": other,
            "missing_passes": sorted((u["cell"], u["task"], u["repeat"], j, i) for us in units.values() for u in us
                                     for j, i in u["missing"])}


def commands(pend: dict) -> list[str]:
    """evalkit commands that would produce what is missing, always with --tasks (rules, 'Commands')."""
    out = []
    for (cell, row), slots in sorted(pend["not_run"].items()):
        out.append(f"python3 evals/evalkit.py run --rows {EVALKIT_ROW[row]} --tasks {','.join(ROWS[row])} "
                   f"--cells {cell} --repeats {PLAN[(cell, row)]}")
    for (row, judge), cells in sorted(pend["passes"].items()):
        cmd = (f"python3 evals/evalkit.py judge --rows {EVALKIT_ROW[row]} --tasks {','.join(ROWS[row])} "
               f"--cells {','.join(cells)}")
        out.append(cmd + (f" --judge-cell {judge}" if judge == SECOND_JUDGE else ""))
    return out


def spend(runs: list[dict], cap: float) -> dict:
    """Known cost of every attempt of the four cells (valid or not), and the attempts with unknown cost."""
    mine = [r for r in runs if r.get("cell_id") in PAIR_CELLS]
    known = sum(number(r.get("cost_usd")) or 0.0 for r in mine)
    unknown = sum(1 for r in mine if number(r.get("cost_usd")) is None)
    return {"attempts": len(mine), "known_usd": known, "unknown_cost_attempts": unknown,
            "bound_usd": known + unknown * cap}


def analyse(data: dict) -> dict:
    """Pure: loaded inputs in, the whole analysis out."""
    units = build_units(data)
    summ = {k: summarise(k[1], us) for k, us in units.items()}
    answered_only = {k: summarise(k[1], [u for u in units[k] if u["status"] == ANSWERED]) for k in PLAN}
    base = {k: summ[k] for k in BASELINE_ROWS}
    q1 = q1_verdict(summ[(Q1_CELL, DESIGN)], base[(OPUS_XHIGH, DESIGN)]["handled"]
                    if base[(OPUS_XHIGH, DESIGN)]["complete"] else None)
    look = second_look(summ[(Q1_SECOND, DESIGN)], base[(OPUS_HIGH, DESIGN)]["handled"]
                       if base[(OPUS_HIGH, DESIGN)]["complete"] else None)
    q2 = {(c, row): q2_verdict(row, summ[(c, row)], base[(OPUS_XHIGH, row)]) for c in SONNET_PAIRS for row in (SYNTH, DESIGN)}
    pend = pending_items(units)
    pending = bool(pend["not_run"] or pend["passes"] or pend["mixed"] or pend["other_rubric"]) \
        or any(not s["complete"] for s in base.values())
    failed = [{"cell": u["cell"], "task": u["task"], "repeat": u["repeat"], "attempts": u["attempts"]}
              for k in PLAN for u in units[k] if u["kind"] == "failed"]
    adv_costs = [u["advisor_cost"] for k in PLAN for u in units[k] if u["status"] == ANSWERED]
    adv_pairs = [(u["advisor_cost"], u["cost"]) for k in PLAN for u in units[k]
                 if u["status"] == ANSWERED and u["advisor_cost"] is not None and u["cost"]]
    return {"units": units, "summary": summ, "answered_only": answered_only, "thresholds": thresholds(base),
            "q1": q1, "second_look": look, "q2": q2, "pending": pend,
            "status": PENDING_STATUS if pending else DECIDED_STATUS, "commands": commands(pend),
            "advisor_cost": {"mean_usd": mean(adv_costs), "n": sum(1 for x in adv_costs if x is not None),
                             "share": (sum(a for a, _ in adv_pairs) / sum(c for _, c in adv_pairs)) if adv_pairs else None},
            "spend": spend(data["runs"], TEST_LIMITS["cap_usd"]), "limits": dict(TEST_LIMITS),
            "harness_limits": data["limits"], "failed_slots": failed}


# -- output ------------------------------------------------------------------

def money(x):
    return "n/a" if x is None else f"${x:.2f}"


def secs(x):
    return "n/a" if x is None else f"{x:.0f} s"


def num(x, d=2):
    return "n/a" if x is None else f"{x:.{d}f}"


def pct(x, ref):
    return "n/a" if x is None or not ref else f"{100 * x / ref:.0f}%"


def table(rows: list[list[str]]) -> list[str]:
    widths = [max(len(r[i]) for r in rows) for i in range(len(rows[0]))]
    return ["  ".join(v.ljust(w) for v, w in zip(r, widths)).rstrip() for r in rows]


def quality(row: str, s: dict) -> str:
    if not s["scored"]:
        return "not scored"
    if row == DESIGN:
        return (f"handled {num(s['handled'])}; {s['passing']} of {s['scored']} pass; "
                f"{s['violating']} violate")
    missed = "n/a" if s["missed"] is None else f"{s['missed']:.0f}"
    return f"{s['passing']} of {s['scored']} pass; {missed} of {s['of']:.0f} items missed; {s['inventing']} invent"


def render(an: dict) -> str:
    S, th = an["summary"], an["thresholds"]
    out = ["Advisor pairs against Opus alone (PREREGISTERED-2026-11-14-advisor-pairs.md)", ""]
    out.append("Baselines (stored valid runs, current task hashes):")
    rows = [["cell", "row", "runs", "mean cost", "mean time", "quality"]]
    for c in BASELINE_CELLS:
        for row in (DESIGN, SYNTH):
            s = S[(c, row)]
            rows.append([c, row, f"{s['scored']}/{s['slots']} scored", money(s["cost"]), secs(s["time_s"]),
                         quality(row, s)])
    out += ["  " + l for l in table(rows)]
    q1t, q2t = th["q1"], th["q2"]
    out += ["", "Thresholds (computed from the unrounded stored means; rounded here):",
            f"  Q1 better: mean handled >= {num(q1t['better_at_least'])} (stored {num(q1t['stored_handled'], 4)} + 1.0), "
            f"at least {Q1_MIN_PASSING} of 6 pass, none violates",
            f"  Q1 worse: mean handled <= {num(q1t['worse_at_most'])} (stored - 1.0), or {Q1_WORSE_VIOLATING} or more violate",
            f"  Q1 not decided: the advisor answered in fewer than {Q1_MIN_ANSWERED} of 6 runs",
            f"  Q1 second look supports a better: mean handled >= {num(q1t['second_look_supports_at'])} "
            f"(stored {OPUS_HIGH} {num(q1t['second_look_stored'], 4)} + 1.0)"]
    for row in (SYNTH, DESIGN):
        t = q2t[row]
        near_text = (f"mean handled >= {num(t['near_handled_at_least'])} and no run violates" if row == DESIGN
                     else f"every run passes, none invents, at most {NEAR_MAX_MISSED} item missed over the runs")
        out += [f"  Q2 {row}: cheaper <= {money(t['cheaper_at_most'])}, not cheaper above {money(t['not_cheaper_above'])} "
                f"(Opus {money(t['opus_cost'])}); faster <= {secs(t['faster_at_most'])}, slower above "
                f"{secs(t['slower_above'])} (Opus {secs(t['opus_time_s'])}); near: {near_text}"]
    out += ["", "The four cells (all slots as they come; a failed slot counts as a failed run):"]
    rows = [["cell", "row", "slots decided", "failed slots", "answered", "mean cost", "mean time", "quality"]]
    for k in PLAN:
        s = S[k]
        rows.append([k[0], k[1], f"{s['decided']}/{s['slots']}", str(s["failed_slots"]), str(s["answered"]),
                     money(s["cost"]) + (f" ({s['cost_n']} known)" if s["cost_n"] != s["decided"] else ""),
                     secs(s["time_s"]), quality(k[1], s)])
    out += ["  " + l for l in table(rows)]
    if an["failed_slots"]:
        out.append("  Failed slots. Check the window of each attempt against the connection log before accepting "
                   "the verdict:")
        for f in an["failed_slots"]:
            out.append(f"    {f['cell']} {f['task']} #{f['repeat']}: "
                       + "; ".join(f"{a['reason']} at {a['ts'] or 'unknown time'}" for a in f["attempts"]))
    if an["harness_limits"] != an["limits"]:
        h = an["harness_limits"]
        out.append(f"  Note: harness.json now has {h['timeout_s']:.0f} s and ${h['cap_usd']:.0f} a run. The test's own "
                   f"limits are used here: {an['limits']['timeout_s']:.0f} s and ${an['limits']['cap_usd']:.0f}.")

    s1 = S[(Q1_CELL, DESIGN)]
    out += ["", f"Question 1 ({Q1_CELL} on {DESIGN}, against stored {OPUS_XHIGH}):"]
    rows = [["", "runs", "answered", "mean handled", "pass", "violate"] + [f"handled {j}" for j in JUDGES[DESIGN]]]
    for label, s in (("pair", s1), ("stored", S[(OPUS_XHIGH, DESIGN)])):
        rows.append([label, str(s["scored"]), str(s["answered"]) if label == "pair" else "-", num(s["handled"]),
                     str(s["passing"]), str(s["violating"])] + [num(s["handled_by_judge"][j]) for j in JUDGES[DESIGN]])
    out += ["  " + l for l in table(rows)]

    out += ["", f"Question 2 (Sonnet with an Opus advisor, against stored {OPUS_XHIGH}):"]
    rows = [["cell", "row", "answered", "mean cost", "of Opus", "cost", "mean time", "of Opus", "time", "near"]]
    for (c, row), v in an["q2"].items():
        s, o = S[(c, row)], S[(OPUS_XHIGH, row)]
        rows.append([c, row, f"{s['answered']}/{s['slots']}", money(s["cost"]), pct(s["cost"], o["cost"]),
                     v.get("cost", "-"), secs(s["time_s"]), pct(s["time_s"], o["time_s"]), v.get("time", "-"),
                     {True: "near", False: "not near"}.get(v.get("near"), "-")])
    out += ["  " + l for l in table(rows)]

    out += ["", "Reported without a verdict:", "  Runs in which the advisor answered, on their own:"]
    rows = [["cell", "row", "runs", "mean cost", "mean time", "quality"]]
    for k, s in an["answered_only"].items():
        rows.append([k[0], k[1], str(s["decided"]), money(s["cost"]), secs(s["time_s"]), quality(k[1], s)])
    out += ["    " + l for l in table(rows)]
    out.append(f"  Against stored {OPUS_HIGH} and {SONNET_XHIGH} (mean cost and time of the pair as a share of theirs):")
    rows = [["cell", "row"] + [f"vs {b}" for b in (OPUS_HIGH, SONNET_XHIGH)]]
    for k in PLAN:
        rows.append([k[0], k[1]] + [f"cost {pct(S[k]['cost'], S[(b, k[1])]['cost'])}, time "
                                    f"{pct(S[k]['time_s'], S[(b, k[1])]['time_s'])}" for b in (OPUS_HIGH, SONNET_XHIGH)])
    out += ["    " + l for l in table(rows)]
    ac = an["advisor_cost"]
    share = "n/a" if ac["share"] is None else f"{100 * ac['share']:.0f}%"
    out.append(f"  Advisor share of cost: mean advisor cost {money(ac['mean_usd'])} over {ac['n']} answered run(s); "
               f"{share} of the cost of those runs")
    tot = {st: sum(S[k]["statuses"][st] for k in PLAN) for st in STATUSES}
    out.append("  Advisor status of the slots: " + ", ".join(f"{st} {tot[st]}" for st in STATUSES))
    out.append(f"  Status line 'ADVISOR: answered' with no advisor usage: {sum(S[k]['claimed'] for k in PLAN)}; "
               f"status line inside the answer block: {sum(S[k]['in_block'] for k in PLAN)}")
    sp = an["spend"]
    out.append(f"  Spend of the four cells' attempts (valid and invalid, judge passes not included): "
               f"{money(sp['known_usd'])} known over {sp['attempts']} attempt(s); {sp['unknown_cost_attempts']} "
               f"attempt(s) with unknown cost; known + ${an['limits']['cap_usd']:.0f} each for those: {money(sp['bound_usd'])}")
    out.append(f"  For the synthesis row, quote: python3 evals/evalkit.py decide")

    pend = an["pending"]
    if an["status"] == PENDING_STATUS:
        out += ["", "PENDING:"]
        for (c, row), slots in sorted(pend["not_run"].items()):
            out.append(f"  {c} {row}: {len(slots)} slot(s) not run yet: "
                       + ", ".join(f"{t} #{r}" for t, r in slots))
        for c, t, r, j, i in pend["missing_passes"]:
            out.append(f"  {c} {t} #{r}: judge {j} pass {i} missing")
        for c, t, r, j in pend["mixed"]:
            out.append(f"  {c} {t} #{r}: judge {j} has scores under more than one rubric hash; judge it again under one")
        for c, t, r, j in pend["other_rubric"]:
            out.append(f"  {c} {t} #{r}: judge {j} scored it under another rubric than the stored baselines of {t}")
        for k, s in S.items():
            if k in BASELINE_ROWS and not s["complete"]:
                out.append(f"  baseline {k[0]} {k[1]}: {s['scored']} of {s['slots']} runs scored")
        if an["commands"]:
            out.append("  Commands that would produce what is missing:")
            out += [f"    {c}" for c in an["commands"]]

    out += ["", "Verdicts:"]
    q1 = an["q1"]
    q1_word = q1["verdict"]
    out.append(f"  Question 1, {Q1_CELL}: {q1_word} ({q1['why']})")
    look = an["second_look"]
    sup = {True: "supports a better", False: "does not support a better", None: PENDING}[look["supports"]]
    out.append(f"  Question 1, second look, {Q1_SECOND}: {sup} ({look['why']}); it changes no verdict")
    for (c, row), v in an["q2"].items():
        if v["verdict"] == PENDING:
            out.append(f"  Question 2, {c}, {row}: {PENDING} ({v['why']})")
        else:
            out.append(f"  Question 2, {c}, {row}: {v['verdict']}; {v['cost']}; {v['time']}; "
                       f"{'near in quality' if v['near'] else 'not near in quality'} ({v['why']})")
    out.append(f"  Status: {an['status']}")
    return "\n".join(out)


def to_json(an: dict) -> dict:
    """The same content as the text, as counts, means, ids and rule words."""
    def summ(s):
        return {k: v for k, v in s.items()}
    return {"status": an["status"],
            "summary": {f"{c}|{row}": summ(s) for (c, row), s in an["summary"].items()},
            "answered_only": {f"{c}|{row}": summ(s) for (c, row), s in an["answered_only"].items()},
            "thresholds": an["thresholds"], "q1": an["q1"], "second_look": an["second_look"],
            "q2": {f"{c}|{row}": v for (c, row), v in an["q2"].items()},
            "pending": {"not_run": {f"{c}|{row}": [f"{t}#{r}" for t, r in v] for (c, row), v in an["pending"]["not_run"].items()},
                        "missing_passes": [f"{c}|{t}#{r}|{j}|{i}" for c, t, r, j, i in an["pending"]["missing_passes"]],
                        "mixed_hashes": [f"{c}|{t}#{r}|{j}" for c, t, r, j in an["pending"]["mixed"]],
                        "other_rubric": [f"{c}|{t}#{r}|{j}" for c, t, r, j in an["pending"]["other_rubric"]]},
            "commands": an["commands"], "advisor_cost": an["advisor_cost"], "spend": an["spend"],
            "limits": an["limits"], "harness_limits": an["harness_limits"], "failed_slots": an["failed_slots"]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--evals-dir", default=str(EVALS), help="the evals folder (default: the folder above this file)")
    ap.add_argument("--json", action="store_true", help="the same result as one JSON object")
    args = ap.parse_args(argv)
    try:
        an = analyse(load(args.evals_dir))
    except AnalysisError as e:
        print(f"advisor_pairs_analysis: error: {e}", file=sys.stderr)
        return 2
    print(json.dumps(to_json(an), sort_keys=True) if args.json else render(an))
    return 0 if an["status"] == DECIDED_STATUS else 3


if __name__ == "__main__":
    sys.exit(main())
