#!/usr/bin/env python3
"""fanout_scan.py: one JSON snapshot of the clean-run fan-outs on this machine.

The agenting plugin's fan-out view (hooks/fanouts/) runs this every few seconds and draws what it prints. It is read-only: it
runs `ps` (and `lsof` to resolve a relative path), reads files, and writes nothing.

Two kinds of fan-out are found:

- runtime: `node ... clean_runtime.mjs <script.js> --out DIR`, which runs every agent() call of a
  Workflow script as its own `python3 cleanrun.py run` child. Read: DIR/log.txt (a `start` line per
  run, then done and FAIL lines), DIR/journal.jsonl (started lines: label and phase),
  DIR/calls/<id>/{tasks.jsonl, stderr.txt, out/summary.json, out/ledger.jsonl, out/outputs/<id>.json},
  DIR/result.json and DIR/cost.json (written when a run ends).
- cleanrun: a `python3 cleanrun.py run ... --out-dir DIR` that no runtime started. Read:
  DIR/.lock (rewritten when each invocation starts), DIR/summary.json, DIR/ledger.jsonl,
  DIR/outputs/*.json, and the --tasks file while it runs.

A folder can hold several runs (a runtime re-run in the same OUT, a cleanrun resumed in the same
out-dir): every file but the outputs is appended or rewritten across runs. Only evidence from the
current run counts: log lines after the last `start`, calls whose tasks.jsonl was written since
that start, ledger lines stamped since then.

Whose runs: only the chat's own. One machine runs many Claude Code sessions (chats), as many as there are
`claude` processes, and a Workflow is shown only in the chat that started it; a clean run is too. The scanner
works for the chat it runs under (the nearest ancestor named `claude`, else its parent) and lists a run only
when it descends from that process, or when the run's own summary.json names that process as its "owner" (a run
that lost its parent, `cmd &`, is still attributed; a clean_runtime.mjs that lost its parent is the chat's when
one of its calls is; a run with no such link, another chat's or one started outside any chat, is not listed). A folder named by --dir is dropped when its summary.json names another owner.
--all lifts all of this, for use by hand.

usage: fanout_scan.py [--dir DIR]... [--cwd PID=DIR]... [--owner PID | --all]
  --dir      a fan-out directory seen earlier, read even when no process holds it any more
  --cwd      a process's working directory resolved earlier (skips one lsof call)
  --owner    the claude process whose runs to list (default: found from this process's ancestors)
  --all      every run on this machine, whoever started it

Always exits 0 and prints one JSON object (version "v": 1). "degraded": true means the process
table could not be read, so the snapshot says nothing about what runs. A problem with one fan-out
is reported in that fan-out's "problems" list instead of failing the whole snapshot.
"""
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime

V = 1
SLACK = 2.0          # seconds: ps etime and log times are whole seconds
SANITISE = re.compile(r"[^A-Za-z0-9._-]")
STARTED_LINE = re.compile(r'^\{\s*"type"\s*:\s*"started"')
LOG_LINE = re.compile(r"^\[(\d\d):(\d\d):(\d\d)\] (.*)$")
DONE_LINE = re.compile(r"^done (.+) \((\d+) s\)$")
FAIL_SEP = ": cleanrun exit "
FINAL_STATES = ("finished", "stopped", "interrupted")
SCAN_DEPTH = 12      # how far into argv to look for the script (interpreter options come first)


def call_id(label):
    """clean_runtime.mjs's directory name for a label: calls/<id>/. JavaScript replaces each
    UTF-16 unit and slices by units, so a character outside the BMP (an emoji) becomes '__'."""
    units = []
    for ch in label:
        if SANITISE.match(ch):
            units.extend("__" if ord(ch) > 0xFFFF else "_")
        else:
            units.append(ch)
    return "".join(units[:120])


def parse_etime(text):
    """ps etime, [[dd-]hh:]mm:ss, in seconds."""
    days = 0
    if "-" in text:
        d, text = text.split("-", 1)
        days = int(d)
    parts = [int(p) for p in text.split(":")]
    while len(parts) < 3:
        parts.insert(0, 0)
    h, m, s = parts[-3:]
    return days * 86400 + h * 3600 + m * 60 + s


