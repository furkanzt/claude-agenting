#!/usr/bin/env python3
"""
cleanrun.py -- run a fan-out of similar, self-contained tasks as clean `claude -p`
processes instead of Workflow agents.

WHY THIS EXISTS
---------------
A Workflow agent starts with the whole harness context (system prompt, CLAUDE.md
files, skill listing, tool list) and inherits the advisor. For many small,
independent tasks that start-up cost dominates. On one measured pipeline (KC grade 7,
Opus 5.5 at xhigh, 2026-10-08) clean runs cost 63% less per task at list price with
no quality loss (evals/research/2026-10-07-launch-cost.md). The usage-window effect
was not measurable on a shared account; every saving here is a list-price saving.

USE IT WHEN every task is self-contained (its files plus one prompt), needs no
session context and no tools beyond Read, does not coordinate with other tasks, and
its output can be checked in code. Otherwise use a Workflow.

USAGE
  cleanrun.py run    --tasks T.jsonl --system-prompt RULES.md --schema S.json \
                     --model claude-opus-5-5 --effort xhigh --out-dir DIR [options]
  cleanrun.py plan   (same arguments)   what would run or resume, and the cost bound
  cleanrun.py status --out-dir DIR      the last run's summary and the ledger totals

  Tasks file (UTF-8): one JSON object per line, {"id": "...", "prompt": "...",
  "files": [...]}. `files` (optional) are copied into the task's own empty working
  directory (the kit), which is all the run can see (--restricted). Relative paths
  resolve against the tasks file. Ids must differ even ignoring case.
  - A string entry is copied flat, under the base name of the file it resolves to (a
    symlink takes its target's name); two string entries may not share a base name.
  - An object entry {"path": "...", "as": "sub/dir/name.pdf"} is copied to that path
    inside the kit, whatever the source is called, and its directories are created
    there. "as" is relative, uses '/', has no empty, '.' or '..' segment, no backslash
    or NUL, at most 512 bytes in UTF-8 and 255 per segment, no lone surrogate, no
    '..namedfork' segment and no code point unassigned in this Python's Unicode tables
    (a disk follows a newer Unicode: it folds such letters into one name or refuses
    them). An object entry's kit path may not equal another entry's ignoring case, nor
    be a file where another entry needs a directory ("a" and "a/b"). Each refusal is
    a usage error before any launch, for plan as well as run. A kit that still cannot
    be built at run time (a full disk, the disk's own rules) fails that one task, with
    nothing launched and nothing spent, and the other tasks go on.
  - The validator's task lists each file by its kit path. The run key holds each
    file's kit path and content, so "as" with no directory ("x.md") keys exactly
    like the string entry "x.md", and changing "as" reruns the task.
  The system prompt file is sent byte for byte (--system-prompt-file); keep the
  stable rules there and the per-task data in the prompt, so runs that follow each
  other share a cached prefix. The schema must be a JSON Schema object.

  Options: --tools "" (default, none) or e.g. Read; --allowed-tools LIST (default none,
  see PERMISSIONS); --also-models LIST (default none, see MODEL CHECK); --validator
  FILE.py (a module with validate(output, task) -> list of problem strings; task carries
  id, prompt and the files' kit paths); --jobs 4; --max-usd X;
  --per-run-usd 2.5; --timeout 1800 (seconds per attempt); --retries 1; --usage-check
  "CMD" (opt-in, see below); --claude-bin PATH (else $CLEANRUN_CLAUDE_BIN, else `claude`).

PERMISSIONS (--allowed-tools)
  `claude -p` cannot ask, so a tool in --tools that needs permission (WebSearch,
  WebFetch, Bash and others) is denied. --allowed-tools LIST, spelled like --tools
  (comma separated, e.g. "WebSearch,WebFetch"), is passed to claude as its
  --allowed-tools flag and grants that permission up front.
  - Default empty: no flag is passed and the claude command line is unchanged.
  - Every name in LIST (the text before the opening parenthesis of a pattern such as
    "Bash(git status:*)") must also be in --tools, else it is a usage error before
    any launch, for plan as well as run. A comma or space inside parentheses belongs
    to the pattern. Nested parentheses and text after an entry's closing parenthesis
    are refused: claude splits such a list differently from how it reads, so the
    list that was checked would not be the list it grants.
  - --tools must name each tool explicitly while LIST is used: "default" (claude's whole
    default set) and an exclusion such as "!WebFetch" are refused, because claude would
    read the grant against a tool set cleanrun cannot see.
  - A non-empty LIST is part of the resume key, because it changes what a run may do:
    changing it reruns finished tasks, while the same entries in another order or
    repeated do not. With none given the key is what it was before this option existed,
    so finished out-dirs keep resuming.
  - What it does NOT solve: it grants permission only. A run that calls WebFetch still
    has a second model (a Haiku summariser) in modelUsage, and the model check still
    rejects that run as a model mismatch unless --also-models lists that model (see
    MODEL CHECK). This flag alone does not make a web stage pass.

MODEL CHECK (--also-models)
  By default a run is valid only when the models in claude's modelUsage are exactly
  [--model]. A tool that calls a helper model of its own (WebFetch runs a small Haiku
  summariser) adds a second model, so such a run is rejected even when the routed model
  answered. --also-models LIST (comma separated full model ids, spaces around a comma
  ignored, aliases refused as for --model, a usage error before any launch for plan as
  well as run) loosens that: the run passes when --model is among the observed models
  and every other observed model is on LIST. An id with a space inside it (a list
  separated by spaces) and --model spelled in another case are refused the same way:
  neither names a model a run could report, so the first would only pay for runs that
  fail and the second would only change the key and rerun finished tasks. So is any id
  not written as claude reports it (lower-case letters, digits, '.' and '-', with a
  version number): a ';' list, a partial id, an upper-case or look-alike spelling.
  While it is in force the plan and start lines say so, and summary.json and each saved
  output carry "also_models"; without it none of them mentions it.
  - This is a weaker check than the default. modelUsage says which models were called,
    not which one wrote the final answer, so a pass is evidence that the routed model
    answered, not proof. A run without --model in modelUsage is still rejected, whatever
    else is there; a model not on LIST is rejected and named.
  - It exists for tools that call a helper model, and is meant to be used together with
    --allowed-tools for web stages. Nothing here was verified against a real WebFetch
    run (the tests use a stub claude). A web stage reads untrusted pages, and the kit
    sandbox does not constrain what the run fetches or what those pages say.
  - Default empty: the exact check, the claude command line and the run key are what
    they were before this option existed. A repeat, or --model itself in LIST, changes
    nothing: LIST is kept as a sorted set without --model, so naming only --model is the
    default. A non-empty set is part of the resume key, so a changed set reruns finished
    tasks, while the same ids reordered or repeated do not.

MONEY (list price)
  - --per-run-usd is passed to claude as --max-budget-usd. It is a SOFT cap: claude
    stops a run after the turn that crosses it, so one run can cost more. A run that
    hits it is not retried (the same prompt would hit it again).
  - --max-usd stops NEW launches once that much is charged in this invocation;
    running attempts finish. Worst-case overshoot is about min(jobs, tasks) x
    --per-run-usd, more if claude overruns its soft cap. A resumed run starts its
    count at zero.
  - A run whose cost is unknown (killed, unparseable) is charged --per-run-usd,
    never as free. A launch that never started is charged nothing.

GUARANTEES
  - Routing is explicit: a full model id (aliases are refused) and an effort, given
    on the command line, never read from a project default. By default the models in
    modelUsage must be exactly that id, or the run is invalid. The one opt-in exception
    is --also-models (see MODEL CHECK): the id must still be there and every other
    model must be listed. The summary lists every model observed, helpers included.
  - Each `claude` runs in its own process group with its output in files, not pipes.
    On timeout the group is killed. On Ctrl-C, SIGTERM, SIGHUP or SIGQUIT every
    running group is killed, nothing new launches and the summary is written; a
    second signal, or a worker that does not finish within 30 s, forces the exit.
  - A crash inside a task stops new launches and is reported (exit 3); the summary
    is written on every exit path.
  - One exclusive lock per output directory; atomic writes; every attempt is
    appended to ledger.jsonl.
  - Resume: a finished task is skipped only if its key (model, effort, tools,
    allowed tools and also-models when given, system prompt, schema, prompt, file
    contents, validator source) is unchanged AND
    its saved output still passes the validator.
  - Input files are hashed in 1 MiB chunks, so a large file costs a megabyte of memory
    and not its own size. They are hashed again for every task and every key, never
    remembered between calls and never cached on disk: a remembered digest can outlive
    a change the file system does not show (a rewrite with the mtime put back), and the
    key would then describe bytes the task was not given. An 80 MB file hashes in about
    40 ms, so the repetition costs seconds across a large fan-out.
  - --usage-check CMD (opt-in): before launches, at most once per 60 s, CMD is run;
    exit 0 = room in the usage window, 2 = window full, anything else = cannot
    tell. "Cannot tell" is retried twice with a backoff, then stops the run as
    "unreadable", distinct from "window full". A real reading is shared for 60 s
    with every other cleanrun process using the same CMD ($CLEANRUN_USAGE_CACHE, else
    a file in the temp dir), because usage endpoints refuse frequent calls.

EXIT CODES  0 all tasks done · 1 some failed · 2 usage error, lock held, or stopped by
--max-usd, the usage check or a claude that cannot start · 3 a task crashed ·
130 interrupted.
"""
import argparse
import fcntl
import hashlib
import importlib.util
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
import time
import unicodedata
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

