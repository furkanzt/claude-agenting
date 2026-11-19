#!/usr/bin/env python3
"""agy_bench  --  the Antigravity (agy) eval bench: one agy run per (task, cell, repeat).

Config and templates live under <evals>/agy/ (bench.json, eval-runner.md, eval_hook.py). Records
go to results/agy-runs.jsonl and results/agy-scores.jsonl; answers to private/agy-answers/. The
Claude instrument (results/runs.jsonl, results/scores.jsonl, private/answers/) is never written.

    python3 evals/probes/agy_bench.py setup                       # install the agent and the guard hook
    python3 evals/probes/agy_bench.py meters [--json]             # weekly and five-hour meters (agy -p /usage)
    python3 evals/probes/agy_bench.py plan --stage N [--json]     # runs of stage N still missing; no model
    python3 evals/probes/agy_bench.py run --stage N [--cells a,b] [--max-runs K]   # the agy runs
    python3 evals/probes/agy_bench.py status [--json]             # valid and invalid counts per cell
    python3 evals/probes/agy_bench.py judge [--max-usd N] [--jobs N]   # judge-graded tasks, pinned judge (claude -p)
    python3 evals/probes/agy_bench.py report --stage N [--json|--md]   # passes, tokens, meters per task and cell

Exit codes: 0 done (nothing skipped or stopped); 2 an error (one line on stderr); 3 a stop line or
a quota error left runs of the plan unstarted.

Files under <evals>/private/work/ (never committed):

    .agents/agents/eval-runner.md   the agent (template with the harness runner system prompt)
    .agents/evalhook/eval_hook.py   the guard and the hook log writer, copied byte for byte
    .agents/hooks.json              the hooks agy runs for every run dir below this folder
    hooklogs/<conversation>.jsonl   one line per hook event, written by the guard
    policy/<run dir name>.json      {"tools": [...]} for the run, removed after the run
    <run dir>/                      the material of one run, removed after the run
"""

import argparse
import json
import os
import re
import shlex
import shutil
import statistics
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import evalkit as ev  # noqa: E402

RUNS_FILE = "agy-runs.jsonl"
SCORES_FILE = "agy-scores.jsonl"
LOCK_FILE = ".agy-bench.lock"
GRACE_DEFAULT_S = 60
METER_TIMEOUT_S = 120
VERSION_TIMEOUT_S = 60
QUOTA_WORDS = ("quota", "resource_exhausted", "rate limit")
POOL_KEYS = (("Weekly", "weekly"), ("Five Hour", "five_hour"))


def bench_path(ctx):
    return ctx.root / "agy" / "bench.json"


def load_bench(ctx):
    path = bench_path(ctx)
    if not path.is_file():
        raise ev.EvalError(f"missing {path}")
    return ev.read_json(path)


def agy_argv(cfg):
    return shlex.split(cfg["agy_bin"])


def stage_of(cfg, stage):
    found = cfg["stages"].get(str(stage))
    if found is None:
        raise ev.EvalError(f"unknown stage {stage!r}; the bench has {sorted(cfg['stages'])}")
    for cell in found["cells"]:
        if cell not in cfg["cells"]:
            raise ev.EvalError(f"stage {stage} names cell {cell!r}, which bench.json does not define")
    return found


# -- setup -------------------------------------------------------------------

def setup(ctx, cfg):
    """Install the agent, the hook and hooks.json under private/work/.agents (idempotent)."""
    agents = ctx.work_dir / ".agents"
    (agents / "agents").mkdir(parents=True, exist_ok=True)
    (agents / "evalhook").mkdir(parents=True, exist_ok=True)
    template = ev.read_text(ctx.root / "agy" / "eval-runner.md")
    agent = template.replace("{SYSTEM_PROMPT}", ctx.harness["runner"]["system_prompt"])
    (agents / "agents" / "eval-runner.md").write_text(agent, encoding="utf-8")
    shutil.copyfile(ctx.root / "agy" / "eval_hook.py", agents / "evalhook" / "eval_hook.py")
    handler = {"type": "command", "command": "python3 ./evalhook/eval_hook.py", "timeout": 10}
    hooks = {"agy-bench": {"SessionStart": [handler], "Stop": [handler],
                           "PreToolUse": [{"matcher": "*", "hooks": [handler]}]}}
    (agents / "hooks.json").write_text(json.dumps(hooks, indent=2) + "\n", encoding="utf-8")


