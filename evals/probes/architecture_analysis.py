#!/usr/bin/env python3
"""Apply evals/results/PREREGISTERED-2026-11-15-architecture.md to the stored runs of the `design-decision` row:
`opus-5-5@xhigh` against `sonnet-5-5@xhigh` on design-01 (6 runs a cell), design-02 (12) and design-03 (12).

    python3 evals/probes/architecture_analysis.py
    python3 evals/probes/architecture_analysis.py --json

It reads only evals/results/runs.jsonl and evals/results/scores.jsonl (override with --runs and --scores): no
private material, no answer text, no model call. Output carries cell ids, task ids, counts and status words.

Exit code: 0 when every one of the 60 slots is decided (DECIDED); 2 when a run is missing or was lost to API
errors (PENDING), when a judge pass is missing (INCOMPLETE), or on an error.

The counting is that of the earlier round (think_first_analysis.py, whose helpers are used here):
  * A slot is (cell, task, repeat) for repeats 1 to the task's target. Its run is the latest valid line.
  * A run is a SOLID FAIL under a judge model when both of that judge's passes fail it. A split is not.
  * A slot with attempts and no valid one is a FAILED SLOT, unless every attempt was an API or infrastructure
    error: then it is LOST, which is neither failed nor decided, and it has to be run again.
  * New here: a slot with a run that reported a second model is a failed slot too, and is listed. The harness
    switches the advisor off for every child; a run that reached one anyway did not work alone. Such a run
    shows in one of two ways: the harness marks it invalid (`model_mismatch`) and runs the slot again, so the
    slot counts as failed even when the retry is valid; or, for a cell that names an advisor, the valid line
    says `advisor_called`. (Until the audit of 2026-11-15, after the runs, only the second way was read. No line of the
    record carries either mark.)
  * A cell's FAILS under a judge = its solid fails + its failed slots. Every count is made once per judge
    model, and a rule fires only when it fires under both.

Rules (F = fails over all 30 slots, F[task] = fails on one task):
  fast      sonnet when F(sonnet) <= F(opus) + 2 and, on every task, F(sonnet)[task] <= F(opus)[task] + 2
  balanced  sonnet when the fast rule holds, F(sonnet) <= F(opus), and sonnet has more fails than opus on at
            most one task
  cheapest  sonnet (the owner's decision of 2026-11-15); "clearly worse" is reported when
            F(sonnet) > F(opus) + 5 under both judges
  critical  opus
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

_spec = importlib.util.spec_from_file_location("think_first_analysis_helpers", HERE / "think_first_analysis.py")
tf = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tf)
AnalysisError = tf.AnalysisError

OPUS, SONNET = "opus-5-5@xhigh", "sonnet-5-5@xhigh"
CELLS = (OPUS, SONNET)
TARGET = {"design-01": 6, "design-02": 12, "design-03": 12}
TASKS = tuple(TARGET)
JUDGES = tf.JUDGES
NEW_TASK = "design-03"
FAST_MARGIN = 2
CLEARLY_WORSE_MARGIN = 5
BALANCED_MAX_TASKS_BEHIND = 1


def build_slots(runs: list[dict]) -> dict:
    """{(cell, task, repeat): {"attempts": [lines], "valid": latest valid line or None}} for the counted slots."""
    slots: dict = {}
    for r in runs:
        cell, task, rep = r.get("cell_id"), r.get("task_id"), r.get("repeat")
        if cell not in CELLS or task not in TARGET or not isinstance(rep, int) or not 1 <= rep <= TARGET[task]:
            continue
        slot = slots.setdefault((cell, task, rep), {"attempts": [], "valid": None})
        slot["attempts"].append(r)
        if r.get("valid"):
            slot["valid"] = r
    return slots


def check_rubric_hashes(runs: list[dict], scores: list[dict]) -> None:
    """More than one rubric hash for one task and judge would mix stale and fresh gradings."""
    task_of = {r.get("run_id"): r.get("task_id") for r in runs if r.get("cell_id") in CELLS}
    seen: dict = defaultdict(set)
    for s in scores:
        task, parts = task_of.get(s.get("run_id")), tf.judge_parts(s.get("grader_id"))
        if task in TARGET and parts and parts[0] in JUDGES:
            seen[(task, parts[0])].add(parts[1])
    for (task, judge), hashes in sorted(seen.items()):
        if len(hashes) > 1:
            raise AnalysisError(f"task {task}: judge {judge} has scores under {len(hashes)} different rubric "
                                f"hashes; grade again under one rubric before analysing")


def second_model(slot: dict) -> bool:
    """True when a run of the slot reported a model besides the cell's own."""
    if any(str(a.get("invalid_reason") or "").startswith("model_mismatch") for a in slot["attempts"]):
        return True
    return (slot["valid"] or {}).get("advisor_called") is True