KEY_VERSION = 2
ALIASES = {"haiku", "sonnet", "opus", "fable", "best", "default", "opusplan"}
EFFORTS = ("low", "medium", "high", "xhigh", "max")
TASK_ID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
FLAGS = ["--restricted", "--strict-mcp-config", "--no-session-persistence", "--disable-slash-commands",
         "--output-format", "json"]
GATE_CACHE_S = 60
MAX_SCHEMA_BYTES = 100_000
# 255 bytes is a file name's limit on APFS and ext4; the total leaves the kit's own temp-dir path room
# under macOS's 1024-byte PATH_MAX, so a path that loads cannot fail the copy and crash the run
MAX_KIT_PATH_BYTES, MAX_NAME_BYTES = 512, 255
BUDGET_SUBTYPE = "error_max_budget_usd"
SIGNALS = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP, signal.SIGQUIT)


class UsageError(Exception):
    pass


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


HASH_CHUNK = 1 << 20


def file_sha(path):
    """sha256 of a file's bytes, the same hex as sha(path.read_bytes()), read in chunks so a large
    input costs a megabyte of memory and not its own size. Deliberately not remembered between calls:
    a digest trusted later, by size and mtime, can describe bytes the file no longer holds (a rewrite
    with the mtime put back, a write through a shared mapping), and the run key must describe the
    bytes a task is given."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(HASH_CHUNK):
            h.update(chunk)
    return h.hexdigest()


def sha(data):
    if isinstance(data, str):
        data = data.encode("utf-8")
    elif not isinstance(data, bytes):
        data = json.dumps(data, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def write_atomic(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            if isinstance(obj, bytes):
                f.buffer.write(obj)
            else:
                json.dump(obj, f, ensure_ascii=True, indent=1)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def kill_group(proc):
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


def read_utf8(path, what):
    try:
        return Path(path).read_bytes().decode("utf-8")
    except FileNotFoundError:
        raise UsageError(f"no {what} file: {path}")
    except IsADirectoryError:
        raise UsageError(f"{what} is a directory, not a file: {path}")
    except UnicodeDecodeError as e:
        raise UsageError(f"{what} file is not UTF-8 ({path}): {e}")
    except OSError as e:
        raise UsageError(f"cannot read {what} file {path}: {e}")


def finite_positive(text):
    value = float(text)
    if not math.isfinite(value) or value <= 0:
        raise argparse.ArgumentTypeError("must be a finite number above 0")
    return value


# ------------------------------------------------------------------ inputs


def check_model_id(model, flag):
    if not model or model.lower() in ALIASES or not model.startswith("claude-"):
        raise UsageError(f"{flag} must be a full model id such as claude-opus-5-5, not {model!r} "
                         "(an alias silently moves to a newer model)")


def check_routing(model, effort):
    check_model_id(model, "--model")
    if effort not in EFFORTS:
        raise UsageError(f"--effort must be one of {', '.join(EFFORTS)}")


# a model id as claude reports it in modelUsage: lower-case ASCII with a version number. Anything
# else (a ';' list, a partial id, a zero-width or fullwidth look-alike, another case) can never match
# an observed model, so a run using it would be paid for and rejected
REPORTED_ID = re.compile(r"claude-[a-z0-9.-]*[0-9][a-z0-9.-]*")


def check_also_models(text, model):
    """The --also-models ids as a sorted list without repeats and without --model itself, [] for none.
    Listing only the routed model therefore keeps the exact check and the key it always had."""
    ids = [m.strip() for m in text.split(",") if m.strip()]
    for m in ids:
        check_model_id(m, "--also-models")
        # both pass the id check yet name no model a run reports: a space-separated list reads as one
        # id, so every helper run is paid and rejected, and --model in another case admits nothing
        # while it changes the key, so every finished task reruns
        if any(ch.isspace() for ch in m):
            raise UsageError(f"--also-models separates ids with a comma, and a model id has no space: {m!r}")
        if m != model and m.lower() == model.lower():
            raise UsageError(f"--also-models names --model {model!r} in another case: {m!r}")
        if not REPORTED_ID.fullmatch(m):
            raise UsageError(f"--also-models ids are written as claude reports them (lower-case letters, digits, '.' "
                             f"and '-', with a version number, such as claude-haiku-4-5-20251001): {m!r}")
    return sorted(set(ids) - {model})


def model_problem(observed, model, also):
    """Why the models in modelUsage do not fit the routing, or None. Without --also-models the
    answer must come from exactly the routed model, as it always has; with it, the routed model
    must still be there and every other model must be on the list."""
    base = f"model mismatch: answered by {observed}, routed to {model}"
    if not also:
        return None if observed == [model] else base
    why = []
    if model not in observed:       # a listed helper never stands in for the model the task was routed to
        why.append(f"{model} is not among them")
    extra = [m for m in observed if m != model and m not in also]
    if extra:
        why.append(f"not on --also-models: {', '.join(extra)}")
    return f"{base} ({'; '.join(why)})" if why else None


def tool_entries(text, flag):
    """The entries of a tool list, split the way claude splits its own: only a comma or a space
    separates, except inside parentheses, where both belong to a pattern such as Bash(git status:*).
    claude tracks 'inside' with one flag, so a nested '(' or text after an entry's ')' would be cut
    differently there than a depth count would cut it. Those are refused here rather than copied,
    so the list that was checked is the list claude grants."""
    entries, cur, inside, closed = [], "", False, False
    for ch in text:
        if inside:
            if ch == "(":
                raise UsageError(f"{flag} has a '(' inside parentheses, which claude would split differently: {text!r}")
            if ch == ")":
                inside, closed = False, True
            cur += ch
        elif ch in ", ":
            if cur:
                entries.append(cur)
            cur, closed = "", False
        elif ch == ")":
            raise UsageError(f"{flag} has a ')' with no '(': {text!r}")
        elif closed:
            raise UsageError(f"{flag} has text after the ')' that ends an entry; separate entries with a comma: {text!r}")
        else:
            if ch == "(":
                inside = True
            cur += ch
    if inside:
        raise UsageError(f"{flag} has a '(' that is never closed: {text!r}")
    if cur:
        entries.append(cur)
    for e in entries:
        name = e.split("(", 1)[0]
        if not name:
            raise UsageError(f"{flag} has an entry with no tool name: {e!r}")
        if any(c.isspace() for c in name):
            raise UsageError(f"{flag} has a tool name with whitespace other than a plain space between entries: {e!r}")
    return entries


def check_allowed_tools(allowed, tools):
    """The normalised --allowed-tools string, '' for none. Every name must be offered by --tools:
    permission for a tool the run does not have would be a silent no-op."""
    entries = tool_entries(allowed, "--allowed-tools")
    if entries:
        listed = tool_entries(tools, "--tools")
        for e in listed:
            if e.startswith("!"):     # claude reads it as withholding the tool, so a grant for it would do nothing
                raise UsageError(f"--allowed-tools cannot be combined with an exclusion in --tools ({e!r}); "
                                 f"name the tools to give instead (--tools {tools!r})")
        offered = {e.split("(", 1)[0] for e in listed}
        for e in entries:
            name = e.split("(", 1)[0]
            if name not in offered:
                raise UsageError(f"--allowed-tools lists {name!r}, which --tools does not list "
                                 f"(--tools {tools!r}); a tool the run is not given cannot be allowed")
    return ",".join(entries)


def check_kit_path(rel, where):
    """An object entry's "as": a plain relative path that can only name a place inside the kit."""
    if not isinstance(rel, str) or not rel:
        raise UsageError(f"{where}: \"as\" must be a non-empty string")
    try:
        size = len(rel.encode("utf-8"))
    except UnicodeEncodeError:      # a lone surrogate is legal JSON but cannot be a file name
        raise UsageError(f"{where}: \"as\" is not valid Unicode text (a lone surrogate)")
    if size > MAX_KIT_PATH_BYTES:
        raise UsageError(f"{where}: \"as\" is longer than {MAX_KIT_PATH_BYTES} bytes")
    if "\x00" in rel or "\\" in rel:
        raise UsageError(f"{where}: \"as\" has a NUL or a backslash; separate directories with '/'")
    # A disk's name rules follow a newer Unicode than this Python's tables: it folds letters Python does
    # not know as one name (a silent overwrite inside the kit that KitPaths cannot see) and refuses others
    # outright (EILSEQ, after plan said the task could run). Every such case is an unassigned code point here.
    for ch in rel:
        if unicodedata.category(ch) == "Cn":
            raise UsageError(f"{where}: \"as\" has U+{ord(ch):04X}, which is unassigned in the Unicode "
                             f"{unicodedata.unidata_version} tables this Python knows; the disk may fold or refuse it")
    if rel.startswith("/"):
        raise UsageError(f"{where}: \"as\" must be relative to the kit, not an absolute path")
    for part in rel.split("/"):
        if part in ("", ".", ".."):
            raise UsageError(f"{where}: \"as\" has an empty, '.' or '..' segment (a double, leading or "
                             "trailing slash counts as empty)")
        if len(part.encode("utf-8")) > MAX_NAME_BYTES:
            raise UsageError(f"{where}: \"as\" has a segment longer than {MAX_NAME_BYTES} bytes")
        if part.casefold() == "..namedfork":      # APFS reads <file>/..namedfork/rsrc as a resource fork
            raise UsageError(f"{where}: \"as\" has a '..namedfork' segment, which a macOS disk reads as a fork, not a name")
    return rel


