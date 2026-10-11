#!/usr/bin/env python3
"""Apply the rules of evals/results/PREREGISTERED-E1b-2026-10-10.md to the stored E1b runs.

For every valid run of the E1b tasks (default dont-guess-08 to dont-guess-11) it re-grades the stored answer
block with the task's own grader (the same call evalkit makes), using the functions of e1_analysis.py, and
counts per cell H (an invented answer to an unanswerable item), W (a confident wrong answer to an answerable
item), M (abstained on an answerable item) and A (correct answerable item). It then applies Rule A (move
`balanced` to opus/xhigh, including the leave-one-item-out robustness check), Rule B (admit haiku/xhigh to
`fast`), Rule D (defective items) and Rule E (anything short of 6 runs per task keeps both rows), and reports
Rule C (the reference cell, the E1 numbers beside the E1b ones, the pooled counts).

    python3 evals/probes/e1b_analysis.py
    python3 evals/probes/e1b_analysis.py --exclude dont-guess-09:Q12     # after a Rule D re-read

Interpretations fixed here, before any E1b run exists (the rules file leaves them open):
  * "1%" and "0.2 x" and "95%" are tested in integer arithmetic (H*100 >= unanswerable item-runs, 5*H_opus
    <= H_sonnet, A*100 >= 95*answerable item-runs), so no float edge decides anything.
  * Rule A (v): for each item Sonnet hallucinated on, that item is removed from every cell and (ii) must still
    hold. If the removal leaves Sonnet with no hallucination at all, (ii) holds only as 0 <= 0 and nothing is
    left to measure: one item carried the whole result, so (v) fails (Rule E, the conservative reading).
  * Rule E: all three decision cells (opus, sonnet, haiku xhigh) need exactly 6 valid runs on every one of
    the four tasks; a shortfall in any of them keeps both rows as they are.

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

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def _load_e1():
    spec = importlib.util.spec_from_file_location("e1_analysis_for_e1b", HERE / "e1_analysis.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


e1 = _load_e1()

OPUS, SONNET, HAIKU_XHIGH, HAIKU_HIGH = "opus-5-5@xhigh", "sonnet-5-5@xhigh", "haiku-5-5@xhigh", "haiku-5-5@high"
DECISION_CELLS = (OPUS, SONNET, HAIKU_XHIGH)
CELLS = DECISION_CELLS + (HAIKU_HIGH,)
TASKS = ("dont-guess-08", "dont-guess-09", "dont-guess-10", "dont-guess-11")
E1_TASKS = tuple(e1.TASKS)
EQUAL_N = 6                 # repeats per task and cell; Rule E
# Rule D reuses e1.defective_candidates, which reads these two cells from e1; they must be the E1b ones.
assert (e1.BASELINE, e1.REFERENCE) == (SONNET, OPUS)

A_YES, A_NO = "MOVE balanced to opus/xhigh", "KEEP balanced on sonnet/xhigh"
B_YES, B_NO = "ADMIT haiku/xhigh to fast", "KEEP fast on sonnet/xhigh"


def collect(private: Path, runs_path: Path, tasks=TASKS, equal_n: int | None = None) -> dict:
    return e1.collect(private, runs_path, tasks, EQUAL_N if equal_n is None else equal_n)


def restrict(data: dict, tasks) -> dict:
    """The same data limited to some tasks (for the E1-beside and pooled tables)."""
    tasks = [t for t in tasks if t in data["truths"]]
    return {"cells": {c: {t: reps for t, reps in per.items() if t in tasks} for c, per in data["cells"].items()},
            "truths": {t: data["truths"][t] for t in tasks}}


def hallucinated_items(data: dict, cell: str, exclude=frozenset()) -> Counter:
    """{item: hallucinated runs} for one cell."""
    out: Counter = Counter()
    for task, reps in data["cells"].get(cell, {}).items():
        for graded in reps.values():
            for q, o in graded["outcomes"].items():
                if o == "hallucinated" and f"{task}:{q}" not in exclude:
                    out[f"{task}:{q}"] += 1
    return out


def item_kind(data: dict, item: str) -> str:
    task, qid = item.split(":", 1)
    return e1.kind_of(data["truths"], task, qid)


def leave_one_out(data: dict, exclude=frozenset()) -> list[dict]:
    """Rule A (v): remove, one at a time, every item Sonnet hallucinated on (from every cell) and test (ii)."""
    rows = []
    for item in sorted(hallucinated_items(data, SONNET, exclude)):
        ex = frozenset(exclude) | {item}
        so, op = e1.aggregate(data, SONNET, ex), e1.aggregate(data, OPUS, ex)
        degenerate = so["H"] == 0
        rows.append({"item": item, "kind": item_kind(data, item), "H_sonnet": so["H"], "H_opus": op["H"],
                     "degenerate": degenerate, "holds": (not degenerate) and 5 * op["H"] <= so["H"]})
    return rows


def decide(data: dict, exclude=frozenset()) -> dict:
    aggs = {c: e1.aggregate(data, c, exclude) for c in CELLS}
    have = {c: {t: len(data["cells"].get(c, {}).get(t, {})) for t in TASKS} for c in DECISION_CELLS}
    short = sorted(f"{c} {t} {n}/{EQUAL_N}" for c, per in have.items() for t, n in per.items() if n != EQUAL_N)
    missing = sorted(t for t in TASKS if t not in data["truths"])
    if short or missing:
        return {"complete": False, "cells": aggs, "short": short, "missing_tasks": missing,
                "verdict": "INCOMPLETE: every decision cell needs exactly 6 valid runs on each of the 4 tasks; "
                           "balanced and fast stay as they are (Rule E)",
                "rule_A_balanced": A_NO, "rule_B_fast": B_NO}
    op, so, hx = aggs[OPUS], aggs[SONNET], aggs[HAIKU_XHIGH]
    loo = leave_one_out(data, exclude)
    a = {"A_i": so["unans_item_runs"] > 0 and so["H"] * 100 >= so["unans_item_runs"],
         "A_ii": 5 * op["H"] <= so["H"],
         "A_iii": op["W"] <= so["W"],
         "A_iv": op["ans_item_runs"] > 0 and op["A"] * 100 >= 95 * op["ans_item_runs"],
         "A_v": all(r["holds"] for r in loo)}
    b = {"B_i": hx["H"] <= so["H"],
         "B_ii": hx["unans_item_runs"] > 0 and hx["H"] * 100 <= hx["unans_item_runs"],
         "B_iii": hx["W"] <= so["W"],
         "B_iv": hx["ans_item_runs"] > 0 and hx["A"] * 100 >= 95 * hx["ans_item_runs"]}
    return {"complete": True, "cells": aggs, "leave_one_out": loo, **a, **b,
            "rule_A_balanced": A_YES if all(a.values()) else A_NO,
            "rule_B_fast": B_YES if all(b.values()) else B_NO}


def by_task(data: dict, cell: str, exclude=frozenset()) -> dict:
    return {t: e1.aggregate(restrict(data, [t]), cell, exclude) for t in sorted(data["truths"])}


def item_rows(data: dict, cells=CELLS, exclude=frozenset()) -> list[dict]:
    """Every item any cell hallucinated on: id, kind, hallucinated runs / runs per cell."""
    per_cell = {c: hallucinated_items(data, c, exclude) for c in cells}
    items = sorted({i for c in per_cell.values() for i in c})
    rows = []
    for item in items:
        task, qid = item.split(":", 1)
        runs = {c: len([1 for g in data["cells"].get(c, {}).get(task, {}).values() if qid in g["outcomes"]]) for c in cells}
        rows.append({"item": item, "kind": item_kind(data, item),
                     "cells": {c: (per_cell[c].get(item, 0), runs[c]) for c in cells}})
    rows.sort(key=lambda r: (-sum(h for h, _ in r["cells"].values()), r["item"]))
    return rows


def distinct_by_task(data: dict, exclude=frozenset()) -> dict:
    out = {}
    for t, truth in sorted(data["truths"].items()):
        c: Counter = Counter()
        for qid, q in truth["questions"].items():
            if f"{t}:{qid}" in exclude:
                continue
            c["answerable" if q.get("answerable") else e1.kind_of(data["truths"], t, qid)] += 1
        out[t] = dict(sorted(c.items()))
    return out


def _cell_table(data: dict, cells, exclude) -> list[str]:
    out = ["| cell | runs | passed (grader) | H | W | M | other | A | unans item-runs | ans item-runs | H by kind (item-runs / distinct items) |",
           "|---|---|---|---|---|---|---|---|---|---|---|"]
    for c in cells:
        r = e1.aggregate(data, c, exclude)
        if not r["runs"]:
            continue
        kinds = ", ".join(f"{k} {r['halluc_by_kind_runs'][k]}/{r['halluc_by_kind_items'].get(k, 0)}"
                          for k in sorted(r["halluc_by_kind_runs"])) or "none"
        out.append(f"| `{c}` | {r['runs']} | {r['passed']} | {r['H']} | {r['W']} | {r['M']} | {r['other_fail']} | {r['A']} | "
                   f"{r['unans_item_runs']} | {r['ans_item_runs']} | {kinds} |")
    return out


def render(data: dict, exclude=frozenset(), extra: dict | None = None) -> str:
    """extra: {title: data} tables printed after the decision (E1 beside, pooled); none decide anything."""
    out = ["Distinct items per task and kind: " + json.dumps(distinct_by_task(data, exclude), sort_keys=True), ""]
    out += _cell_table(data, CELLS, exclude)
    out += ["", "Hallucinated item-runs by task (H over runs passed / runs):", "",
            "| cell | " + " | ".join(sorted(data["truths"])) + " |", "|---|" + "---|" * len(data["truths"])]
    for c in CELLS:
        per = by_task(data, c, exclude)
        out.append(f"| `{c}` | " + " | ".join(f"{per[t]['H']} ({per[t]['passed']}/{per[t]['runs']})" for t in sorted(per)) + " |")
    rows = item_rows(data, CELLS, exclude)
    out += ["", "Items any cell hallucinated on (hallucinated runs / runs; ids and kinds only):", "",
            "| item | kind | " + " | ".join(f"`{c}`" for c in CELLS) + " |", "|---|---|" + "---|" * len(CELLS)]
    for r in rows:
        out.append(f"| `{r['item']}` | {r['kind']} | " + " | ".join(f"{h}/{n}" for h, n in (r["cells"][c] for c in CELLS)) + " |")
    if not rows:
        out.append("| none | | " + " | ".join("" for _ in CELLS) + " |")
    out += ["", "Rule D candidates (failed by sonnet and opus in at least half their runs): "
            + (", ".join(e1.defective_candidates(data, exclude)) or "none")]
    d = decide(data, exclude)
    out.append("")
    if not d["complete"]:
        out += [d["verdict"], "short: " + (", ".join(d["short"]) or "none") + "; missing tasks: " + (", ".join(d["missing_tasks"]) or "none")]
    else:
        c = d["cells"]
        out += [f"Rule A (i)   H(sonnet) {c[SONNET]['H']} of {c[SONNET]['unans_item_runs']} unanswerable item-runs is at least 1%: {d['A_i']}",
                f"Rule A (ii)  H(opus) {c[OPUS]['H']} <= 0.2 x H(sonnet) {c[SONNET]['H']}: {d['A_ii']}",
                f"Rule A (iii) W(opus) {c[OPUS]['W']} <= W(sonnet) {c[SONNET]['W']}: {d['A_iii']}",
                f"Rule A (iv)  A(opus) {c[OPUS]['A']} of {c[OPUS]['ans_item_runs']} answerable item-runs is at least 95%: {d['A_iv']}",
                f"Rule A (v)   (ii) after removing each item sonnet hallucinated on: {d['A_v']}"]
        for r in d["leave_one_out"]:
            out.append(f"               without `{r['item']}` ({r['kind']}): H(sonnet) {r['H_sonnet']}, H(opus) {r['H_opus']}, "
                       f"holds {r['holds']}" + (" (nothing left of the sonnet signal)" if r["degenerate"] else ""))
        out += [f"=> {d['rule_A_balanced']}", "",
                f"Rule B (i)   H(haiku xhigh) {c[HAIKU_XHIGH]['H']} <= H(sonnet) {c[SONNET]['H']}: {d['B_i']}",
                f"Rule B (ii)  H(haiku xhigh) {c[HAIKU_XHIGH]['H']} of {c[HAIKU_XHIGH]['unans_item_runs']} unanswerable item-runs is at most 1%: {d['B_ii']}",
                f"Rule B (iii) W(haiku xhigh) {c[HAIKU_XHIGH]['W']} <= W(sonnet) {c[SONNET]['W']}: {d['B_iii']}",
                f"Rule B (iv)  A(haiku xhigh) {c[HAIKU_XHIGH]['A']} of {c[HAIKU_XHIGH]['ans_item_runs']} answerable item-runs is at least 95%: {d['B_iv']}",
                f"=> {d['rule_B_fast']}"]
    for title, other in (extra or {}).items():
        out += ["", f"{title} (reported only, Rule C):", ""] + _cell_table(other, CELLS, exclude)
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--private", default=str(ROOT / "evals" / "private"))
    ap.add_argument("--runs", default=str(ROOT / "evals" / "results" / "runs.jsonl"))
    ap.add_argument("--tasks", default=",".join(TASKS))
    ap.add_argument("--exclude", default="", help="comma-separated task:Qn items removed for every cell (Rule D)")
    args = ap.parse_args(argv)
    tasks = tuple(t for t in args.tasks.split(",") if t)
    exclude = frozenset(x for x in args.exclude.split(",") if x)
    everything = collect(Path(args.private), Path(args.runs), tasks + tuple(t for t in E1_TASKS if t not in tasks))
    data = restrict(everything, tasks)
    if not data["truths"]:
        print("no E1b tasks found under", args.private, file=sys.stderr)
        return 2
    extra = {}
    if any(t in everything["truths"] for t in E1_TASKS):
        extra["E1 beside (dont-guess-04 to -07; Opus had 3 repeats there)"] = restrict(everything, E1_TASKS)
        extra["Pooled E1 + E1b (item-runs; Opus N differs between the two)"] = restrict(everything, E1_TASKS + tasks)
    print(render(data, exclude, extra))
    return 0


if __name__ == "__main__":
    sys.exit(main())