# -- meters ------------------------------------------------------------------

def read_meters(cfg):
    """{pool: {"weekly": int, "five_hour": int}} from `agy -p /usage`. Raises EvalError."""
    try:
        r = subprocess.run(agy_argv(cfg) + ["-p", "/usage"], capture_output=True, text=True,
                           timeout=METER_TIMEOUT_S)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise ev.EvalError(f"meters unreadable: {e}")
    if r.returncode != 0:
        raise ev.EvalError(f"meters unreadable: agy /usage exited {r.returncode}")
    meters = {}
    for line in r.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        pool = cfg["usage_pools"].get(parts[0].strip())
        pct = re.match(r"\s*(\d+)\s*%", parts[2])
        if pool is None or pct is None:
            continue
        for word, key in POOL_KEYS:
            if word in parts[1]:
                meters.setdefault(pool, {})[key] = int(pct.group(1))
    if not meters:
        raise ev.EvalError("meters unreadable: no pool line in agy /usage output")
    return meters


def cmd_meters(ctx, cfg, args):
    meters = read_meters(cfg)
    if args.json:
        print(json.dumps(meters, sort_keys=True))
    else:
        for pool in sorted(meters):
            print(f"{pool}: " + ", ".join(f"{k} {v}%" for k, v in sorted(meters[pool].items())))
    return 0


# -- plan --------------------------------------------------------------------

def plan_items(ctx, cfg, stage_key, cells=None):
    """The runs of the stage that have no valid line yet, in task, cell, repeat order."""
    stage = stage_of(cfg, stage_key)
    wanted = list(stage["cells"])
    if cells:
        unknown = [c for c in cells if c not in stage["cells"]]
        if unknown:
            raise ev.EvalError(f"cells not in stage {stage_key}: {', '.join(unknown)}")
        wanted = cells
    done = {r.get("run_id") for r in ev.read_jsonl(ctx.root / "results" / RUNS_FILE)
            if r.get("valid")}
    tasks = ev.load_tasks(ctx)
    items = []
    for tid in sorted(tasks):
        task = tasks[tid]
        if task["phase"] != stage["phase"]:
            continue
        for cell in wanted:
            pools = list(cfg["cells"][cell]["pools"])
            reps = stage["repeats"]
            count = reps.get(pools[0], reps.get("default", 1))
            cell_hash = ev.compute_cell_hash(cell, cfg["cells"][cell])
            for repeat in range(1, count + 1):
                rid = ev.compute_run_id(ctx.harness["harness_version"], task["id"],
                                        task["task_hash"], cell_hash, repeat)
                if rid in done:
                    continue
                items.append({"run_id": rid, "task": task["id"], "cell": cell,
                              "repeat": repeat, "pools": pools,
                              "task_hash": task["task_hash"]})
    return items


def cmd_plan(ctx, cfg, args):
    items = plan_items(ctx, cfg, args.stage, parse_cells(args.cells))
    if args.json:
        keys = ("run_id", "task", "cell", "repeat", "pools")
        print(json.dumps([{k: i[k] for k in keys} for i in items]))
    else:
        print(f"stage {args.stage}: {len(items)} runs missing")
    return 0


def parse_cells(value):
    return ev.parse_csv(value)


# -- run ---------------------------------------------------------------------