def evaluate_slot(slot: dict | None, by_run: dict) -> dict:
    """state: not_run | lost | failed | incomplete | decided. For a decided slot, solid[judge] says whether it is a
    solid fail under that judge; a failed slot is a fail under both."""
    rec = {"state": "not_run", "solid": {}, "missing": 0, "cost": None, "seconds": None, "handled": [],
           "all_pass": False, "advisor": False}
    if not slot or not slot["attempts"]:
        return rec
    run = slot["valid"]
    if run is not None:
        if isinstance(run.get("cost_usd"), (int, float)):
            rec["cost"] = float(run["cost_usd"])
        if isinstance(run.get("duration_ms"), (int, float)):
            rec["seconds"] = run["duration_ms"] / 1000.0
    if second_model(slot):
        rec["state"], rec["advisor"] = "failed", True
        return rec
    if run is None:
        rec["state"] = "lost" if tf.slot_lost(slot) else "failed"
        return rec
    lines = by_run.get(run.get("run_id"), [])
    if tf.has_no_block(lines):
        rec["state"], rec["solid"] = "decided", {j: True for j in JUDGES}
        return rec
    passed = []
    for j in JUDGES:
        passes = tf.judge_passes(lines, j)
        rec["missing"] += sum(1 for i in tf.PASS_INDEXES if i not in passes)
        rec["solid"][j] = tf.solid_fail(passes)
        for line in passes.values():
            passed.append(bool(line.get("passed")))
            details = line.get("details")
            if isinstance(details, dict) and isinstance(details.get("handled"), (int, float)):
                rec["handled"].append(details["handled"])
    rec["state"] = "incomplete" if rec["missing"] else "decided"
    rec["all_pass"] = rec["state"] == "decided" and len(passed) == len(JUDGES) * len(tf.PASS_INDEXES) and all(passed)
    return rec


def mean(values):
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None


def analyse(runs: list[dict], scores: list[dict]) -> dict:
    check_rubric_hashes(runs, scores)
    slots, by_run = build_slots(runs), tf.index_scores(scores)
    an = {"fails": {}, "total": {}, "failed_slots": {}, "missing_runs": {}, "missing_passes": 0,
          "advisor_runs": [], "per_task": {}, "cells": {}}
    pending = incomplete = False
    for cell in CELLS:
        an["fails"][cell] = {j: {t: 0 for t in TASKS} for j in JUDGES}
        an["missing_runs"][cell] = {t: 0 for t in TASKS}
        an["failed_slots"][cell] = 0
        an["per_task"][cell] = {}
        recs_all = []
        for task in TASKS:
            recs = []
            for rep in range(1, TARGET[task] + 1):
                rec = evaluate_slot(slots.get((cell, task, rep)), by_run)
                recs.append(rec)
                if rec["state"] in ("not_run", "lost"):
                    an["missing_runs"][cell][task] += 1
                    pending = True
                elif rec["state"] == "incomplete":
                    an["missing_passes"] += rec["missing"]
                    incomplete = True
                elif rec["state"] == "failed":
                    an["failed_slots"][cell] += 1
                    if rec["advisor"]:
                        an["advisor_runs"].append((cell, task, rep))
                    for j in JUDGES:
                        an["fails"][cell][j][task] += 1
                else:
                    for j in JUDGES:
                        an["fails"][cell][j][task] += 1 if rec["solid"][j] else 0
            decided = [r for r in recs if r["state"] in ("decided", "failed")]
            an["per_task"][cell][task] = {
                "slots": TARGET[task], "decided": len(decided),
                "all_pass": sum(1 for r in recs if r["all_pass"]),
                "handled": mean([h for r in recs for h in r["handled"]]),
                "cost": mean([r["cost"] for r in recs]), "seconds": mean([r["seconds"] for r in recs])}
            recs_all += recs
        an["total"][cell] = {j: sum(an["fails"][cell][j].values()) for j in JUDGES}
        an["cells"][cell] = {"cost": mean([r["cost"] for r in recs_all]),
                             "seconds": mean([r["seconds"] for r in recs_all]),
                             "all_pass": sum(1 for r in recs_all if r["all_pass"])}
    an["status"] = "PENDING" if pending else "INCOMPLETE" if incomplete else "DECIDED"
    return an


def verdict(cell: str, why: str) -> dict:
    return {"cell": cell, "why": why}


def decide(an: dict) -> dict | None:
    """The four cells of the row and whether Sonnet was clearly worse; None until every slot is decided."""
    if an["status"] != "DECIDED":
        return None
    fast_ok = balanced_ok = worse = True
    fast_why, balanced_why = [], []
    for j in JUDGES:
        f_o, f_s = an["total"][OPUS][j], an["total"][SONNET][j]
        over = [t for t in TASKS if an["fails"][SONNET][j][t] > an["fails"][OPUS][j][t] + FAST_MARGIN]
        behind = [t for t in TASKS if an["fails"][SONNET][j][t] > an["fails"][OPUS][j][t]]
        if f_s > f_o + FAST_MARGIN:
            fast_ok = False
            fast_why.append(f"{j}: {f_s} fails against {f_o}, more than {FAST_MARGIN} above")
        if over:
            fast_ok = False
            fast_why.append(f"{j}: more than {FAST_MARGIN} above on {', '.join(over)}")
        if f_s > f_o:
            balanced_ok = False
            balanced_why.append(f"{j}: {f_s} fails against {f_o}")
        if len(behind) > BALANCED_MAX_TASKS_BEHIND:
            balanced_ok = False
            balanced_why.append(f"{j}: behind on {len(behind)} task(s)")
        worse = worse and f_s > f_o + CLEARLY_WORSE_MARGIN
    counts = "; ".join(f"{j}: {an['total'][SONNET][j]} fails against {an['total'][OPUS][j]}" for j in JUDGES)
    fast = verdict(SONNET, counts) if fast_ok else verdict(OPUS, "; ".join(fast_why))
    balanced = (verdict(SONNET, counts) if fast_ok and balanced_ok
                else verdict(OPUS, "; ".join(balanced_why or fast_why)))
    return {"fast": fast, "balanced": balanced,
            "cheapest": verdict(SONNET, "the owner's decision of 2026-11-15; no rule here moves it"),
            "critical": verdict(OPUS, "not in question"), "clearly_worse": worse}


