#!/usr/bin/env python3
"""
evalkit  --  the eval harness CLI (stdlib only, no network, no API key).

Measures which (model, effort) cell can carry each routing row, and keeps the
evidence so a new model release costs only the runs that are missing. The
contract is evals/README.md; this file implements it.

  manifest    build tasks.json (public) from private/tasks/*/task.json
  status      per row: tasks, cells, valid/invalid runs, scored/ungraded, cost
  plan        list the (task, cell, repeat) runs that are missing or retryable
  run         execute the plan: one `claude -p` process per run, graded at once
  grade       re-grade stored answers of code tasks whose grader changed
  judge       judge-graded tasks: pinned judge cell scores every valid run
  report      per-row table: pass rate, mean score, mean cost, thinking tokens
              (--phase screening|confirmation|all, default screening)
  decide      apply the README decision bar per row (provisional when a candidate is incomplete)
  selfcheck   run every grader against its fixtures, scan material for secrets
  sanitize    rewrite results/scores.jsonl so every `details` holds scalars only

LAYOUT / ISOLATION
  Everything lives under $AGENTING_EVALS_DIR (default: the directory holding
  this file). Tests point it at a temp copy, so they never touch the real
  results/ or private/. private/ may be absent: commands that only read public
  files fall back to tasks.json; commands that need prompts say so and stop.

RUN ID
  sha1("{harness_version}|{task_id}|{task_hash}|{cell_hash}|{repeat}")[:16]
  cell_hash = sha8 of the canonical JSON of {cell_id, model_id, effort, system_append}
  (missing system_append = ""), so changing any of them re-plans that cell only
  (README rule 3). The cell's system_append, if any, goes after the harness system
  prompt, separated by two newlines.

GRADING SAFETY
  Every grader call (grade, score_judgment) runs in a child python process with a
  30 s timeout; the grader never runs in this process. A crash, a timeout or an
  invalid return value leaves the run UNGRADED: a warning is printed, nothing is
  appended to scores.jsonl, status counts it as ungraded and report/decide treat
  it as a missing run. A harness fault is never recorded as a model failure.

VALIDITY (README): process exited 0, JSON parsed, is_error false, and
  modelUsage names exactly the cell's model_id. Invalid runs are logged with
  valid:false and re-planned up to harness max_retries_invalid times. A missing
  answer block is a graded failure (score 0), never an invalid run.

Cost guard: `run --max-usd` stops LAUNCHING once the cost spent in this
invocation (invalid runs included) reaches the cap; runs already in flight
finish, so the overshoot is at most jobs x max_budget_usd_per_run. A run whose
cost cannot be known (killed on timeout, unparseable output) is logged with
cost_usd null and cost_unknown true and charged runner.max_budget_usd_per_run.

CONCURRENCY: run, judge, grade and sanitize hold ONE exclusive non-blocking flock on
results/.evalkit.lock for the whole invocation; a second one exits 2. Read-only
commands (and run --dry-run) never lock. Each run gets its own mkdtemp work directory.

PUBLIC RESULTS: scores.jsonl is committed to a public repo. score_line keeps only
scalar `details` (int, float, bool, str up to 40 chars); dicts and lists are dropped
so a line can never say which items of a task were missed. `sanitize` applies the
same rule to lines already written. tasks.json carries `pass_rule_public` (or a
generic `score >= <threshold>`), never the private pass_rule text.
"""

import argparse
import concurrent.futures as cf
import fcntl
import hashlib
import json
import math
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REQUIRED_TASK_FIELDS = ("id", "row", "phase", "title", "delivery", "pass_threshold",
                        "pass_rule", "grading")
PHASES = ("screening", "confirmation")
UP_ROLES = ("up_reference", "ceiling")
NOTICED_FAIL_BELOW = 0.5      # noticed tier: baseline "fails its row" under this pass rate
GRADER_TIMEOUT_S = 30         # per grader call; module-level so tests can shorten it
DETAIL_STR_MAX = 40           # longest string kept in a public score `details` value
LOCKED_COMMANDS = ("run", "judge", "grade", "sanitize")   # commands that write results/
JUDGE_FORMAT_RETRIES = 2      # extra judge attempts after an unparseable or rejected reply
SECRET_PATTERNS = [re.compile(p) for p in (
    r"sk-ant-[A-Za-z0-9_-]{8,}", r"sk-[A-Za-z0-9]{20,}", r"ghp_[A-Za-z0-9]{16,}",
    r"AKIA[0-9A-Z]{12,}", r"-----BEGIN")]


class EvalError(Exception):
    """A user-facing failure: printed as one line, exit status 2."""


# -- small utilities ---------------------------------------------------------

def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha8(*chunks):
    return sha256_bytes(b"|".join(chunks))[:8]