def agy_version(cfg):
    try:
        r = subprocess.run(agy_argv(cfg) + ["--version"], capture_output=True, text=True,
                           timeout=VERSION_TIMEOUT_S)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise ev.EvalError(f"agy --version failed: {e}")
    lines = r.stdout.strip().splitlines()
    if r.returncode != 0 or not lines:
        raise ev.EvalError(f"agy --version failed (exit {r.returncode})")
    return lines[0].strip()


def hook_log_names(ctx):
    d = ctx.work_dir / "hooklogs"
    return set(os.listdir(d)) if d.is_dir() else set()


def judge_run(ctx, cfg, item, task, wd, out, timed_out, before, version, meters_before,
              duration):
    """The validity of one run (README order: first match wins) and its record."""
    hook_dir = ctx.work_dir / "hooklogs"
    model_id = cfg["cells"][item["cell"]]["model_id"]
    reason, data, conv, lines = None, None, None, []
    if timed_out:
        reason = "timeout"
    else:
        try:
            data = json.loads(out)
        except ValueError:
            data = None
        if not isinstance(data, dict):
            data, reason = None, "json_parse"
    if reason is None and data.get("status") != "SUCCESS":
        err = str(data.get("error") or "").lower()
        reason = "quota" if any(w in err for w in QUOTA_WORDS) else "status_error"
    if reason is None and not str(data.get("response") or "").strip():
        reason = "no_output"
    if reason is None:
        conv = data.get("conversation_id")
        main_name = os.path.basename(str(conv or "unknown")) + ".jsonl"
        main_log = hook_dir / main_name
        if not conv or not main_log.is_file():
            reason = "no_hook_log"
        else:
            lines = ev.read_jsonl(main_log)
    if reason is None and any(x.get("modelName") != model_id for x in lines):
        reason = "model_mismatch"
    wd_real = os.path.realpath(wd)
    if reason is None:
        for x in lines:
            if x.get("event") == "SessionStart":
                paths = [os.path.realpath(p) for p in (x.get("workspacePaths") or [])]
                if paths != [wd_real]:
                    reason = "workspace_mismatch"
    if reason is None:
        new = hook_log_names(ctx) - before - {main_name}
        for name in sorted(new):
            if any(os.path.realpath(x["cwd"]) == wd_real for x in ev.read_jsonl(hook_dir / name)
                   if x.get("cwd")):
                reason = "helper_spawned"
                break
    usage = (data or {}).get("usage") or {}
    rec = {"ts": ev.now(), "run_id": item["run_id"], "task": item["task"],
           "task_hash": item["task_hash"], "cell": item["cell"], "repeat": item["repeat"],
           "model_id": model_id, "pools": item["pools"], "agy_version": version,
           "valid": reason is None, "invalid_reason": reason,
           "input_tokens": usage.get("input_tokens"), "output_tokens": usage.get("output_tokens"),
           "thinking_tokens": usage.get("thinking_tokens"),
           "cache_read_tokens": usage.get("cache_read_tokens"),
           "duration_s": round(duration, 2),
           "tool_calls": sum(1 for x in lines if x.get("event") == "PreToolUse"),
           "denied_tool_calls": sum(1 for x in lines if x.get("event") == "PreToolUse"
                                    and x.get("decision") == "deny"),
           "meters_before": meters_before, "conversation_id": conv}
    return rec, data