def money(x) -> str:
    return "n/a" if x is None else f"${x:.2f}"


def num(x, unit="") -> str:
    return "n/a" if x is None else f"{x:.1f}{unit}"


def render(an: dict, d: dict | None) -> str:
    out = ["Opus xhigh against Sonnet xhigh on the architecture row (PREREGISTERED-2026-11-15-architecture.md)", ""]
    head = f"  {'cell':<18} {'task':<10} {'runs':>5}  " + "  ".join(f"fails, {j}" for j in JUDGES) \
           + "   all 4 passes  P handled  cost    time"
    out.append(head)
    for cell in CELLS:
        for task in TASKS:
            pt = an["per_task"][cell][task]
            out.append(f"  {cell:<18} {task:<10} {pt['decided']:>2}/{pt['slots']:<2}  "
                       + "  ".join(f"{an['fails'][cell][j][task]:>{len('fails, ' + j)}}" for j in JUDGES)
                       + f"   {pt['all_pass']:>12}  {num(pt['handled']):>9}  {money(pt['cost']):<7} {num(pt['seconds'], ' s')}")
        out.append(f"  {cell:<18} {'all':<10} {sum(an['per_task'][cell][t]['decided'] for t in TASKS):>2}/30  "
                   + "  ".join(f"{an['total'][cell][j]:>{len('fails, ' + j)}}" for j in JUDGES)
                   + f"   {an['cells'][cell]['all_pass']:>12}  {'':>9}  {money(an['cells'][cell]['cost']):<7} "
                   + num(an['cells'][cell]['seconds'], ' s'))
    out.append("")
    out.append(f"  {NEW_TASK} alone (the one checklist no Opus agent wrote): "
               + "; ".join(f"{cell} {an['fails'][cell][j][NEW_TASK]} of {an['per_task'][cell][NEW_TASK]['decided']} "
                           f"under {j}" for cell in CELLS for j in JUDGES))
    for cell in CELLS:
        if an["failed_slots"][cell]:
            out.append(f"  {cell}: {an['failed_slots'][cell]} failed slot(s), counted as fails under both judges")
    for cell, task, rep in an["advisor_runs"]:
        out.append(f"  {cell} {task} repeat {rep}: a run reported a second model; counted as a failed slot")
    for cell in CELLS:
        for task in TASKS:
            if an["missing_runs"][cell][task]:
                out.append(f"  {cell} {task}: {an['missing_runs'][cell][task]} run(s) missing")
    if an["missing_passes"]:
        out.append(f"  {an['missing_passes']} judge pass(es) missing")
    out.append("")
    if d:
        out.append("Verdicts:")
        for name in ("cheapest", "fast", "balanced", "critical"):
            out.append(f"  {name}: {d[name]['cell']} ({d[name]['why']})")
        if d["clearly_worse"]:
            out.append(f"  Sonnet was clearly worse (more than {CLEARLY_WORSE_MARGIN} fails above Opus under both "
                       "judges): the row in cheapest goes back to the owner")
    out.append(f"Status: {an['status']}")
    return "\n".join(out)


def to_json(an: dict, d: dict | None) -> dict:
    return {"status": an["status"], "fails": an["fails"], "total": an["total"],
            "failed_slots": an["failed_slots"], "missing_runs": an["missing_runs"],
            "missing_passes": an["missing_passes"],
            "advisor_runs": [list(x) for x in an["advisor_runs"]],
            "per_task": an["per_task"], "cells": an["cells"], "verdicts": d}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--runs", default=str(ROOT / "evals" / "results" / "runs.jsonl"))
    ap.add_argument("--scores", default=str(ROOT / "evals" / "results" / "scores.jsonl"))
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    try:
        an = analyse(tf.read_jsonl(args.runs), tf.read_jsonl(args.scores))
    except AnalysisError as exc:
        print(f"architecture_analysis: {exc}", file=sys.stderr)
        return 2
    d = decide(an)
    print(json.dumps(to_json(an, d), indent=1) if args.json else render(an, d))
    return 0 if an["status"] == "DECIDED" else 2


if __name__ == "__main__":
    sys.exit(main())