def canon(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_text(path):
    return Path(path).read_text(encoding="utf-8")


def read_json(path):
    try:
        return json.loads(read_text(path))
    except FileNotFoundError:
        raise EvalError(f"missing file: {path}")
    except ValueError as e:
        raise EvalError(f"{path}: invalid JSON ({e})")


def read_jsonl(path):
    """All parseable lines; a torn or garbled line is skipped, never fatal."""
    out = []
    if not Path(path).exists():
        return out
    for n, line in enumerate(read_text(path).splitlines(), 1):
        if not line.strip():
            continue
        try:
            out.append(json.loads(line))
        except ValueError:
            print(f"evalkit: warning: {path}:{n} unreadable line skipped", file=sys.stderr)
    return out


def append_jsonl(path, obj):
    """ONE write of ONE line under an exclusive flock: lines never interleave."""
    line = (json.dumps(obj, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        view = memoryview(line)
        while view:
            view = view[os.write(fd, view):]
    finally:
        os.close(fd)


def write_json_atomic(path, obj):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(str(path) + f".tmp{os.getpid()}")
    tmp.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


class exclusive_lock:
    """One exclusive, NON-blocking flock on results/.evalkit.lock, held for a whole invocation
    of a writing command. flock belongs to the open file description, so it is released when
    this process exits however it dies, and the subprocesses we spawn (close_fds) never keep it."""

    def __init__(self, path):
        self.path, self.fd = Path(path), None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o644)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            holder = ""
            try:
                holder = os.pread(fd, 32, 0).decode("ascii", "ignore").strip()
            except OSError:
                pass
            os.close(fd)
            raise EvalError("another evalkit run/judge/grade/sanitize is already writing results "
                            f"(lock {self.path}{', pid ' + holder if holder else ''}); "
                            "wait for it to finish, then retry")
        os.ftruncate(fd, 0)
        os.write(fd, str(os.getpid()).encode("ascii"))
        self.fd = fd
        return self

    def __exit__(self, *exc):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None
        return False


def parse_csv(value):
    return [x.strip() for x in value.split(",") if x.strip()] if value else None


def mean(values):
    values = list(values)
    return sum(values) / len(values) if values else None


# -- context -----------------------------------------------------------------

class Ctx:
    """The evals directory and its three config files."""

    def __init__(self, root=None):
        self.root = Path(root or os.environ.get("AGENTING_EVALS_DIR") or HERE).resolve()
        self.harness = read_json(self.root / "harness.json")
        self.cells = read_json(self.root / "cells.json")["cells"]
        self.rows = read_json(self.root / "rows.json")["rows"]
        self.private = self.root / "private"
        self.tasks_dir = self.private / "tasks"
        self.answers_dir = self.private / "answers"
        self.work_dir = self.private / "work"
        self.runs_path = self.root / "results" / "runs.jsonl"
        self.scores_path = self.root / "results" / "scores.jsonl"
        self.manifest_path = self.root / "tasks.json"
        self.lock_path = self.root / "results" / ".evalkit.lock"
        self.cli_version = None        # set once per run/judge invocation; never part of an id

    def row(self, row_id):
        return next(r for r in self.rows if r["id"] == row_id)

    def model_id(self, cell_id):
        return self.cells[cell_id]["model_id"]

    def cell_hash(self, cell_id):
        return compute_cell_hash(cell_id, self.cells[cell_id])

    def system_prompt(self, cell_id):
        """The runner system prompt plus the cell's system_append, if any."""
        return with_append(self.harness["runner"]["system_prompt"], self.cells[cell_id])


def require_private(ctx):
    if not ctx.tasks_dir.is_dir():
        raise EvalError(f"{ctx.tasks_dir} does not exist. private/ holds the task prompts, "
                        "material and graders (gitignored); restore it from backup or "
                        "author tasks there first.")


# -- tasks and the manifest --------------------------------------------------

def material_files(tdir):
    mat = tdir / "material"
    if not mat.is_dir():
        return []
    files = [p for p in mat.rglob("*") if p.is_file() and p.name != ".DS_Store"]
    return sorted([p.relative_to(mat).as_posix(), sha256_bytes(p.read_bytes())] for p in files)


def compute_task_hash(tdir, delivery):
    prompt = tdir / "prompt.md"
    if not prompt.is_file():
        raise EvalError(f"{tdir.name}: prompt.md is missing")
    return sha256_bytes(canon({"prompt": sha256_bytes(prompt.read_bytes()), "delivery": delivery,
                               "material": material_files(tdir)}).encode("utf-8"))


def public_pass_rule(task):
    """The pass rule that may appear in the public manifest: `pass_rule_public` when the task
    has one, else a generic threshold rule. The private `pass_rule` text is never copied."""
    public = task.get("pass_rule_public")
    if isinstance(public, str) and public.strip():
        return public.strip()
    return f"score >= {task['pass_threshold']}"


def manifest_entry(tdir):
    t = read_json(tdir / "task.json")
    missing = [k for k in REQUIRED_TASK_FIELDS if k not in t]
    if missing:
        raise EvalError(f"{tdir.name}/task.json: missing fields {missing}")
    gtype = (t["grading"] or {}).get("type")
    return {"id": t["id"], "row": t["row"], "phase": t["phase"], "title": t["title"],
            "delivery": t["delivery"], "grading_type": gtype, "pass_rule": public_pass_rule(t),
            "pass_threshold": t["pass_threshold"],
            "task_hash": compute_task_hash(tdir, t["delivery"])}


def load_tasks(ctx):
    """{task_id: entry}. Private tasks when present (entries carry `dir`), else tasks.json."""
    if ctx.tasks_dir.is_dir():
        tasks = {}
        for tdir in sorted(p for p in ctx.tasks_dir.iterdir() if p.is_dir()):
            e = manifest_entry(tdir)
            e["dir"] = tdir
            tasks[e["id"]] = e
        return tasks
    if ctx.manifest_path.is_file():
        return {e["id"]: e for e in read_json(ctx.manifest_path)}
    raise EvalError(f"no tasks: {ctx.tasks_dir} is missing and there is no tasks.json. "
                    "private/ is gitignored; restore it or run `manifest` where it exists.")


def row_tasks(tasks, row_id, phases=PHASES):
    return sorted((t for t in tasks.values() if t["row"] == row_id and t["phase"] in phases),
                  key=lambda t: t["id"])


def grader_prefix(ctx, task):
    """Id (code) or id prefix (judge) of the task's CURRENT grader."""
    if task["grading_type"] == "judge":
        cell = ctx.harness["judge"]["cell"]
        if "dir" in task:
            return f"judge:{cell}:{sha8(read_bytes_or_empty(task['dir'] / 'rubric.md'))}:"
        return f"judge:{cell}:"
    if "dir" in task:
        grader = read_bytes_or_empty(task["dir"] / "grader.py")
        return "code:" + sha8(grader, json.dumps(task["pass_threshold"]).encode())
    return "code:"


def read_bytes_or_empty(path):
    try:
        return Path(path).read_bytes()
    except FileNotFoundError:
        return b""


def cmd_manifest(ctx, args):
    require_private(ctx)
    entries = sorted(load_tasks(ctx).values(), key=lambda e: e["id"])
    out = [{k: v for k, v in e.items() if k != "dir"} for e in entries]
    ctx.manifest_path.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n",
                                 encoding="utf-8")
    print(f"wrote {ctx.manifest_path} ({len(out)} tasks)")
    return 0


# -- run ids, run index, scores ----------------------------------------------

def compute_cell_hash(cell_id, cell):
    """sha8 of the canonical JSON of the fields that define what a cell *is*."""
    ident = {"cell_id": cell_id, "model_id": cell["model_id"], "effort": cell.get("effort"),
             "system_append": cell.get("system_append") or ""}
    return sha256_bytes(canon(ident).encode("utf-8"))[:8]


def with_append(system_prompt, cell):
    extra = cell.get("system_append") or ""
    return f"{system_prompt}\n\n{extra}" if extra else system_prompt


def compute_run_id(harness_version, task_id, task_hash, cell_hash, repeat):
    key = f"{harness_version}|{task_id}|{task_hash}|{cell_hash}|{repeat}"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


def run_id_for(ctx, task, cell_id, repeat):
    return compute_run_id(ctx.harness["harness_version"], task["id"], task["task_hash"],
                          ctx.cell_hash(cell_id), repeat)


class RunIndex:
    """runs.jsonl grouped by run_id: the latest valid line and the invalid-attempt count."""

    def __init__(self, ctx):
        self.lines = read_jsonl(ctx.runs_path)
        self.valid, self.invalid = {}, {}
        for r in self.lines:
            if r.get("valid"):
                self.valid[r["run_id"]] = r
            else:
                self.invalid[r["run_id"]] = self.invalid.get(r["run_id"], 0) + 1


def scores_by_run(ctx):
    out = {}
    for s in read_jsonl(ctx.scores_path):
        out.setdefault(s["run_id"], []).append(s)
    return out


def effective(ctx, task, rid, scores):
    """(score, passed) for a run under the task's current grader, or None if unscored."""
    prefix = grader_prefix(ctx, task)
    recs = scores.get(rid, [])
    if task["grading_type"] != "judge":
        match = [s for s in recs if s["grader_id"].startswith(prefix)]
        return (match[-1]["score"], bool(match[-1]["passed"])) if match else None
    latest = {s["grader_id"]: s for s in recs if s["grader_id"].startswith(prefix)}
    if len(latest) < ctx.harness["judge"]["repeats"]:
        return None
    votes = list(latest.values())
    return (mean(s["score"] for s in votes), sum(1 for s in votes if s["passed"]) * 2 > len(votes))


# -- plan --------------------------------------------------------------------

def add_filter_args(p, with_repeats=True):
    p.add_argument("--rows", help="comma-separated row ids")
    p.add_argument("--cells", help="comma-separated cell ids")
    p.add_argument("--tasks", help="comma-separated task ids (overrides --phase)")
    p.add_argument("--phase", choices=("screening", "confirmation", "all"), default="screening",
                   help="which task phase to cover (default screening)")
    if with_repeats:
        p.add_argument("--repeats", type=int, help="repeats per (task, cell); default from harness.json")


def check_known(label, wanted, known):
    bad = [w for w in wanted or [] if w not in known]
    if bad:
        raise EvalError(f"unknown {label}: {', '.join(bad)} (known: {', '.join(sorted(known))})")


def make_plan(ctx, tasks, args):
    rows, cells, task_ids = parse_csv(args.rows), parse_csv(args.cells), parse_csv(args.tasks)
    check_known("row", rows, [r["id"] for r in ctx.rows])
    check_known("cell", cells, ctx.cells)
    check_known("task", task_ids, tasks)
    phases = PHASES if args.phase == "all" else (args.phase,)
    repeats = args.repeats or ctx.harness["repeats_default"]
    idx, max_retry = RunIndex(ctx), ctx.harness["max_retries_invalid"]
    items, exhausted = [], 0
    for row in ctx.rows:
        if rows and row["id"] not in rows:
            continue
        chosen = [t for t in row_tasks(tasks, row["id"]) if (t["id"] in task_ids if task_ids
                                                              else t["phase"] in phases)]
        for task in chosen:
            for g in row["grid"]:
                if cells and g["cell"] not in cells:
                    continue
                for rep in range(1, repeats + 1):
                    rid = run_id_for(ctx, task, g["cell"], rep)
                    stored = idx.valid.get(rid)
                    if stored and stored.get("model_id_expected") == ctx.model_id(g["cell"]):
                        continue
                    failed = idx.invalid.get(rid, 0)
                    if failed > max_retry:
                        exhausted += 1
                        continue
                    items.append({"run_id": rid, "row": row["id"], "task": task["id"],
                                  "cell": g["cell"], "repeat": rep,
                                  "reason": "retry" if failed else "missing"})
    items.sort(key=lambda i: (i["row"], i["task"], i["cell"], i["repeat"]))
    return items, exhausted


def cmd_plan(ctx, args):
    items, exhausted = make_plan(ctx, load_tasks(ctx), args)
    counts = {}
    for i in items:
        counts[i["cell"]] = counts.get(i["cell"], 0) + 1
    if args.json:
        print(json.dumps({"items": items, "counts": dict(sorted(counts.items())),
                          "exhausted": exhausted}, indent=2))
        return 0
    print(f"{len(items)} run(s) to do" + (f"; {exhausted} exhausted their retries" if exhausted else ""))
    for cell, n in sorted(counts.items()):
        print(f"  {cell:<20} {n}")
    for i in items:
        print(f"  {i['reason']:<8} {i['row']:<18} {i['task']:<20} {i['cell']:<20} #{i['repeat']}  {i['run_id']}")
    return 0


# -- the claude process ------------------------------------------------------

class Stop:
    """Cooperative cancel flag plus the set of live process groups to kill on Ctrl-C."""

    def __init__(self):
        self.event, self.procs, self.lock = threading.Event(), set(), threading.Lock()

    def add(self, proc):
        with self.lock:
            self.procs.add(proc)

    def drop(self, proc):
        with self.lock:
            self.procs.discard(proc)

    def kill_all(self):
        self.event.set()
        with self.lock:
            for p in list(self.procs):
                kill_group(p)


def kill_group(proc):
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


def build_cmd(ctx, cell, tools, system_prompt):
    r = ctx.harness["runner"]
    cmd = shlex.split(r["claude_bin"]) + ["-p", "--model", cell["model_id"]]
    if cell.get("effort"):
        cmd += ["--effort", cell["effort"]]
    return cmd + list(r["flags"]) + ["--tools", tools, "--system-prompt", system_prompt,
                                     "--max-budget-usd", str(r["max_budget_usd_per_run"])]


def call_claude(ctx, cell, prompt, cwd, tools, system_prompt, stop):
    """Run one process; return {"stdout","returncode","timeout","error"}. Prompt goes on stdin."""
    cmd = build_cmd(ctx, cell, tools, system_prompt)
    out = {"stdout": "", "returncode": None, "timeout": False, "error": None}
    try:
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, cwd=cwd, text=True, encoding="utf-8",
                                start_new_session=True)
    except OSError as e:
        out["error"] = f"spawn failed: {e}"
        return out
    stop.add(proc)
    try:
        out["stdout"], _ = proc.communicate(prompt, timeout=ctx.harness["runner"]["timeout_s"])
        out["returncode"] = proc.returncode
    except subprocess.TimeoutExpired:
        kill_group(proc)
        proc.communicate()
        out["timeout"] = True
    finally:
        stop.drop(proc)
        kill_group(proc)       # reap any grandchildren the CLI left behind
    return out