def run_one(ctx, cfg, task, item, version, meters_before):
    """One agy run end to end. Returns the record (its invalid_reason may be "quota")."""
    rid = item["run_id"]
    wd = ev.prepare_workdir(ctx, task, rid)
    policy_dir = ctx.work_dir / "policy"
    policy = policy_dir / (wd.name + ".json")
    try:
        tools = cfg["tools_files"] if task["delivery"] == "files" else cfg["tools_inline"]
        policy_dir.mkdir(parents=True, exist_ok=True)
        policy.write_text(json.dumps({"tools": tools}), encoding="utf-8")
        prompt = ev.read_text(task["dir"] / "prompt.md")
        cell = cfg["cells"][item["cell"]]
        argv = agy_argv(cfg) + ["--agent", cfg["agent"], "--model", cell["model_id"],
                                "--settings", json.dumps(cfg["settings"]),
                                "--output-format", "json",
                                "--print-timeout", f"{cfg['print_timeout_s']}s",
                                "-p=" + prompt]
        before = hook_log_names(ctx)
        limit = cfg["print_timeout_s"] + cfg.get("kill_grace_s", GRACE_DEFAULT_S)
        t0 = time.monotonic()
        proc = subprocess.Popen(argv, cwd=str(wd), stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True, encoding="utf-8",
                                start_new_session=True)
        timed_out = False
        try:
            out, _ = proc.communicate(timeout=limit)
        except subprocess.TimeoutExpired:
            timed_out = True
            ev.kill_group(proc)
            try:
                out, _ = proc.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                out = ""
        duration = time.monotonic() - t0
        rec, data = judge_run(ctx, cfg, item, task, wd, out or "", timed_out, before, version,
                              meters_before, duration)
    finally:
        shutil.rmtree(wd, ignore_errors=True)
        policy.unlink(missing_ok=True)
    ev.append_jsonl(ctx.root / "results" / RUNS_FILE, rec)
    if rec["valid"]:
        text = data["response"]
        block = ev.extract_block(text, ctx.harness["answer_markers"])
        ev.write_json_atomic(ctx.private / "agy-answers" / f"{rid}.json",
                             {"run_id": rid, "result": text, "block": block,
                              "usage": data.get("usage")})
        if task["grading_type"] == "code":
            score_code(ctx, task, rid, block)
    return rec


def score_code(ctx, task, rid, block):
    if block is None:
        res = {"score": 0.0, "passed": False, "details": {"no_block": True}}
    else:
        try:
            res = ev.call_grader(task, "grade", block)
        except (ev.GraderFault, ev.EvalError) as e:
            print(f"agy_bench: warning: {task['id']} run {rid} left ungraded: {e}",
                  file=sys.stderr)
            return
    ev.append_jsonl(ctx.root / "results" / SCORES_FILE,
                    ev.score_line(rid, ev.grader_prefix(ctx, task), res))


def cmd_run(ctx, cfg, args):
    with ev.exclusive_lock(ctx.root / "results" / LOCK_FILE):
        setup(ctx, cfg)
        items = plan_items(ctx, cfg, args.stage, parse_cells(args.cells))
        version = agy_version(cfg)
        tasks = ev.load_tasks(ctx)
        blocked, skipped, started, valid, invalid = set(), 0, 0, 0, 0
        for item in items:
            pools = item["pools"]
            if set(pools) & blocked:
                skipped += 1
                continue
            if args.max_runs is not None and started >= args.max_runs:
                break
            meters = read_meters(cfg)
            try:
                meters_before = {p: meters[p]["weekly"] for p in pools}
            except KeyError as e:
                raise ev.EvalError(f"meters unreadable: no weekly meter for pool {e}")
            low = [p for p in pools if p in cfg["stop_lines"]
                   and meters_before[p] < cfg["stop_lines"][p]]
            if low:
                blocked |= set(low)
                skipped += 1
                print(f"stop line: {', '.join(low)} weekly meter below its stop line; "
                      f"skipping {item['cell']} and the rest of that pool")
                continue
            started += 1
            rec = run_one(ctx, cfg, tasks[item["task"]], item, version, meters_before)
            if rec["valid"]:
                valid += 1
            else:
                invalid += 1
            if rec["invalid_reason"] == "quota":
                blocked |= set(pools)
                print(f"quota error on {item['cell']}: the pool(s) {', '.join(pools)} stop")
    print(f"agy_bench: stage {args.stage}: {started} runs started, {valid} valid, "
          f"{invalid} invalid, {skipped} skipped")
    return 3 if skipped else 0


# -- status ------------------------------------------------------------------