class KitPaths:
    """The kit paths of one task's files, compared the way a macOS disk compares names (ignoring case
    and Unicode normalisation), so no two entries land on one file and no file sits where another
    entry needs a directory. Two string entries keep their older rule (an exact base-name match only):
    a task file that loaded before object entries existed still loads."""

    def __init__(self, where):
        self.where = where
        self.files, self.dirs = {}, {}      # folded kit path -> (entry, is_object); folded directory -> entry

    def add(self, rel, is_object, entry):
        # Unicode's canonical caseless match: casefold can undo a normalisation (Greek letters with two
        # accents), so NFC before it alone misses names a macOS disk treats as one
        fold = lambda s: unicodedata.normalize("NFD", unicodedata.normalize("NFD", s).casefold())
        parts = rel.split("/")
        key = fold(rel)
        prefixes = [fold("/".join(parts[:i])) for i in range(1, len(parts))]
        other = self.files.get(key)
        if other and (is_object or other[1]):
            raise UsageError(f"{self.where}: files entry {entry} lands on the same kit path as {other[0]} "
                             "(kit paths must differ even ignoring case)")
        if key in self.dirs:
            raise UsageError(f"{self.where}: files entry {entry} would be a file where {self.dirs[key]} "
                             "needs a directory")
        for d in prefixes:
            if d in self.files:
                raise UsageError(f"{self.where}: files entry {entry} needs a directory where "
                                 f"{self.files[d][0]} is a file")
        self.files.setdefault(key, (entry, is_object))
        for d in prefixes:
            self.dirs.setdefault(d, entry)