def parse_ts(text):
    """A ledger or summary timestamp (ISO 8601) in epoch seconds, else None."""
    if not isinstance(text, str):
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def parse_ps(text):
    """Rows of `ps -axww -o pid=,ppid=,etime=,command=`. The command is split on spaces, so a
    path with a space in it spans several tokens; flag_path() joins them back."""
    procs = []
    for line in text.splitlines():
        parts = line.split(None, 3)
        if len(parts) < 4:
            continue
        try:
            pid, ppid, etime = int(parts[0]), int(parts[1]), parse_etime(parts[2])
        except ValueError:
            continue
        procs.append({"pid": pid, "ppid": ppid, "etime": etime, "argv": parts[3].split()})
    return procs


def flag(argv, name):
    """The value after `name` (or of `name=value`) in argv, else None."""
    for i, a in enumerate(argv):
        if a == name and i + 1 < len(argv):
            return argv[i + 1]
        if a.startswith(name + "="):
            return a[len(name) + 1:]
    return None


def flag_tokens(argv, name):
    """Every token after `name` up to the next option: a value that had spaces in it."""
    for i, a in enumerate(argv):
        if a == name:
            out = []
            for t in argv[i + 1:]:
                if t.startswith("--"):
                    break
                out.append(t)
            return out
        if a.startswith(name + "="):
            return [a[len(name) + 1:]]
    return []


def script_index(argv, basename):
    """Where `basename` sits in argv (after any interpreter options), else None."""
    for i, a in enumerate(argv[:SCAN_DEPTH]):
        if os.path.basename(a) == basename:
            return i
    return None


def runtime_script(argv):
    """For a clean_runtime.mjs process: the Workflow script it runs, else None (not a runtime)."""
    i = script_index(argv, "clean_runtime.mjs")
    if i is None or i == 0 or not flag_tokens(argv, "--out"):
        return None
    return argv[i + 1] if i + 1 < len(argv) and not argv[i + 1].startswith("--") else ""


def is_cleanrun(argv):
    i = script_index(argv, "cleanrun.py")
    return (i is not None and i > 0 and i + 1 < len(argv) and argv[i + 1] == "run"
            and bool(flag_tokens(argv, "--out-dir")))


def is_claude_print(argv):
    return bool(argv) and os.path.basename(argv[0]) == "claude" and "-p" in argv


def lsof_cwd(pid):
    """A process's working directory: /proc on Linux, lsof on macOS; None when unknown."""
    try:
        return os.readlink(f"/proc/{pid}/cwd")
    except OSError:
        pass
    try:
        out = subprocess.run(["lsof", "-a", "-p", str(pid), "-d", "cwd", "-Fn"],
                             capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    for line in out.splitlines():
        if line.startswith("n") and len(line) > 1:
            return line[1:]
    return None


class Resolver:
    """Makes a process's path argument absolute, resolving its working directory at most once."""

    def __init__(self, known, lookup=lsof_cwd):
        self.cwds = dict(known)   # pid -> cwd
        self.lookup = lookup

    def absolute(self, path, pid):
        if not path:
            return None
        if os.path.isabs(path):
            return os.path.normpath(path)
        if pid not in self.cwds:
            cwd = self.lookup(pid)
            if cwd is None:
                return None
            self.cwds[pid] = cwd
        return os.path.normpath(os.path.join(self.cwds[pid], path))


def flag_path(resolver, proc, name, exists=os.path.isdir):
    """A path option made absolute. When ps split it at spaces, the longest join that exists
    wins; else the first token. None when it is relative and the cwd cannot be read."""
    tokens = flag_tokens(proc["argv"], name)
    if not tokens:
        return None
    for k in range(len(tokens), 1, -1):
        p = resolver.absolute(" ".join(tokens[:k]), proc["pid"])
        if p and exists(p):
            return p
    return resolver.absolute(tokens[0], proc["pid"])


def read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def descendants(procs, root):
    """Pids of every process below `root` in the table."""
    kids = {}
    for p in procs:
        kids.setdefault(p["ppid"], []).append(p["pid"])
    below, todo = set(), [root]
    while todo:
        for k in kids.get(todo.pop(), ()):
            if k not in below:
                below.add(k)
                todo.append(k)
    return below


def recorded_owner(out_dir):
    """The claude pid a cleanrun wrote into out_dir/summary.json as its "owner", else None (a run from before
    the field, or one started outside Claude Code)."""
    summ = read_json(os.path.join(out_dir, "summary.json"))
    owner = summ.get("owner") if isinstance(summ, dict) else None
    pid = owner.get("pid") if isinstance(owner, dict) else None
    return pid if isinstance(pid, int) and not isinstance(pid, bool) else None


def chat_pid(procs, parent):
    """The claude process this scanner works for: the nearest ancestor named `claude` (the module's scanner
    is its direct child), else the parent."""
    by_pid = {p["pid"]: p for p in procs}
    pid = parent
    for _ in range(64):
        p = by_pid.get(pid)
        if p is None:
            break
        if p["argv"] and os.path.basename(p["argv"][0]) == "claude":
            return pid
        pid = p["ppid"]
    return parent


def iter_lines(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                yield line.rstrip("\n")
    except OSError:
        return


def last_line(path, limit=400):
    """The last non-empty line of a small file, read from its last `limit` bytes."""
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - limit))
            text = f.read().decode("utf-8", errors="replace")
    except OSError:
        return None
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return lines[-1][:200] if lines else None


