#!/usr/bin/env python3
"""Apply the rules of evals/results/PREREGISTERED-E1-2026-10-10.md to the stored E1 runs.

For every valid run of the E1 tasks (default dont-guess-04 to dont-guess-07) it re-grades the stored
answer block with the task's own grader (the same call evalkit makes) and keeps the per-question outcomes,
so it can count, per cell: H hallucinations (an invented answer to an unanswerable item), W confident wrong
answers to answerable items, M answerable items abstained on, A correct answerable items, pass counts, and
the hallucinations by kind. It then applies Rule A (balanced), Rule B (fast) and Rule D (defective items).

    python3 evals/probes/e1_analysis.py
    python3 evals/probes/e1_analysis.py --exclude dont-guess-05:Q12     # after a Rule D re-read

Output carries counts, item ids and kinds only: never question text, answers or source names, because the
report that quotes it is public. The task material and answers stay under evals/private/.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CANDIDATE, BASELINE, REFERENCE = "haiku-5-5@high", "sonnet-5-5@xhigh", "opus-5-5@xhigh"
TASKS = ("dont-guess-04", "dont-guess-05", "dont-guess-06", "dont-guess-07")
EQUAL_N = 6              # repeats compared at equal N for the decision (runs #1 to #6)
ANSWERABLE_MIN = 0.95    # Rule A (iii)
FAST_MAX_RATE = 0.01     # Rule B
GOOD = {"correct", "abstained"}


def load_grader(task_dir: Path):
    spec = importlib.util.spec_from_file_location(f"e1_grader_{task_dir.name}", task_dir / "grader.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def grade_record(grader, truth: dict, record: dict) -> dict:
    """{"outcomes": per-question outcome, "passed": the grader's verdict} for one stored answer; a missing
    block is a failure on every question."""
    block = record.get("block")
    if block is None:
        return {"outcomes": {q: "missing" for q in truth["questions"]}, "passed": False}
    res = grader.grade(block, truth)
    outcomes = (res.get("details") or {}).get("outcomes")
    if not isinstance(outcomes, dict):
        raise ValueError("grader returned no per-question outcomes")
    return {"outcomes": outcomes, "passed": bool(res.get("passed"))}


def collect(private: Path, runs_path: Path, tasks=TASKS, equal_n: int = EQUAL_N) -> dict:
    """{cell: {task: {repeat: graded record}}} for valid runs with repeat <= equal_n, plus truth by task."""
    graders, truths = {}, {}
    for t in tasks:
        d = private / "tasks" / t
        if d.is_dir():
            graders[t] = load_grader(d)
            truths[t] = json.loads((d / "truth.json").read_text(encoding="utf-8"))
    cells: dict = defaultdict(lambda: defaultdict(dict))
    for line in runs_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if not r.get("valid") or r.get("task_id") not in graders or not 1 <= r.get("repeat", 0) <= equal_n:
            continue
        ans = private / "answers" / f"{r['run_id']}.json"
        if not ans.is_file():
            continue
        record = json.loads(ans.read_text(encoding="utf-8"))
        cells[r["cell_id"]][r["task_id"]][r["repeat"]] = grade_record(graders[r["task_id"]], truths[r["task_id"]], record)
    return {"cells": cells, "truths": truths}


def kind_of(truths, task, qid):
    q = truths[task]["questions"][qid]
    return q.get("kind") or ("answerable" if q.get("answerable") else "unanswerable")


def aggregate(data: dict, cell: str, exclude=frozenset()) -> dict:
    truths = data["truths"]
    runs = passed = 0
    c = Counter()
    unans_item_runs = ans_item_runs = 0
    by_kind_runs: Counter = Counter()
    by_kind_items: dict[str, set] = defaultdict(set)
    for task, reps in data["cells"].get(cell, {}).items():
        qs = truths[task]["questions"]
        for graded in reps.values():
            runs += 1
            passed += graded["passed"]          # the grader's own verdict; exclusions do not change it
            kept = {q: o for q, o in graded["outcomes"].items() if f"{task}:{q}" not in exclude}
            unans = [q for q in kept if not qs[q].get("answerable")]
            ans = [q for q in kept if qs[q].get("answerable")]
            unans_item_runs += len(unans)
            ans_item_runs += len(ans)
            for q, o in kept.items():
                c[o] += 1
                if o == "hallucinated":
                    k = kind_of(truths, task, q)
                    by_kind_runs[k] += 1
                    by_kind_items[k].add(f"{task}:{q}")
    return {"cell": cell, "runs": runs, "passed": passed, "H": c["hallucinated"], "W": c["wrong"], "M": c["missed"],
            "other_fail": c["hedged"] + c["nonconforming"] + c["missing"], "A": c["correct"],
            "unans_item_runs": unans_item_runs, "ans_item_runs": ans_item_runs,
            "halluc_by_kind_runs": dict(by_kind_runs), "halluc_by_kind_items": {k: len(v) for k, v in by_kind_items.items()}}


def distinct_items(data: dict, exclude=frozenset()) -> dict:
    out: Counter = Counter()
    for t, truth in data["truths"].items():
        for qid, q in truth["questions"].items():
            if f"{t}:{qid}" in exclude:
                continue
            out["answerable" if q.get("answerable") else kind_of(data["truths"], t, qid)] += 1
    return dict(out)


def defective_candidates(data: dict, exclude=frozenset()) -> list[str]:
    """Rule D: items that both the baseline and the reference fail in at least half of their runs."""
    flagged = []
    for task, truth in data["truths"].items():
        for qid in truth["questions"]:
            item = f"{task}:{qid}"
            if item in exclude:
                continue
            fails = {}
            for cell in (BASELINE, REFERENCE):
                outs = [g["outcomes"][qid] for g in data["cells"].get(cell, {}).get(task, {}).values() if qid in g["outcomes"]]
                fails[cell] = (sum(1 for o in outs if o not in GOOD), len(outs))
            if all(n and f * 2 >= n for f, n in fails.values()):
                flagged.append(item)
    return flagged


def decide(data: dict, exclude=frozenset()) -> dict:
    cand, base = aggregate(data, CANDIDATE, exclude), aggregate(data, BASELINE, exclude)
    expected_runs = len(data["truths"]) * EQUAL_N
    if cand["runs"] < expected_runs or base["runs"] < expected_runs:
        return {"complete": False, "verdict": "INCOMPLETE: the candidate and the baseline need "
                f"{expected_runs} runs each (6 per task); keep balanced on Sonnet and fast as it is (Rule E)",
                "candidate": cand, "baseline": base}
    a1, a2 = cand["H"] <= base["H"], cand["W"] <= base["W"]
    rate_a = cand["A"] / cand["ans_item_runs"] if cand["ans_item_runs"] else 0.0
    a3 = rate_a >= ANSWERABLE_MIN
    rate_h = cand["H"] / cand["unans_item_runs"] if cand["unans_item_runs"] else 1.0
    rule_a, rule_b = a1 and a2 and a3, rate_h <= FAST_MAX_RATE
    return {"complete": True, "candidate": cand, "baseline": base,
            "A_i_H": a1, "A_ii_W": a2, "A_iii_answerable_rate": round(rate_a, 4), "A_iii": a3,
            "rule_A_balanced": "ADOPT haiku/high for balanced" if rule_a else "KEEP balanced on sonnet/xhigh",
            "B_hallucination_rate": round(rate_h, 4),
            "rule_B_fast": "KEEP haiku/high for fast" if rule_b else "REVERT fast to sonnet/xhigh"}


def render(data: dict, exclude=frozenset()) -> str:
    rows = [aggregate(data, c, exclude) for c in sorted(data["cells"])]
    out = ["Distinct items (all tasks): " + json.dumps(distinct_items(data, exclude), sort_keys=True), "",
           "| cell | runs | passed (grader) | H | W | M | other | A | unans item-runs | ans item-runs | H by kind (item-runs / distinct items) |",
           "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        kinds = ", ".join(f"{k} {r['halluc_by_kind_runs'][k]}/{r['halluc_by_kind_items'].get(k, 0)}" for k in sorted(r["halluc_by_kind_runs"])) or "none"
        out.append(f"| `{r['cell']}` | {r['runs']} | {r['passed']} | {r['H']} | {r['W']} | {r['M']} | {r['other_fail']} | {r['A']} | "
                   f"{r['unans_item_runs']} | {r['ans_item_runs']} | {kinds} |")
    d = decide(data, exclude)
    out += ["", "Rule D candidates (failed by both baseline and reference in at least half their runs): "
            + (", ".join(defective_candidates(data, exclude)) or "none")]
    if not d["complete"]:
        out += ["", d["verdict"]]
    else:
        out += ["", f"Rule A (i) H {d['candidate']['H']} <= baseline {d['baseline']['H']}: {d['A_i_H']}",
                f"Rule A (ii) W {d['candidate']['W']} <= baseline {d['baseline']['W']}: {d['A_ii_W']}",
                f"Rule A (iii) answerable correct {d['A_iii_answerable_rate']:.1%} >= 95%: {d['A_iii']}",
                f"=> {d['rule_A_balanced']}", "",
                f"Rule B hallucination rate {d['B_hallucination_rate']:.2%} (limit 1%) => {d['rule_B_fast']}"]
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--private", default=str(ROOT / "evals" / "private"))
    ap.add_argument("--runs", default=str(ROOT / "evals" / "results" / "runs.jsonl"))
    ap.add_argument("--tasks", default=",".join(TASKS))
    ap.add_argument("--exclude", default="", help="comma-separated task:Qn items removed for every cell (Rule D)")
    args = ap.parse_args(argv)
    data = collect(Path(args.private), Path(args.runs), tuple(t for t in args.tasks.split(",") if t))
    if not data["truths"]:
        print("no E1 tasks found under", args.private, file=sys.stderr)
        return 2
    print(render(data, frozenset(x for x in args.exclude.split(",") if x)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