def place(kit, rel):
    """Where a kit path is copied to, created inside the kit. load_tasks already refuses any path that
    could leave it; this check is the second line, because the kit is the model's whole sandbox."""
    root = Path(kit).resolve()
    dest = (root / rel).resolve()
    if dest == root or not dest.is_relative_to(root):
        raise RuntimeError(f"kit path {rel!r} resolves outside the kit")
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_dir():       # copy2 would write inside it, under the source's base name: not the declared path
        raise RuntimeError(f"kit path {rel!r} is already a directory in the kit")
    return dest


def load_tasks(path):
    path = Path(path)
    text = read_utf8(path, "tasks").lstrip("\ufeff")
    tasks, seen = [], {}
    for n, line in enumerate(text.split("\n"), 1):      # JSONL lines end at \n only, not at U+2028
        line = line.rstrip("\r")
        if not line.strip():
            continue
        try:
            t = json.loads(line)
        except ValueError as e:
            raise UsageError(f"{path.name}:{n}: not JSON ({e})")
        if not isinstance(t, dict):
            raise UsageError(f"{path.name}:{n}: each line must be a JSON object")
        tid, prompt = t.get("id"), t.get("prompt")
        if not isinstance(tid, str) or not TASK_ID.match(tid):
            raise UsageError(f"{path.name}:{n}: id must match {TASK_ID.pattern}")
        if tid.casefold() in seen:                      # outputs/<id>.json collide on case-insensitive disks
            raise UsageError(f"{path.name}:{n}: id {tid!r} repeats {seen[tid.casefold()]!r} (ids must differ ignoring case)")
        if not isinstance(prompt, str) or not prompt.strip():
            raise UsageError(f"{path.name}:{n}: {tid}: prompt must be a non-empty string")
        files = t.get("files") or []
        if not isinstance(files, list) or not all(isinstance(f, (str, dict)) for f in files):
            raise UsageError(f"{path.name}:{n}: {tid}: files must be a list of paths or {{\"path\": ..., \"as\": ...}} objects")
        placed, names, kit = [], set(), KitPaths(f"{path.name}:{n}: {tid}")
        for f in files:
            entry = json.dumps(f, ensure_ascii=True)
            if isinstance(f, dict):
                if set(f) != {"path", "as"} or not isinstance(f["path"], str) or not f["path"]:
                    raise UsageError(f"{kit.where}: files entry {entry}: an object entry needs exactly a "
                                     "non-empty \"path\" and an \"as\"")
                rel = check_kit_path(f["as"], f"{kit.where}: files entry {entry}")
                src = f["path"]
            else:
                rel, src = None, f
            p = Path(src) if Path(src).is_absolute() else path.parent / src
            if not p.is_file():
                raise UsageError(f"{kit.where}: no such file {src}")
            if rel is None:
                if p.name in names:
                    raise UsageError(f"{kit.where}: two files are both named {p.name}")
                names.add(p.name)
            resolved = p.resolve()
            # a string entry lands under its resolved name, as it always has, so its key does not move
            kit.add(rel or resolved.name, rel is not None, entry)
            placed.append((resolved, rel or resolved.name))
        seen[tid.casefold()] = tid
        tasks.append({**t, "id": tid, "prompt": prompt, "files": placed})
    if not tasks:
        raise UsageError(f"{path.name}: no tasks")
    return tasks


def load_validator(path):
    if not path:
        return None, ""
    source = read_utf8(path, "validator")
    spec = importlib.util.spec_from_file_location("cleanrun_validator", path)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except BaseException as e:
        raise UsageError(f"validator {Path(path).name} does not import: {type(e).__name__}: {e}")
    if not callable(getattr(mod, "validate", None)):
        raise UsageError(f"validator {Path(path).name} has no validate(output, task) function")
    return mod.validate, source


def run_key(cfg, task):
    files = sorted([rel, file_sha(p)] for p, rel in task["files"])
    key = {"v": KEY_VERSION, "model": cfg["model"], "effort": cfg["effort"], "tools": cfg["tools"],
           "system": sha(cfg["system"]), "schema": sha(cfg["schema_text"]), "prompt": sha(task["prompt"]),
           "files": files, "validator": sha(cfg["validator_source"])}
    if cfg["allowed_tools"]:       # only a run that uses it: finished out-dirs from before it keep their keys
        # the entries as a set: the same grant in another order, or repeated, must not rerun finished tasks
        key["allowed_tools"] = sorted(set(tool_entries(cfg["allowed_tools"], "--allowed-tools")))
    if cfg["also_models"]:         # the same rule: an output the weaker check passed must not resume under the exact one
        key["also_models"] = cfg["also_models"]
    return sha(key)


def task_view(task):
    return {**{k: v for k, v in task.items() if k != "files"}, "files": [rel for _, rel in task["files"]]}


def check(validate, output, task):
    """Problems with a structured output: the validator's list, or the validator's own failure."""
    if not isinstance(output, dict):
        return ["structured_output missing or not an object"]
    if validate is None:
        return []
    try:
        problems = validate(output, task_view(task))
    except Exception as e:
        return [f"validator raised {type(e).__name__}: {e}"]
    if problems is None:
        return []
    if not isinstance(problems, (list, tuple)):
        return ["validator must return a list of problems"]
    return [str(p) for p in problems]