def cmd_status(ctx, cfg, args):
    runs = ev.read_jsonl(ctx.root / "results" / RUNS_FILE)
    stage = stage_of(cfg, "1")
    left = len(plan_items(ctx, cfg, "1"))
    rows = {}
    for cell in stage["cells"]:
        mine = [r for r in runs if r.get("cell") == cell]
        rows[cell] = {"valid": sum(1 for r in mine if r.get("valid")),
                      "invalid": sum(1 for r in mine if not r.get("valid"))}
    if args.json:
        print(json.dumps({"cells": rows, "stage_1_left": left}, sort_keys=True))
    else:
        for cell, c in rows.items():
            print(f"{cell}: {c['valid']} valid, {c['invalid']} invalid")
        print(f"stage 1 runs left: {left}")
    return 0


# -- judge and report ----------------------------------------------------------

class AgyCtx(ev.Ctx):
    """evalkit's context with the bench's own records, so evalkit's judge and its effective-score
    reading work on agy runs without ever touching the Claude instrument's files."""

    def __init__(self, root=None):
        super().__init__(root)
        self.runs_path = self.root / "results" / RUNS_FILE
        self.scores_path = self.root / "results" / SCORES_FILE
        self.answers_dir = self.private / "agy-answers"


def cmd_judge(ctx, cfg, args):
    """Judge-grade the valid agy runs of judge-graded tasks with the harness's pinned judge
    (a `claude -p` call: it runs on the Claude plan, not on an Antigravity meter)."""
    actx = AgyCtx(ctx.root)
    tasks = ev.load_tasks(actx)
    judge_cell = actx.harness["judge"]["cell"]
    have = {(s.get("run_id"), s.get("grader_id")) for s in ev.read_jsonl(actx.scores_path)}
    units = []
    for r in ev.read_jsonl(actx.runs_path):
        task = tasks.get(r.get("task"))
        if not r.get("valid") or not task or task["grading_type"] != "judge":
            continue
        prefix = ev.grader_prefix(actx, task, judge_cell)
        for k in range(actx.harness["judge"]["repeats"]):
            if (r["run_id"], f"{prefix}{k}") not in have:
                units.append((task, {"run_id": r["run_id"]}, k))
    print(f"{len(units)} judge pass(es) to do")
    if not units:
        return 0
    actx.cli_version = ev.claude_version(actx)
    budget = ev.Budget(args.max_usd, actx.harness["runner"]["max_budget_usd_per_run"])
    faults = []
    code = ev.run_pool(actx, units,
                       lambda u, stop: ev.judge_one(actx, u, budget, stop, faults, judge_cell),
                       args.jobs or actx.harness["runner"]["jobs"], "judge")
    print(f"judge cost ${budget.spent:.4f}")
    if faults:
        print(f"{len(faults)} judge pass(es) left missing; run `judge` again to retry them")
    return code


def median_of(values):
    vals = [v for v in values if isinstance(v, (int, float))]
    return statistics.median(vals) if vals else None


def report_data(ctx, cfg, stage_key):
    """Per (task, cell) of the stage: attempts, valid, scored, passed, mean score, median tokens;
    per pool: the first and last weekly meter read before a run."""
    actx = AgyCtx(ctx.root)
    stage = stage_of(cfg, stage_key)
    tasks = ev.load_tasks(actx)
    scores = ev.scores_by_run(actx)
    runs = ev.read_jsonl(actx.runs_path)
    rows = []
    for tid in sorted(tasks):
        task = tasks[tid]
        if task["phase"] != stage["phase"]:
            continue
        for cell in stage["cells"]:
            mine = [r for r in runs if r.get("task") == tid and r.get("cell") == cell]
            valid = [r for r in mine if r.get("valid")]
            eff = [e for e in (ev.effective(actx, task, r["run_id"], scores) for r in valid) if e]
            rows.append({
                "task": tid, "row": task["row"], "cell": cell, "attempts": len(mine),
                "valid": len(valid), "scored": len(eff), "passed": sum(1 for e in eff if e[1]),
                "mean_score": ev.mean([e[0] for e in eff]) if eff else None,
                "median_input_tokens": median_of(r.get("input_tokens") for r in valid),
                "median_output_tokens": median_of(r.get("output_tokens") for r in valid),
                "median_thinking_tokens": median_of(r.get("thinking_tokens") for r in valid),
                "median_duration_s": median_of(r.get("duration_s") for r in valid),
                "denied_tool_calls": sum(r.get("denied_tool_calls") or 0 for r in valid)})
    meters = {}
    for r in sorted(runs, key=lambda x: x.get("ts") or ""):
        for pool, pct in (r.get("meters_before") or {}).items():
            m = meters.setdefault(pool, {"first": pct, "last": pct, "runs": 0})
            m["last"] = pct
            m["runs"] += 1
    return {"rows": rows, "meters": meters}


