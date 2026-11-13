#!/usr/bin/env python3
"""Apply sections 2 and 3 of evals/results/PREREGISTERED-2026-11-13-think-first.md to the stored runs of the
`design-decision` row (tasks design-01 and design-02): count solid fails per cell under each judge model, decide
which stage-2 runs the rules warrant, and say which cell takes the row in `quality`, `balanced` and `fast`.

    python3 evals/probes/think_first_analysis.py
    python3 evals/probes/think_first_analysis.py --json

It reads only evals/results/runs.jsonl and evals/results/scores.jsonl (override with --runs and --scores): no
private material, no answer text, no model call. Output carries cell ids, counts, rule names and status words.

Exit code: 0 when quality, balanced and fast are all decided; 2 when a judge pass is missing (INCOMPLETE, no
verdict), when a disposition is still PENDING (slots not yet run or stage 2 not yet run), or on an error.

Readings fixed here, where the pre-registration leaves room (each is stated again beside the code):
  * A slot is (cell, task, repeat) for repeats 1 to 6. Its run is the latest valid line for the slot.
  * A slot is FAILED (regardless of judging) when it has attempts and none is valid, or, for a Fable cell, when
    any attempt (valid or not) was REFUSED by the safety classifier, or was answered by a different model. An
    attempt is refused when its run line has stop_reason "refusal", or safety_stops above 0, or an
    invalid_reason starting with "refusal"; it is a wrong model when invalid_reason starts with
    "model_mismatch". A bare is_error or exit_code (a rate limit, a usage limit, an overload) is NOT a refusal.
    Run lines written before evalkit recorded stop_reason and safety_stops lack both: they read as not refused.
    A failed slot needs no judge passes. The count the rules use is "fails" = solid fails under that judge +
    failed slots; a no_block run is a solid fail under every judge and needs no judge passes.
  * A slot whose attempts are ALL invalid AND ALL API or infrastructure errors (infra_error: a rate limit, an
    overload, a spawn failure) is LOST: not failed and not decided, so its cell stays PENDING for every rule
    that needs all 12 slots; it has to be run again. One non-infra invalid attempt (a timeout) with no valid
    run keeps the slot failed. A valid run after infra errors is an ordinary slot.
  * A rule that needs 12 slots is PENDING until all 12 are decided. A cell with a fail under either judge is
    out of Rule Q and B for good (they need 0 under both), so it is not pending.
  * "Both fail" fires only when Rule Q's opus condition holds (>= 4 under both judges) and every Fable cell has
    at least one fail under both judges; any other case that stays on opus-5-5@xhigh is "otherwise".
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

TASKS = ("design-01", "design-02")
JUDGES = ("fable-5-1@high", "opus-5-5@high")
PASS_INDEXES = (0, 1)
FABLE_CELLS = ("fable-5-2@low", "fable-5-2@medium", "fable-5-2@high")
OPUS_XHIGH = "opus-5-5@xhigh"
OPUS_HIGH = "opus-5-5@high"
SONNET_XHIGH = "sonnet-5-5@xhigh"
FAST_CANDIDATES = (OPUS_HIGH, SONNET_XHIGH)
CELLS = FABLE_CELLS + (OPUS_XHIGH,) + FAST_CANDIDATES
STAGE1_REPEATS = (1, 2, 3)
ALL_REPEATS = (1, 2, 3, 4, 5, 6)
SLOTS_PER_CELL = len(TASKS) * len(ALL_REPEATS)          # 12
STAGE1_SLOTS = len(TASKS) * len(STAGE1_REPEATS)         # 6
RULE_Q_MIN_OPUS_FAILS = 4
RULE_B_MIN_OPUS_FAILS = 6

# What marks a Fable attempt as refused or as answered by another model. evalkit's run_record copies the CLI
# result JSON's top-level stop_reason and safety_stops onto every run line (old lines lack them: null and 0).
#   refused      stop_reason == "refusal", or safety_stops > 0, or invalid_reason starting with "refusal"
#   wrong model  invalid_reason starting with "model_mismatch" (parse_call in evals/evalkit.py: modelUsage does
#                not name exactly the cell's model, for example a fallback after a classifier flag)
# "is_error" and "exit_code=<n>" are deliberately NOT refusals: a rate limit, a usage limit or an overload
# produces them too, and the pre-registration counts a classifier refusal, not an infrastructure fault.
REFUSAL_STOP_REASONS = ("refusal",)
REFUSAL_REASONS = ("refusal",)
WRONG_MODEL_REASONS = ("model_mismatch",)

RUN_USD_MARGIN = 1.5            # --max-usd printed for stage 2 = measured mean cost x runs to add x this, rounded up
RUN_USD_FALLBACK = 6.0          # per run, when a cell has no measured cost (harness runner.max_budget_usd_per_run)

RULE_Q, RULE_B, RULE_FAST = "rule Q", "rule B", "rule fast"
RULE_OTHERWISE, RULE_BOTH_FAIL = "otherwise", "both fail"
DECIDED, PENDING, INCOMPLETE, VERDICT = "decided", "pending", "INCOMPLETE", "VERDICT"
NOT_ADOPTED = "Fable 5.2 measured, not adopted"
NO_CELL_PASSED = "no cell passed these tasks"


class AnalysisError(Exception):
    """The stored data cannot be analysed (mixed rubric hashes, unreadable file)."""


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


# -- slots, passes, solid fails ----------------------------------------------

def is_refusal(line: dict) -> bool:
    stops = line.get("safety_stops")
    return (line.get("stop_reason") in REFUSAL_STOP_REASONS
            or str(line.get("invalid_reason") or "").startswith(REFUSAL_REASONS)
            or (isinstance(stops, (int, float)) and not isinstance(stops, bool) and stops > 0))


def infra_error(line: dict) -> bool:
    """An INVALID attempt that is an API or infrastructure fault, not the model's doing. This mirrors
    infra_error() in evals/evalkit.py (a test keeps the two in step): a non-null api_error_status, or a
    `spawn failed` reason, or `is_error` / `exit_code=` with no output (output_tokens 0 or null, only on a
    line that has the stop_reason key) that is not a refusal. A timeout, json_parse, model_mismatch, a
    refusal and a valid line are never infra errors."""
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


def attempt_class(line: dict) -> str | None:
    """'refusal' or 'wrong_model' for a refused or wrong-model attempt (valid or not); 'other' for any other
    invalid attempt; None for a valid attempt that was neither."""
    if is_refusal(line):
        return "refusal"
    if str(line.get("invalid_reason") or "").startswith(WRONG_MODEL_REASONS):
        return "wrong_model"
    return None if line.get("valid") else "other"


def build_slots(runs: list[dict]) -> dict:
    """{(cell, task, repeat): {"attempts": [lines], "valid": latest valid line or None}} for the counted slots."""
    slots: dict = {}
    for r in runs:
        key = (r.get("cell_id"), r.get("task_id"), r.get("repeat"))
        if key[0] not in CELLS or key[1] not in TASKS or key[2] not in ALL_REPEATS:
            continue
        slot = slots.setdefault(key, {"attempts": [], "valid": None})
        slot["attempts"].append(r)
        if r.get("valid"):
            slot["valid"] = r
    return slots


def index_scores(scores: list[dict]) -> dict:
    by_run: dict = defaultdict(list)
    for s in scores:
        by_run[s.get("run_id")].append(s)
    return by_run


def judge_parts(grader_id) -> tuple | None:
    """(judge cell, rubric hash, pass index) of a 'judge:<cell>:<sha8>:<k>' grader id, else None."""
    parts = str(grader_id).split(":")
    if len(parts) != 4 or parts[0] != "judge":
        return None
    try:
        return parts[1], parts[2], int(parts[3])
    except ValueError:
        return None


def check_rubric_hashes(runs: list[dict], scores: list[dict]) -> None:
    """Stale and fresh gradings must not be mixed: more than one rubric hash for one task and judge is an error."""
    task_of = {r.get("run_id"): r.get("task_id") for r in runs}
    seen: dict = defaultdict(set)
    for s in scores:
        task, parts = task_of.get(s.get("run_id")), judge_parts(s.get("grader_id"))
        if task in TASKS and parts and parts[0] in JUDGES:
            seen[(task, parts[0])].add(parts[1])
    for (task, judge), hashes in sorted(seen.items()):
        if len(hashes) > 1:
            raise AnalysisError(f"task {task}: judge {judge} has scores under {len(hashes)} different rubric "
                                f"hashes; grade again under one rubric before analysing")


def judge_passes(lines: list[dict], judge: str) -> dict:
    """{pass index: score line} of one run under one judge; the latest line wins for an index."""
    out = {}
    for s in lines:
        parts = judge_parts(s.get("grader_id"))
        if parts and parts[0] == judge and parts[2] in PASS_INDEXES:
            out[parts[2]] = s
    return out


def has_no_block(lines: list[dict]) -> bool:
    return any(isinstance(s.get("details"), dict) and s["details"].get("no_block") is True for s in lines)


def solid_fail(passes: dict) -> bool:
    """Both passes exist and both failed. A split is not a solid fail."""
    return all(i in passes and not passes[i].get("passed") for i in PASS_INDEXES)


def slot_lost(slot: dict) -> bool:
    """Every attempt is invalid and every one is an API or infrastructure error: no measurement was made."""
    return bool(slot["attempts"]) and slot["valid"] is None and all(infra_error(a) for a in slot["attempts"])


def slot_failed(cell: str, slot: dict) -> bool:
    """Failed regardless of judging (section 2, 'A failed run'). A slot lost to API errors is not failed."""
    if not slot["attempts"] or slot_lost(slot):
        return False
    if slot["valid"] is None:
        return True
    return cell in FABLE_CELLS and any(attempt_class(a) in ("refusal", "wrong_model") for a in slot["attempts"])


def evaluate_slot(cell: str, task: str, repeat: int, slot: dict | None, by_run: dict) -> dict:
    rec = {"cell": cell, "task": task, "repeat": repeat, "state": "not_run", "solid": {}, "missing": [],
           "cost": None}
    if not slot or not slot["attempts"]:
        return rec
    run = slot["valid"]
    if run is not None and isinstance(run.get("cost_usd"), (int, float)):
        rec["cost"] = float(run["cost_usd"])
    if slot_lost(slot):
        rec["state"] = "lost"                       # neither failed nor decided: it has to be run again
        return rec
    if slot_failed(cell, slot):
        rec["state"] = "failed"
        return rec
    lines = by_run.get(run.get("run_id"), [])
    if has_no_block(lines):
        rec["state"], rec["solid"] = "decided", {j: True for j in JUDGES}
        return rec
    for j in JUDGES:
        passes = judge_passes(lines, j)
        rec["missing"] += [(j, i) for i in PASS_INDEXES if i not in passes]
        rec["solid"][j] = solid_fail(passes)
    rec["state"] = "incomplete" if rec["missing"] else "decided"
    return rec


def cell_stats(cell: str, recs: list[dict]) -> dict:
    """Counts for one cell over its slots. fails = solid fails + failed slots, the number the rules read."""
    decided = [r for r in recs if r["state"] in ("decided", "failed")]
    stage1 = [r for r in decided if r["repeat"] in STAGE1_REPEATS]
    failed = [r for r in decided if r["state"] == "failed"]

    def solid(rs, j):
        return sum(1 for r in rs if r["state"] == "decided" and r["solid"][j])

    def fails(rs, j):
        return solid(rs, j) + sum(1 for r in rs if r["state"] == "failed")

    costs = [r["cost"] for r in recs if r["cost"] is not None]
    lost = [r for r in recs if r["state"] == "lost"]
    return {"cell": cell, "slots": len(recs), "decided": len(decided), "stage1_decided": len(stage1),
            "failed": len(failed), "lost": len(lost), "lost_repeats": sorted({r["repeat"] for r in lost}), "solid": {j: solid(decided, j) for j in JUDGES},
            "fails": {j: fails(decided, j) for j in JUDGES},
            "stage1_fails": {j: fails(stage1, j) for j in JUDGES},
            "task_fails": {j: {t: fails([r for r in decided if r["task"] == t], j) for t in TASKS} for j in JUDGES},
            "mean_cost": sum(costs) / len(costs) if costs else None, "cost_n": len(costs),
            "unrun_stage2": [r for r in recs if r["state"] in ("not_run", "lost") and r["repeat"] not in STAGE1_REPEATS]}


def analyse(runs: list[dict], scores: list[dict]) -> dict:
    """Pure: parsed runs.jsonl and scores.jsonl lines in, the analysis out. Raises AnalysisError."""
    check_rubric_hashes(runs, scores)
    slots, by_run = build_slots(runs), index_scores(scores)
    recs = {c: [evaluate_slot(c, t, r, slots.get((c, t, r)), by_run) for t in TASKS for r in ALL_REPEATS]
            for c in CELLS}
    stats = {c: cell_stats(c, rs) for c, rs in recs.items()}
    missing = [(r["cell"], r["task"], r["repeat"], j, i) for rs in recs.values() for r in rs
               if r["state"] == "incomplete" for j, i in r["missing"]]
    invalid = {c: dict.fromkeys(("refusal", "wrong_model", "other"), 0) for c in FABLE_CELLS}
    for (c, _, _), slot in slots.items():
        for a in slot["attempts"]:
            if c in FABLE_CELLS and attempt_class(a):
                invalid[c][attempt_class(a)] += 1
    return {"cells": stats, "missing": missing, "fable_invalid": invalid}


# -- stage logic -------------------------------------------------------------

def opus_conditions(an: dict) -> dict:
    """Which opus-5-5@xhigh conditions hold under BOTH judges (None while its 12 slots are not decided)."""
    o = an["cells"][OPUS_XHIGH]
    if o["decided"] < SLOTS_PER_CELL:
        return {"complete": False, "q": None, "b": None}
    q = all(o["fails"][j] >= RULE_Q_MIN_OPUS_FAILS for j in JUDGES)
    b = all(o["fails"][j] >= RULE_B_MIN_OPUS_FAILS and all(o["task_fails"][j][t] >= 1 for t in TASKS)
            for j in JUDGES)
    return {"complete": True, "q": q, "b": b}


def stage2_state(cell: str, an: dict) -> tuple[str, str]:
    """('warranted' | 'not warranted' | 'waiting', reason) for the cells that can run repeats 4 to 6."""
    s = an["cells"][cell]
    if s["stage1_decided"] < STAGE1_SLOTS:
        return "waiting", f"stage 1 has {s['stage1_decided']}/{STAGE1_SLOTS} slots decided"
    if any(s["stage1_fails"][j] > 0 for j in JUDGES):
        return "not warranted", "a fail in stage 1 under at least one judge"
    if cell in FABLE_CELLS:
        oc = opus_conditions(an)
        if not oc["complete"]:
            return "waiting", f"{OPUS_XHIGH} has {an['cells'][OPUS_XHIGH]['decided']}/{SLOTS_PER_CELL} slots decided"
        if not oc["q"]:
            return "not warranted", f"{OPUS_XHIGH} has fewer than {RULE_Q_MIN_OPUS_FAILS} fails under a judge"
    return "warranted", "no fail in stage 1" + (f" and {OPUS_XHIGH} has >= {RULE_Q_MIN_OPUS_FAILS} fails under both judges"
                                                  if cell in FABLE_CELLS else "")


def cell_state(cell: str, an: dict) -> str:
    """'out' (a fail under a judge), 'clear' (12 slots decided, no fail under either judge) or 'pending'."""
    s = an["cells"][cell]
    if any(s["fails"][j] > 0 for j in JUDGES):
        return "out"
    return "clear" if s["decided"] >= SLOTS_PER_CELL else "pending"


def needed(cell: str, an: dict) -> int:
    """Slots a cell must have decided before its count is final: 12 once stage 2 applies, else the 6 of stage 1."""
    return SLOTS_PER_CELL if cell == OPUS_XHIGH or stage2_state(cell, an)[0] == "warranted" else STAGE1_SLOTS


def stage2_plan(an: dict) -> dict:
    """{'lines': [(reason, command)], 'cells': [...], 'max_usd': N, 'notes': [...]}."""
    groups = (("Fable cells", FABLE_CELLS), ("cheaper candidates for fast", FAST_CANDIDATES))
    lines, all_cells, total, notes = [], [], 0.0, []
    for label, cells in groups:
        todo, group_usd = [], 0.0
        for c in cells:
            state, why = stage2_state(c, an)
            if state != "warranted":
                notes.append(f"{c}: stage 2 {state} ({why})")
                continue
            unrun = an["cells"][c]["unrun_stage2"]
            if not unrun:
                notes.append(f"{c}: stage 2 warranted ({why}) and already run")
                continue
            mean = an["cells"][c]["mean_cost"]
            group_usd += (mean if mean is not None else RUN_USD_FALLBACK) * len(unrun)
            todo.append(c)
        if todo:
            usd = max(1, math.ceil(group_usd * RUN_USD_MARGIN))
            lines.append((f"{label}: stage 2 warranted",
                          "python3 evals/evalkit.py run --phase all --rows design-decision "
                          f"--cells {','.join(todo)} --repeats 6 --max-usd {usd}"))
            all_cells += todo
            total += usd
    return {"lines": lines, "cells": all_cells, "max_usd": int(total), "notes": notes}


def lost_plan(an: dict, skip=()) -> list[tuple[str, str]]:
    """[(cell, run command)] for the slots lost to API errors, which need running again. `skip`: cells whose
    stage-2 line already covers theirs. --repeats is the highest repeat that was lost for the cell; plan only
    issues what is still missing up to it."""
    out = []
    for c in CELLS:
        s = an["cells"][c]
        if not s["lost"] or c in skip:
            continue
        mean = s["mean_cost"] if s["mean_cost"] is not None else RUN_USD_FALLBACK
        usd = max(1, math.ceil(mean * s["lost"] * RUN_USD_MARGIN))
        out.append((c, "python3 evals/evalkit.py run --phase all --rows design-decision "
                       f"--cells {c} --repeats {max(s['lost_repeats'])} --max-usd {usd}"))
    return out


# -- dispositions ------------------------------------------------------------

def cheapest(cells, an: dict) -> str:
    """Lowest measured mean cost per valid run; no measured cost sorts last; a tie keeps the listed order."""
    return min(cells, key=lambda c: (an["cells"][c]["mean_cost"] is None, an["cells"][c]["mean_cost"] or 0.0))


def disposition(status: str, cell: str | None, rule: str, why: str = "") -> dict:
    return {"status": status, "cell": cell, "rule": rule, "why": why}


def fallback(an: dict, kind: str) -> dict:
    """Row stays opus-5-5@xhigh: 'both fail' when nothing at all passed, else 'otherwise'."""
    oc = opus_conditions(an)
    all_out = all(cell_state(c, an) == "out" and all(an["cells"][c]["fails"][j] > 0 for j in JUDGES)
                  for c in FABLE_CELLS)
    if oc["q"] and all_out:
        return disposition(DECIDED, OPUS_XHIGH, RULE_BOTH_FAIL, NO_CELL_PASSED)
    return disposition(DECIDED, OPUS_XHIGH, RULE_OTHERWISE, NOT_ADOPTED)


def pick_fable(an: dict, kind: str) -> dict:
    """Rule Q (kind 'quality') or Rule B (kind 'balanced')."""
    rule, key = (RULE_Q, "q") if kind == "quality" else (RULE_B, "b")
    oc = opus_conditions(an)
    if not oc["complete"]:
        return disposition(PENDING, None, rule, f"{OPUS_XHIGH} has {an['cells'][OPUS_XHIGH]['decided']}/"
                                                 f"{SLOTS_PER_CELL} slots decided")
    if not oc[key]:
        return fallback(an, kind)
    states = {c: cell_state(c, an) for c in FABLE_CELLS}
    pending = [c for c, s in states.items() if s == "pending"]
    if pending:
        return disposition(PENDING, None, rule, "waiting for 12 decided slots of " + ", ".join(pending))
    clear = [c for c, s in states.items() if s == "clear"]
    if not clear:
        return fallback(an, kind)
    best = cheapest(clear, an)
    return disposition(DECIDED, best, rule, f"cheapest of {len(clear)} qualifying Fable cell(s)")


def pick_fast(an: dict) -> dict:
    states = {c: cell_state(c, an) for c in FAST_CANDIDATES}
    pending = [c for c, s in states.items() if s == "pending"]
    if pending:
        return disposition(PENDING, None, RULE_FAST, "waiting for 12 decided slots of " + ", ".join(pending))
    clear = [c for c, s in states.items() if s == "clear"]
    if clear:
        return disposition(DECIDED, cheapest(clear, an), RULE_FAST, f"cheapest of {len(clear)} candidate(s) with 0 fails")
    return disposition(DECIDED, OPUS_XHIGH, RULE_FAST, "neither candidate has 0 fails in 12 runs")


def decide(an: dict) -> dict:
    return {"quality": pick_fable(an, "quality"), "balanced": pick_fable(an, "balanced"), "fast": pick_fast(an)}


def overall_status(an: dict, disp: dict | None) -> str:
    if an["missing"]:
        return INCOMPLETE
    return VERDICT if all(d["status"] == DECIDED for d in disp.values()) else PENDING


# -- output ------------------------------------------------------------------

def money(x) -> str:
    return "n/a" if x is None else f"${x:.4f}"


def render(an: dict, disp: dict | None, plan: dict | None) -> str:
    out = ["Think-first rules (PREREGISTERED-2026-11-13-think-first.md, section 3), tasks "
           + ", ".join(TASKS) + "; judges " + " and ".join(JUDGES), ""]
    head = ["cell", "slots decided"] + [f"solid fails {j}" for j in JUDGES] + ["failed slots", "lost to API errors", "mean cost/run"]
    rows = [head]
    for c in CELLS:
        s = an["cells"][c]
        need = needed(c, an)
        rows.append([c, f"{s['decided']}/{need}"] + [str(s["solid"][j]) for j in JUDGES]
                    + [str(s["failed"]), str(s["lost"]), money(s["mean_cost"])])
    widths = [max(len(r[i]) for r in rows) for i in range(len(head))]
    out += ["  ".join(v.ljust(w) for v, w in zip(r, widths)).rstrip() for r in rows]
    out += ["", "Count the rules read = solid fails + failed slots, per judge: "
            + "; ".join(f"{c} " + "/".join(str(an['cells'][c]['fails'][j]) for j in JUDGES) for c in CELLS)]
    o = an["cells"][OPUS_XHIGH]
    out.append(f"{OPUS_XHIGH} fails per task under " + "; ".join(
        f"{j}: " + ", ".join(f"{t} {o['task_fails'][j][t]}" for t in TASKS) for j in JUDGES))
    inv = an["fable_invalid"]
    out.append("Fable attempts (refused / wrong model / other invalid): "
               + "; ".join(f"{c} {inv[c]['refusal']}/{inv[c]['wrong_model']}/{inv[c]['other']}" for c in FABLE_CELLS))
    if an["missing"]:
        out += ["", f"INCOMPLETE: {len(an['missing'])} judge pass(es) missing; no verdict until they are scored "
                    "(`evalkit.py judge`, and `evalkit.py judge --judge-cell <cell>` for the second judge):"]
        out += [f"  {c} {t} repeat {r}: {j} pass {i}" for c, t, r, j, i in an["missing"]]
        return "\n".join(out)
    out += ["", "Stage 2:"]
    if plan["lines"]:
        for why, cmd in plan["lines"]:
            out += [f"  {why}:", f"    {cmd}"]
    else:
        out.append("  none are warranted or still to run")
    out += [f"  {n}" for n in plan["notes"]]
    lost = lost_plan(an, skip=plan["cells"])
    if any(an["cells"][c]["lost"] for c in CELLS):
        out += ["", "Slots lost to API errors (every attempt a rate limit, overload or other API fault; not failed, "
                    "not decided, so their cells stay PENDING until they are run again):"]
        out += [f"  {c}: {an['cells'][c]['lost']} slot(s)" for c in CELLS if an["cells"][c]["lost"]]
        out += [f"    {cmd}" for _, cmd in lost]
    out += ["", "Dispositions:"]
    for kind in ("quality", "balanced", "fast"):
        d = disp[kind]
        if d["status"] == PENDING:
            out.append(f"  {kind}: PENDING ({d['rule']}: {d['why']})")
        else:
            out.append(f"  {kind}: {d['cell']}  [{d['rule']}: {d['why']}]")
    return "\n".join(out)


def to_json(an: dict, disp: dict | None, plan: dict | None) -> dict:
    """Cell ids, counts, rule names and status words only: safe to commit."""
    out = {"status": overall_status(an, disp),
           "cells": {c: {"slots_decided": s["decided"], "slots_needed": needed(c, an),
                         "solid_fails": dict(s["solid"]), "failed_slots": s["failed"],
                         "lost_to_api_errors": s["lost"],
                         "mean_cost_usd": None if s["mean_cost"] is None else round(s["mean_cost"], 6)}
                     for c, s in an["cells"].items()}}
    if an["missing"]:
        out["missing_passes"] = len(an["missing"])
        return out
    for kind in ("quality", "balanced", "fast"):
        d = disp[kind]
        out[kind] = {"status": d["status"], "cell": d["cell"], "rule": d["rule"]}
    out["stage2"] = {"cells": plan["cells"], "max_usd": plan["max_usd"]}
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--runs", default=str(ROOT / "evals" / "results" / "runs.jsonl"))
    ap.add_argument("--scores", default=str(ROOT / "evals" / "results" / "scores.jsonl"))
    ap.add_argument("--json", action="store_true", help="the same result as one JSON object (cell ids and counts)")
    args = ap.parse_args(argv)
    try:
        an = analyse(read_jsonl(args.runs), read_jsonl(args.scores))
    except AnalysisError as e:
        print(f"think_first_analysis: error: {e}", file=sys.stderr)
        return 2
    disp = plan = None
    if not an["missing"]:
        disp, plan = decide(an), stage2_plan(an)
    print(json.dumps(to_json(an, disp, plan), sort_keys=True) if args.json else render(an, disp, plan))
    return 0 if overall_status(an, disp) == VERDICT else 2


if __name__ == "__main__":
    sys.exit(main())