def load_saved(path):
    try:
        saved = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return saved if isinstance(saved, dict) else {}


# ------------------------------------------------------------------ running


class shared_gate:
    """A usage-check verdict shared by every cleanrun process for GATE_CACHE_S, keyed by the
    command. The file lives in $CLEANRUN_USAGE_CACHE or the temp dir; an exclusive lock on it
    makes one process probe while the others wait and then read its verdict."""

    def __init__(self, cmd):
        self.key = sha(cmd)
        self.path = Path(os.environ.get("CLEANRUN_USAGE_CACHE") or Path(tempfile.gettempdir()) / "cleanrun_usage_gate.json")
        self.fd, self.verdict = None, None

    def __enter__(self):
        try:
            self.fd = os.open(str(self.path) + ".lock", os.O_CREAT | os.O_RDWR, 0o600)
            fcntl.flock(self.fd, fcntl.LOCK_EX)
        except OSError:
            self.fd = None                         # no shared cache: fall back to probing alone
        return self

    def __exit__(self, *exc):
        if self.fd is not None:
            os.close(self.fd)
        return False

    def entries(self):
        data = load_saved(self.path)
        return data if isinstance(data, dict) else {}

    def fresh(self):
        if self.fd is None:
            return False
        e = self.entries().get(self.key)
        if isinstance(e, dict) and e.get("verdict") in ("ok", "window full") \
                and isinstance(e.get("ts"), (int, float)) and 0 <= time.time() - e["ts"] < GATE_CACHE_S:
            self.verdict = e["verdict"]
            return True
        return False

    def store(self, verdict):
        if self.fd is None:
            return
        data = self.entries()
        data[self.key] = {"verdict": verdict, "ts": time.time()}
        try:
            write_atomic(self.path, data)
        except OSError:
            pass



class Budget:
    def __init__(self, cap, per_run):
        self.cap, self.per_run = cap, per_run
        self.spent = self.observed = 0.0
        self.unknown = 0
        self.lock = threading.Lock()

    def room(self):
        with self.lock:
            return self.cap is None or self.spent < self.cap

    def charge(self, cost):
        with self.lock:
            if isinstance(cost, bool) or not isinstance(cost, (int, float)) or not math.isfinite(cost) or cost < 0:
                self.unknown += 1
                cost = self.per_run              # unknown cost is never free
            else:
                self.observed += cost
            self.spent += cost
            return cost


def tokens(d):
    """Token counts for the ledger: top-level usage, else the sum over modelUsage (errored runs zero the former)."""
    u = d.get("usage") or {}
    vals = {"output": u.get("output_tokens"), "cache_write": u.get("cache_creation_input_tokens"),
            "cache_read": u.get("cache_read_input_tokens")}
    if any(isinstance(v, (int, float)) and v for v in vals.values()):
        return vals
    mu = [m for m in (d.get("modelUsage") or {}).values() if isinstance(m, dict)]
    pick = lambda k: sum(m.get(k) or 0 for m in mu if isinstance(m.get(k), (int, float))) if mu else None
    return {"output": pick("outputTokens"), "cache_write": pick("cacheCreationInputTokens"), "cache_read": pick("cacheReadInputTokens")}