def parse_call(call, model_id):
    """(valid, invalid_reason, data) following the README validity rules."""
    if call["error"]:
        return False, call["error"], None
    if call["timeout"]:
        return False, "timeout", None
    try:
        data = json.loads(call["stdout"])
    except ValueError:
        return False, "json_parse", None
    if not isinstance(data, dict):
        return False, "json_parse", None
    observed = sorted(data.get("modelUsage") or {})
    if call["returncode"] != 0:
        return False, f"exit_code={call['returncode']}", data
    if data.get("is_error"):
        return False, "is_error", data
    if observed != [model_id]:
        return False, f"model_mismatch: observed {observed}", data
    return True, None, data


def usage_of(data, model_id):
    u = (data or {}).get("usage") or {}
    mu = (data or {}).get("modelUsage") or {}
    m = mu.get(model_id) or (next(iter(mu.values())) if len(mu) == 1 else {})
    thinking = (u.get("output_tokens_details") or {}).get("thinking_tokens", m.get("thinkingTokens"))
    return {"input_tokens": u.get("input_tokens"), "output_tokens": u.get("output_tokens"),
            "thinking_tokens": thinking, "cache_read_tokens": u.get("cache_read_input_tokens")}


def extract_block(text, markers):
    """The LAST start..end block in text, stripped, or None."""
    start_m, end_m = markers
    end = (text or "").rfind(end_m)
    start = text.rfind(start_m, 0, end) if end >= 0 else -1
    return text[start + len(start_m):end].strip() if start >= 0 else None


# -- graders -----------------------------------------------------------------

class GraderFault(Exception):
    """A grader call that crashed, timed out or returned a bad value: a harness fault,
    never a model failure. `timeout` tells the judge retry loop it is not a format fault."""

    def __init__(self, message, timeout=False):
        super().__init__(message)
        self.timeout = timeout


class GraderRejected(GraderFault):
    """The grader refused its input and said so through details.error."""


# The child sees only a JSON request on stdin; whatever the grader prints goes to
# stderr, so stdout carries the marked result line and nothing else.
GRADER_CHILD = r"""
import importlib.util, json, os, sys
sys.dont_write_bytecode = True
req = json.loads(sys.stdin.read())
real_out, sys.stdout = sys.stdout, sys.stderr
sys.path.insert(0, os.path.dirname(req["path"]))
spec = importlib.util.spec_from_file_location("evalgrader", req["path"])
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
fn = getattr(mod, req["func"], None)
if not callable(fn):
    sys.stderr.write("no callable " + req["func"] + "()\n")
    sys.exit(3)
res = fn(req["arg"], req["truth"])
real_out.write("\n@@RESULT@@" + json.dumps(res) + "\n")
real_out.flush()
"""
RESULT_MARK = "@@RESULT@@"


def validate_grade(res):
    """The shape contract of grade()/score_judgment(); returns the normalised dict."""
    if not isinstance(res, dict) or "score" not in res or "passed" not in res:
        raise GraderFault("returned something other than {'score','passed','details'}")
    score = res["score"]
    if isinstance(score, bool) or not isinstance(score, (int, float)) or score != score \
            or not -1e-9 <= score <= 1 + 1e-9:
        raise GraderFault(f"score must be a number in 0..1, got {score!r}")
    if not isinstance(res["passed"], bool):
        raise GraderFault(f"passed must be true or false, got {res['passed']!r}")
    details = res.get("details")
    if details is not None and not isinstance(details, dict):
        raise GraderFault("details must be an object")
    if details and details.get("error"):
        # every grader reports its own internal faults (bad truth, trapped exception) as
        # details.error with a score of 0; that is a harness fault, never a model failure
        raise GraderRejected(f"grader reported an internal error: {details['error']}")
    return {"score": float(score), "passed": res["passed"], "details": details or {}}