def cmd_report(ctx, cfg, args):
    data = report_data(ctx, cfg, args.stage)
    if args.json:
        print(json.dumps(data, sort_keys=True))
        return 0
    header = ["row", "cell", "valid", "passed", "mean", "in tok", "out tok", "think", "sec", "denied"]
    body = [[r["row"], r["cell"], f"{r['valid']}/{r['attempts']}", f"{r['passed']}/{r['scored']}",
             ev.fmt(r["mean_score"], ".2f"), ev.fmt(r["median_input_tokens"], ".0f"),
             ev.fmt(r["median_output_tokens"], ".0f"), ev.fmt(r["median_thinking_tokens"], ".0f"),
             ev.fmt(r["median_duration_s"], ".0f"), str(r["denied_tool_calls"])]
            for r in data["rows"]]
    print(ev.render(header, body, args.md))
    for pool, m in sorted(data["meters"].items()):
        print(f"{pool} weekly meter: {m['first']}% before the first run, {m['last']}% before the "
              f"last ({m['runs']} runs)")
    return 0


# -- CLI ---------------------------------------------------------------------

def build_parser():
    p = argparse.ArgumentParser(prog="agy_bench", description="the Antigravity eval bench")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("setup", help="install the agent and the guard hook")
    sp = sub.add_parser("meters", help="read the usage meters")
    sp.add_argument("--json", action="store_true")
    sp = sub.add_parser("plan", help="list the runs of a stage that are missing")
    sp.add_argument("--stage", required=True)
    sp.add_argument("--cells")
    sp.add_argument("--json", action="store_true")
    sp = sub.add_parser("run", help="execute the runs of a stage")
    sp.add_argument("--stage", required=True)
    sp.add_argument("--cells")
    sp.add_argument("--max-runs", type=int)
    sp = sub.add_parser("status", help="valid and invalid counts per cell")
    sp.add_argument("--json", action="store_true")
    sp = sub.add_parser("judge", help="judge-grade agy runs of judge-graded tasks (claude -p)")
    sp.add_argument("--max-usd", type=float)
    sp.add_argument("--jobs", type=int)
    sp = sub.add_parser("report", help="pass counts, tokens and meters per task and cell")
    sp.add_argument("--stage", required=True)
    sp.add_argument("--json", action="store_true")
    sp.add_argument("--md", action="store_true")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        ctx = ev.Ctx()
        cfg = load_bench(ctx)
        if args.cmd == "setup":
            setup(ctx, cfg)
            print(f"agy_bench: installed under {ctx.work_dir / '.agents'}")
            return 0
        if args.cmd == "meters":
            return cmd_meters(ctx, cfg, args)
        if args.cmd == "plan":
            return cmd_plan(ctx, cfg, args)
        if args.cmd == "run":
            return cmd_run(ctx, cfg, args)
        if args.cmd == "judge":
            return cmd_judge(ctx, cfg, args)
        if args.cmd == "report":
            return cmd_report(ctx, cfg, args)
        return cmd_status(ctx, cfg, args)
    except (ev.EvalError, OSError) as e:
        print(f"agy_bench: error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