class Runner:
    def __init__(self, cfg, out_dir, system_file):
        self.cfg, self.out, self.system_file = cfg, Path(out_dir), system_file
        self.budget = Budget(cfg["max_usd"], cfg["per_run_usd"])
        self.claude = cfg["claude_argv"]
        self.stop_reason = None
        self.stop = threading.Event()
        self.killed = threading.Event()
        self.procs, self.lock = set(), threading.Lock()
        self.ledger_lock, self.gate_lock = threading.Lock(), threading.Lock()
        self.models = Counter()
        self.gate = (0.0, None)
        self.launches = 0
        self.status = {}                              # task id -> (state, problems), filled as tasks end

    # -- stopping
    def halt(self, reason, kill=False):
        """Stop new launches; with kill (signals only) also kill every running process group."""
        with self.lock:
            if self.stop_reason is None:
                self.stop_reason = reason
            self.stop.set()
            if kill:
                self.killed.set()
                for p in list(self.procs):
                    kill_group(p)

    def halt_from_signal(self):
        """The signal-handler path. It takes no lock: Python runs handlers on the main thread,
        which may be holding self.lock (writing the summary) when the signal lands."""
        if self.stop_reason is None:
            self.stop_reason = "interrupted"
        self.killed.set()                              # set before the snapshot: a later spawn sees it and kills itself
        self.stop.set()
        try:
            procs = tuple(self.procs)                  # copied in C, without running Python code
        except RuntimeError:
            procs = ()
        for p in procs:
            kill_group(p)

    def may_launch(self):
        if self.stop.is_set():
            return False
        if not self.budget.room():
            self.halt(f"--max-usd {self.cfg['max_usd']} reached")
            return False
        verdict = self.usage_verdict()
        if verdict != "ok":
            self.halt(f"usage check: {verdict}")
            return False
        return not self.stop.is_set()

    def usage_verdict(self):
        cmd = self.cfg["usage_check"]
        if not cmd:
            return "ok"
        with self.gate_lock:                          # one probe at a time in this process
            t, v = self.gate
            if v is not None and time.time() - t < GATE_CACHE_S:
                return v
            with shared_gate(cmd) as shared:          # and one across processes: the usage endpoint answers 429
                if shared.fresh():                    # after a few calls, so parallel runs share one reading
                    self.gate = (time.time(), shared.verdict)
                    return shared.verdict
                backoff = float(os.environ.get("CLEANRUN_GATE_BACKOFF_S", "20"))
                verdict = "unreadable"
                for attempt in range(3):
                    rc = self.probe(cmd)
                    if rc == 0:
                        verdict = "ok"
                        break
                    if rc == 2:
                        verdict = "window full"
                        break
                    if attempt < 2 and self.stop.wait(backoff * (attempt + 1)):
                        break
                if verdict != "unreadable":           # only real readings are shared
                    shared.store(verdict)
            self.gate = (time.time(), verdict)
            return verdict

    def probe(self, cmd):
        """Run the usage-check command in its own group; an interrupt kills it."""
        try:
            p = subprocess.Popen(shlex.split(cmd), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL, start_new_session=True)
        except (OSError, ValueError):
            return None
        end = time.time() + 60
        while True:
            try:
                return p.wait(timeout=0.2)
            except subprocess.TimeoutExpired:
                if self.stop.is_set() or time.time() > end:
                    kill_group(p)
                    p.wait()
                    return None

    # -- one process
    def call(self, task):
        kit = Path(tempfile.mkdtemp(prefix="cleanrun_kit_"))       # all the model can see
        io = Path(tempfile.mkdtemp(prefix="cleanrun_io_"))         # prompt and outputs, outside the kit
        out = {"stdout": "", "stderr": "", "rc": None, "timeout": False, "error": None, "kit_error": None, "wall": 0.0}
        try:
            try:
                for p, rel in task["files"]:
                    shutil.copy2(p, place(kit, rel))
            except (OSError, RuntimeError) as e:      # nothing has launched: this task fails, the rest go on
                out["kit_error"] = f"could not build the task's kit: {e}"
                return out
            (io / "prompt").write_bytes(task["prompt"].encode("utf-8"))
            cmd = self.claude + ["-p", "--model", self.cfg["model"], "--effort", self.cfg["effort"], *FLAGS,
                                 "--tools", self.cfg["tools"],
                                 *(["--allowed-tools", self.cfg["allowed_tools"]] if self.cfg["allowed_tools"] else []),
                                 "--system-prompt-file", str(self.system_file),
                                 "--max-budget-usd", str(self.cfg["per_run_usd"]), "--json-schema", self.cfg["schema_text"]]
            t0 = time.time()
            with open(io / "prompt", "rb") as fin, open(io / "stdout", "wb") as fout, open(io / "stderr", "wb") as ferr:
                try:
                    proc = subprocess.Popen(cmd, cwd=kit, stdin=fin, stdout=fout, stderr=ferr, start_new_session=True)
                except OSError as e:
                    out["error"] = f"could not start claude: {e}"
                    return out
                with self.lock:
                    self.procs.add(proc)
                    self.launches += 1
                    late = self.killed.is_set()
                if late:                                   # killed between the check and the spawn
                    kill_group(proc)
                try:
                    out["rc"] = proc.wait(timeout=self.cfg["timeout"])
                except subprocess.TimeoutExpired:
                    kill_group(proc)
                    out["rc"] = proc.wait()
                    out["timeout"] = True
                finally:
                    with self.lock:
                        self.procs.discard(proc)
                    kill_group(proc)                       # anything the CLI left in its group
                    out["wall"] = round(time.time() - t0, 1)
            out["stdout"] = (io / "stdout").read_bytes().decode("utf-8", "replace")
            out["stderr"] = (io / "stderr").read_bytes().decode("utf-8", "replace")[-300:]
            return out
        finally:
            shutil.rmtree(kit, ignore_errors=True)
            shutil.rmtree(io, ignore_errors=True)

    def judge(self, call, task, validate):
        """(output or None, problems, parsed json or {}, retry_allowed)."""
        tail = f" [stderr: {call['stderr'].strip()}]" if call["stderr"].strip() else ""
        if self.killed.is_set() and call["rc"] != 0:
            return None, ["interrupted"], {}, False
        if call["timeout"]:
            return None, [f"timeout after {self.cfg['timeout']} s"], {}, True
        try:
            d = json.loads(call["stdout"])
        except ValueError:
            return None, [f"output is not JSON (exit {call['rc']}){tail}"], {}, True
        if not isinstance(d, dict):
            return None, ["output is not a JSON object"], {}, True
        observed = sorted((d.get("modelUsage") or {}).keys())
        with self.lock:
            for m in observed:
                self.models[m] += 1
        if d.get("is_error"):
            if d.get("subtype") == BUDGET_SUBTYPE:
                return None, [f"per-run budget reached (--per-run-usd {self.cfg['per_run_usd']}); not retried"], d, False
            msg = d.get("result") or "; ".join(str(e) for e in (d.get("errors") or [])) or "no message"
            return None, [f"is_error ({d.get('subtype') or 'no subtype'}): {str(msg)[:160]}{tail}"], d, True
        if call["rc"] != 0:
            return None, [f"exit {call['rc']}{tail}"], d, True
        mismatch = model_problem(observed, self.cfg["model"], self.cfg["also_models"])
        if mismatch:
            return None, [mismatch], d, True
        output = d.get("structured_output")
        problems = check(validate, output, task)
        return (output if not problems else None), problems, d, True

    def ledger(self, rec):
        with self.ledger_lock:
            with open(self.out / "ledger.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps({"ts": now(), **rec}, ensure_ascii=True) + "\n")

    # -- one task
    def do_task(self, task, validate):
        key = run_key(self.cfg, task)
        state = self.out / "outputs" / f"{task['id']}.json"
        if state.exists():
            saved = load_saved(state)
            if saved.get("key") == key:
                problems = check(validate, saved.get("output"), task)
                if not problems:
                    return "resumed", []
                self.ledger({"id": task["id"], "event": "resume_rejected", "problems": problems[:6]})
        problems = []
        for attempt in range(1 + self.cfg["retries"]):
            if not self.may_launch():
                return "stopped", problems
            call = self.call(task)
            if call["kit_error"]:                          # this task's files cannot be laid out; the next task's may be fine
                self.ledger({"id": task["id"], "event": "not_started", "error": call["kit_error"]})
                return "failed", [call["kit_error"]]
            if call["error"]:                              # nothing ran, nothing was spent
                self.ledger({"id": task["id"], "event": "not_started", "error": call["error"]})
                self.halt("claude could not start")
                return "failed", [call["error"]]
            output, problems, d, retry = self.judge(call, task, validate)
            cost = d.get("total_cost_usd")
            charged = self.budget.charge(cost)
            tk = tokens(d)
            self.ledger({"id": task["id"], "event": "attempt", "attempt": attempt + 1,
                         "model": self.cfg["model"], "model_observed": sorted((d.get("modelUsage") or {}).keys()),
                         "effort": self.cfg["effort"], "valid": output is not None, "problems": problems[:6],
                         "cost_usd": cost if isinstance(cost, (int, float)) and not isinstance(cost, bool) else None,
                         "cost_unknown": not isinstance(cost, (int, float)) or isinstance(cost, bool),
                         "charged_usd": charged, "wall_s": call["wall"], "turns": d.get("num_turns"),
                         "output_tokens": tk["output"], "cache_write": tk["cache_write"], "cache_read": tk["cache_read"]})
            if output is not None:
                write_atomic(state, {"id": task["id"], "key": key, "model": self.cfg["model"], "ts": now(),
                                     **({"also_models": self.cfg["also_models"]} if self.cfg["also_models"] else {}),
                                     "output": output})
                return "ran", []
            if not retry or self.killed.is_set():
                break
        return ("stopped" if self.killed.is_set() else "failed"), problems

    def task_entry(self, task, validate):
        """Worker entry: a crash stops new launches instead of escaping and losing the summary."""
        state, problems = "crashed", ["did not finish"]
        try:
            state, problems = self.do_task(task, validate)
        except BaseException as e:                         # includes SystemExit raised inside a validator
            problems = [f"{type(e).__name__}: {e}"]
            self.halt(f"internal error in task {task['id']}: {type(e).__name__}")
        finally:
            with self.lock:
                self.status[task["id"]] = (state, problems)


# ------------------------------------------------------------------ commands


def build_cfg(a):
    check_routing(a.model, a.effort)
    also_models = check_also_models(a.also_models, a.model)
    allowed_tools = check_allowed_tools(a.allowed_tools, a.tools)
    system = read_utf8(a.system_prompt, "system prompt")
    schema_text = read_utf8(a.schema, "schema")
    try:
        schema = json.loads(schema_text)
    except ValueError as e:
        raise UsageError(f"schema is not JSON: {e}")
    if not isinstance(schema, dict) or schema.get("type") != "object":
        raise UsageError("schema must be a JSON Schema object with \"type\": \"object\"")
    schema_text = json.dumps(schema, ensure_ascii=False)    # the exact string sent and hashed
    if len(schema_text.encode("utf-8")) > MAX_SCHEMA_BYTES:
        raise UsageError(f"schema is over {MAX_SCHEMA_BYTES} bytes; it travels on the command line")
    if a.jobs < 1 or a.retries < 0 or a.timeout < 1:
        raise UsageError("--jobs and --timeout must be >= 1 and --retries >= 0")
    claude = a.claude_bin or os.environ.get("CLEANRUN_CLAUDE_BIN") or "claude"
    try:
        claude_argv = shlex.split(claude)
    except ValueError as e:
        raise UsageError(f"cannot parse the claude command {claude!r}: {e}")
    if not claude_argv or not shutil.which(claude_argv[0]):
        raise UsageError(f"cannot find the claude executable {claude_argv[0] if claude_argv else claude!r}")
    validate, vsource = load_validator(a.validator)
    cfg = {"model": a.model, "effort": a.effort, "tools": a.tools, "allowed_tools": allowed_tools,
           "also_models": also_models, "system": system, "schema_text": schema_text,
           "validator_source": vsource, "max_usd": a.max_usd, "per_run_usd": a.per_run_usd,
           "timeout": a.timeout, "retries": a.retries, "jobs": a.jobs, "usage_check": a.usage_check,
           "claude_argv": claude_argv}
    return cfg, validate, load_tasks(a.tasks)


def to_run(cfg, validate, tasks, out):
    """Tasks that will launch: those without a saved output that matches the key and validates."""
    pending = []
    for t in tasks:
        saved = load_saved(Path(out) / "outputs" / f"{t['id']}.json")
        if not (saved.get("key") == run_key(cfg, t) and not check(validate, saved.get("output"), t)):
            pending.append(t)
    return pending


def bound_line(cfg, n):
    worst = n * (1 + cfg["retries"]) * cfg["per_run_usd"]
    line = (f"cost bound: {n} task(s) x {1 + cfg['retries']} attempt(s) x ${cfg['per_run_usd']} soft cap "
            f"= about ${worst:.2f}")
    if cfg["max_usd"] is not None and n:
        k = min(cfg["jobs"], n)
        line += (f"; --max-usd {cfg['max_usd']} stops new launches in this invocation, worst-case overshoot "
                 f"about {k} x ${cfg['per_run_usd']} = ${k * cfg['per_run_usd']:.2f}")
    return line + " (list price; claude can overrun a soft cap by part of a turn)"


def cmd_plan(a):
    cfg, validate, tasks = build_cfg(a)
    pending = to_run(cfg, validate, tasks, a.out_dir)
    print(f"plan: {len(tasks)} task(s), {len(tasks) - len(pending)} resume, {len(pending)} to run; "
          f"{cfg['model']} @ {cfg['effort']}, tools {cfg['tools']!r}{routing_extras(cfg)}, {cfg['jobs']} job(s)")
    print(bound_line(cfg, len(pending)))
    return 0


def summary_of(run, tasks, cfg, state):
    with run.lock:
        status = dict(run.status)
        models = dict(run.models)
        hold = os.environ.get("CLEANRUN_TEST_HOLD_LOCK_S")   # test seam: widens the window a signal can land in
        if hold:
            time.sleep(float(hold))
    by = {s: [] for s in ("ran", "resumed", "failed", "crashed", "stopped")}
    for t in tasks:
        st, p = status.get(t["id"], ("stopped", []))
        by.setdefault(st, []).append((t["id"], p))
    return {"ts": now(), "state": state, "requested": len(tasks), "ran": len(by["ran"]), "resumed": len(by["resumed"]),
            "failed": [{"id": i, "problems": p[:6]} for i, p in by["failed"]],
            "crashed": [{"id": i, "problems": p[:6]} for i, p in by["crashed"]],
            "not_run": [{"id": i, "problems": p[:6]} for i, p in by["stopped"]],
            "stopped": run.stop_reason, "launches": run.launches,
            "charged_usd": round(run.budget.spent, 4), "observed_cost_usd": round(run.budget.observed, 4),
            "unknown_cost_runs": run.budget.unknown, "models_observed": models,
            "model": cfg["model"], "effort": cfg["effort"],
            **({"also_models": cfg["also_models"]} if cfg["also_models"] else {})}      # the weaker check was in force


def routing_extras(cfg):
    """What beyond model, effort and tools shapes a run, for the plan and start lines: the grant, and the
    weaker model check. Empty by default, so a default line reads as it always has."""
    out = ""
    if cfg["allowed_tools"]:
        out += f", allowed {cfg['allowed_tools']!r}"
    if cfg["also_models"]:
        out += f", also models {', '.join(cfg['also_models'])} (weaker model check)"
    return out


def cmd_run(a):
    cfg, validate, tasks = build_cfg(a)
    out = Path(a.out_dir)
    if out.exists() and not out.is_dir():
        raise UsageError(f"--out-dir is a file: {out}")
    try:
        out.mkdir(parents=True, exist_ok=True)
        lock_fd = os.open(out / ".lock", os.O_CREAT | os.O_RDWR, 0o644)
    except OSError as e:
        raise UsageError(f"cannot use --out-dir {out}: {e}")
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(lock_fd)
        raise UsageError(f"another cleanrun is writing to {out} (lock {out / '.lock'})")
    os.ftruncate(lock_fd, 0)
    os.write(lock_fd, str(os.getpid()).encode())

    system_file = out / ".system-prompt"
    write_atomic(system_file, cfg["system"].encode("utf-8"))     # byte for byte, CRLF included
    run = Runner(cfg, out, system_file.resolve())
    pending = to_run(cfg, validate, tasks, out)
    write_atomic(out / "summary.json", summary_of(run, tasks, cfg, "running"))
    signals = {"count": 0, "first": None}
    grace = float(os.environ.get("CLEANRUN_GRACE_S", "30"))

    def finish(state):
        write_atomic(out / "summary.json", summary_of(run, tasks, cfg, state))

    def on_signal(signum, _frame):
        # No lock and no file write here: the main thread may hold run.lock when a signal lands.
        # The main loop writes the summary; a second signal or the grace period makes it leave.
        signals["count"] += 1
        if signals["first"] is None:
            signals["first"] = time.time()
        run.halt_from_signal()

    for s in SIGNALS:
        signal.signal(s, on_signal)
    print(f"cleanrun: {len(tasks)} task(s), {len(tasks) - len(pending)} resume, {len(pending)} to run; "
          f"{cfg['model']} @ {cfg['effort']}{routing_extras(cfg)}, {cfg['jobs']} job(s); " + bound_line(cfg, len(pending)), flush=True)
    ex = ThreadPoolExecutor(cfg["jobs"])
    state = "finished"
    try:
        futures = [ex.submit(run.task_entry, t, validate) for t in tasks]
        while not all(f.done() for f in futures):     # poll, so signals are handled promptly
            if signals["count"] >= 2 or (signals["first"] is not None and time.time() - signals["first"] > grace):
                finish("interrupted")                 # a second signal, or a worker that will not finish
                os._exit(130)
            time.sleep(0.2)
    finally:
        ex.shutdown(wait=signals["count"] == 0, cancel_futures=True)
        if signals["count"]:
            state = "interrupted"
        elif run.stop_reason:
            state = "stopped"
        summary = summary_of(run, tasks, cfg, state)
        write_atomic(out / "summary.json", summary)
        os.close(lock_fd)
        for s in SIGNALS:            # the run is over and its summary is on disk: Python's shutdown would put
            signal.signal(s, signal.SIG_IGN)   # the default handler back, and a late Ctrl-C would hide exit 130

    done = summary["ran"] + summary["resumed"]
    print(f"{done}/{len(tasks)} done ({summary['ran']} ran, {summary['resumed']} resumed), "
          f"{len(summary['failed'])} failed, {len(summary['crashed'])} crashed, {len(summary['not_run'])} not run; "
          f"charged ${summary['charged_usd']:.4f} list (observed ${summary['observed_cost_usd']:.4f}; "
          f"{summary['unknown_cost_runs']} unknown-cost run(s) charged at the cap); "
          f"models observed {summary['models_observed'] or '{}'}"
          + (f"; STOPPED: {run.stop_reason}" if run.stop_reason else ""), flush=True)
    for f in summary["failed"] + summary["crashed"]:
        print(f"  {f['id']}: {'; '.join(f['problems'][:3])}")
    if signals["count"]:
        return 130
    if summary["crashed"]:
        return 3
    if run.stop_reason:
        return 2
    return 1 if summary["failed"] else 0


def cmd_status(a):
    out = Path(a.out_dir)
    if not out.is_dir():
        print(f"cleanrun: no output directory {out}", file=sys.stderr)
        return 2
    s = load_saved(out / "summary.json")
    clean = False
    if s:
        clean = s.get("state") == "finished" and not s.get("failed") and not s.get("crashed") and not s.get("stopped")
        print(f"last run ({s.get('ts')}): state {s.get('state')}, {s.get('ran', 0)} ran, {s.get('resumed', 0)} resumed, "
              f"{len(s.get('failed') or [])} failed, {len(s.get('crashed') or [])} crashed, "
              f"{len(s.get('not_run') or [])} not run, charged ${s.get('charged_usd', 0)}"
              + (f", stopped: {s['stopped']}" if s.get("stopped") else ""))
    else:
        print("no readable summary.json")
    rows, bad = [], 0
    ledger = out / "ledger.jsonl"
    if ledger.exists():
        for line in ledger.read_bytes().decode("utf-8", "replace").split("\n"):
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except ValueError:
                bad += 1
                continue
            if isinstance(r, dict):
                rows.append(r)
            else:
                bad += 1
    att = [r for r in rows if r.get("event") == "attempt"]
    charged = sum(r.get("charged_usd") or 0 for r in att if isinstance(r.get("charged_usd"), (int, float)))
    print(f"ledger, all runs: {len(att)} attempt(s), {sum(1 for r in att if r.get('valid'))} valid, "
          f"charged ${charged:.4f} list, {sum(1 for r in att if r.get('cost_unknown'))} unknown-cost, "
          f"{sum(1 for r in rows if r.get('event') == 'resume_rejected')} resume rejection(s)"
          + (f", {bad} unreadable line(s)" if bad else ""))
    return 0 if clean else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("run", "plan"):
        p = sub.add_parser(name)
        p.add_argument("--tasks", required=True)
        p.add_argument("--system-prompt", required=True)
        p.add_argument("--schema", required=True)
        p.add_argument("--model", required=True)
        p.add_argument("--effort", required=True)
        p.add_argument("--out-dir", required=True)
        p.add_argument("--tools", default="")
        p.add_argument("--allowed-tools", default="")
        p.add_argument("--also-models", default="")
        p.add_argument("--validator")
        p.add_argument("--jobs", type=int, default=4)
        p.add_argument("--max-usd", type=finite_positive)
        p.add_argument("--per-run-usd", type=finite_positive, default=2.5)
        p.add_argument("--timeout", type=int, default=1800)
        p.add_argument("--retries", type=int, default=1)
        p.add_argument("--usage-check")
        p.add_argument("--claude-bin")
    st = sub.add_parser("status")
    st.add_argument("--out-dir", required=True)
    a = ap.parse_args(argv)
    try:
        return {"run": cmd_run, "plan": cmd_plan, "status": cmd_status}[a.cmd](a)
    except UsageError as e:
        print(f"cleanrun: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