def born(path):
    """When a file was created (macOS birth time), else its change time; None when missing."""
    try:
        st = os.stat(path)
    except OSError:
        return None
    return getattr(st, "st_birthtime", None) or st.st_ctime


def mtime(path):
    try:
        return os.stat(path).st_mtime
    except OSError:
        return None


def newest(*times):
    known = [t for t in times if t is not None]
    return max(known) if known else None


def fresh(t, since):
    """True when a file time is from this run (or there is no run start to compare with)."""
    return since is None or (t is not None and t >= since - SLACK)


def ledger(path, since=None):
    """Per task id, over the lines stamped since `since`: attempts, invalid attempts, cost
    (charged, list price), output tokens, wall seconds, whether one never started, last line."""
    by = {}
    for line in iter_lines(path):
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if not isinstance(e, dict):
            continue
        ts = parse_ts(e.get("ts"))
        if since is not None and ts is not None and ts < since - SLACK:
            continue
        s = by.setdefault(e.get("id"), {"attempts": 0, "invalid": 0, "cost": None, "tokens": None,
                                        "total": None, "wall": None, "last": None, "not_started": False})
        s["last"] = e
        if e.get("event") == "not_started":
            s["not_started"] = True
        if e.get("event") != "attempt":
            continue
        s["attempts"] += 1
        if e.get("valid") is not True:
            s["invalid"] += 1
        c = e.get("charged_usd", e.get("cost_usd"))
        if isinstance(c, (int, float)):
            s["cost"] = (s["cost"] or 0) + c
        t = e.get("output_tokens")
        if isinstance(t, int):
            s["tokens"] = (s["tokens"] or 0) + t
        # every token the attempt used, as the Workflow view's "tok" counts them: output plus the
        # cache writes and reads (cleanrun records no uncached input; with caching it is a few)
        parts = [v for v in (t, e.get("cache_write"), e.get("cache_read")) if isinstance(v, int)]
        if parts:
            s["total"] = (s["total"] or 0) + sum(parts)
        w = e.get("wall_s")
        if isinstance(w, (int, float)):
            s["wall"] = (s["wall"] or 0) + w
    return by


def final_failure(last):
    """True when cleanrun will not retry this task (cleanrun.py judge(): interrupted, or the
    per-run budget reached), so a live run's task with this last line has failed already."""
    if not last or last.get("event") != "attempt" or last.get("valid") is not False:
        return False
    first = str((last.get("problems") or [""])[0])
    return first == "interrupted" or first.startswith("per-run budget reached")


def problem_of(last):
    """One line saying why a call failed, from its last ledger line."""
    if not last:
        return None
    if last.get("event") == "not_started":
        return str(last.get("error") or "not started")[:200]
    problems = last.get("problems") or []
    if problems:
        return str(problems[0])[:200]
    if last.get("event") == "attempt" and last.get("valid") is False:
        return "output did not validate"
    return None