def call_grader(task, func, arg):
    """Run grade()/score_judgment() of the task's grader.py in a child python process with
    a GRADER_TIMEOUT_S timeout and validate the result. Raises GraderFault on a crash, a
    timeout or an invalid return value (EvalError only for an unreadable truth.json)."""
    truth = read_json(task["dir"] / "truth.json")
    request = json.dumps({"path": str(task["dir"] / "grader.py"), "func": func,
                          "arg": arg, "truth": truth})
    try:
        proc = subprocess.Popen([sys.executable, "-c", GRADER_CHILD], stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                encoding="utf-8", cwd=task["dir"], start_new_session=True)
    except OSError as e:
        raise GraderFault(f"could not start the grader process: {e}")
    try:
        stdout, stderr = proc.communicate(request, timeout=GRADER_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        kill_group(proc)
        proc.communicate()
        raise GraderFault(f"{func}() exceeded {GRADER_TIMEOUT_S} s", timeout=True)
    finally:
        kill_group(proc)
    if proc.returncode != 0:
        tail = (stderr or "").strip().splitlines()[-1:] or ["no stderr"]
        raise GraderFault(f"{func}() crashed (exit {proc.returncode}): {tail[0][:300]}")
    marked = [ln for ln in stdout.splitlines() if ln.startswith(RESULT_MARK)]
    if not marked:
        raise GraderFault(f"{func}() produced no result")
    try:
        res = json.loads(marked[-1][len(RESULT_MARK):])
    except ValueError:
        raise GraderFault(f"{func}() result is not JSON")
    return validate_grade(res)


def public_scalar(value):
    """May this value sit in a public score line? bool/int/float (finite) and short strings."""
    if isinstance(value, (bool, int)):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    return isinstance(value, str) and len(value) <= DETAIL_STR_MAX


def public_details(details):
    """`details` reduced to its scalar entries. Dicts and lists (per-question maps, per-finding
    verdicts, id lists) are dropped: scores.jsonl is public and must not say which items of a
    task were missed. Anything that is not an object becomes {}."""
    if not isinstance(details, dict):
        return {}
    return {k: v for k, v in details.items() if isinstance(k, str) and public_scalar(v)}


def score_line(rid, grader_id, res, extra=None):
    return {"run_id": rid, "grader_id": grader_id, "score": res["score"], "passed": res["passed"],
            "details": public_details({**res["details"], **(extra or {})}), "ts": now()}


def grade_code(ctx, task, rid, block):
    """Append the code-grader score of one answer block (None block = failure).
    Returns False when the grader faulted: nothing is appended and the run stays ungraded."""
    if block is None:
        res = {"score": 0.0, "passed": False, "details": {"no_block": True}}
    else:
        try:
            res = call_grader(task, "grade", block)
        except (GraderFault, EvalError) as e:        # a grader bug is not a model failure
            print(f"evalkit: warning: {task['id']} run {rid} left ungraded: {e}", file=sys.stderr)
            return False
    append_jsonl(ctx.scores_path, score_line(rid, grader_prefix(ctx, task), res))
    return True


# -- run ---------------------------------------------------------------------

class Budget:
    """Money spent in this invocation. A call whose cost is unknown is charged the per-run cap."""

    def __init__(self, cap, per_run_cap=0.0):
        self.cap, self.per_run_cap = cap, per_run_cap or 0.0
        self.spent, self.unknown, self.lock = 0.0, 0, threading.Lock()

    def add(self, usd):
        """Charge a known cost, or (usd is None) the conservative per-run cap."""
        with self.lock:
            if usd is None:
                self.spent += self.per_run_cap
                self.unknown += 1
            else:
                self.spent += usd

    def exhausted(self):
        with self.lock:
            return self.cap is not None and self.spent >= self.cap


def call_cost(call, data):
    """(cost_usd or None, unknown). Unknown when the process was killed or its output carries no
    usable total_cost_usd: guessing 0 would make a cell look free."""
    if call["error"]:                       # the process never started: nothing was spent
        return 0.0, False
    cost = (data or {}).get("total_cost_usd")
    if isinstance(cost, bool) or not isinstance(cost, (int, float)):
        return None, True
    return float(cost), False


def was_cancelled(call, stop):
    """True only when a stop request killed THIS process (negative return code). A run that
    completed while Ctrl-C was landing is a finished run and must still be logged."""
    return stop.event.is_set() and call["returncode"] is not None and call["returncode"] < 0


def prepare_workdir(ctx, task, rid):
    """A fresh private directory (mkdtemp, prefix = run_id) so two processes can never share
    or delete each other's directory."""
    ctx.work_dir.mkdir(parents=True, exist_ok=True)
    wd = Path(tempfile.mkdtemp(prefix=rid, dir=ctx.work_dir))
    try:
        if task["delivery"] == "files" and (task["dir"] / "material").is_dir():
            shutil.copytree(task["dir"] / "material", wd, dirs_exist_ok=True)
    except BaseException:
        shutil.rmtree(wd, ignore_errors=True)
        raise
    return wd


def run_record(ctx, item, call, valid, reason, data):
    cell, model = ctx.cells[item["cell"]], ctx.model_id(item["cell"])
    cost, unknown = call_cost(call, data)
    return {"run_id": item["run_id"], "harness_version": ctx.harness["harness_version"],
            "task_id": item["task"], "task_hash": item["task_hash"], "cell_id": item["cell"],
            "cell_hash": ctx.cell_hash(item["cell"]), "repeat": item["repeat"], "model_id_expected": model,
            "model_id_observed": ",".join(sorted((data or {}).get("modelUsage") or {})) or None,
            "valid": valid, "invalid_reason": reason, "effort": cell.get("effort"),
            **usage_of(data, model), "cost_usd": cost, **({"cost_unknown": True} if unknown else {}),
            "duration_ms": (data or {}).get("duration_ms"), "num_turns": (data or {}).get("num_turns"),
            "cli_version": ctx.cli_version, "ts": now()}


def claude_version(ctx):
    """`<claude_bin> --version`, first line, capped for the public record; None if unavailable."""
    cmd = shlex.split(ctx.harness["runner"]["claude_bin"]) + ["--version"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=30,
                           stdin=subprocess.DEVNULL)
        lines = (r.stdout or "").strip().splitlines()
        if r.returncode == 0 and lines:
            return lines[0].strip()[:DETAIL_STR_MAX]
        reason = f"exit {r.returncode}" if r.returncode else "no output"
    except (OSError, subprocess.SubprocessError) as e:
        reason = str(e)
    print(f"evalkit: warning: could not read the claude version ({reason}); "
          "cli_version will be null", file=sys.stderr)
    return None


def has_valid_run(ctx, rid):
    return any(r.get("run_id") == rid and r.get("valid") for r in read_jsonl(ctx.runs_path))


def execute_one(ctx, task, item, budget, stop):
    """One run, end to end. Returns (runs.jsonl record, graded, duplicate), or None if a stop
    request killed the process. `graded` is False when a valid run's grader faulted and the run
    stays ungraded. `duplicate` is True when a valid line for this run_id already existed: the
    new result is then NOT stored (no second valid line, no answer file, no score)."""
    item = {**item, "task_hash": task["task_hash"]}
    wd = prepare_workdir(ctx, task, item["run_id"])
    runner = ctx.harness["runner"]
    tools = runner["tools_files"] if task["delivery"] == "files" else runner["tools_inline"]
    try:
        call = call_claude(ctx, ctx.cells[item["cell"]], read_text(task["dir"] / "prompt.md"), wd,
                           tools, ctx.system_prompt(item["cell"]), stop)
    finally:
        shutil.rmtree(wd, ignore_errors=True)
    if was_cancelled(call, stop):
        return None
    valid, reason, data = parse_call(call, ctx.model_id(item["cell"]))
    rec = run_record(ctx, item, call, valid, reason, data)
    budget.add(rec["cost_usd"])
    if valid and has_valid_run(ctx, item["run_id"]):
        print(f"evalkit: warning: run {item['run_id']} ({item['task']} {item['cell']} "
              f"#{item['repeat']}) already has a valid line in runs.jsonl; new result skipped",
              file=sys.stderr)
        return rec, True, True
    block = None
    if valid:
        text = data.get("result") or ""
        block = extract_block(text, ctx.harness["answer_markers"])
        write_json_atomic(ctx.answers_dir / f"{item['run_id']}.json",
                          {"run_id": item["run_id"], "result": text, "block": block,
                           "usage": data.get("usage"), "modelUsage": data.get("modelUsage")})
    append_jsonl(ctx.runs_path, rec)
    graded = True
    if valid and task["grading_type"] == "code":
        graded = grade_code(ctx, task, item["run_id"], block)
    return rec, graded, False


def run_pool(ctx, units, worker, jobs, label):
    """Fan units out to `jobs` threads; Ctrl-C kills process groups and exits 130."""
    stop = Stop()
    ex = cf.ThreadPoolExecutor(max_workers=jobs)
    done = 0
    try:
        futures = [ex.submit(worker, u, stop) for u in units]
        for f in cf.as_completed(futures):
            done += 1
            msg = f.result()
            if msg:
                print(f"  [{done}/{len(units)}] {label} {msg}", flush=True)
        return 0
    except KeyboardInterrupt:
        print("\nevalkit: interrupted; killing running processes", file=sys.stderr)
        stop.kill_all()
        return 130
    finally:
        ex.shutdown(wait=True, cancel_futures=True)


def cmd_run(ctx, args):
    require_private(ctx)
    tasks = load_tasks(ctx)
    items, _ = make_plan(ctx, tasks, args)
    print(f"{len(items)} run(s) planned")
    if args.dry_run:
        for i in items:
            print(f"  {i['reason']:<8} {i['row']} {i['task']} {i['cell']} #{i['repeat']}")
        if items:
            cell = ctx.cells[items[0]["cell"]]
            print("command: " + shlex.join(build_cmd(ctx, cell, ctx.harness["runner"]["tools_files"],
                                                     "<system prompt>")) + "  < prompt.md")
        return 0
    if items:
        ctx.cli_version = claude_version(ctx)
    budget = Budget(args.max_usd, ctx.harness["runner"]["max_budget_usd_per_run"])

    def worker(item, stop):
        if stop.event.is_set():
            return None
        if budget.exhausted():
            return f"{item['cell']} {item['task']}#{item['repeat']} skipped (budget)"
        done = execute_one(ctx, tasks[item["task"]], item, budget, stop)
        if done is None:
            return None
        rec, graded, duplicate = done
        state = ("valid" if rec["valid"] else f"INVALID ({rec['invalid_reason']})") + \
                ("" if graded else " UNGRADED (grader fault)") + \
                (" DUPLICATE (not stored)" if duplicate else "")
        cost = "cost unknown" if rec["cost_usd"] is None else f"${rec['cost_usd']:.4f}"
        return f"{item['cell']} {item['task']}#{item['repeat']} {state} {cost}"

    code = run_pool(ctx, items, worker, args.jobs or ctx.harness["runner"]["jobs"], "run")
    print(f"spent ${budget.spent:.4f}" + (f" of ${args.max_usd}" if args.max_usd else "") +
          (f" ({budget.unknown} run(s) with unknown cost charged at the per-run cap)"
           if budget.unknown else ""))
    return code


def cmd_grade(ctx, args):
    """Re-grade stored answers of code tasks under the current grader (no model calls)."""
    require_private(ctx)
    tasks, scores, n, faults = load_tasks(ctx), scores_by_run(ctx), 0, 0
    for t, run in valid_current_runs(ctx, tasks, args):
        if t["grading_type"] != "code" or effective(ctx, t, run["run_id"], scores):
            continue
        ans = ctx.answers_dir / f"{run['run_id']}.json"
        if ans.exists():
            if grade_code(ctx, t, run["run_id"], read_json(ans).get("block")):
                n += 1
            else:
                faults += 1
    print(f"graded {n} run(s)" + (f"; {faults} left ungraded (grader fault)" if faults else ""))
    return 0


# -- judge -------------------------------------------------------------------

def valid_current_runs(ctx, tasks, args):
    """(task, run line) for valid runs whose run_id still matches the current inputs."""
    rows, cells, task_ids = parse_csv(args.rows), parse_csv(args.cells), parse_csv(args.tasks)
    out = []
    for r in RunIndex(ctx).valid.values():
        t = tasks.get(r["task_id"])
        if not t or r["cell_id"] not in ctx.cells or (rows and t["row"] not in rows):
            continue
        if (cells and r["cell_id"] not in cells) or (task_ids and t["id"] not in task_ids):
            continue
        if run_id_for(ctx, t, r["cell_id"], r["repeat"]) == r["run_id"]:
            out.append((t, r))
    return sorted(out, key=lambda x: x[1]["run_id"])


def judge_prompt(task, block):
    return "\n\n".join([
        "## Task given to the system under evaluation\n\n" + read_text(task["dir"] / "prompt.md").strip(),
        "## Rubric\n\n" + read_text(task["dir"] / "rubric.md").strip(),
        "## Answer to grade\n\n" + block])


def parse_judgment(text, markers):
    body = extract_block(text, markers)
    if body is None:
        return None
    body = re.sub(r"^```(?:json)?\s*|\s*```$", "", body.strip())
    try:
        obj = json.loads(body)
    except ValueError:
        return None
    return obj if isinstance(obj, dict) else None


def judge_units(ctx, tasks, args):
    """(task, run, k) triples still lacking a judge score under the current rubric."""
    scores, units = scores_by_run(ctx), []
    reps = ctx.harness["judge"]["repeats"]
    for t, run in valid_current_runs(ctx, tasks, args):
        if t["grading_type"] != "judge":
            continue
        prefix = grader_prefix(ctx, t)
        have = {s["grader_id"] for s in scores.get(run["run_id"], [])}
        units += [(t, run, k) for k in range(reps) if f"{prefix}{k}" not in have]
    return units


def judge_attempt(ctx, task, block, cell, budget, stop):
    """One judge call. Returns (kind, payload, cost): ("ok", scored result), ("format", why)
    for an unparseable reply or a rejected shape (retryable), ("fault", why) for anything
    a retry will not fix (invalid call, grader timeout), or (None, ...) when cancelled. The
    third item is the call's cost, None when it cannot be known."""
    judge = ctx.harness["judge"]
    ctx.work_dir.mkdir(parents=True, exist_ok=True)
    wd = Path(tempfile.mkdtemp(prefix="judge-", dir=ctx.work_dir))
    try:
        call = call_claude(ctx, cell, judge_prompt(task, block), wd, "",
                           judge["system_prompt"], stop)
    finally:
        shutil.rmtree(wd, ignore_errors=True)
    if was_cancelled(call, stop):
        return None, None, 0.0
    valid, reason, data = parse_call(call, cell["model_id"])
    cost, _ = call_cost(call, data)            # None = unknown: the budget is charged the cap
    budget.add(cost)
    if not valid:
        return "fault", f"judge call invalid ({reason})", cost
    judgment = parse_judgment(data.get("result") or "", ctx.harness["answer_markers"])
    if judgment is None:
        return "format", "reply has no parseable JSON object between the markers", cost
    try:
        return "ok", call_grader(task, "score_judgment", judgment), cost
    except GraderFault as e:
        return ("fault" if e.timeout else "format"), f"score_judgment rejected the reply: {e}", cost
    except EvalError as e:
        return "fault", str(e), cost


def judge_one(ctx, unit, budget, stop, faults=None):
    """One judge pass. A format fault is retried up to JUDGE_FORMAT_RETRIES more times; if
    still bad the pass stays missing (nothing appended) and is reported through `faults`."""
    task, run, k = unit
    judge = ctx.harness["judge"]
    gid = f"{grader_prefix(ctx, task)}{k}"
    label = f"{task['id']} {run['run_id']}#{k}"
    ans = ctx.answers_dir / f"{run['run_id']}.json"
    if not ans.exists():
        return f"{label} skipped: no stored answer"
    block = read_json(ans).get("block")
    if block is None:
        append_jsonl(ctx.scores_path, score_line(run["run_id"], gid,
                     {"score": 0.0, "passed": False, "details": {"no_block": True}}))
        return f"{label} no answer block -> 0"
    cell, spent, why, unknown = ctx.cells[judge["cell"]], 0.0, "", False
    for attempt in range(1, JUDGE_FORMAT_RETRIES + 2):
        if budget.exhausted() or stop.event.is_set():
            return None
        kind, payload, cost = judge_attempt(ctx, task, block, cell, budget, stop)
        spent += cost or 0.0
        unknown = unknown or cost is None
        if kind is None:
            return None
        if kind == "ok":
            append_jsonl(ctx.scores_path, score_line(run["run_id"], gid, payload, {
                "judge_cost_usd": spent, "judge_cell": judge["cell"], "judge_attempts": attempt,
                "cli_version": ctx.cli_version, **({"judge_cost_unknown": True} if unknown else {})}))
            return f"{label} score {payload['score']:.2f}" + (f" (attempt {attempt})" if attempt > 1 else "")
        why = payload
        if kind == "fault":
            break
    msg = f"{label} judge pass left missing after {attempt} attempt(s): {why}"
    if faults is not None:
        faults.append(msg)
    print(f"evalkit: warning: {msg}", file=sys.stderr)
    return msg


def cmd_judge(ctx, args):
    require_private(ctx)
    units = judge_units(ctx, load_tasks(ctx), args)
    print(f"{len(units)} judge pass(es) to do")
    if units:
        ctx.cli_version = claude_version(ctx)
    budget, faults = Budget(args.max_usd, ctx.harness["runner"]["max_budget_usd_per_run"]), []
    code = run_pool(ctx, units, lambda u, stop: judge_one(ctx, u, budget, stop, faults),
                    args.jobs or ctx.harness["runner"]["jobs"], "judge")
    print(f"judge cost ${budget.spent:.4f}" +
          (f" ({budget.unknown} call(s) with unknown cost charged at the per-run cap)"
           if budget.unknown else ""))
    if faults:
        print(f"{len(faults)} judge pass(es) left missing (judge format fault); "
              "re-run `judge` to try them again")
    return code


# -- status / report ---------------------------------------------------------

def collect(ctx, tasks):
    """{(task_id, cell_id): {"attempts": n, "valid": [run dict with score/passed/cost/thinking]}}
    over runs whose run_id matches the current harness, task hash and model id."""
    scores, table = scores_by_run(ctx), {}
    for r in RunIndex(ctx).lines:
        t = tasks.get(r.get("task_id"))
        if not t or r.get("cell_id") not in ctx.cells:
            continue
        if run_id_for(ctx, t, r["cell_id"], r["repeat"]) != r["run_id"]:
            continue
        slot = table.setdefault((t["id"], r["cell_id"]), {"attempts": 0, "valid": {}})
        slot["attempts"] += 1
        if r.get("valid"):
            eff = effective(ctx, t, r["run_id"], scores)
            slot["valid"][r["run_id"]] = {"repeat": r["repeat"], "cost": r.get("cost_usd"),
                                          "thinking": r.get("thinking_tokens"),
                                          "score": eff[0] if eff else None,
                                          "passed": eff[1] if eff else None}
    return table


def cmd_status(ctx, args):
    tasks = load_tasks(ctx)
    table = collect(ctx, tasks)
    print(f"{'row':<20} {'tasks':<7} {'cells':<6} {'valid':<6} {'invalid':<8} {'scored':<7} ungraded")
    for row in ctx.rows:
        present = row_tasks(tasks, row["id"])
        ids = {t["id"] for t in present}
        slots = [s for (tid, _), s in table.items() if tid in ids]
        valid = [v for s in slots for v in s["valid"].values()]
        scored = sum(1 for v in valid if v["score"] is not None)
        invalid = sum(s["attempts"] - len(s["valid"]) for s in slots)
        declared = len(set(row["tasks"]) | ids)
        print(f"{row['id']:<20} {len(ids)}/{declared:<5} {len(row['grid']):<6} {len(valid):<6} "
              f"{invalid:<8} {scored:<7} {len(valid) - scored}")
    lines = RunIndex(ctx).lines
    total = sum(r.get("cost_usd") or 0.0 for r in lines)
    judge = sum((s.get("details") or {}).get("judge_cost_usd", 0.0) for s in read_jsonl(ctx.scores_path))
    print(f"total cost so far: ${total + judge:.4f} (runs ${total:.4f}, judge ${judge:.4f})")
    unknown = sum(1 for r in lines if r.get("cost_unknown") or ("cost_usd" in r and r["cost_usd"] is None))
    if unknown:
        print(f"{unknown} run(s) with unknown cost (not in the total)")
    return 0


def fmt(value, spec, none="n/a"):
    return none if value is None else format(value, spec)


def render(header, rows, md):
    if md:
        lines = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
        return "\n".join(lines + ["| " + " | ".join(r) + " |" for r in rows])
    widths = [max(len(str(x)) for x in col) for col in zip(header, *rows)]
    return "\n".join("  ".join(str(c).ljust(w) for c, w in zip(r, widths)).rstrip()
                     for r in [header] + rows)


def known_costs(runs):
    """Costs of scored runs whose cost is known (None = unknown, never counted as 0)."""
    return [v["cost"] for v in runs if v["cost"] is not None]


def cmd_report(ctx, args):
    tasks = load_tasks(ctx)
    check_known("row", parse_csv(args.rows), [r["id"] for r in ctx.rows])
    table = collect(ctx, tasks)
    phases = PHASES if args.phase == "all" else (args.phase,)
    header = ["cell", "role", "runs", "valid", "passed", "pass rate", "mean score",
              "mean cost/run", "mean thinking", "tasks"]
    if args.phase == "all":
        print("warning: --phase all mixes screening and confirmation runs; cells may cover "
              "different task sets, so their mean costs are not comparable")
        print()
    for row in ctx.rows:
        if parse_csv(args.rows) and row["id"] not in parse_csv(args.rows):
            continue
        covered = [t["id"] for t in row_tasks(tasks, row["id"], phases)]
        ids = set(covered)
        body, ungraded = [], 0
        for g in row["grid"]:
            slots = [(tid, s) for (tid, c), s in table.items() if c == g["cell"] and tid in ids]
            valid = [v for _, s in slots for v in s["valid"].values()]
            scored = [v for v in valid if v["score"] is not None]
            counted = {tid for tid, s in slots if any(v["score"] is not None for v in s["valid"].values())}
            passed = sum(1 for v in scored if v["passed"])
            body.append([g["cell"], g["role"], str(sum(s["attempts"] for _, s in slots)), str(len(valid)),
                         str(passed), fmt(passed / len(scored) * 100 if scored else None, ".1f") +
                         ("%" if scored else ""), fmt(mean(v["score"] for v in scored), ".3f"),
                         "$" + fmt(mean(known_costs(scored)), ".4f"),
                         fmt(mean(v["thinking"] for v in scored if v["thinking"] is not None), ".0f"),
                         str(len(counted))])
            ungraded += len(valid) - len(scored)
        print(("### " if args.md else "") + f"{row['id']}  ({row['tier']}, baseline {row['baseline']})")
        print(f"phase: {args.phase}; tasks: {', '.join(covered) if covered else 'none'}")
        print(render(header, body, args.md))
        if ungraded:
            print(f"  {ungraded} ungraded run(s) excluded (treated as missing)")
        print()
    return 0


# -- decide ------------------------------------------------------------------

def cell_stats(ctx, table, tasks_subset, cell_id):
    """Complete-or-not statistics of one cell over a task subset (repeats_default each)."""
    reps = ctx.harness["repeats_default"]
    missing, scored = [], []
    for t in tasks_subset:
        valid = (table.get((t["id"], cell_id)) or {"valid": {}})["valid"].values()
        by_rep = {v["repeat"]: v for v in valid}
        for rep in range(1, reps + 1):
            v = by_rep.get(rep)
            if v is None or v["score"] is None:
                miss = {"task": t["id"], "cell": cell_id, "repeat": rep}
                if v is not None:                    # a valid run exists but its grading is missing
                    miss["ungraded"] = True
                missing.append(miss)
            else:
                scored.append(v)
    fails = sum(1 for v in scored if not v["passed"])
    costs = known_costs(scored)
    return {"cell": cell_id, "expected": len(tasks_subset) * reps, "missing": missing,
            "fails": fails, "passes": len(scored) - fails, "cost": mean(costs),
            "cost_unknown": len(scored) - len(costs),
            "rate": (len(scored) - fails) / len(scored) if scored else None}


def baseline_fails(tier, bs):
    return bs["fails"] > 0 if tier == "silent_damage" else bs["rate"] < NOTICED_FAIL_BELOW


def cell_passes(tier, cs):
    return cs["fails"] == 0 if tier == "silent_damage" else cs["rate"] >= NOTICED_FAIL_BELOW


def ungraded_note(who, stats):
    n = sum(1 for m in stats["missing"] if m.get("ungraded"))
    return f"{who}: {n} run(s) ungraded (grader fault), treated as missing" if n else None


def exhausted_runs(ctx, idx, tasks_subset, cell_id):
    """Runs of a cell that used up max_retries_invalid without a valid line: plan will never
    re-issue them, so they never complete. Same threshold and ids as make_plan."""
    out, max_retry = [], ctx.harness["max_retries_invalid"]
    for t in tasks_subset:
        for rep in range(1, ctx.harness["repeats_default"] + 1):
            rid = run_id_for(ctx, t, cell_id, rep)
            attempts = idx.invalid.get(rid, 0)
            if rid not in idx.valid and attempts > max_retry:
                out.append({"task": t["id"], "repeat": rep, "attempts": attempts})
    return out


def decide_row(ctx, row, tasks, table, idx=None):
    idx = idx or RunIndex(ctx)
    tier, base = row["tier"], row["baseline"]
    scr = row_tasks(tasks, row["id"], ("screening",))
    conf = row_tasks(tasks, row["id"], ("confirmation",))
    res = {"row": row["id"], "tier": tier, "baseline": base, "recommendation": "INSUFFICIENT_DATA",
           "cell": None, "provisional": False, "missing_runs": [], "candidates": [], "notes": []}
    bs = cell_stats(ctx, table, scr, base)
    if not scr or bs["missing"]:
        res["missing_runs"] = bs["missing"]
        res["notes"].append("no screening tasks" if not scr else "baseline has missing screening runs")
        if scr and ungraded_note("baseline", bs):
            res["notes"].append(ungraded_note("baseline", bs))
        return res
    if bs["cost_unknown"]:                        # a mean over a partial cost set is not a baseline
        res["notes"].append(f"baseline has {bs['cost_unknown']} run(s) with unknown cost: "
                            "costs cannot be compared")
        return res
    res["baseline_cost"], res["baseline_fails"] = bs["cost"], bs["fails"]
    cands = []
    for g in row["grid"]:
        if g["cell"] != base:
            cs = cell_stats(ctx, table, scr, g["cell"])
            cand = {"cell": g["cell"], "role": g["role"], "cost": cs["cost"], "fails": cs["fails"],
                    "cost_unknown": cs["cost_unknown"], "qualifies": False, "reason": ""}
            res["candidates"].append(cand)
            cands.append((cand, cs))
            if ungraded_note(g["cell"], cs):
                res["notes"].append(ungraded_note(g["cell"], cs))
    for cand, cs in cands:
        if cs["missing"]:                         # an incomplete candidate may be the cheaper one
            res["provisional"] = True
            res["notes"].append(f"provisional: candidate {cand['cell']} has "
                                f"{len(cs['missing'])} missing run(s)")
        dead = exhausted_runs(ctx, idx, scr + conf, cand["cell"])
        cand["exhausted"] = len(dead)
        for d in dead:
            res["notes"].append(f"candidate {cand['cell']}: run {d['task']} #{d['repeat']} exhausted "
                                f"its retries ({d['attempts']} invalid attempts); it will never complete")
    if all(cs["missing"] for _, cs in cands):
        res["notes"].append("no candidate has a complete set of screening runs")
        res["missing_runs"] = [m for _, cs in cands for m in cs["missing"] if m.get("ungraded")]
        for cand, cs in cands:
            cand["reason"] = f"incomplete: {len(cs['missing'])} of {cs['expected']} runs missing"
        return res
    bfail = baseline_fails(tier, bs)
    qualified = sorted(screen_candidates(ctx, tier, bs, cands, bfail), key=lambda c: (c["cost"], c["cell"]))
    ungraded = [m for _, cs in cands for m in cs["missing"] if m.get("ungraded")]
    if tier == "silent_damage":                   # confirmation runs decide reads for qualified candidates
        for cand in qualified:
            cs = cell_stats(ctx, table, conf, cand["cell"])
            ungraded += [m for m in cs["missing"] if m.get("ungraded")]
            if ungraded_note(cand["cell"], cs):
                res["notes"].append(ungraded_note(cand["cell"], cs) + " (confirmation)")
    if ungraded:                                  # a harness fault must not decide the row
        res["missing_runs"] = ungraded
        res["notes"].append("a run is ungraded: no recommendation until it is graded (`grade` / `judge`)")
        return res
    if bfail:
        res["notes"].append(f"baseline fails its row ({bs['fails']} of {bs['expected']} screening runs failed)")
    res["recommendation"] = "KEEP"
    if tier == "silent_damage":
        # a silent-damage candidate ALWAYS needs its confirmation runs, whatever the baseline did
        res = confirm_candidates(ctx, res, qualified, conf, table)
    elif qualified:
        res.update(recommendation="MOVE_TO", cell=qualified[0]["cell"])
    if bfail and res["recommendation"] == "KEEP":
        baseline_fails_to(res, tier, cands)
    return res


def baseline_fails_to(res, tier, cands):
    """The baseline failed its row and no candidate qualified: name the cheapest passing up-cell."""
    res["recommendation"] = "BASELINE_FAILS"
    up = [c for c, cs in cands if c["role"] in UP_ROLES and not cs["missing"]
          and not cs["cost_unknown"] and not c.get("confirmation_failed") and cell_passes(tier, cs)]
    best = min(up, key=lambda c: (c["cost"], c["cell"]), default=None)
    res["cell"] = best["cell"] if best else None
    if best:
        best["qualifies"], best["reason"] = True, "cheapest up-cell that passes"
    else:
        res["notes"].append("no up-cell passes (or none measured yet)")


def screen_candidates(ctx, tier, bs, cands, bfail=False):
    """Mark and return the candidates that clear the screening bar for this tier. A move
    must also save at least decision.min_saving_fraction of the baseline's measured cost
    (default 0), unless the baseline itself fails its row."""
    extra, out = ctx.harness["decision"]["noticed_extra_misses"], []
    min_saving = ctx.harness["decision"].get("min_saving_fraction", 0.0)
    for cand, cs in cands:
        saving = 1 - cs["cost"] / bs["cost"] if cs["cost"] is not None and bs["cost"] else 0.0
        if cs["missing"]:
            cand["reason"] = f"incomplete: {len(cs['missing'])} of {cs['expected']} runs missing"
        elif cs["cost_unknown"]:
            cand["reason"] = f"cost unknown for {cs['cost_unknown']} run(s): cannot compare with the baseline"
        elif not cs["cost"] < bs["cost"]:
            cand["reason"] = f"not cheaper: ${cs['cost']:.4f} vs baseline ${bs['cost']:.4f}"
        elif not bfail and saving < min_saving:
            cand["reason"] = (f"cheaper by only {saving:.0%} (needs {min_saving:.0%}): "
                              "not worth a move")
        elif tier == "silent_damage" and cs["fails"] > 0:
            cand["reason"] = f"failed {cs['fails']} screening run(s); silent-damage needs every run"
        elif tier != "silent_damage" and cs["fails"] > bs["fails"] + extra:
            cand["reason"] = f"{cs['fails']} failures vs baseline {bs['fails']} + {extra}"
        elif tier != "silent_damage" and not cell_passes(tier, cs):
            cand["reason"] = "fails its own row"
        else:
            cand["qualifies"], cand["reason"] = True, "cheaper and within the screening bar"
            out.append(cand)
    return out


def confirm_candidates(ctx, res, qualified, conf, table):
    """Silent-damage: the cheapest qualified candidate must pass every confirmation run.
    NEEDS_CONFIRMATION lists that candidate's missing confirmation runs only."""
    need = ctx.harness["decision"]["confirmation_tasks_min"]
    for cand in qualified:
        cs = cell_stats(ctx, table, conf, cand["cell"])
        if cs["fails"]:                              # one failed confirmation run is final
            cand["qualifies"], cand["reason"] = False, f"failed {cs['fails']} confirmation run(s)"
            cand["confirmation_failed"] = True
            continue
        if len(conf) < need or cs["missing"]:
            res.update(recommendation="NEEDS_CONFIRMATION", cell=cand["cell"],
                       missing_runs=cs["missing"])
            if len(conf) < need:
                res["notes"].append(f"{need - len(conf)} more confirmation task(s) must be authored "
                                    f"(have {len(conf)}, need {need})")
            cand["reason"] += "; confirmation pending"
            return res
        cand["reason"] += "; passed every confirmation run"
        res.update(recommendation="MOVE_TO", cell=cand["cell"])
        return res
    return res


def cmd_decide(ctx, args):
    tasks = load_tasks(ctx)
    table = collect(ctx, tasks)
    idx = RunIndex(ctx)
    out = [decide_row(ctx, row, tasks, table, idx) for row in ctx.rows]
    if args.json:
        print(json.dumps(out, indent=2))
        return 0
    for r in out:
        head = r["recommendation"] + (f" {r['cell']}" if r["cell"] else "") + \
               (" (provisional)" if r["provisional"] else "")
        print(f"{r['row']:<20} [{r['tier']}] baseline {r['baseline']}: {head}")
        for m in r["missing_runs"]:
            print(f"    missing: {m['task']} {m['cell']} #{m['repeat']}")
        for n in r["notes"]:
            print(f"    note: {n}")
        for c in r["candidates"]:
            cost = "n/a" if c["cost"] is None else f"${c['cost']:.4f}"
            print(f"    {c['cell']:<20} {c['role']:<12} {cost:<9} {'yes' if c['qualifies'] else 'no '}  {c['reason']}")
    return 0


# -- selfcheck ---------------------------------------------------------------

def check_fixtures(task, errors):
    fx, tid = task["dir"] / "fixtures", task["id"]
    judge = task["grading_type"] == "judge"
    func, perfect = ("score_judgment", "judgment_perfect.json") if judge else ("grade", "perfect.txt")
    flawed = sorted(fx.glob("judgment_flawed_*.json" if judge else "flawed_*.txt")) if fx.is_dir() else []
    okays = sorted(fx.glob("ok_*.json" if judge else "ok_*.txt")) if fx.is_dir() else []

    def load(p):
        return json.loads(read_text(p)) if judge else read_text(p)

    try:
        if not (fx / perfect).is_file():
            errors.append(f"{tid}: fixtures/{perfect} missing")
        else:
            r = call_grader(task, func, load(fx / perfect))
            if not (abs(r["score"] - 1.0) < 1e-9 and r["passed"]):
                errors.append(f"{tid}: {perfect} scored {r['score']} passed={r['passed']} (want 1.0, pass)")
        if not flawed:
            errors.append(f"{tid}: no flawed fixtures")
        for p in flawed:
            try:
                passed = call_grader(task, func, load(p))["passed"]
            except GraderRejected:
                if judge:                            # a malformed judge reply is rightly rejected
                    continue
                raise
            if passed:
                errors.append(f"{tid}: {p.name} passed but is flawed")
        for p in okays:                              # acceptable-but-imperfect answers must pass
            if not call_grader(task, func, load(p))["passed"]:
                errors.append(f"{tid}: {p.name} is an ok fixture but did not pass")
    except Exception as e:
        errors.append(f"{tid}: grader failed on fixtures: {type(e).__name__}: {e}")


def scan_secrets(tdir, errors):
    for p in sorted(x for x in tdir.rglob("*") if x.is_file() and "fixtures" not in x.parts):
        if p.name.startswith(".env"):
            errors.append(f"{tdir.name}: {p.relative_to(tdir)} is an env file")
            continue
        text = p.read_bytes().decode("latin-1")
        for pat in SECRET_PATTERNS:
            if pat.search(text):
                errors.append(f"{tdir.name}: {p.relative_to(tdir)} matches secret pattern {pat.pattern!r}")


def check_threshold(task, tdir, errors):
    """task.json pass_threshold must equal truth.json pass_threshold when truth has that key."""
    try:
        truth = read_json(tdir / "truth.json")
    except EvalError:
        return                                       # a missing or broken truth.json is reported elsewhere
    if isinstance(truth, dict) and "pass_threshold" in truth \
            and truth["pass_threshold"] != task["pass_threshold"]:
        errors.append(f"{task['id']}: task.json pass_threshold {task['pass_threshold']!r} != "
                      f"truth.json pass_threshold {truth['pass_threshold']!r}")


def check_task(ctx, tdir, errors):
    try:
        e = manifest_entry(tdir)
    except EvalError as ex:
        errors.append(str(ex))
        return
    e["dir"], tid = tdir, e["id"]
    if tdir.name != tid:
        errors.append(f"{tdir.name}: directory name differs from id {tid!r}")
    if e["row"] not in [r["id"] for r in ctx.rows]:
        errors.append(f"{tid}: unknown row {e['row']!r}")
    if e["phase"] not in PHASES or e["delivery"] not in ("files", "inline"):
        errors.append(f"{tid}: bad phase or delivery")
    if not isinstance(e["pass_threshold"], (int, float)) or not 0 <= e["pass_threshold"] <= 1:
        errors.append(f"{tid}: pass_threshold must be 0..1")
    if e["grading_type"] not in ("code", "judge"):
        errors.append(f"{tid}: grading.type must be code or judge")
        return
    needed = ["truth.json", "grader.py"] + (["rubric.md"] if e["grading_type"] == "judge" else [])
    for name in needed:
        if not (tdir / name).is_file():
            errors.append(f"{tid}: {name} missing")
    if (e["delivery"] == "files") != bool(material_files(tdir)):
        errors.append(f"{tid}: delivery {e['delivery']!r} does not match material/ contents")
    scan_secrets(tdir, errors)
    check_threshold(e, tdir, errors)
    if (tdir / "grader.py").is_file() and (tdir / "truth.json").is_file():
        check_fixtures(e, errors)


def cmd_selfcheck(ctx, args):
    require_private(ctx)
    dirs = sorted(p for p in ctx.tasks_dir.iterdir() if p.is_dir())
    errors = []
    for tdir in dirs:
        check_task(ctx, tdir, errors)
    for e in errors:
        print(f"FAIL {e}")
    print(f"selfcheck: {len(dirs)} task(s), {len(errors)} problem(s)")
    return 1 if errors else 0


# -- sanitize ----------------------------------------------------------------

def sanitize_text(text):
    """(new text, changed line count, total line count) with every score line's `details`
    reduced to scalars. Lines that are not valid JSON objects, and lines already clean, are kept
    byte for byte. Split on "\\n" only: a raw U+2028 inside a JSON string is not a line break."""
    out, changed, total = [], 0, 0
    for line in text.split("\n"):
        if not line.strip():
            out.append(line)
            continue
        total += 1
        try:
            obj = json.loads(line)
        except ValueError:
            out.append(line)
            continue
        if isinstance(obj, dict) and "details" in obj:
            clean = public_details(obj["details"])
            if not isinstance(obj["details"], dict) or len(clean) != len(obj["details"]):
                obj["details"] = clean
                line = json.dumps(obj, separators=(",", ":"), ensure_ascii=False)
                changed += 1
        out.append(line)
    return "\n".join(out), changed, total


def cmd_sanitize(ctx, args):
    """Rewrite results/scores.jsonl in place (temp file + os.replace) applying the public-details
    rule to the existing lines. Idempotent; the file is not touched when nothing changes."""
    path = ctx.scores_path
    if not path.exists():
        print("sanitize: no scores.jsonl; 0 line(s) changed")
        return 0
    text = read_text(path)
    new_text, changed, total = sanitize_text(text)
    if changed:
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".scores-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(new_text)
                f.flush()
                os.fsync(f.fileno())
            os.chmod(tmp, path.stat().st_mode & 0o777)
            os.replace(tmp, path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
    print(f"sanitize: {changed} line(s) changed ({total} score line(s) read)")
    return 0


# -- CLI ---------------------------------------------------------------------

def build_parser():
    p = argparse.ArgumentParser(prog="evalkit", description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)

    def add(name, fn, help_):
        sp = sub.add_parser(name, help=help_, description=help_)
        sp.set_defaults(fn=fn)
        return sp

    add("manifest", cmd_manifest, "build tasks.json from private/tasks/*/task.json")
    add("status", cmd_status, "per-row counts of tasks, runs, scores and total cost")
    sp = add("plan", cmd_plan, "list the missing or retryable runs")
    add_filter_args(sp)
    sp.add_argument("--json", action="store_true")
    sp = add("run", cmd_run, "execute the plan with `claude -p`")
    add_filter_args(sp)
    sp.add_argument("--jobs", type=int, help="parallel workers (default harness runner.jobs)")
    sp.add_argument("--max-usd", type=float, help="stop launching new runs once this much is spent")
    sp.add_argument("--dry-run", action="store_true")
    sp = add("grade", cmd_grade, "re-grade stored answers of code tasks under the current grader")
    add_filter_args(sp, with_repeats=False)
    sp = add("judge", cmd_judge, "judge-grade valid runs that lack scores for the current rubric")
    add_filter_args(sp, with_repeats=False)
    sp.add_argument("--jobs", type=int)
    sp.add_argument("--max-usd", type=float)
    sp = add("report", cmd_report, "per-row table of pass rate, score, cost and thinking tokens")
    sp.add_argument("--rows")
    sp.add_argument("--phase", choices=("screening", "confirmation", "all"), default="screening",
                    help="which task phase to report (default screening); cells of different "
                         "phases cover different tasks, so their costs do not compare")
    sp.add_argument("--md", action="store_true", help="markdown tables")
    sp = add("decide", cmd_decide, "apply the README decision bar to every row")
    sp.add_argument("--json", action="store_true")
    add("selfcheck", cmd_selfcheck, "run graders on their fixtures and scan material for secrets")
    add("sanitize", cmd_sanitize, "rewrite results/scores.jsonl keeping only scalar details")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        ctx = Ctx()
        if args.cmd in LOCKED_COMMANDS and not getattr(args, "dry_run", False):
            with exclusive_lock(ctx.lock_path):          # before any side effect
                return args.fn(ctx, args)
        return args.fn(ctx, args)
    except EvalError as e:
        print(f"evalkit: error: {e}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\nevalkit: interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