def agent_row(aid, label, phase, state, model=None, effort=None, elapsed=None, stats=None, error=None,
              resumed=False):
    stats = stats or {}
    return {"id": aid, "label": label, "phase": phase, "state": state, "model": model or None,
            "effort": effort, "elapsed_s": round(elapsed) if isinstance(elapsed, (int, float)) else None,
            "out_tokens": stats.get("tokens"), "tokens": stats.get("total"),
            "cost_usd": round(stats["cost"], 4) if stats.get("cost") is not None else None,
            "attempts": stats.get("attempts", 0), "error": error, "resumed": resumed}


def counts_of(agents):
    c = {"total": len(agents), "done": 0, "running": 0, "queued": 0, "failed": 0, "skipped": 0}
    for a in agents:
        st = a["state"]
        if st == "done":
            c["done"] += 1
        elif st == "running":
            c["running"] += 1
        elif st in ("queued", "pending"):
            c["queued"] += 1
        elif st in ("failed", "died"):
            c["failed"] += 1
        elif st == "skipped":
            c["skipped"] += 1
    return c


def row_tokens(agents):
    known = [a["tokens"] for a in agents if a.get("tokens") is not None]
    return sum(known) if known else None


def row_cost(agents):
    known = [a["cost_usd"] for a in agents if a["cost_usd"] is not None]
    return round(sum(known), 4) if known else None


def read_log(path):
    """log.txt, scoped to the last run in it: each `start` line clears what came before.
    Per label its last done/FAIL event, warnings, whether that run finished or wrote its cost,
    the script name, the start line's time of day (UTC seconds), and the last message."""
    log = {"events": {}, "warnings": [], "last": None, "script": None, "finished": False,
           "cost_written": False, "start_tod": None, "starts": 0}
    for line in iter_lines(path):
        m = LOG_LINE.match(line)
        if not m:
            continue
        msg = m.group(4)
        log["last"] = msg[:200]
        if msg.startswith("start "):
            log.update(events={}, warnings=[], finished=False, cost_written=False,
                       script=msg[6:].split(" ", 1)[0],
                       start_tod=int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3)))
            log["starts"] += 1
            continue
        d = DONE_LINE.match(msg)
        if d:
            log["events"][d.group(1)] = ("done", int(d.group(2)))
        elif msg.startswith("FAIL ") and FAIL_SEP in msg:
            label, _, why = msg[5:].partition(FAIL_SEP)
            log["events"][label] = ("fail", "cleanrun exit " + why.split(":", 1)[0].strip())
        elif " dropped: " in msg:
            log["warnings"].append(msg[:200])
        elif msg.startswith("cost (list price"):
            log["cost_written"] = True
        elif msg.startswith("finished in "):
            log["finished"] = True
    log["warnings"] = log["warnings"][-3:]
    return log


def run_start_of(log, log_path):
    """Epoch seconds of the last `start` line: its UTC time of day on the day log.txt was last
    written, a day earlier when that would put it after the log's last write (a midnight crossing)."""
    if log["start_tod"] is None:
        return None
    end = mtime(log_path)
    if end is None:
        return None
    start = (end // 86400) * 86400 + log["start_tod"]
    if start > end + 60:
        start -= 86400
    return start


def fail_reason(calldir, cdir, summ, led, ev):
    """Why a runtime call failed: cleanrun's stderr, the summary's stop reason, the ledger."""
    err = last_line(os.path.join(calldir, "stderr.txt")) if fresh(mtime(os.path.join(calldir, "stderr.txt")),
                                                                     mtime(os.path.join(calldir, "tasks.jsonl"))) else None
    if err:
        return err
    if summ and summ.get("stopped"):
        return str(summ["stopped"])[:200]
    return problem_of(led.get("last")) or ev[1]


def scan_runtime(out, node, cleanruns, now):
    """One clean_runtime.mjs fan-out. `node`: its process or None; `cleanruns`: out-dir -> process."""
    problems = []
    log_path = os.path.join(out, "log.txt")
    jpath = os.path.join(out, "journal.jsonl")
    log = read_log(log_path)
    alive = node is not None
    run_start = now - node["etime"] if alive else run_start_of(log, log_path)
    latest, order = {}, []   # label -> its last started line; labels in first-seen order
    for line in iter_lines(jpath):
        if STARTED_LINE.match(line):
            try:
                e = json.loads(line)
            except ValueError:
                continue
            label = e.get("label") or "agent"
            if label not in latest:
                order.append(label)
            latest[label] = e
    # this run's labels: clean_runtime rewrites calls/<id>/tasks.jsonl each time agent() is called
    current, task_times = [], {}
    for label in order:
        t = mtime(os.path.join(out, "calls", call_id(label), "tasks.jsonl"))
        if t is not None and not fresh(t, run_start):
            continue
        current.append(label)
        task_times[label] = t
    by_id = {}
    for label in current:
        by_id.setdefault(call_id(label), []).append(label)
    for cid, labels in by_id.items():
        if len(labels) > 1:
            problems.append(f"labels {', '.join(labels)} share calls/{cid}: they ran as one call")
    agents, touched = [], []
    shared = None   # a folder whose calls/ was consolidated keeps one OUT/ledger.jsonl keyed by call id
    for label in current:
        e = latest[label]
        cid = call_id(label)
        calldir = os.path.join(out, "calls", cid)
        cdir = os.path.join(calldir, "out")
        since = task_times[label] if task_times[label] is not None else run_start
        proc = cleanruns.get(cdir)
        spath = os.path.join(cdir, "summary.json")
        summ = read_json(spath) if fresh(mtime(spath), since) else None
        lpath = os.path.join(cdir, "ledger.jsonl")
        if os.path.exists(lpath):
            led = ledger(lpath, since).get(cid, {})
        else:
            if shared is None:
                shared = ledger(os.path.join(out, "ledger.jsonl"), run_start)
            led = shared.get(cid, {})
        opath = os.path.join(cdir, "outputs", cid + ".json")
        has_output = os.path.exists(opath) and fresh(mtime(opath), since)
        touched += [mtime(spath), mtime(os.path.join(cdir, "ledger.jsonl"))]
        ev = log["events"].get(label)
        others = [x for x in by_id[cid] if x != label]
        model = (summ or {}).get("model")
        effort = (summ or {}).get("effort")
        elapsed, error, resumed, stats = led.get("wall"), None, False, led
        if others and ev and ev[0] == "fail":
            state, error, elapsed, stats = "failed", f"shares calls/{cid} with {others[0]}", None, None
        elif proc is not None:
            state, elapsed = "running", proc["etime"]
            model = flag(proc["argv"], "--model") or model
            effort = flag(proc["argv"], "--effort") or effort
        elif ev and ev[0] == "fail":
            state, error = "failed", fail_reason(calldir, cdir, summ, led, ev)
        elif (ev and ev[0] == "done") or has_output:
            state = "done"
            resumed = led.get("attempts", 0) == 0
            if elapsed is None and ev and ev[0] == "done" and not resumed:
                elapsed = ev[1]
        elif summ and summ.get("state") in FINAL_STATES:
            state = "failed"
            error = str(summ.get("stopped") or "")[:200] or problem_of(led.get("last")) or f"cleanrun {summ.get('state')}"
        elif summ:   # this call's 'running' placeholder with no process behind it
            state = "running" if alive else "died"
            if not alive:
                error = "its process is gone"
        else:
            state = "queued" if alive else "skipped"
        if others and by_id[cid][0] != label:
            stats, elapsed = None, None   # the folder's numbers are counted once, on its first label
        agents.append(agent_row(cid, label, e.get("phase"), state, model, effort, elapsed, stats, error, resumed))

    if alive:
        state = "running"
    elif log["starts"]:
        if log["finished"]:
            state = "done"
        elif log["cost_written"]:
            state = "failed"
            problems.append("the script stopped with an error (its cost line is written, no 'finished' line)")
        else:
            state = "died"
            problems.append("no process, and the last run never finished")
    elif os.path.exists(os.path.join(out, "result.json")):
        state = "done"
    elif os.path.exists(os.path.join(out, "cost.json")):
        state = "failed"
        problems.append("the script stopped with an error (cost.json but no result.json)")
    else:
        state = "died"
        problems.append("no process and no result.json")
    if not alive and any(a["state"] == "running" for a in agents):
        problems.append("calls still running with no runtime process to record them")
    started = run_start if run_start is not None else born(log_path) or born(jpath)
    if alive:
        ended = None
    elif state == "done":
        rp = mtime(os.path.join(out, "result.json"))
        ended = rp if fresh(rp, run_start) else mtime(log_path)
    else:
        ended = newest(mtime(log_path), mtime(jpath), *touched)
    script = runtime_script(node["argv"]) if node is not None else None
    script = os.path.basename(script) if script else log["script"]
    phases = []
    for a in agents:
        if a["phase"] and a["phase"] not in phases:
            phases.append(a["phase"])
    jobs = flag(node["argv"], "--jobs") if node else None
    return {"id": out, "kind": "runtime", "name": os.path.basename(out), "dir": out, "script": script,
            "pid": node["pid"] if node else None, "alive": alive, "state": state,
            "started_at": started, "ended_at": ended,
            "elapsed_s": round(max(0, (ended or now) - started)) if started else None,
            "jobs": int(jobs) if jobs and jobs.isdigit() else None,
            "phases": phases, "agents": agents, "counts": counts_of(agents), "cost_usd": row_cost(agents),
            "tokens": row_tokens(agents),
            "last_log": log["last"], "warnings": log["warnings"], "problems": problems}


def task_ids(path):
    ids = []
    for line in iter_lines(path):
        try:
            tid = json.loads(line).get("id")
        except (ValueError, AttributeError):
            continue
        if tid is not None and tid not in ids:
            ids.append(tid)
    return ids


def scan_cleanrun(out, proc, running, tasks_path, now):
    """One standalone cleanrun.py out-dir. `proc`: its process or None; `running`: live claude -p children."""
    problems = []
    alive = proc is not None
    lock = os.path.join(out, ".lock")
    lpath = os.path.join(out, "ledger.jsonl")
    spath = os.path.join(out, "summary.json")
    start = now - proc["etime"] if alive else (mtime(lock) or born(lpath))
    summ = (read_json(spath) or {}) if fresh(mtime(spath), start) else {}
    led = ledger(lpath, start)
    ids = task_ids(tasks_path) if tasks_path else []
    odir = os.path.join(out, "outputs")
    try:
        names = [n for n in os.listdir(odir) if n.endswith(".json")]
    except OSError:
        names = []
    # an output written in this invocation is done; an older one is done only if the task was
    # resumed (no attempt now): with attempts now, it is the stale answer to an older prompt
    fresh_ids = {n[:-5] for n in names if fresh(mtime(os.path.join(odir, n)), start)}
    old_ids = {n[:-5] for n in names} - fresh_ids
    done_ids = fresh_ids | {t for t in old_ids if led.get(t, {}).get("attempts", 0) == 0}
    failed = {f.get("id"): f for f in summ.get("failed", []) + summ.get("crashed", []) if isinstance(f, dict)}
    not_run = {f.get("id"): f for f in summ.get("not_run", []) if isinstance(f, dict)}
    final = summ.get("state") in FINAL_STATES
    evidence = [t for t in list(led) + sorted(fresh_ids) + list(failed) + sorted(not_run, key=str) if t is not None]
    for tid in evidence:
        if tid not in ids:
            ids.append(tid)
    # resumed tasks leave no trace but their old output; without the tasks file, take as many of
    # those as the summary says were requested, so a reused out-dir's older outputs do not count
    requested = summ.get("requested") if final else None
    for tid in sorted(old_ids & done_ids):
        if tid in ids:
            continue
        if tasks_path is None and isinstance(requested, int) and len(ids) >= requested:
            break
        ids.append(tid)
    retries = flag(proc["argv"], "--retries") if alive else None
    retries = int(retries) if retries and retries.isdigit() else 1
    model = flag(proc["argv"], "--model") if alive else summ.get("model")
    effort = flag(proc["argv"], "--effort") if alive else summ.get("effort")
    agents = []
    for tid in ids:
        s = led.get(tid, {})
        error, resumed = None, False
        if tid in done_ids:
            state, resumed = "done", s.get("attempts", 0) == 0
        elif tid in failed:
            state = "failed"
            ps_ = failed[tid].get("problems") or []
            error = str(ps_[0])[:200] if ps_ else problem_of(s.get("last"))
        elif alive and (s.get("not_started") or s.get("invalid", 0) >= retries + 1 or final_failure(s.get("last"))):
            state, error = "failed", problem_of(s.get("last"))   # out of attempts, or not retried, mid-run
        elif alive:
            state = "pending"   # waiting for a slot or running: cleanrun does not say which
        elif final and tid in not_run:
            ps_ = not_run[tid].get("problems") or []
            state, error = "skipped", (str(ps_[0])[:200] if ps_ else None)
        elif final:
            state, error = "failed", problem_of(s.get("last"))
        else:
            state, error = "died", "its process is gone"
        agents.append(agent_row(str(tid), str(tid), None, state, model, effort, s.get("wall"), s, error, resumed))
    counts = counts_of(agents)
    if alive:
        counts["running"] = running
        counts["queued"] = max(0, counts["queued"] - running)
        state = "running"
    elif summ.get("state") == "finished":
        state = "done"
    elif summ.get("state") in ("stopped", "interrupted"):
        state = "stopped"
        problems.append(str(summ.get("stopped") or summ.get("state"))[:200])
    else:
        state = "died"
        problems.append("no process and no final summary.json")
    if alive:
        ended = None
    else:
        ended = newest(mtime(spath), mtime(lpath), mtime(lock), *[mtime(os.path.join(odir, n)) for n in names])
    if final and isinstance(summ.get("charged_usd"), (int, float)):
        cost = round(summ["charged_usd"], 4)
    else:
        cost = row_cost(agents)
    base = os.path.basename(out)
    name = os.path.basename(os.path.dirname(out)) + "/" + base if base in ("out", "output", "outputs") else base
    jobs = flag(proc["argv"], "--jobs") if proc else None
    return {"id": out, "kind": "cleanrun", "name": name, "dir": out, "script": None,
            "pid": proc["pid"] if proc else None, "alive": alive, "state": state,
            "started_at": start, "ended_at": ended,
            "elapsed_s": round(max(0, (ended or now) - start)) if start else None,
            "jobs": int(jobs) if jobs and jobs.isdigit() else None,
            "phases": [], "agents": agents, "counts": counts, "cost_usd": cost, "tokens": row_tokens(agents),
            "last_log": None, "warnings": [], "problems": problems, "tasks": tasks_path}


def runtime_dir_of(out_dir):
    """OUT for a cleanrun out-dir shaped OUT/calls/<id>/out when OUT holds a journal, else None."""
    parts = out_dir.rstrip("/").split("/")
    if len(parts) >= 4 and parts[-1] == "out" and parts[-3] == "calls":
        root = "/".join(parts[:-3])
        if os.path.exists(os.path.join(root, "journal.jsonl")) or os.path.exists(os.path.join(root, "log.txt")):
            return root
    return None


def broken(fid, kind, exc):
    return {"id": fid, "kind": kind, "name": os.path.basename(fid), "dir": fid, "state": "unknown",
            "alive": None, "agents": [], "problems": [f"scan failed: {exc!r}"[:200]]}


def scan(procs, known_dirs, resolver, now, owner=None):
    """owner: the claude pid whose runs to list; None lists every run on the machine."""
    below = None if owner is None else descendants(procs, owner)

    def mine(p, out=None):
        if below is None or p["pid"] in below:
            return True
        return out is not None and recorded_owner(out) == owner

    runtimes = {}       # OUT -> node process (None for a dead runtime that still has calls running)
    runtime_pids = {}
    cleanruns = {}      # out-dir -> cleanrun process
    children = {}       # cleanrun pid -> live claude -p children
    unresolved = []     # relative paths of fan-out processes whose cwd could not be read
    for p in procs:
        if is_claude_print(p["argv"]):
            children[p["ppid"]] = children.get(p["ppid"], 0) + 1
    for p in procs:
        if is_cleanrun(p["argv"]):
            out = flag_path(resolver, p, "--out-dir")
            if out:
                if mine(p, out):
                    cleanruns[out] = p
            elif mine(p):
                unresolved.append(" ".join(flag_tokens(p["argv"], "--out-dir")))
    calling = {c["ppid"] for c in cleanruns.values()}      # a runtime that lost its parent has no record of its
    for p in procs:                                         # own: it is the chat's when one of its calls is
        if runtime_script(p["argv"]) is not None:
            if not (mine(p) or p["pid"] in calling):
                continue
            out = flag_path(resolver, p, "--out")
            if out:
                runtimes[out] = p
                runtime_pids[p["pid"]] = out
            else:
                unresolved.append(" ".join(flag_tokens(p["argv"], "--out")))
    fanouts, seen = [], set()
    # a runtime's calls: children of a live runtime, or cleanruns orphaned under a dead runtime's OUT
    for out_dir, p in cleanruns.items():
        root = runtime_pids.get(p["ppid"]) or runtime_dir_of(out_dir)
        if root and root not in runtimes:
            runtimes[root] = None
    for out, node in runtimes.items():
        try:
            fanouts.append(scan_runtime(out, node, cleanruns, now))
        except Exception as exc:   # one broken run must not hide the others
            fanouts.append(broken(out, "runtime", exc))
        seen.add(out)
    for out, p in cleanruns.items():
        if runtime_pids.get(p["ppid"]) or runtime_dir_of(out):
            continue
        try:
            tasks = flag_path(resolver, p, "--tasks", exists=os.path.isfile)
            fanouts.append(scan_cleanrun(out, p, children.get(p["pid"], 0), tasks, now))
        except Exception as exc:
            fanouts.append(broken(out, "cleanrun", exc))
        seen.add(out)
    for d in known_dirs:
        d = os.path.normpath(d)
        if d in seen or not os.path.isdir(d):
            continue
        if owner is not None and recorded_owner(d) not in (None, owner):
            continue      # another chat's run: this folder reached us through a table that listed every chat's
        seen.add(d)
        held = [r for r in unresolved if r and (d.endswith("/" + os.path.normpath(r))
                                                 or os.path.normpath(r) == "." or os.path.normpath(r).startswith(".."))]
        if held:   # a live process may hold it; without its cwd that cannot be told, so do not call it dead
            fanouts.append({"id": d, "kind": "unknown", "name": os.path.basename(d), "dir": d, "state": "unknown",
                            "alive": None, "agents": [],
                            "problems": ["a running process names this folder but its working directory could not be read"]})
            continue
        try:
            if os.path.exists(os.path.join(d, "journal.jsonl")) or os.path.exists(os.path.join(d, "log.txt")):
                fanouts.append(scan_runtime(d, None, cleanruns, now))
            elif os.path.exists(os.path.join(d, "summary.json")):
                fanouts.append(scan_cleanrun(d, None, 0, None, now))
        except Exception as exc:
            fanouts.append(broken(d, "unknown", exc))
    fanouts.sort(key=lambda f: (f.get("state") != "running", -(f.get("started_at") or 0)))
    return fanouts, unresolved


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    dirs, cwds, problems = [], {}, []
    owner, every = None, False
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("--dir", "--cwd", "--owner") and i + 1 < len(argv):
            v = argv[i + 1]
            if a == "--dir":
                dirs.append(v)
            elif a == "--owner":
                if v.isdigit():
                    owner = int(v)
                else:
                    problems.append(f"--owner needs a pid, not {v!r}")
            else:
                pid, _, cwd = v.partition("=")
                if pid.isdigit() and cwd:
                    cwds[int(pid)] = cwd
            i += 2
        elif a == "--all":
            every = True
            i += 1
        else:
            problems.append(f"unknown argument {a!r}")
            i += 1
    now = time.time()
    degraded = False
    try:
        ran = subprocess.run(["ps", "-axww", "-o", "pid=,ppid=,etime=,command="],
                             capture_output=True, text=True, timeout=10)
        procs = parse_ps(ran.stdout)
        # a real table always lists at least ps itself and this scanner
        if ran.returncode != 0 or not procs:
            procs, degraded = [], True
            problems.append(f"ps failed: exit {ran.returncode}: {(ran.stderr or '').strip()}"[:200])
    except (OSError, subprocess.SubprocessError) as exc:
        procs, degraded = [], True
        problems.append(f"ps failed: {exc!r}"[:200])
    if every:
        owner = None
    elif owner is None:
        owner = chat_pid(procs, os.getppid())
    resolver = Resolver(cwds)
    fanouts, unresolved = scan(procs, dirs, resolver, now, owner)
    if unresolved:
        problems.append(f"could not read the working directory of {len(unresolved)} fan-out process(es)")
    live = {str(p["pid"]) for p in procs}
    snapshot = {"v": V, "now": now, "platform": sys.platform, "degraded": degraded, "owner": owner, "fanouts": fanouts,
                "cwds": {str(k): v for k, v in resolver.cwds.items() if str(k) in live},
                "problems": problems}
    sys.stdout.write(json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
