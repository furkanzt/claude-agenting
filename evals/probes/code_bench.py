#!/usr/bin/env python3
"""code_bench  --  who writes the tests and who writes the code (rule set:
evals/results/PREREGISTERED-2026-11-14-coding.md).

    python3 evals/probes/code_bench.py selftest [--json]       # canaries in the sandbox; exit 0 only if all refused
    python3 evals/probes/code_bench.py install [--task CODE]   # build start/, reference/, hidden/ and check them
    python3 evals/probes/code_bench.py plan [--json]           # what is missing, spend so far and projected; no model
    python3 evals/probes/code_bench.py write-tests [--task CODE] [--cells ...] [--max-usd N] [--jobs N]   # step T
    python3 evals/probes/code_bench.py fix-suites [--task CODE]   # fit or not per suite; the given suite per task
    python3 evals/probes/code_bench.py code [--task CODE] [--rounds N] [--cells ...] [--arms ...] [--max-usd N]
    python3 evals/probes/code_bench.py cross [--task CODE]     # every fit suite on the final copies of arms A and C
    python3 evals/probes/code_bench.py status [--json]

Exit codes: 0 done; 1 a task failed its installation or the self-test failed; 2 an error (one code
word, see ERROR_WORDS); 3 the spend stop was reached; 130 interrupted.

Options shared by the commands: --root (default <evals>/private/code), --results (default
<evals>/results/code-runs.jsonl; with a custom --root the default is <root>/code-runs.jsonl, so a
trial root never writes into the repository's public record), --evals-dir (where evalkit's lock
lives), --work (scratch copies, default a folder in the system temp directory; a command that takes
the lock first removes the copy-* and snap-* folders a killed invocation left there),
--vitest-modules (a node_modules folder that holds vitest, for the vitest canary; also
$CODE_BENCH_VITEST_MODULES).

Private layout under --root (never committed, never printed):

    tasks.json                      {"tasks": [ task record, ... ]}  (see validate_task)
    briefs/<code>.md                the brief of a task
    tasks/<code>/start/             the project at `before` (git archive), minus the strip list
    tasks/<code>/reference/         start with the change's source files taken from `after`
    tasks/<code>/hidden/            the hidden test files from `after` (tree-relative paths)
    tasks/<code>/installed.json     scalars of the installation check and the task hash (ok false and
                                    a reason word when the task failed; removed first by every install)
    suites/<code>/<cell>/<run>/     a step-T suite: files/, meta.json, and fit.json once scored
    runs/<code>/<cell>/<arm>/<run>/ a step-C run: overlay/, deleted.json, meta.json
    given.json                      per task: the given suite ("<cell>#<run>", or null when none is fit)
    cross.json                      the cross pairs already run
    attempts.jsonl                  every public line again plus `detail` (output tail, paths, tracebacks)

THE SANDBOXED TEST RUNNER, run_tests(tree_dir, runner, test_cwd, files, time_limit_s, names).
Every run goes through /usr/bin/sandbox-exec with a profile that denies all network, denies every
signal to a process outside the sandbox, denies every write except under the tree and a per-run
scratch folder (also HOME and TMPDIR), and denies reading file contents under the user's real home
folder (from the password database, not $HOME) except the tree and the scratch folder. The environment is minimal: PATH (the folders of this python and of
node, then /usr/bin:/bin), HOME, TMPDIR, LANG, PYTHONDONTWRITEBYTECODE=1, PYTHONNOUSERSITE=1, CI=1;
NODE_OPTIONS and every other variable of the parent are absent. Output is captured to a file, never
inherited, and only its tail is read; a run whose output passes LOG_MAX_BYTES is stopped as a time-out.
The runner gets its own process group, killed with SIGKILL at the time limit and after it ends; a
process that left the group (setsid) is found by its working folder or by the output file it holds
open (lsof) and killed too. `files` are tree-relative paths, passed relative to `test_cwd`. An empty
`files` is no_tests and starts nothing (no runner may fall back to "all tests"); a file that does not
exist is load_error before anything starts.

The result is one fixed word (RESULT_WORDS), with `tests` and `failed` counts and the private
`detail` (the last DETAIL_MAX characters of the output). Precedence, first match wins:
check_infra, timeout, load_error, load_error_missing_name, fail, no_tests, pass. "Loads" means:
EVERY file given loaded. One file that fails to load for another reason makes the run `load_error`
even when other files have failing tests (for pytest a collection error stops the whole run anyway);
`load_error_missing_name` needs every file that failed to load to have failed only because of a
listed name (missing_name_in). `tests` counts the tests that ran (passed plus failed; skipped and todo
tests do not count); `failed` counts failed ones. pass = loaded, tests >= 1, failed = 0; fail = loaded,
failed >= 1; no_tests = loaded, tests = 0 (nothing collected, or everything skipped).

  pytest:    python -m pytest <files> -q -p no:cacheprovider -o addopts= -W ignore --junitxml=<scratch>/r.xml.
             A file does not load when the junit file has a test case with <error message="collection
             failure">, or pytest exits 2, 3 or 4 (collection interrupted, internal error, usage error such
             as a conftest that cannot import or a file not found). Exit 5 = no_tests. A test fails when
             its junit case has <failure> or <error> (a setup or teardown error counts as failing).
             No junit file and an exit code that is not 2..5 = check_infra (pytest itself did not start);
             a runner killed by a signal other than the time limit = fail.
  node-test: node --test --test-reporter=tap --test-reporter-destination=stdout plus a JSON-lines
             reporter written to the scratch folder (NODE_REPORTER), which tags every event with its
             file. node reports a file that ended with an error outside any test as a top-level test
             named after the file. A file does not load when that file-level test failed and no real
             test of the file ran; when real tests of the file ran first, the file-level failure is one
             more failed test (an error after the tests). A file-level test that passed (a file with
             no tests) adds no test. A failing suite with no failing test inside adds one failure
             (a hook error). A requested file with no event at all did not load (load_error). The
             arguments are glob-escaped, because node reads them as globs ([id].test.mjs).
  vitest:    <test_cwd or a parent up to the tree root>/node_modules/.bin/vitest run <files>
             --reporter=json --outputFile=<scratch>/r.json (no npx: npx may reach the network). No such
             binary = check_infra. A file does not load when its testResults entry has status "failed",
             no assertionResults and a message that does not start with "No test suite found" (that
             message = a file with no tests). A test fails when its assertion status is "failed"; a
             file with status "failed" whose tests all passed adds one failure (an error outside the
             tests); a non-zero exit with tests that all passed is `fail` (an unhandled error). vitest
             reads file arguments as SUBSTRING filters, so results of files that were not requested
             are dropped (and the exit code is not read when one of them failed); a requested file
             with no result did not load. No JSON file: "No test files found" in the output =
             no_tests, else load_error.

"Red on the start state" = fail, timeout or load_error_missing_name (is_red).

missing_name_in(text, names): the error text holds one of the error forms in MISSING_PATTERNS (cannot
import name 'X', No module named 'X', has no attribute 'X', name 'X' is not defined, No such file or
directory 'X', does not provide an export named 'X', Cannot find module/package 'X', Failed to
resolve import "X", Failed to load url X (vitest 2), ENOENT ... 'X', ReferenceError: X is not defined,
(reading 'X'), X is not a function/constructor) and the X it names matches a listed name: equal; or
its last dotted part is equal; or, for a path, its base name, its base name without extension, or its
tail after a "/" is equal to the name (with or without the name's own extension); for a relative
import (./X, ../X) also the base name of a listed path.

TREES. clone_tree is `cp -cR` (a copy-on-write clone on APFS; plain copy elsewhere). make_copy puts a
clone of a tree under --work, applies deletions and overlay files and clones node_modules into place
(clone_node_modules: a symlink that points into the source node_modules by an absolute path is
re-pointed into the clone; one that leaves it otherwise is removed). Writing a file keeps the mode
of the file it replaces or of its source; reference and hidden files take git's mode at `after`.
overlay_of(copy, start) lists the files that are new or differ by content hash, and the deleted
paths; node_modules, __pycache__, .pytest_cache and .vite* folders are ignored; symlinks that the
start tree does not have are ignored and counted. Copies live under --work, outside the repository,
because pytest looks for its configuration in the folders above the tree, and inside the repository
it would find this repository's pytest.ini (and the sandbox denies reading it).

INSTALL. For every task (or --task CODE), after the self-test passed (fail closed) and under evalkit's
exclusive lock: start/ = `git -C <project> archive <before>`, minus the task's own `strip` (each entry
must exist) and the fixed strip list of the rules (FIXED_STRIP_FILES at any depth and in any letter
case, .claude and .github at any depth, docs and features at the tree root and at test_cwd);
reference/ = start with every source file read from `after` (`cat-file -e` says whether `after` has
it; a path it lacks is deleted; a path that neither commit has is task_invalid);
hidden/ = every hidden test file from `after`. Links in the archive that leave the tree are skipped
and counted (links_skipped). Then the leak check (rules: "no name the change adds, and the hidden
tests need, occurs in what is left"). A listed name is ADDED by the change when the project does not
have it yet: it does not occur as a whole token (not inside a longer identifier) in the `before`
version of any source file, nor in the contents or the path of any file of the stripped start tree
that is not prose (code, tests, data, configuration; an existing file a test reads and an existing
field a test checks are names the project already has). No added name may occur in a prose file that
is left (PROSE_ENDINGS, or a name with no ending), in its contents or its path: that is a note about
the change, and the task fails with `leak`. Then,
through the sandbox with a 60 s limit: the run files on start + hidden must be red; on reference +
hidden they must be `pass` three times out of three (a time-out there = reference_slow). check_infra
on any of these runs is the reason check_infra (the runner failed, not the task). A task that fails
while being built, or with an unexpected error (internal), gets installed.json with ok false and its
reason, and the other tasks go on. installed.json is written either way (ok, reason, counts, seconds; reference_seconds is the slowest of the three
runs; task_hash covers start, hidden and brief). A failure prints the task code and a reason word.

RECORDS. The public file holds only check and model lines with the keys CHECK_KEYS / MODEL_KEYS and
values from fixed vocabularies or numbers (public_line refuses anything else). attempts.jsonl gets
the same line plus `detail`. The terminal shows task codes, fixed words and numbers only. A top-level
exception prints `code_bench: error: internal <task>`; the traceback goes to attempts.jsonl.

THE MODEL STEPS. A model process is evalkit's call_claude with a stand-in context whose runner flags
are the harness's plus PERMISSION_FLAGS (harness.json is not changed), the tools MODEL_TOOLS (read,
search, write, edit; nothing runs), the fixed SYSTEM_PROMPT, the working copy as its folder, the
advisor switched off by evalkit's child_env and DISABLE_AUTOUPDATER=1. Every command that calls a
model first checks that `claude --version` names 2.1.325 as a whole version (2.1.3251 and 2.1.325.1
are other versions; --allow-version, for tests only, names another whole version), then runs the
self-test (fail closed). Before EVERY model process the spend total is
read from the public record (all invocations): the sum of cost_usd over the model lines, the harness's
per-process cap (6 USD) for a line whose cost is unknown; no process starts at or above --max-usd
(default 226). Validity is evalkit's parse_call; a refusal and a budget stop are invalid too. Reason
words, first match: spawn_failed, timeout, json_parse, budget_cap (the CLI's subtype names the
budget), refusal, model_mismatch, is_error. An attempt is an infra error by evalkit's infra_error
reading (never a budget stop or a refusal): it is NOT a try; the working copy is put back as it was
before that attempt and the same try starts again, at most MAX_ATTEMPTS attempts; after three the run
ends ("infra"). Any other invalid process IS a try, and its files are checked like any other try's.

Step T (write-tests): for every task, T_CELLS cell and run 1..2, a working copy of start; up to three
tries. After a try the suite is the copy's new or changed files under test_patterns; every other change
(a source file changed or added, any deletion, a new symlink) is reverted in the copy and counted
(files_dropped). Check "red first": the suite's files on a fresh copy of START, its runnable files
(RUN_PATTERNS of the runner, or the task's own run_patterns) run; red = is_red. A suite with no test
file, or none the runner would run, is no_tests (not red). Not red and not the third try: the next try
gets the check's output. The reference is never run. The last suite is stored.

fix-suites: per stored suite, fit = red on start and `pass` on the reference two runs out of two
(fit.json; a suite whose run ended on infra errors is not fit and not run). Once all eight suites of a
task are stored and scored, the given suite is the first fit one in GIVEN_ORDER, written to given.json
and never changed afterwards; with none fit, arms B and C of that task are left out.

Step C (code): rounds; round n = run n of every cell and arm on every task, in the order task, cell,
arm (c_units). Arms B and C wait for the task's given suite and are left out when there is none. A
run: a working copy (arm B: the given suite's files written into it); up to three tries (arm A one);
after each try: arm B puts the given suite's files and the runner_config files back as they were
(a change = check result locked_changed, counted as files_dropped; the suite is still run so the next
try sees its output, after a note that names the files that were put back); the check (arm A none; arm B the given suite on start + the copy's overlay with
the suite written last; arm C own_check); then the hidden tests on start + overlay with the hidden
files written last, never shown to the model. A try whose check is not `pass` and that is not the last
gets the next try in the same copy with the check's output. Stored: overlay/, deleted.json and
meta.json (tries, check and hidden words per try, finished, correct, correct_first, escaped, costs).

cross: every fit suite on every stored copy of arms A and C whose run ended normally and whose source
is not unchanged: start + the copy's non-test files and non-test deletions (the run's own test files
left out), the suite written, its runnable files run. One check line per pair; a (task, suite,
non-test overlay) triple already run reuses its result (cross.json). Before the pairs, every stored
copy of arms A and C that ended normally gets one public `copy` line (step cross, suite null, result
`changed` or `unchanged`), once, so the analysis can tell from the public record alone which copies
cross has seen and which are left out because their source is unchanged.

CHECK_INFRA IS A STOP. In write-tests, fix-suites, code and cross a test run that comes back
check_infra (the runner could not start) is the runner's failure, never a result: its public check line
is written, then CheckInfraStop is raised before anything is stored (meta.json, fit.json, given.json, a
cross.json entry) and before the model gets another try. write-tests and code start no new model
process after it and end with `code_bench: error: check_infra` (exit 2); fix-suites and cross end the
same way at once. The unit is made again by the next invocation. The analysis ignores check lines whose
result is check_infra.

READINGS the rules leave open, fixed here:
  * files_changed (model line) = paths the process added, changed or removed in its copy;
    files_dropped = paths reverted after it (step T) or locked files put back (arm B).
  * A run cut by the spend stop, a check_infra stop or Ctrl-C is not stored; the next invocation makes
    it again from a fresh copy. The public lines of the cut tries stay (their cost was spent and counts
    in the spend). The public record has no incarnation field; the analysis reads a run's FINAL
    incarnation as the lines from its last model line with try 1 and attempt 1 onward (every model line
    of a run is written by one thread, in order), and everything earlier for that run as a cut
    incarnation. Likewise fix-suites repeats a suite's fit lines from its fit_start line, and cross can
    repeat a pair's line when killed between the public line and cross.json; the analysis keeps the last.
  * A model process killed by Ctrl-C (or a SIGKILL of the tool) before its model line is written leaves
    no line, so its cost is missing from the spend total; with 4 jobs that is at most 4 x the $6 cap
    per interruption. The operator keeps that margin in mind when an invocation is interrupted.
  * A spend stop in the middle of a round leaves that round partly done (no later round starts); the
    runs it never made, or cut, are listed by the analysis as not started and are left out of every
    share, never counted as not correct.
  * Arm B locks the given suite's files and the task's runner_config paths only. A new file the coder
    creates that the runner would read (a conftest.py, pytest.ini, vitest.config.ts, a setup file) is
    locked only when the task record lists it in runner_config (a listed path that does not exist at
    start is removed again before every check), so the lead lists every such name for each task.
  * correct_first is read from the hidden tests after try 1 even when the run later ended on infra
    errors; correct and finished are then false (rules, "Missing and invalid runs").
  * fit lines: `run` is the writer's run, `try` is the reference repetition (1, 2). The given line
    (step fit, what given) has result pass when a suite is fixed and fail when none of the eight is fit.
  * Arm C check: no own test file, or none the runner would run = no_tests; own tests not red on start
    = fail (own_reason own_not_red, private); else their result on the copy.
  * A test run whose output passes LOG_MAX_BYTES is stopped and read as a time-out.
  * The hidden tests of arms B and C run on start + the run's overlay, so the copy also holds the
    given suite's files or the coder's own test files and their helpers (a conftest.py). Arm A's copy
    holds none. The rules say "the copy".
  * cross puts EVERY path under the test patterns back to the start state before the suite is
    written: files the run added are removed (the rules), and also a start-state test file the run
    changed (reverted) or deleted (restored). A suite is judged on the copy's source only.
  * A model process that answered with another model than the cell's (model_mismatch) counts as a
    try, as in evalkit, and its files are checked; the report lists every such line.
  * A test-pattern entry that ends with "/" means everything under that folder.

WHAT THE SANDBOX DOES NOT DO (rules, limit 10: it guards against accidents, not an adversary).
Names and sizes of files under the home folder can still be read (stat); only their contents are
denied. Everything outside the home folder is readable, the system temp folders included. Name
lookups through system services were not tested. There is no memory limit. A test file that ends the
runner on purpose with exit code 0 (pytest.exit) reads as `pass` with the tests that ran before it.

"""
from __future__ import annotations

import argparse
import contextlib
import copy as _copy
import hashlib
import io
import json
import os
import pwd
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import traceback
import types
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Mapping, Sequence

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import evalkit as ev  # noqa: E402

# -- fixed vocabularies --------------------------------------------------------

RESULT_WORDS = ("pass", "fail", "no_tests", "load_error_missing_name", "load_error", "timeout",
                "check_infra")
COPY_WORDS = ("changed", "unchanged")      # the result of a cross `copy` line: is the copy's source changed
CHECK_RESULT_WORDS = RESULT_WORDS + ("locked_changed",) + COPY_WORDS
RED_WORDS = frozenset({"fail", "timeout", "load_error_missing_name"})
RUNNERS = ("pytest", "node-test", "vitest")
LANGUAGES = ("python", "typescript")
RATINGS = ("easy", "medium", "hard")
CHECK_STEPS = ("install", "T", "fit", "C", "cross")
MODEL_STEPS = ("T", "C")
CHECK_WHATS = ("install_start", "install_reference", "red_first", "fit_start", "fit_reference",
               "given", "own", "hidden", "cross", "copy")
MODEL_REASONS = ("timeout", "json_parse", "model_mismatch", "refusal", "budget_cap", "spawn_failed",
                 "is_error")
ARMS = ("A", "B", "C")
INSTALL_REASONS = ("task_invalid", "git_failed", "brief_missing", "strip_missing", "hidden_missing",
                   "source_stripped", "leak", "start_not_red", "reference_fails", "reference_slow",
                   "check_infra", "internal")
ERROR_WORDS = ("no_tasks", "no_task", "task_invalid", "selftest_failed", "locked", "internal", "harness",
               "version_mismatch", "cell_unknown", "arm_unknown", "check_infra")

CHECK_KEYS = ("kind", "step", "task", "cell", "arm", "run", "try", "what", "suite", "result",
              "tests", "failed", "seconds", "ts")
MODEL_KEYS = ("kind", "step", "task", "cell", "arm", "run", "try", "attempt", "valid", "reason",
              "infra", "cost_usd", "cost_unknown", "duration_ms", "input_tokens", "output_tokens",
              "cache_read_tokens", "num_turns", "denials", "files_changed", "files_dropped",
              "cli_version", "ts")

FIXED_STRIP_FILES = ("CLAUDE.md", "AGENTS.md", "PLAN.md", "QUESTIONS.md", "HANDOFF.md",
                     "CHANGELOG.md", "TDD.md", "BDD.md")
FIXED_STRIP_FILES_LOWER = frozenset(f.lower() for f in FIXED_STRIP_FILES)   # Changelog.md goes too
PROSE_ENDINGS = (".md", ".mdx", ".markdown", ".txt", ".rst", ".adoc", ".org")  # where a note can live
FIXED_STRIP_DIRS_ANYWHERE = (".claude", ".github")
FIXED_STRIP_DIRS_AT_ROOTS = ("docs", "features")

IGNORED_DIR_NAMES = ("node_modules", "__pycache__", ".pytest_cache")
IGNORED_DIR_PREFIXES = (".vite",)

DETAIL_MAX = 4000
INSTALL_TIME_LIMIT_S = 60.0
REFERENCE_RUNS = 3
TIME_LIMIT_MIN_S, TIME_LIMIT_MAX_S, TIME_LIMIT_FACTOR = 20.0, 60.0, 5.0
SELFTEST_TIME_LIMIT_S = 60.0
SANDBOX_EXEC = "/usr/bin/sandbox-exec"
GIT_SUBCOMMANDS = frozenset({"archive", "show", "cat-file", "rev-parse", "ls-tree"})

CODE_RE = re.compile(r"^code-\d{2}$")
CELL_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*@[a-z]+$")
SUITE_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*@[a-z]+#\d+$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}([0-9a-f]{24})?$")
VERSION_RE = re.compile(r"^\d+(?:\.\d+){1,3}$")
TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


class BenchError(Exception):
    """A handled failure: printed as `code_bench: error: <word> [<task>]`, exit 2. The word comes
    from ERROR_WORDS or INSTALL_REASONS; `detail` is private (attempts.jsonl only)."""

    def __init__(self, word: str, task: str | None = None, detail: str = ""):
        super().__init__(word)
        self.word, self.task, self.detail = word, task, detail


class CheckInfraStop(BenchError):
    """A test run of write-tests, fix-suites, code or cross came back check_infra (the runner could not
    start): the runner failed, not the suite or the coder. Raised after the run's public check line and
    before anything is stored (meta.json, fit.json, given.json, a cross.json entry) and before the model
    gets another try; the unit is made again by the next invocation."""

    def __init__(self, task: str | None = None, detail: str = ""):
        super().__init__("check_infra", task, detail)


def no_infra(res, task_code: str | None):
    """Stop the unit when a test run came back check_infra; else return the result unchanged."""
    if res is not None and res.result == "check_infra":
        raise CheckInfraStop(task_code, res.detail)
    return res


def is_red(result: str) -> bool:
    """Red on the start state (rules, "A try"): a test fails, a time-out, or a listed name is missing."""
    return result in RED_WORDS


def time_limit_for(reference_seconds: float) -> float:
    """Five times the reference run, at least 20 s, at most 60 s."""
    return min(TIME_LIMIT_MAX_S, max(TIME_LIMIT_MIN_S, TIME_LIMIT_FACTOR * float(reference_seconds)))


# -- the sandboxed test runner ---------------------------------------------------

@dataclass(frozen=True)
class TestResult:
    """One sandboxed test run. `detail` is PRIVATE: attempts.jsonl and a model's next try only."""
    __test__ = False                       # not a pytest test class
    result: str
    tests: int | None
    failed: int | None
    seconds: float
    detail: str = ""

    @property
    def red(self) -> bool:
        return is_red(self.result)


@dataclass(frozen=True)
class Tools:
    """The binaries a run uses; tests replace them to provoke check_infra."""
    python: str
    node: str | None
    sandbox: str = SANDBOX_EXEC


def default_tools() -> Tools:
    node = shutil.which("node") or ("/opt/homebrew/bin/node" if Path("/opt/homebrew/bin/node").exists()
                                    else None)
    return Tools(python=sys.executable, node=node)


def real_home() -> Path:
    """The user's home folder from the password database, whatever $HOME says."""
    return Path(pwd.getpwuid(os.getuid()).pw_dir).resolve()


def _sb_str(path) -> str:
    return '"' + str(path).replace("\\", "\\\\").replace('"', '\\"') + '"'


def sandbox_profile(write_dirs: Sequence[Path], home: Path) -> str:
    """No network; no signal to a process outside this sandbox; writes only under write_dirs (and the
    null devices); no reading of file contents under `home` except write_dirs. Paths must be real
    paths (sandbox-exec matches resolved paths)."""
    dirs = " ".join(f"(subpath {_sb_str(d)})" for d in write_dirs)
    return ("(version 1)\n(allow default)\n(deny network*)\n"
            "(deny signal)\n(allow signal (target same-sandbox))\n(deny file-write*)\n"
            f"(allow file-write* {dirs} (literal \"/dev/null\") (literal \"/dev/zero\") "
            "(literal \"/dev/tty\") (literal \"/dev/dtracehelper\") (regex #\"^/dev/fd/\"))\n"
            f"(deny file-read-data (subpath {_sb_str(home)}))\n"
            f"(allow file-read-data {dirs})\n")


def minimal_env(scratch: Path, tools: Tools) -> dict:
    path = []
    for b in (tools.python, tools.node):
        if b:
            d = str(Path(b).parent)
            if d not in path:
                path.append(d)
    path += ["/usr/bin", "/bin"]
    return {"PATH": ":".join(path), "HOME": str(scratch), "TMPDIR": str(scratch) + "/",
            "LANG": "en_US.UTF-8", "PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1", "CI": "1"}


class InfraError(Exception):
    """The runner cannot start (binary missing); becomes the word check_infra."""


@dataclass
class Spawned:
    exit_code: int | None
    output: str
    seconds: float
    timed_out: bool


LOG_MAX_BYTES = 64 * 1024 * 1024     # a run whose output grows past this is stopped like a time-out
LOG_TAIL_BYTES = 64 * 1024           # only this much of the output is ever read into memory
POLL_S = 0.1


def read_tail(path: Path, limit: int = LOG_TAIL_BYTES) -> str:
    """The last `limit` bytes of a file, decoded; never the whole file."""
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - limit))
            return f.read().decode("utf-8", "replace")
    except OSError:
        return ""


def _under(path: str, dirs: Sequence[str]) -> bool:
    return any(path == d or path.startswith(d.rstrip("/") + "/") for d in dirs)


def stray_pids(dirs: Sequence[Path], open_files: Sequence[Path] = ()) -> set[int]:
    """Processes of this user that a run left behind outside its process group (a child that called
    setsid or setpgid): every process whose working folder is under one of `dirs`, or that still holds
    one of `open_files` open (the run's output file, inherited as stdout). Read with lsof; empty when
    lsof is missing. This process and its parent are never listed."""
    real = [os.path.realpath(d) for d in dirs]
    pids: set[int] = set()
    lsof = shutil.which("lsof") or ("/usr/sbin/lsof" if Path("/usr/sbin/lsof").exists() else None)
    if not lsof:
        return pids
    try:
        r = subprocess.run([lsof, "-n", "-P", "-w", "-u", str(os.getuid()), "-a", "-d", "cwd", "-F", "pn"],
                           capture_output=True, text=True, timeout=20, stdin=subprocess.DEVNULL)
        pid = None
        for line in r.stdout.splitlines():
            if line.startswith("p"):
                pid = int(line[1:]) if line[1:].isdigit() else None
            elif line.startswith("n") and pid and _under(line[1:], real):
                pids.add(pid)
        for f in open_files:
            if Path(f).exists():
                r = subprocess.run([lsof, "-n", "-P", "-w", "-t", "--", str(f)], capture_output=True,
                                   text=True, timeout=20, stdin=subprocess.DEVNULL)
                pids |= {int(x) for x in r.stdout.split() if x.isdigit()}
    except (OSError, subprocess.SubprocessError):
        return set()
    pids -= {os.getpid(), os.getppid()}
    return pids


def kill_strays(dirs: Sequence[Path], open_files: Sequence[Path] = ()) -> int:
    """SIGKILL every stray process of a finished run (stray_pids), twice in case one forked again."""
    killed = 0
    for _ in range(2):
        found = stray_pids(dirs, open_files)
        if not found:
            break
        for pid in found:
            try:
                os.kill(pid, signal.SIGKILL)
                killed += 1
            except (ProcessLookupError, PermissionError):
                pass
        time.sleep(POLL_S)
    return killed


def spawn_sandboxed(cmd: Sequence[str], cwd: Path, write_dirs: Sequence[Path], scratch: Path,
                    time_limit_s: float, tools: Tools, profile_fn: Callable | None = None) -> Spawned:
    """Run `cmd` in the sandbox. Stopped (SIGKILL to its process group) at the time limit or when its
    output passes LOG_MAX_BYTES (both read as timed_out). After it ends, strays outside the group
    (kill_strays over write_dirs and the output file) are killed too. Only the output's tail is read."""
    profile = (profile_fn or sandbox_profile)(write_dirs, real_home())
    log = scratch.parent / "output.txt"
    started = time.monotonic()
    timed_out = False
    with open(log, "wb") as out:
        proc = subprocess.Popen([tools.sandbox, "-p", profile, *cmd], cwd=str(cwd),
                                env=minimal_env(scratch, tools), stdin=subprocess.DEVNULL,
                                stdout=out, stderr=subprocess.STDOUT, start_new_session=True,
                                close_fds=True)
        try:
            while True:
                try:
                    proc.wait(timeout=POLL_S)
                    break
                except subprocess.TimeoutExpired:
                    if time.monotonic() - started >= time_limit_s:
                        timed_out = True
                        break
                    try:
                        if log.stat().st_size > LOG_MAX_BYTES:
                            timed_out = True
                            break
                    except OSError:
                        pass
        finally:
            ev.kill_group(proc)            # the whole group, also grandchildren left behind
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                pass
    kill_strays(write_dirs, [log])
    seconds = time.monotonic() - started
    return Spawned(proc.returncode, read_tail(log), seconds, timed_out)


def tail(text: str, limit: int = DETAIL_MAX) -> str:
    return text if len(text) <= limit else text[-limit:]


# -- missing names ---------------------------------------------------------------

MISSING_PATTERNS = [re.compile(p) for p in (
    r"cannot import name '([^']+)'",
    r"No module named '([^']+)'",
    r"has no attribute '([^']+)'",
    r"name '([^']+)' is not defined",
    r"No such file or directory: '([^']+)'",
    r"does not provide an export named '([^']+)'",
    r"Cannot find module '([^']+)'",
    r"Cannot find package '([^']+)'",
    r"Failed to resolve import \"([^\"]+)\"",
    r"Failed to load url (\S+) \(resolved id",                 # vitest 2.x: a relative import that is missing
    r"no such file or directory, (?:open|stat|lstat|scandir|access) '([^']+)'",
    r"ReferenceError: ([\w$]+) is not defined",
    r"\(reading '([^']+)'\)",
    r"TypeError: (?:\(0\s*,\s*)?([\w$.]+)\)? is not a (?:function|constructor)",
)]


def name_matches(found: str, name: str) -> bool:
    """Does the thing an error says is missing (`found`) match a listed name? Equal; the last dotted
    part of `mod.X`; a dotted module read as a path; a path's base name, with or without extension;
    or a path that ends with "/" + the name (with or without extensions on either side); for a
    relative import (./x, ../x) also the name's base name, since the import is relative to its test."""
    found, name = found.strip(), name.strip()
    if not found or not name:
        return False
    forms = {found}
    if "/" not in found and "." in found:
        forms.add(found.rsplit(".", 1)[-1])              # mod.X -> X
        forms.add(found.replace(".", "/"))               # pkg.sub -> pkg/sub
    for f in list(forms):
        base = f.rsplit("/", 1)[-1]
        forms |= {base, _strip_ext(base), _strip_ext(f)}
    wanted = {name, _strip_ext(name)}
    if wanted & forms:
        return True
    if found.startswith(("./", "../")):                  # a relative import: compare base names
        nb = name.rsplit("/", 1)[-1]
        if {nb, _strip_ext(nb)} & forms:
            return True
    return any(f.endswith("/" + w) for f in forms for w in wanted)


def _strip_ext(p: str) -> str:
    head, _, base = p.rpartition("/")
    if "." in base[1:]:
        base = base[:base.rfind(".")]
    return f"{head}/{base}" if head else base


def missing_name_in(text: str, names: Iterable[str]) -> bool:
    names = [n for n in names if n]
    for pat in MISSING_PATTERNS:
        for m in pat.finditer(text or ""):
            if any(name_matches(m.group(1), n) for n in names):
                return True
    return False


def load_word(load_texts: Sequence[str], names: Iterable[str]) -> str:
    """Every file that failed to load must have failed only because of a listed name."""
    names = list(names)
    return ("load_error_missing_name" if load_texts and all(missing_name_in(t, names) for t in load_texts)
            else "load_error")


def decide(load_texts: Sequence[str], tests: int, failed: int, names) -> str:
    if load_texts:
        return load_word(load_texts, names)
    if failed > 0:
        return "fail"
    if tests == 0:
        return "no_tests"
    return "pass"


# -- runner adapters ---------------------------------------------------------------

@dataclass
class Parsed:
    result: str
    tests: int | None
    failed: int | None
    detail: str | None = None          # replaces the output tail when set


class PytestAdapter:
    name = "pytest"

    def prepare(self, scratch: Path) -> None:
        pass

    def command(self, tree: Path, cwd: Path, files: Sequence[str], scratch: Path, tools: Tools) -> list:
        if not tools.python or not Path(tools.python).exists():
            raise InfraError("python missing")
        return [tools.python, "-m", "pytest", *files, "-q", "-p", "no:cacheprovider", "-o", "addopts=",
                "-W", "ignore", f"--junitxml={scratch / 'r.xml'}"]

    def parse(self, exit_code: int | None, scratch: Path, output: str, names, files, cwd) -> Parsed:
        return parse_pytest(exit_code, _read_or_none(scratch / "r.xml"), output, names)


def _read_or_none(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def parse_pytest(exit_code: int | None, junit: str | None, output: str, names) -> Parsed:
    import xml.etree.ElementTree as ET
    passed = failed = 0
    load_texts: list[str] = []
    if junit:
        try:
            root = ET.fromstring(junit)
        except ET.ParseError:
            root = None
        if root is not None:
            for case in root.iter("testcase"):
                err = case.find("error")
                fail = case.find("failure")
                if err is not None and (err.get("message") or "") == "collection failure":
                    load_texts.append((err.text or "") + "\n" + (err.get("message") or ""))
                elif case.find("skipped") is not None and fail is None and err is None:
                    continue
                elif fail is not None or err is not None:
                    failed += 1
                else:
                    passed += 1
    if exit_code is not None and exit_code < 0:
        return Parsed("fail", passed + failed or None, failed or None)
    if junit is None and exit_code not in (2, 3, 4, 5):
        return Parsed("check_infra", None, None)
    if exit_code in (2, 3, 4) and not load_texts:
        load_texts = [output]
    if exit_code == 5 and not load_texts:
        return Parsed("no_tests", 0, 0)
    tests = passed + failed
    if exit_code == 1 and failed == 0 and not load_texts:
        return Parsed("fail", tests, failed)
    return Parsed(decide(load_texts, tests, failed, names), tests, failed)


NODE_REPORTER = r"""
export default async function* reporter(source) {
  for await (const ev of source) {
    const d = ev.data || {};
    if (ev.type === 'test:pass' || ev.type === 'test:fail') {
      const det = d.details || {};
      const err = det.error;
      yield JSON.stringify({ event: ev.type === 'test:pass' ? 'pass' : 'fail', file: d.file ?? null,
        name: String(d.name ?? ''), nesting: d.nesting ?? 0, kind: det.type ?? null,
        skip: d.skip !== undefined && d.skip !== false, todo: d.todo !== undefined && d.todo !== false,
        failure: err ? (err.failureType ?? null) : null }) + '\n';
    } else if (ev.type === 'test:stderr' || ev.type === 'test:stdout') {
      yield JSON.stringify({ event: ev.type === 'test:stderr' ? 'stderr' : 'stdout', file: d.file ?? null,
        message: String(d.message ?? '') }) + '\n';
    }
  }
}
"""


class NodeTestAdapter:
    name = "node-test"

    def prepare(self, scratch: Path) -> None:
        (scratch / "reporter.mjs").write_text(NODE_REPORTER, encoding="utf-8")

    def command(self, tree, cwd, files, scratch, tools) -> list:
        if not tools.node or not Path(tools.node).exists():
            raise InfraError("node missing")
        return [tools.node, "--test", "--test-reporter=tap", "--test-reporter-destination=stdout",
                f"--test-reporter={scratch / 'reporter.mjs'}",
                f"--test-reporter-destination={scratch / 'events.jsonl'}",
                *(glob_escape(f) for f in files)]

    def parse(self, exit_code, scratch, output, names, files, cwd) -> Parsed:
        return parse_node_events(exit_code, _read_or_none(scratch / "events.jsonl"), output, names,
                                 files, cwd)


GLOB_CHARS = "*?[]{}"


def glob_escape(path: str) -> str:
    """node --test reads its arguments as globs: put every glob character in a class of its own, so
    a file such as r/[id].test.mjs is run as itself."""
    return "".join(f"[{c}]" if c in GLOB_CHARS else c for c in str(path))


def _norm_file(f, cwd: Path) -> str:
    p = Path(f) if os.path.isabs(str(f)) else Path(cwd) / str(f)
    return os.path.realpath(p)


def parse_node_events(exit_code, events_text: str | None, output: str, names, files, cwd) -> Parsed:
    events = []
    for line in (events_text or "").splitlines():
        try:
            events.append(json.loads(line))
        except ValueError:
            continue
    wanted = {_norm_file(f, cwd): str(f) for f in files}
    labels = {}
    for norm, given in wanted.items():
        labels[norm] = {given, glob_escape(given), os.path.relpath(norm, os.path.realpath(cwd)), norm}
    per_file: dict[str, dict] = {}

    def slot(f):
        key = _norm_file(f, cwd) if f else "?"
        return per_file.setdefault(key, {"real": 0, "file_fail": False, "file_pass": False,
                                         "passed": 0, "failed": 0, "suite_fail": 0, "stderr": []})

    for e in events:
        s = slot(e.get("file"))
        if e.get("event") in ("stderr", "stdout"):
            s["stderr"].append(e.get("message", ""))
            continue
        key = _norm_file(e.get("file"), cwd) if e.get("file") else "?"
        is_file_level = (e.get("nesting", 0) == 0 and e.get("kind") == "test"
                         and e.get("name") in labels.get(key, set()))
        if is_file_level:
            s["file_fail" if e["event"] == "fail" else "file_pass"] = True
            continue
        if e.get("kind") == "suite":
            if e["event"] == "fail" and e.get("failure") != "subtestsFailed":
                s["suite_fail"] += 1
            continue
        s["real"] += 1
        if e.get("skip") or e.get("todo"):
            continue
        s["passed" if e["event"] == "pass" else "failed"] += 1
    passed = failed = 0
    load_texts = []
    for key, s in per_file.items():
        passed += s["passed"]
        failed += s["failed"]
        if s["suite_fail"] and not s["failed"]:
            failed += 1
        if s["file_fail"]:
            if s["real"] == 0:
                load_texts.append("".join(s["stderr"]))
            else:
                failed += 1
    tests = passed + failed
    unreported = [given for norm, given in wanted.items() if norm not in per_file]
    if unreported:                      # a requested file that never reported did not load
        load_texts.append(("no result for " + ", ".join(unreported)) if per_file else (output or "no result"))
    if not load_texts and exit_code not in (0, None) and failed == 0:
        if tests == 0:
            load_texts = [output]
        else:
            return Parsed("fail", tests, failed)
    return Parsed(decide(load_texts, tests, failed, names), tests, failed)


class VitestAdapter:
    name = "vitest"

    def prepare(self, scratch: Path) -> None:
        pass

    @staticmethod
    def binary(tree: Path, cwd: Path) -> Path | None:
        here = Path(cwd)
        tree = Path(tree)
        while True:
            cand = here / "node_modules" / ".bin" / "vitest"
            if cand.exists():
                return cand
            if here == tree or tree not in here.parents:
                return None
            here = here.parent

    def command(self, tree, cwd, files, scratch, tools) -> list:
        if not tools.node or not Path(tools.node).exists():
            raise InfraError("node missing")
        binary = self.binary(tree, cwd)
        if binary is None:
            raise InfraError("vitest missing")
        return [str(binary), "run", *files, "--reporter=json", f"--outputFile={scratch / 'r.json'}"]

    def parse(self, exit_code, scratch, output, names, files, cwd) -> Parsed:
        return parse_vitest_json(exit_code, _read_or_none(scratch / "r.json"), output, names, files, cwd)


def parse_vitest_json(exit_code, json_text: str | None, output: str, names, files=None, cwd=None) -> Parsed:
    """With `files` (paths relative to `cwd`): vitest reads its file arguments as SUBSTRING filters, so
    a result for any other file is dropped, and a requested file with no result did not load. When a
    dropped file failed, the exit code and `success` say nothing about the requested files and are
    not read."""
    try:
        data = json.loads(json_text) if json_text else None
    except ValueError:
        data = None
    if not isinstance(data, dict):
        if "No test files found" in (output or ""):
            return Parsed("no_tests", 0, 0)
        return Parsed(load_word([output], names), None, None)
    passed = failed = 0
    load_texts, lines = [], []
    results = data.get("testResults") or []
    trust_exit = True
    if files is not None:
        wanted = {_norm_file(f, cwd): str(f) for f in files}
        kept, seen = [], set()
        for r in results:
            norm = _norm_file(r.get("name") or "?", cwd)
            if norm in wanted:
                kept.append(r)
                seen.add(norm)
            elif r.get("status") != "passed":
                trust_exit = False
        results = kept
        unreported = [g for n, g in wanted.items() if n not in seen]
        if unreported:
            load_texts.append("no result for " + ", ".join(unreported))
    for r in results:
        asserts = r.get("assertionResults") or []
        msg = r.get("message") or ""
        status = r.get("status")
        if not asserts:
            if status == "failed" and msg and not msg.startswith("No test suite found"):
                load_texts.append(msg)
                lines.append(f"FILE {r.get('name', '')}: {msg}")
            continue
        file_failed = 0
        for a in asserts:
            st = a.get("status")
            if st == "passed":
                passed += 1
            elif st == "failed":
                failed += 1
                file_failed += 1
                lines.append(f"FAIL {a.get('fullName') or a.get('title', '')}: "
                              + "\n".join(a.get("failureMessages") or []))
        if status == "failed" and file_failed == 0:
            failed += 1
            lines.append(f"FILE {r.get('name', '')}: {msg}")
    tests = passed + failed
    detail = "\n".join(lines + [f"tests {tests}, failed {failed}"])
    if not load_texts and failed == 0 and tests > 0 and trust_exit and \
            (exit_code not in (0, None) or data.get("success") is False):
        return Parsed("fail", tests, failed, detail)
    return Parsed(decide(load_texts, tests, failed, names), tests, failed, detail)


ADAPTERS = {"pytest": PytestAdapter(), "node-test": NodeTestAdapter(), "vitest": VitestAdapter()}


def _sandbox_refused(sp: Spawned) -> bool:
    head = sp.output.lstrip()[:200]
    return sp.exit_code in (65, 71, 126, 127) and head.startswith("sandbox-exec:")


def run_tests(tree_dir, runner: str, test_cwd: str, files: Sequence[str], time_limit_s: float,
              names: Iterable[str], *, tools: Tools | None = None,
              profile_fn: Callable | None = None) -> TestResult:
    """Run `files` (tree-relative) with `runner` in `tree_dir/test_cwd`, sandboxed. Never raises for a
    test outcome; an unusable runner is `check_infra`."""
    tools = tools or default_tools()
    adapter = ADAPTERS[runner]
    tree = Path(os.path.realpath(tree_dir))
    cwd = tree / test_cwd if test_cwd not in ("", ".") else tree
    if not files:                       # nothing to run: never let a runner fall back to "all tests"
        return TestResult("no_tests", 0, 0, 0.0, "no test file was given")
    missing = [f for f in files if not (tree / f).is_file()]
    if missing:                         # node and vitest would skip a missing file without a word
        return TestResult("load_error", None, None, 0.0, "test file missing: " + ", ".join(missing))
    run_dir = Path(os.path.realpath(tempfile.mkdtemp(prefix="code_bench-run-")))
    scratch = run_dir / "home"
    scratch.mkdir()
    started = time.monotonic()
    try:
        rel_files = [os.path.relpath(tree / f, cwd) for f in files]
        rel_files = ["./" + f if f.startswith("-") else f for f in rel_files]
        try:
            adapter.prepare(scratch)
            cmd = adapter.command(tree, cwd, rel_files, scratch, tools)
            if not Path(tools.sandbox).exists():
                raise InfraError("sandbox-exec missing")
        except InfraError as e:
            return TestResult("check_infra", None, None, round(time.monotonic() - started, 3), str(e))
        try:
            sp = spawn_sandboxed(cmd, cwd, [tree, scratch], scratch, time_limit_s, tools, profile_fn)
        except OSError as e:
            return TestResult("check_infra", None, None, round(time.monotonic() - started, 3), str(e))
        secs = round(sp.seconds, 3)
        if _sandbox_refused(sp):
            return TestResult("check_infra", None, None, secs, tail(sp.output))
        if sp.timed_out:
            return TestResult("timeout", None, None, secs, tail(sp.output))
        p = adapter.parse(sp.exit_code, scratch, sp.output, list(names), rel_files, cwd)
        detail = tail(sp.output if p.detail is None else p.detail + "\n" + sp.output)
        return TestResult(p.result, p.tests, p.failed, secs, detail)
    finally:
        shutil.rmtree(run_dir, ignore_errors=True)


# -- trees, copies, overlays ---------------------------------------------------------

def clone_tree(src: Path, dst: Path) -> None:
    """`cp -cR src dst` (copy-on-write on APFS); a plain copy when clonefile is not possible."""
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(["cp", "-cR", str(src), str(dst)], capture_output=True)
    if r.returncode != 0:
        shutil.rmtree(dst, ignore_errors=True)
        shutil.copytree(src, dst, symlinks=True)


def _ignored_dir(name: str) -> bool:
    return name in IGNORED_DIR_NAMES or name.startswith(IGNORED_DIR_PREFIXES)


def file_sha(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def tree_index(tree: Path) -> tuple[dict, dict]:
    """({rel: sha256} of regular files, {rel: link target} of symlinks); ignored folders skipped."""
    files, links = {}, {}
    tree = Path(tree)
    for dirpath, dirnames, filenames in os.walk(tree, followlinks=False):
        rel_dir = os.path.relpath(dirpath, tree)
        keep = []
        for d in dirnames:
            full = os.path.join(dirpath, d)
            rel = d if rel_dir == "." else f"{rel_dir}/{d}"
            if os.path.islink(full):
                links[rel] = os.readlink(full)
            elif not _ignored_dir(d):
                keep.append(d)
        dirnames[:] = keep
        for fn in filenames:
            full = os.path.join(dirpath, fn)
            rel = fn if rel_dir == "." else f"{rel_dir}/{fn}"
            if os.path.islink(full):
                links[rel] = os.readlink(full)
            elif os.path.isfile(full):
                files[rel] = file_sha(Path(full))
    return files, links


@dataclass(frozen=True)
class Overlay:
    """What a copy changed against the start tree. `files` maps tree-relative path -> sha256."""
    files: dict
    deleted: tuple
    symlinks_ignored: int

    def paths(self) -> list[str]:
        return sorted(self.files) + list(self.deleted)


def overlay_of(copy: Path, start_tree: Path) -> Overlay:
    cfiles, clinks = tree_index(copy)
    sfiles, slinks = tree_index(start_tree)
    changed = {rel: sha for rel, sha in cfiles.items() if sfiles.get(rel) != sha}
    deleted = tuple(sorted(rel for rel in sfiles if rel not in cfiles))
    new_links = sum(1 for rel, target in clinks.items() if slinks.get(rel) != target)
    return Overlay(changed, deleted, new_links)


def overlay_contents(copy: Path, overlay: Overlay) -> dict:
    """{rel: bytes} of an overlay's files, read from the copy (to store a run's overlay)."""
    return {rel: (Path(copy) / rel).read_bytes() for rel in sorted(overlay.files)}


def _glob_regex(pattern: str) -> re.Pattern:
    i, out = 0, []
    p = pattern.strip("/")
    if pattern.endswith("/") and p:      # "tests/" = everything under tests
        p += "/**"
    while i < len(p):
        c = p[i]
        if p.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif p.startswith("**", i):
            out.append(".*")
            i += 2
        elif c == "*":
            out.append("[^/]*")
            i += 1
        elif c == "?":
            out.append("[^/]")
            i += 1
        elif c == "[":
            j = p.find("]", i + 1)
            if j == -1:
                out.append(re.escape(c))
                i += 1
            else:
                body = p[i + 1:j]
                if body.startswith("!"):
                    body = "^" + body[1:]
                out.append("[" + body.replace("\\", "\\\\") + "]")
                i = j + 1
        else:
            out.append(re.escape(c))
            i += 1
    return re.compile("^" + "".join(out) + "$")


def matches_patterns(path: str, patterns: Iterable[str]) -> bool:
    """Glob match on the whole tree-relative path: `*` and `?` stay inside one folder, `**` spans
    folders, `**/` also matches no folder at all."""
    path = path.strip("/")
    return any(_glob_regex(p).match(path) for p in patterns)


def source_unchanged(overlay: Overlay, test_patterns: Iterable[str]) -> bool:
    """Rules, question 4: no changed, new or deleted path outside the test patterns."""
    pats = list(test_patterns)
    return all(matches_patterns(p, pats) for p in overlay.paths())


def _write_file(path: Path, data, mode: int | None = None) -> None:
    """Write bytes, or copy a source file, to `path`. The file mode is `mode` when given; else the
    source file's mode; else the mode of the file it replaces (an executable stays executable)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    old_mode = None
    if path.is_symlink() or path.is_file():
        if not path.is_symlink():
            old_mode = path.stat().st_mode & 0o7777
        path.unlink()
    if isinstance(data, (bytes, bytearray)):
        path.write_bytes(data)
        keep = mode if mode is not None else old_mode
    else:
        shutil.copyfile(data, path)
        keep = mode if mode is not None else os.stat(data).st_mode & 0o7777
    if keep is not None:
        os.chmod(path, keep)


def _remove(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)


_OUTWARD_LINKS: dict = {}


def outward_links(src: Path) -> list[tuple[str, str]]:
    """[(rel, target)] of the symlinks under src whose target is absolute or climbs out of src (read
    once per folder and cached)."""
    key = os.path.realpath(src)
    if key not in _OUTWARD_LINKS:
        found = []
        for dirpath, dirnames, filenames in os.walk(key, followlinks=False):
            for name in dirnames + filenames:
                full = os.path.join(dirpath, name)
                if os.path.islink(full):
                    target = os.readlink(full)
                    resolved = os.path.normpath(os.path.join(dirpath, target))
                    if os.path.isabs(target) or not _under(resolved, [key]):
                        found.append((os.path.relpath(full, key), target))
        _OUTWARD_LINKS[key] = found
    return _OUTWARD_LINKS[key]


def clone_node_modules(src: Path, dst: Path) -> int:
    """Clone a node_modules folder; a symlink that points into the source folder by an absolute path
    is re-pointed (relative) into the clone, and one that points anywhere else outside the clone is
    removed, because the sandbox denies reading the owner's folders. Returns the links changed."""
    clone_tree(src, dst)
    real_src = os.path.realpath(src)
    changed = 0
    for rel, target in outward_links(src):
        link = Path(dst) / rel
        resolved = os.path.realpath(os.path.join(real_src, os.path.dirname(rel), target))
        try:
            link.unlink()
        except OSError:
            continue
        if _under(resolved, [real_src]):
            inside = Path(dst) / os.path.relpath(resolved, real_src)
            os.symlink(os.path.relpath(inside, link.parent), link)
        changed += 1
    return changed


def make_copy(work_dir: Path, base_tree: Path, overlay_files: Mapping[str, bytes | Path] | None = None,
              deleted: Iterable[str] = (), node_modules: Mapping | None = None) -> Path:
    """A fresh copy of base_tree under work_dir: deletions, then overlay files (bytes or a source
    file), then node_modules cloned to its place. Returns the copy's tree folder."""
    Path(work_dir).mkdir(parents=True, exist_ok=True)
    base = Path(tempfile.mkdtemp(prefix="copy-", dir=work_dir))
    tree = base / "tree"
    clone_tree(base_tree, tree)
    for rel in deleted:
        _remove(tree / rel)
    for rel, data in (overlay_files or {}).items():
        _write_file(tree / rel, data)
    if node_modules:
        dst = tree / node_modules["to"]
        _remove(dst)
        clone_node_modules(Path(node_modules["from"]), dst)
    return tree


def working_copy(work_dir: Path, start_tree: Path) -> Path:
    """The model's own working copy: a clone of the start tree WITHOUT node_modules."""
    return make_copy(work_dir, start_tree)


WORK_PREFIXES = ("copy-", "snap-")


def sweep_work(work: Path) -> int:
    """Remove the copies and snapshots a killed invocation left under --work. Called with evalkit's
    exclusive lock held, so no running command owns them. Only folders this tool names are touched."""
    n = 0
    try:
        children = list(Path(work).iterdir())
    except OSError:
        return 0
    for child in children:
        if child.name.startswith(WORK_PREFIXES) and child.is_dir() and not child.is_symlink():
            shutil.rmtree(child, ignore_errors=True)
            n += 1
    return n


def drop_copy(tree: Path) -> None:
    tree = Path(tree)
    shutil.rmtree(tree.parent if tree.name == "tree" else tree, ignore_errors=True)


def run_on_copy(work_dir: Path, task: "Task", base_tree: Path, overlay_files: Mapping[str, bytes | Path],
                run_files: Sequence[str], time_limit_s: float, deleted: Iterable[str] = (),
                tools: Tools | None = None, layers: Sequence[Mapping] = ()) -> TestResult:
    """make_copy + run_tests + drop_copy: every test run gets its own copy. `layers` are further
    {rel: bytes | Path} maps written in order over the overlay (a suite, the hidden tests)."""
    tree = make_copy(work_dir, base_tree, overlay_files, deleted, task.node_modules)
    try:
        for layer in layers:
            for rel, data in layer.items():
                _write_file(tree / rel, data)
        return run_tests(tree, task.runner, task.test_cwd, run_files, time_limit_s, task.names, tools=tools)
    finally:
        drop_copy(tree)


# -- task records -------------------------------------------------------------------

@dataclass(frozen=True)
class Task:
    code: str
    project_dir: Path
    before: str
    after: str
    language: str
    rating: str
    runner: str
    test_cwd: str
    hidden_tests: tuple
    run_files: tuple
    test_patterns: tuple
    runner_config: tuple
    source_files: tuple
    names: tuple
    node_modules: dict | None
    strip: tuple
    brief: str
    run_patterns: tuple = ()          # optional: which test-pattern files a runner gets as files to run


def _rel_ok(p) -> bool:
    if not isinstance(p, str) or not p or p.startswith("/") or "\\" in p or "\0" in p:
        return False
    return all(part not in ("..", "") for part in p.split("/")) or p == "."


def _str_list(rec: dict, key: str, rel=True) -> tuple:
    v = rec.get(key)
    if not isinstance(v, list) or not all(isinstance(x, str) and x for x in v):
        raise ValueError(key)
    if rel and not all(_rel_ok(x) and x != "." for x in v):
        raise ValueError(key)
    return tuple(v)


def validate_task(rec: dict) -> Task:
    """A task record as in the design, or BenchError("task_invalid", code). The detail names the field."""
    code = rec.get("code") if isinstance(rec, dict) else None
    code = code if isinstance(code, str) and CODE_RE.match(code) else None
    try:
        if code is None:
            raise ValueError("code")
        pd = rec.get("project_dir")
        if not isinstance(pd, str) or not os.path.isabs(pd):
            raise ValueError("project_dir")
        for k in ("before", "after"):
            if not isinstance(rec.get(k), str) or not COMMIT_RE.match(rec[k]):
                raise ValueError(k)
        for k, allowed in (("language", LANGUAGES), ("rating", RATINGS), ("runner", RUNNERS)):
            if rec.get(k) not in allowed:
                raise ValueError(k)
        if not _rel_ok(rec.get("test_cwd")):
            raise ValueError("test_cwd")
        hidden = _str_list(rec, "hidden_tests")
        run_files = _str_list(rec, "run_files")
        if not hidden or not run_files or not set(run_files) <= set(hidden):
            raise ValueError("run_files")
        patterns = _str_list(rec, "test_patterns", rel=False)
        if not patterns:
            raise ValueError("test_patterns")
        source = _str_list(rec, "source_files")
        if not source:
            raise ValueError("source_files")
        names = _str_list(rec, "names", rel=False)
        if not names:
            raise ValueError("names")
        nm = rec.get("node_modules")
        if nm is not None:
            if not (isinstance(nm, dict) and isinstance(nm.get("from"), str) and os.path.isabs(nm["from"])
                    and _rel_ok(nm.get("to")) and nm["to"] != "."):
                raise ValueError("node_modules")
            nm = {"from": nm["from"], "to": nm["to"]}
        brief = rec.get("brief")
        if not _rel_ok(brief):
            raise ValueError("brief")
        run_patterns = _str_list(rec, "run_patterns", rel=False) if "run_patterns" in rec else ()
        return Task(code=code, project_dir=Path(pd), before=rec["before"], after=rec["after"],
                    language=rec["language"], rating=rec["rating"], runner=rec["runner"],
                    test_cwd=rec["test_cwd"], hidden_tests=hidden, run_files=run_files,
                    test_patterns=patterns, runner_config=_str_list(rec, "runner_config"),
                    source_files=source, names=names, node_modules=nm,
                    strip=_str_list(rec, "strip"), brief=brief, run_patterns=run_patterns)
    except ValueError as e:
        raise BenchError("task_invalid", code, f"field {e}") from None


def load_tasks(root: Path) -> list[Task]:
    path = Path(root) / "tasks.json"
    if not path.is_file():
        raise BenchError("no_tasks")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        raise BenchError("task_invalid", None, "tasks.json is not JSON") from None
    recs = data.get("tasks") if isinstance(data, dict) else None
    if not isinstance(recs, list) or not recs:
        raise BenchError("no_tasks")
    tasks = [validate_task(r) for r in recs]
    codes = [t.code for t in tasks]
    if len(set(codes)) != len(codes):
        raise BenchError("task_invalid", None, "a code appears twice")
    return tasks


def task_dir(root: Path, code: str) -> Path:
    return Path(root) / "tasks" / code


def read_installed(root: Path, code: str) -> dict | None:
    p = task_dir(root, code) / "installed.json"
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


# -- git (read only) -------------------------------------------------------------------

def git(project_dir: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    """`git -C <project_dir> <sub> ...` with a read-only subcommand; anything else is refused."""
    if not args or args[0] not in GIT_SUBCOMMANDS:
        raise ValueError("git subcommand not allowed")
    if not os.path.isabs(str(project_dir)):
        raise ValueError("git needs an absolute path")
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    r = subprocess.run(["git", "-C", str(project_dir), *args], capture_output=True,
                       stdin=subprocess.DEVNULL, env=env)
    if check and r.returncode != 0:
        raise BenchError("git_failed", None, f"git {args[0]} exit {r.returncode}: "
                         + r.stderr.decode("utf-8", "replace")[-500:])
    return r


def git_file(project_dir: Path, commit: str, path: str) -> bytes | None:
    """The file's bytes at `commit`, or None when the commit does not have it."""
    if git(project_dir, "cat-file", "-e", f"{commit}:{path}", check=False).returncode != 0:
        return None
    return git(project_dir, "show", f"{commit}:{path}").stdout


def git_mode(project_dir: Path, commit: str, path: str) -> int:
    """0o755 when `git ls-tree` says the file is executable at `commit` (mode 100755), else 0o644."""
    r = git(project_dir, "ls-tree", commit, "--", path, check=False)
    first = r.stdout.decode("utf-8", "replace").split(" ", 1)[0] if r.returncode == 0 else ""
    return 0o755 if first == "100755" else 0o644


def archive_into(project_dir: Path, commit: str, dest: Path) -> int:
    """Extract `git archive <commit>` into dest with tarfile's "data" filter. A symlink or hard link
    that the filter refuses (absolute, or pointing outside the tree) is skipped and counted; any other
    refusal or a broken archive is git_failed. Returns the number of links skipped."""
    git(project_dir, "rev-parse", "--verify", "--quiet", f"{commit}^{{commit}}")
    data = git(project_dir, "archive", "--format=tar", commit).stdout
    dest.mkdir(parents=True, exist_ok=True)
    skipped = []

    def keep_safe(member, path):
        try:
            return tarfile.data_filter(member, path)
        except tarfile.FilterError:
            if member.issym() or member.islnk():
                skipped.append(member.name)
                return None
            raise
    try:
        with tarfile.open(fileobj=io.BytesIO(data)) as tar:
            tar.extractall(dest, filter=keep_safe)
    except (tarfile.TarError, OSError) as e:
        raise BenchError("git_failed", None, f"archive could not be extracted: {e}") from None
    return len(skipped)


# -- install -------------------------------------------------------------------------------

def _roots_for_dirs(task: Task) -> list[str]:
    roots = [""]
    if task.test_cwd not in (".", ""):
        roots.append(task.test_cwd.rstrip("/") + "/")
    return roots


def strip_tree(tree: Path, task: Task) -> list[str]:
    """Remove the task's own strip entries (each must exist) and the fixed list of the rules.
    Returns the removed tree-relative paths."""
    removed = []
    for rel in task.strip:
        p = tree / rel
        if not (p.exists() or p.is_symlink()):
            raise BenchError("strip_missing", task.code, f"strip entry missing: {rel}")
        _remove(p)
        removed.append(rel)
    for root in _roots_for_dirs(task):
        for d in FIXED_STRIP_DIRS_AT_ROOTS:
            p = tree / (root + d)
            if p.exists() or p.is_symlink():
                _remove(p)
                removed.append(root + d)
    for dirpath, dirnames, filenames in os.walk(tree):
        rel_dir = os.path.relpath(dirpath, tree)
        for d in list(dirnames):
            if d in FIXED_STRIP_DIRS_ANYWHERE:
                _remove(Path(dirpath) / d)
                dirnames.remove(d)
                removed.append(d if rel_dir == "." else f"{rel_dir}/{d}")
        for fn in filenames:
            if fn.lower() in FIXED_STRIP_FILES_LOWER:
                _remove(Path(dirpath) / fn)
                removed.append(fn if rel_dir == "." else f"{rel_dir}/{fn}")
    return removed


def token_re(name: str) -> re.Pattern:
    """A name as a whole token: not inside a longer identifier."""
    return re.compile(rb"(?<![A-Za-z0-9_$])" + re.escape(name.encode("utf-8")) + rb"(?![A-Za-z0-9_$])")


def added_names(names: Iterable[str], before_sources: Iterable[bytes]) -> list[str]:
    blobs = [b for b in before_sources if b]
    return [n for n in names if not any(token_re(n).search(b) for b in blobs)]


def is_prose(rel: str) -> bool:
    """A file people write notes in: Markdown or plain text by its ending, or a name with no ending."""
    base = os.path.basename(rel).lower()
    return base.endswith(PROSE_ENDINGS) or "." not in base


def find_leaks(tree: Path, names: Iterable[str]) -> list[tuple[str, str]]:
    """[(name, tree-relative path)]: the notes that mention a name the project does not have yet.
    A name counts as found in a file when it is a whole token of the file's contents or of its path.
    Found in any file that is not prose (code, a test, data, configuration): the project already has
    the name, the change does not add it, and it is never a leak. Found in prose files only: every
    such file is a hit."""
    pats = [(n, token_re(n)) for n in names]
    if not pats:
        return []
    notes: dict[str, list[str]] = {n: [] for n, _ in pats}
    existing: set[str] = set()
    for dirpath, dirnames, filenames in os.walk(tree):
        for fn in filenames:
            full = Path(dirpath) / fn
            rel = os.path.relpath(full, tree)
            rel_bytes = rel.encode("utf-8", "surrogateescape")
            prose = is_prose(rel)
            data = b"" if full.is_symlink() or not full.is_file() else full.read_bytes()
            for n, pat in pats:
                if n in existing:
                    continue
                in_path = bool(pat.search(rel_bytes))
                if not in_path and not pat.search(data):
                    continue
                if prose:
                    notes[n].append(rel + (" (its path)" if in_path else ""))
                else:
                    existing.add(n)
    return [(n, path) for n, _ in pats if n not in existing for path in sorted(notes[n])]


def task_hash(start: Path, hidden: Path, brief: bytes) -> str:
    h = hashlib.sha256()
    for label, tree in (("start", start), ("hidden", hidden)):
        files, links = tree_index(tree)
        for rel in sorted(files):
            h.update(f"{label}\0{rel}\0{files[rel]}\n".encode("utf-8"))
        for rel in sorted(links):
            h.update(f"{label}-link\0{rel}\0{links[rel]}\n".encode("utf-8"))
    h.update(b"brief\0" + hashlib.sha256(brief).hexdigest().encode("ascii"))
    return h.hexdigest()


def _hidden_overlay(hidden: Path) -> dict:
    files, _ = tree_index(hidden)
    return {rel: hidden / rel for rel in files}


def build_task_trees(task: Task, root: Path) -> dict:
    """Build start/, reference/ and hidden/ for one task (replacing old ones). Returns
    {"before_sources": [bytes], "stripped": int}."""
    tdir = task_dir(root, task.code)
    staging = tdir.parent / f".{task.code}.building"
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    try:
        start = staging / "start"
        links_skipped = archive_into(task.project_dir, task.before, start)
        git(task.project_dir, "rev-parse", "--verify", "--quiet", f"{task.after}^{{commit}}")
        before_sources = [git_file(task.project_dir, task.before, p) for p in task.source_files]
        removed = strip_tree(start, task)
        for p, blob in zip(task.source_files, before_sources):
            if blob is not None and not (start / p).exists():
                raise BenchError("source_stripped", task.code, f"source file stripped: {p}")
        reference = staging / "reference"
        clone_tree(start, reference)
        for p, before_blob in zip(task.source_files, before_sources):
            blob = git_file(task.project_dir, task.after, p)
            if blob is None and before_blob is None:     # a typo in the record, not a deletion
                raise BenchError("task_invalid", task.code, f"source file at neither commit: {p}")
            if blob is None:
                _remove(reference / p)
            else:
                _write_file(reference / p, blob, git_mode(task.project_dir, task.after, p))
        hidden = staging / "hidden"
        hidden.mkdir()
        for p in task.hidden_tests:
            blob = git_file(task.project_dir, task.after, p)
            if blob is None:
                raise BenchError("hidden_missing", task.code, f"hidden test missing at after: {p}")
            _write_file(hidden / p, blob, git_mode(task.project_dir, task.after, p))
        tdir.mkdir(parents=True, exist_ok=True)
        for part in ("start", "reference", "hidden"):
            shutil.rmtree(tdir / part, ignore_errors=True)
            os.replace(staging / part, tdir / part)
        return {"before_sources": [b for b in before_sources if b is not None], "stripped": len(removed),
                "links_skipped": links_skipped}
    finally:
        shutil.rmtree(staging, ignore_errors=True)


@dataclass
class InstallOutcome:
    code: str
    ok: bool
    reason: str | None
    start: TestResult | None = None
    reference: list = field(default_factory=list)


def write_install_failure(root: Path, code: str, reason: str) -> None:
    """installed.json for a task that failed before its checks: ok false and the reason word."""
    ev.write_json_atomic(task_dir(root, code) / "installed.json",
                         {"code": code, "ok": False, "reason": reason, "installed_at": ev.now()})


def install_task(app: "App", task: Task) -> InstallOutcome:
    tdir = task_dir(app.root, task.code)
    (tdir / "installed.json").unlink(missing_ok=True)    # an old ok must never outlive a failed rebuild
    brief_path = app.root / task.brief
    if not brief_path.is_file():
        raise BenchError("brief_missing", task.code)
    built = build_task_trees(task, app.root)
    start, reference, hidden = tdir / "start", tdir / "reference", tdir / "hidden"
    out = InstallOutcome(task.code, False, None)
    info = {"code": task.code, "ok": False, "reason": None, "installed_at": ev.now(),
            "start_files": len(tree_index(start)[0]), "hidden_files": len(tree_index(hidden)[0]),
            "stripped": built["stripped"], "links_skipped": built.get("links_skipped", 0),
            "task_hash": task_hash(start, hidden, brief_path.read_bytes())}
    added = added_names(task.names, built["before_sources"])
    leaks = find_leaks(start, added)
    info["names_added"] = len(added)
    if leaks:
        app.records.note(task.code, "leak", "; ".join(f"{n} in {p}" for n, p in leaks[:20]))
        out.reason = "leak"
    else:
        overlay = _hidden_overlay(hidden)
        res = run_on_copy(app.work, task, start, overlay, task.run_files, INSTALL_TIME_LIMIT_S,
                          tools=app.tools)
        out.start = res
        app.records.check(step="install", task=task.code, what="install_start", res=res, run=1)
        info.update(start_result=res.result, start_seconds=res.seconds)
        if res.result == "check_infra":      # the runner failed, not the task
            out.reason = "check_infra"
        elif not res.red:
            out.reason = "start_not_red"
        else:
            for n in range(1, REFERENCE_RUNS + 1):
                r = run_on_copy(app.work, task, reference, overlay, task.run_files, INSTALL_TIME_LIMIT_S,
                                tools=app.tools)
                out.reference.append(r)
                app.records.check(step="install", task=task.code, what="install_reference", res=r, run=n)
                if r.result != "pass":
                    out.reason = {"timeout": "reference_slow", "check_infra": "check_infra"}.get(
                        r.result, "reference_fails")
                    break
            info["reference_runs"] = len(out.reference)
            info["reference_passes"] = sum(1 for r in out.reference if r.result == "pass")
            if out.reason is None:
                info["reference_seconds"] = max(r.seconds for r in out.reference)
                info["reference_tests"] = out.reference[-1].tests
                info["time_limit_s"] = time_limit_for(info["reference_seconds"])
    out.ok = out.reason is None
    info.update(ok=out.ok, reason=out.reason)
    ev.write_json_atomic(tdir / "installed.json", info)
    return out


# -- records --------------------------------------------------------------------------------

def _is_scalar(v) -> bool:
    return v is None or isinstance(v, (bool, int, float, str))


def public_line(line: dict) -> dict:
    """Refuse anything that is not a fixed word, a number, a bool or null in the fixed keys."""
    kind = line.get("kind")
    keys = CHECK_KEYS if kind == "check" else MODEL_KEYS if kind == "model" else None
    if keys is None or set(line) != set(keys):
        raise ValueError("public line: wrong keys")
    for k, v in line.items():
        if not _is_scalar(v):
            raise ValueError(f"public line: {k} is not a scalar")
    checks = {
        "step": lambda v: v in (CHECK_STEPS if kind == "check" else MODEL_STEPS),
        "task": lambda v: isinstance(v, str) and bool(CODE_RE.match(v)),
        "cell": lambda v: v is None or (isinstance(v, str) and bool(CELL_RE.match(v))),
        "arm": lambda v: v is None or v in ARMS,
        "what": lambda v: v in CHECK_WHATS,
        "suite": lambda v: v is None or (isinstance(v, str) and bool(SUITE_RE.match(v))),
        "result": lambda v: v in CHECK_RESULT_WORDS,
        "reason": lambda v: v is None or v in MODEL_REASONS,
        "cli_version": lambda v: v is None or (isinstance(v, str) and bool(VERSION_RE.match(v))),
        "ts": lambda v: isinstance(v, str) and bool(TS_RE.match(v)),
        "kind": lambda v: True,
    }
    for k, v in line.items():
        if k in checks:
            if not checks[k](v):
                raise ValueError(f"public line: {k} is not from its vocabulary")
        elif isinstance(v, str):
            raise ValueError(f"public line: {k} may not be text")
    return line


class Records:
    """The public record (scalars and fixed words) and the private attempts.jsonl (plus detail)."""

    def __init__(self, public_path: Path, private_path: Path):
        self.public_path, self.private_path = Path(public_path), Path(private_path)

    def _write(self, line: dict, detail, extra: Mapping | None = None) -> dict:
        public_line(line)
        ev.append_jsonl(self.public_path, line)
        private = dict(line, detail=detail)
        if extra:
            private.update(extra)
        ev.append_jsonl(self.private_path, private)
        return line

    def check(self, *, step: str, task: str, what: str, res: TestResult | None = None,
              result: str | None = None, cell=None, arm=None, run=None, try_=None, suite=None,
              extra: Mapping | None = None) -> dict:
        line = {"kind": "check", "step": step, "task": task, "cell": cell, "arm": arm, "run": run,
                "try": try_, "what": what, "suite": suite,
                "result": result if result is not None else res.result,
                "tests": res.tests if res else None, "failed": res.failed if res else None,
                "seconds": res.seconds if res else None, "ts": ev.now()}
        return self._write(line, res.detail if res else None, extra)

    def model(self, fields: Mapping, detail=None, extra: Mapping | None = None) -> dict:
        """Missing keys become null; a key outside MODEL_KEYS is refused (it may be private text)."""
        unknown = set(fields) - set(MODEL_KEYS)
        if unknown:
            raise ValueError("model line: unknown keys")
        line = {k: fields.get(k) for k in MODEL_KEYS}
        line["kind"] = "model"
        line["ts"] = fields.get("ts") or ev.now()
        return self._write(line, detail, extra)

    def note(self, task: str | None, event: str, detail: str) -> None:
        """A private-only line (a leak's names, a failure's text, a traceback)."""
        ev.append_jsonl(self.private_path, {"kind": "note", "task": task, "event": event,
                                            "detail": detail, "ts": ev.now()})


# -- selftest --------------------------------------------------------------------------------

PY_CANARY = '''import os, socket

def test_ordinary_test_passes():
    assert 1 + 1 == 2

def test_tcp_connect_is_refused():
    s = socket.socket()
    try:
        s.connect(("127.0.0.1", 9))
    except PermissionError:
        return
    except OSError as e:
        raise AssertionError("not refused by the sandbox: " + repr(e))
    finally:
        s.close()
    raise AssertionError("connected")

def test_write_outside_the_tree_is_refused():
    try:
        with open(OUTSIDE, "w") as f:
            f.write("x")
    except PermissionError:
        return
    raise AssertionError("written")

def test_reading_the_home_folder_is_refused():
    try:
        os.listdir(HOME)
    except PermissionError:
        return
    raise AssertionError("listed")

def test_signal_to_an_outside_process_is_refused():
    import signal
    try:
        os.kill(OTHER_PID, signal.SIGTERM)
    except PermissionError:
        return
    raise AssertionError("signalled")
'''

JS_CANARY = '''import net from 'node:net';
import fs from 'node:fs';
const OUTSIDE = __OUTSIDE__;
const HOME = __HOME__;
test('ordinary test passes', () => { if (1 + 1 !== 2) throw new Error('math'); });
test('tcp connect is refused', async () => {
  const code = await new Promise((res) => { const s = net.connect(9, '127.0.0.1');
    s.on('connect', () => { s.destroy(); res('CONNECTED'); }); s.on('error', (e) => res(e.code)); });
  if (code !== 'EPERM') throw new Error('not refused: ' + code);
});
test('write outside the tree is refused', () => {
  let code = 'WRITTEN'; try { fs.writeFileSync(OUTSIDE, 'x'); } catch (e) { code = e.code; }
  if (code !== 'EPERM') throw new Error('not refused: ' + code);
});
test('reading the home folder is refused', () => {
  let code = 'LISTED'; try { fs.readdirSync(HOME); } catch (e) { code = e.code; }
  if (code !== 'EPERM') throw new Error('not refused: ' + code);
});
test('signal to an outside process is refused', () => {
  let code = 'SIGNALLED'; try { process.kill(OTHER_PID, 'SIGTERM'); } catch (e) { code = e.code; }
  if (code !== 'EPERM') throw new Error('not refused: ' + code);
});
'''

CANARY_TESTS = 5


def _canary_project(base: Path, runner: str, vitest_modules: Path | None, other_pid: int) -> tuple[Path, str]:
    tree = base / "tree"
    tree.mkdir(parents=True)
    outside = base / "outside.txt"
    home = str(real_home())
    if runner == "pytest":
        (tree / "test_canary.py").write_text(
            f"OUTSIDE = {str(outside)!r}\nHOME = {home!r}\nOTHER_PID = {int(other_pid)}\n" + PY_CANARY,
            encoding="utf-8")
        return tree, "test_canary.py"
    body = JS_CANARY.replace("__OUTSIDE__", json.dumps(str(outside))).replace("__HOME__", json.dumps(home))
    body = body.replace("const HOME", f"const OTHER_PID = {int(other_pid)};\nconst HOME", 1)
    if runner == "node-test":
        (tree / "canary.test.mjs").write_text("import { test } from 'node:test';\n" + body, encoding="utf-8")
        return tree, "canary.test.mjs"
    (tree / "package.json").write_text('{"type": "module", "private": true}\n', encoding="utf-8")
    clone_node_modules(vitest_modules, tree / "node_modules")
    (tree / "canary.test.mjs").write_text("import { test } from 'vitest';\n" + body, encoding="utf-8")
    return tree, "canary.test.mjs"


def vitest_reachable(path) -> Path | None:
    if not path:
        return None
    p = Path(path)
    return p if (p / ".bin" / "vitest").exists() else None


def selftest(work: Path, vitest_modules: Path | None = None, tools: Tools | None = None,
             profile_fn: Callable | None = None) -> dict:
    """{"pytest": word, "node-test": word, "vitest": word or "skipped", "ok": bool}. A runner's word is
    `pass` only when its run was `pass` with all five canary tests, the outside file does not exist and
    the helper process outside the sandbox (the target of the signal canary) is still alive."""
    report = {}
    Path(work).mkdir(parents=True, exist_ok=True)
    base_all = Path(os.path.realpath(tempfile.mkdtemp(prefix="selftest-", dir=work)))
    try:
        for runner in RUNNERS:
            if runner == "vitest" and vitest_reachable(vitest_modules) is None:
                report[runner] = "skipped"
                continue
            base = base_all / runner
            helper = subprocess.Popen(["/bin/sleep", "300"], stdin=subprocess.DEVNULL,
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                tree, test_file = _canary_project(base, runner, vitest_modules, helper.pid)
                res = run_tests(tree, runner, ".", [test_file], SELFTEST_TIME_LIMIT_S, (), tools=tools,
                                profile_fn=profile_fn)
                helper_alive = helper.poll() is None
            finally:
                helper.kill()
                helper.wait()
            escaped = (base / "outside.txt").exists() or not helper_alive
            good = res.result == "pass" and res.tests == CANARY_TESTS and res.failed == 0 and not escaped
            if good:
                report[runner] = "pass"
            elif escaped:
                report[runner] = "escaped"
            else:
                report[runner] = res.result if res.result != "pass" else "wrong_count"
            report[runner + "_detail"] = res.detail
    finally:
        shutil.rmtree(base_all, ignore_errors=True)
    report["ok"] = all(report[r] in ("pass", "skipped") for r in RUNNERS) and report["pytest"] == "pass" \
        and report["node-test"] == "pass"
    return report


def require_selftest(app: "App", need_vitest: bool = False) -> dict:
    """Fail closed. When a task in scope runs vitest, the vitest canary must have run and passed."""
    rep = selftest(app.work, app.vitest_modules, app.tools, app.profile_fn)
    if not rep["ok"] or (need_vitest and rep.get("vitest") != "pass"):
        app.records.note(None, "selftest_failed", json.dumps(rep)[-DETAIL_MAX:])
        raise BenchError("selftest_failed")
    return rep


# -- the model steps: the fixed plan --------------------------------------------------------------

T_CELLS = ("sonnet-5-5@high", "sonnet-5-5@xhigh", "opus-5-5@medium", "opus-5-5@high")
T_RUNS = 2
GIVEN_ORDER = tuple((c, r) for c in T_CELLS for r in range(1, T_RUNS + 1))
C_PLAN = (("haiku-5-5@medium", ("A", "B"), 4),
          ("haiku-5-5@high", ("A", "B", "C"), 4),
          ("sonnet-5-5@low", ("A", "B"), 3),
          ("sonnet-5-5@medium", ("B",), 3),
          ("opus-5-5@high", ("B",), 1))
C_CELLS = tuple(c for c, _, _ in C_PLAN)
C_ROUNDS = max(n for _, _, n in C_PLAN)
MAX_TRIES = {"T": 3, "A": 1, "B": 3, "C": 3}
MAX_ATTEMPTS = 3
FIT_REFERENCE_RUNS = 2
DEFAULT_MAX_USD = 226.0
REQUIRED_VERSION = "2.1.325"
MODEL_TOOLS = "Read,Grep,Glob,Write,Edit"
PERMISSION_FLAGS = ("--permission-mode", "dontAsk", "--allowedTools", "Read", "Grep", "Glob", "Write", "Edit")
OWN_REASONS = ("no_own_tests", "no_runnable", "own_not_red")

# The runner's own naming rule: which files of a suite are handed to the runner as files to run (the
# other suite files are helpers and fixtures, put in place but not run). A task may override it with
# `run_patterns`.
RUN_PATTERNS = {
    "pytest": ("**/test_*.py", "**/*_test.py"),
    "node-test": ("**/*.test.*", "**/*.spec.*", "**/*-test.*", "**/*_test.*", "**/test-*.*", "**/test.*"),
    "vitest": ("**/*.test.*", "**/*.spec.*"),
}
JS_TEST_EXT = re.compile(r"\.[cm]?[jt]sx?$")

# -- the fixed prompts (public: they name no task detail; the brief is inserted from the private file)

SYSTEM_PROMPT = ("You are a careful software engineer working in the project in your working directory. "
                 "You have file tools only: you can read, search, write and edit files, and you cannot run "
                 "anything. Work only from the brief and the files.")
INSTRUCTIONS = {
    "T": ("Write the tests for this change, in the project's own test style and test folders. The tests "
          "must fail on the code as it is now and pass once the change is made. Do not change any source "
          "file."),
    "A": "Make this change in the source files. Do not write or change tests.",
    "B": ("The test files listed below were written for this change. Read them first. Make them pass by "
          "changing the source files. Do not change these test files or the test runner's configuration."),
    "C": ("First write tests for this change, in the project's own test style and test folders; they must "
          "fail on the code as it is now. Then change the source files so that they pass."),
}
DONE_LINE = "When you are done, answer with the single word DONE."
RETRY_LINE = "Your previous try did not pass its check. The files are as you left them. Output of the check:"
NOTE_NO_TESTS = "No test file was added or changed, so there was nothing to check."
NOTE_NO_RUNNABLE = "No added or changed file is a test file that the test runner would run."
NOTE_LOCKED = ("A listed test file or a configuration file of the test runner was changed. It has been put "
               "back as it was, and this try counts as failed.")
NOTE_OWN_NOT_RED = ("Your tests passed on the code as it was before your change, so they do not test the "
                    "change. Output of your tests on the code before the change:")


def build_prompt(kind: str, brief: str, suite_paths: Sequence[str] = (), feedback: str | None = None) -> str:
    """The brief, the fixed instruction of the step or arm, the given suite's paths (arm B), the DONE
    line and, on a later try, the retry line with the check's output tail (at most DETAIL_MAX)."""
    text = brief.rstrip() + "\n\n" + INSTRUCTIONS[kind]
    if kind == "B":
        text += "\n\n" + "\n".join(f"- {p}" for p in suite_paths)
    text += "\n\n" + DONE_LINE
    if feedback is not None:
        text += "\n\n" + RETRY_LINE + "\n" + tail(feedback, DETAIL_MAX)
    return text


def with_note(note: str, output: str) -> str:
    """The note that says why a try failed, then the check's output cut so that note and output together
    fit DETAIL_MAX: build_prompt keeps the LAST DETAIL_MAX characters, so a long output must never push
    the note out."""
    room = max(0, DETAIL_MAX - len(note) - 1)
    return note + "\n" + (tail(output or "", room) if room else "")


def runnable_files(paths: Iterable[str], task: Task) -> list[str]:
    pats = task.run_patterns or RUN_PATTERNS[task.runner]
    out = [p for p in paths if matches_patterns(p, pats)]
    if not task.run_patterns and task.runner != "pytest":
        out = [p for p in out if JS_TEST_EXT.search(p)]
    return sorted(out)


def suite_id(cell: str, run: int) -> str:
    return f"{cell}#{run}"


# -- the launcher -------------------------------------------------------------------------------

class SpendStop(Exception):
    """The spend total reached --max-usd: no new model process starts."""


class Cancelled(Exception):
    """Ctrl-C killed a model process."""


@dataclass
class Proc:
    """One model process. `detail` is private."""
    valid: bool
    reason: str | None
    infra: bool
    cost: float | None
    unknown: bool
    data: dict | None
    detail: str
    cancelled: bool = False


def version_matches(line: str, required: str) -> bool:
    """`claude --version` names exactly `required` as a whole version: 2.1.325 matches "2.1.325 (Claude
    Code)" but not 2.1.3251 or 2.1.325.1."""
    return bool(re.match(re.escape(required) + r"(?=\s|$)", line.strip()))


class Launcher:
    """evalkit's launcher with a stand-in context: the harness's runner flags plus PERMISSION_FLAGS, so a
    model may write and edit files in its working directory (harness.json is not changed)."""

    def __init__(self, evals_dir: Path):
        self.ctx = ev.Ctx(evals_dir)
        harness = _copy.deepcopy(self.ctx.harness)
        harness["runner"]["flags"] = list(harness["runner"]["flags"]) + list(PERMISSION_FLAGS)
        self.standin = types.SimpleNamespace(harness=harness)
        self.cap = float(harness["runner"]["max_budget_usd_per_run"])
        self.jobs = int(harness["runner"].get("jobs") or 1)
        self.cli_version: str | None = None

    def require_cells(self, cells: Iterable[str]) -> None:
        missing = [c for c in cells if c not in self.ctx.cells]
        if missing:
            raise BenchError("cell_unknown", None, "cells.json lacks " + ", ".join(missing))

    def version_line(self) -> str | None:
        """`<claude_bin> --version`, first line; None when it cannot be read (nothing is printed)."""
        cmd = shlex.split(self.standin.harness["runner"]["claude_bin"]) + ["--version"]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=30,
                               stdin=subprocess.DEVNULL, env=dict(os.environ, DISABLE_AUTOUPDATER="1"))
        except (OSError, subprocess.SubprocessError):
            return None
        lines = (r.stdout or "").strip().splitlines()
        return lines[0].strip() if r.returncode == 0 and lines else None

    def check_version(self, required: str) -> None:
        line = self.version_line()
        if not line or not version_matches(line, required):
            raise BenchError("version_mismatch", None, f"claude --version said {line!r}")
        m = re.match(r"\d+(?:\.\d+){1,3}", line)
        self.cli_version = m.group(0) if m else None

    def run(self, cell_id: str, prompt: str, cwd: Path, stop) -> Proc:
        cell = self.ctx.cells[cell_id]
        call = ev.call_claude(self.standin, cell, prompt, str(cwd), MODEL_TOOLS, SYSTEM_PROMPT, stop)
        if ev.was_cancelled(call, stop):
            return Proc(False, None, False, None, False, None, "cancelled", cancelled=True)
        return read_process(call, cell, self.cap)


def _num(x):
    return x if isinstance(x, (int, float)) and not isinstance(x, bool) else None


def is_budget_cap(data) -> bool:
    """The CLI stopped the process at --max-budget-usd (its subtype names the budget)."""
    sub = (data or {}).get("subtype") if isinstance(data, dict) else None
    return isinstance(sub, str) and "budget" in sub


def read_process(call: dict, cell: dict, cap: float) -> Proc:
    """Validity by evalkit's parse_call, then one reason word of MODEL_REASONS, and the infra reading
    of evalkit's infra_error (a budget cap is never infra). A refusal is invalid even with exit 0."""
    valid, raw, data = ev.parse_call(call, cell["model_id"], (ev.advisor_of(cell) or {}).get("model_id"))
    sf = ev.stop_fields(data)
    usage = ev.usage_of(data, cell["model_id"])
    refusal = isinstance(data, dict) and ev.is_refusal(sf)
    budget = is_budget_cap(data)
    if refusal or budget:
        valid = False
    reason = None
    if not valid:
        if call["error"]:
            reason = "spawn_failed"
        elif call["timeout"]:
            reason = "timeout"
        elif raw == "json_parse":
            reason = "json_parse"
        elif budget:
            reason = "budget_cap"
        elif refusal:
            reason = "refusal"
        elif isinstance(raw, str) and raw.startswith("model_mismatch"):
            reason = "model_mismatch"
        else:
            reason = "is_error"
    line = {"valid": valid, "invalid_reason": raw or ("refusal" if refusal else None), **sf,
            "output_tokens": usage.get("output_tokens")}
    infra = (not valid) and not budget and not refusal and ev.infra_error(line)
    cost, unknown = ev.call_cost(call, data)
    result = (data or {}).get("result") if isinstance(data, dict) else None
    detail = json.dumps({"raw_reason": raw, "api_error_status": sf.get("api_error_status"),
                         "result_tail": tail(result if isinstance(result, str) else "", 2000),
                         "stdout_tail": "" if isinstance(data, dict) else tail(call.get("stdout") or "", 2000),
                         "error": call.get("error")})
    return Proc(valid, reason, infra, cost, unknown, data if isinstance(data, dict) else None, detail)


def read_public(path: Path) -> list[dict]:
    """The public record's lines; an unreadable line is skipped without a word (no path is printed)."""
    out = []
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        return out
    for line in text.splitlines():
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if isinstance(obj, dict):
            out.append(obj)
    return out


def spend_of(lines: Iterable[dict], cap: float) -> tuple[float, int]:
    """(total, unknown): the sum of cost_usd over the public model lines, `cap` for a line whose cost
    is unknown."""
    total, unknown = 0.0, 0
    for line in lines:
        if line.get("kind") != "model":
            continue
        if line.get("cost_unknown"):
            total += cap
            unknown += 1
        elif _num(line.get("cost_usd")) is not None:
            total += float(line["cost_usd"])
    return total, unknown


@contextlib.contextmanager
def autoupdater_off():
    """DISABLE_AUTOUPDATER=1 for every claude process this command starts (they inherit it)."""
    old = os.environ.get("DISABLE_AUTOUPDATER")
    os.environ["DISABLE_AUTOUPDATER"] = "1"
    try:
        yield
    finally:
        if old is None:
            os.environ.pop("DISABLE_AUTOUPDATER", None)
        else:
            os.environ["DISABLE_AUTOUPDATER"] = old


# -- copies of a model run ------------------------------------------------------------------------

def _changes(before: tuple[dict, dict], after: tuple[dict, dict]) -> int:
    """Paths (files and symlinks) that are new, changed or gone between two tree_index readings."""
    n = 0
    for b, a in zip(before, after):
        n += sum(1 for k in set(b) | set(a) if b.get(k) != a.get(k))
    return n


def snapshot(work: Path, tree: Path) -> Path:
    base = Path(tempfile.mkdtemp(prefix="snap-", dir=work))
    clone_tree(tree, base / "tree")
    return base / "tree"


def restore_snapshot(tree: Path, snap: Path) -> None:
    shutil.rmtree(tree, ignore_errors=True)
    os.replace(snap, tree)


def new_symlinks(copy: Path, start: Path) -> list[str]:
    clinks, slinks = tree_index(copy)[1], tree_index(start)[1]
    return sorted(rel for rel, target in clinks.items() if slinks.get(rel) != target)


def settle_suite(copy: Path, start: Path, task: Task) -> tuple[list[str], int]:
    """Step T after a try: the suite is the copy's new or changed files under test_patterns; every other
    change (a source file changed or added, any deletion, a new symlink) is reverted in the copy and
    counted. Returns (suite paths, number reverted)."""
    ov = overlay_of(copy, start)
    suite = sorted(p for p in ov.files if matches_patterns(p, task.test_patterns))
    dropped = 0
    for p in ov.files:
        if p in suite:
            continue
        if (start / p).is_file():
            _write_file(copy / p, start / p)
        else:
            _remove(copy / p)
        dropped += 1
    for p in ov.deleted:
        _write_file(copy / p, start / p)
        dropped += 1
    for p in new_symlinks(copy, start):
        _remove(copy / p)
        if (start / p).is_file():
            _write_file(copy / p, start / p)
        dropped += 1
    return suite, dropped


def restore_locked(copy: Path, locked: Mapping[str, bytes | None]) -> list[str]:
    """Arm B: put every locked file back as it was (None = it did not exist). Returns the paths that
    had changed, sorted."""
    changed = []
    for rel, data in locked.items():
        p = copy / rel
        now = p.read_bytes() if (p.is_file() and not p.is_symlink()) else None
        if p.is_symlink() or p.is_dir() or now != data:
            changed.append(rel)
            if p.is_dir() and not p.is_symlink():
                shutil.rmtree(p)
            if data is None:
                _remove(p)
            else:
                _write_file(p, data)
    return sorted(changed)


def locked_note(paths: Sequence[str]) -> str:
    """NOTE_LOCKED plus the names of the files that were put back (at most ten), so the coder knows
    which of its own changes was refused."""
    shown = ", ".join(paths[:10]) + (f" and {len(paths) - 10} more" if len(paths) > 10 else "")
    return f"{NOTE_LOCKED} Put back: {shown}."


def store_tree_files(dest: Path, src_root: Path, paths: Iterable[str]) -> None:
    for rel in paths:
        _write_file(dest / rel, src_root / rel)


def overlay_hash(files: Mapping[str, str], deleted: Iterable[str]) -> str:
    h = hashlib.sha256()
    for rel in sorted(files):
        h.update(f"f\0{rel}\0{files[rel]}\n".encode("utf-8"))
    for rel in sorted(deleted):
        h.update(f"d\0{rel}\n".encode("utf-8"))
    return h.hexdigest()


def _replace_dir(staging: Path, final: Path) -> None:
    shutil.rmtree(final, ignore_errors=True)
    final.parent.mkdir(parents=True, exist_ok=True)
    os.replace(staging, final)


# -- private store paths ----------------------------------------------------------------------------

def suite_dir(root: Path, code: str, cell: str, run: int) -> Path:
    return Path(root) / "suites" / code / cell / str(run)


def run_dir_of(root: Path, code: str, cell: str, arm: str, run: int) -> Path:
    return Path(root) / "runs" / code / cell / arm / str(run)


def read_json_or(path: Path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def suite_files_of(root: Path, code: str, cell: str, run: int) -> dict:
    d = suite_dir(root, code, cell, run)
    meta = read_json_or(d / "meta.json", {}) or {}
    return {rel: d / "files" / rel for rel in meta.get("files") or []}


# -- the steps ------------------------------------------------------------------------------------

class Steps:
    """What the model commands share: the app, the launcher, the spend limit, the stop flag, the
    installed tasks and their briefs."""

    def __init__(self, app: "App", launcher: Launcher | None, max_usd: float | None, tasks: Sequence[Task]):
        self.app, self.launcher = app, launcher
        self.max_usd = DEFAULT_MAX_USD if max_usd is None else float(max_usd)
        self.cap = launcher.cap if launcher else 6.0
        self.tasks = list(tasks)
        self.installed = {t.code: read_installed(app.root, t.code) or {} for t in tasks}
        self.spend_stopped = False
        self.infra_stopped = False
        self.lock = threading.Lock()

    def limit(self, task: Task) -> float:
        return time_limit_for(self.installed[task.code].get("reference_seconds") or TIME_LIMIT_MIN_S)

    def tdir(self, task: Task) -> Path:
        return task_dir(self.app.root, task.code)

    def brief(self, task: Task) -> str:
        return (self.app.root / task.brief).read_text(encoding="utf-8")

    def spend(self) -> tuple[float, int]:
        return spend_of(read_public(self.app.results), self.cap)

    def check_spend(self) -> float:
        """Before every model process: no new process after a check_infra stop, nor at the spend stop."""
        if self.infra_stopped:
            raise CheckInfraStop()
        total, _ = self.spend()
        if total >= self.max_usd:
            with self.lock:
                self.spend_stopped = True
            raise SpendStop()
        return total

    def model_work(self) -> Path:
        d = self.app.work / "model"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def suite_check(self, task: Task, base: Path, suite: Mapping[str, Path | bytes], *,
                    overlay: Mapping | None = None, deleted: Iterable[str] = ()) -> TestResult:
        """Run a suite's runnable files on base (+ overlay), with all the suite's files written last."""
        if not suite:
            return TestResult("no_tests", 0, 0, 0.0, NOTE_NO_TESTS)
        run = runnable_files(suite, task)
        if not run:
            return TestResult("no_tests", 0, 0, 0.0, NOTE_NO_RUNNABLE)
        return run_on_copy(self.app.work, task, base, overlay or {}, run, self.limit(task), deleted=deleted,
                           tools=self.app.tools, layers=[suite])

    def one_try(self, *, step: str, task: Task, cell: str, arm: str | None, run: int, try_no: int,
                prompt: str, copy: Path, settle: Callable[[], int], stop, spent: list) -> Proc | None:
        """One try: up to MAX_ATTEMPTS attempts. An attempt that is an API or infrastructure error is
        not a try: the copy is put back as it was before that attempt and the same try starts again.
        Returns the try's process, or None after MAX_ATTEMPTS infra errors. Before every process the
        spend total is checked (SpendStop). One model line per attempt; `spent` collects the costs."""
        for attempt in range(1, MAX_ATTEMPTS + 1):
            self.check_spend()
            snap = snapshot(self.model_work(), copy)
            try:
                before = tree_index(copy)
                proc = self.launcher.run(cell, prompt, copy, stop)
                if proc.cancelled:
                    raise Cancelled()
                changed = _changes(before, tree_index(copy))
                dropped = 0
                if proc.infra:
                    restore_snapshot(copy, snap)
                else:
                    dropped = settle()
            finally:
                shutil.rmtree(snap.parent, ignore_errors=True)
            data = proc.data or {}
            usage = ev.usage_of(data, self.launcher.ctx.cells[cell]["model_id"])
            denials = data.get("permission_denials")
            self.app.records.model({
                "step": step, "task": task.code, "cell": cell, "arm": arm, "run": run, "try": try_no,
                "attempt": attempt, "valid": proc.valid, "reason": proc.reason, "infra": proc.infra,
                "cost_usd": proc.cost, "cost_unknown": proc.unknown, "duration_ms": _num(data.get("duration_ms")),
                "input_tokens": _num(usage.get("input_tokens")), "output_tokens": _num(usage.get("output_tokens")),
                "cache_read_tokens": _num(usage.get("cache_read_tokens")), "num_turns": _num(data.get("num_turns")),
                "denials": len(denials) if isinstance(denials, list) else None, "files_changed": changed,
                "files_dropped": dropped, "cli_version": self.launcher.cli_version}, detail=proc.detail)
            spent.append(proc)
            if not proc.infra:
                return proc
        return None


def _costs(procs: Sequence[Proc], cap: float) -> dict:
    known = sum(p.cost for p in procs if p.cost is not None)
    unknown = sum(1 for p in procs if p.unknown)
    dur = sum(_num((p.data or {}).get("duration_ms")) or 0 for p in procs)
    return {"cost_usd": round(known + cap * unknown, 6), "cost_unknown": unknown, "duration_ms": dur,
            "processes": len(procs)}


def t_run(st: Steps, task: Task, cell: str, run: int, stop) -> str:
    """Step T, one run: up to three tries; after each the suite is kept and every other change
    reverted; the check is "red first" (the suite on a fresh copy of the START tree; the reference is
    never used). Stores suites/<code>/<cell>/<run>/ (files/ and meta.json)."""
    start = st.tdir(task) / "start"
    brief = st.brief(task)
    copy = working_copy(st.model_work(), start)
    procs: list[Proc] = []
    suite: list[str] = []
    words: list[str] = []
    dropped_total = 0
    ended = "done"
    feedback = None
    sid = suite_id(cell, run)
    try:
        for try_no in range(1, MAX_TRIES["T"] + 1):
            holder = {}

            def settle():
                holder["suite"], n = settle_suite(copy, start, task)
                holder["dropped"] = n
                return n
            proc = st.one_try(step="T", task=task, cell=cell, arm=None, run=run, try_no=try_no,
                              prompt=build_prompt("T", brief, feedback=feedback), copy=copy, settle=settle,
                              stop=stop, spent=procs)
            if proc is None:
                ended = "infra"
                break
            suite = holder.get("suite", [])
            dropped_total += holder.get("dropped", 0)
            res = st.suite_check(task, start, {p: copy / p for p in suite})
            st.app.records.check(step="T", task=task.code, what="red_first", res=res, cell=cell, run=run,
                                 try_=try_no, suite=sid)
            no_infra(res, task.code)
            words.append(res.result)
            if res.red:
                break
            feedback = res.detail or NOTE_NO_TESTS
        d = suite_dir(st.app.root, task.code, cell, run)
        staging = d.parent / f".{run}.building"
        shutil.rmtree(staging, ignore_errors=True)
        store_tree_files(staging / "files", copy, suite)
        ev.write_json_atomic(staging / "meta.json", {
            "task": task.code, "cell": cell, "run": run, "suite": sid, "ended": ended, "tries": len(words),
            "red_first": words, "red": bool(words) and is_red(words[-1]), "files": suite,
            "files_dropped": dropped_total,
            "task_hash": st.installed[task.code].get("task_hash"), "stored_at": ev.now(),
            **_costs(procs, st.cap)})
        _replace_dir(staging, d)
    finally:
        drop_copy(copy)
    last = words[-1] if words else "none"
    return f"{task.code} {cell} run {run}: {'infra_failed' if ended == 'infra' else 'red' if is_red(last) else 'not_red'} after {len(words)} tries"


def given_of(root: Path) -> dict:
    return read_json_or(Path(root) / "given.json", {}) or {}


def c_run(st: Steps, task: Task, cell: str, arm: str, run: int, stop) -> str:
    """Step C, one run of one arm (see the module docstring). Stores runs/<code>/<cell>/<arm>/<run>/."""
    root = st.app.root
    start, hidden_dir = st.tdir(task) / "start", st.tdir(task) / "hidden"
    hidden = _hidden_overlay(hidden_dir)
    brief = st.brief(task)
    given_sid, given_files = None, {}
    if arm == "B":
        given_sid = given_of(root)[task.code]["suite"]
        gcell, grun = given_sid.split("#")
        given_files = suite_files_of(root, task.code, gcell, int(grun))
    copy = working_copy(st.model_work(), start)
    procs: list[Proc] = []
    checks, hiddens, whys = [], [], []
    finished = None if arm == "A" else False
    ended = "done"
    feedback = None
    try:
        locked: dict = {}
        if arm == "B":
            for rel, src in given_files.items():
                _write_file(copy / rel, src)
                locked[rel] = Path(src).read_bytes()
            for rel in task.runner_config:
                p = start / rel
                locked.setdefault(rel, p.read_bytes() if p.is_file() else None)
        for try_no in range(1, MAX_TRIES[arm] + 1):
            hit = {"n": 0, "paths": []}

            def settle():
                hit["paths"] = restore_locked(copy, locked) if arm == "B" else []
                hit["n"] = len(hit["paths"])
                return hit["n"]
            proc = st.one_try(step="C", task=task, cell=cell, arm=arm, run=run, try_no=try_no,
                              prompt=build_prompt(arm, brief, sorted(given_files), feedback), copy=copy,
                              settle=settle, stop=stop, spent=procs)
            if proc is None:
                ended = "infra"
                break
            ov = overlay_of(copy, start)
            ov_files = {p: copy / p for p in ov.files}
            word, why, detail = None, None, ""
            if arm == "B":
                res = st.suite_check(task, start, given_files, overlay=ov_files, deleted=ov.deleted)
                word = "locked_changed" if hit["n"] else res.result
                detail = with_note(locked_note(hit["paths"]), res.detail) if hit["n"] else res.detail
                st.app.records.check(step="C", task=task.code, what="given", res=res, result=word, cell=cell,
                                     arm=arm, run=run, try_=try_no, suite=given_sid)
                no_infra(res, task.code)
            elif arm == "C":
                word, res, why, detail = own_check(st, task, start, copy, ov)
                st.app.records.check(step="C", task=task.code, what="own", res=res, result=word, cell=cell,
                                     arm=arm, run=run, try_=try_no, extra={"own_reason": why})
                no_infra(res, task.code)
            h = run_on_copy(st.app.work, task, start, ov_files, task.run_files, st.limit(task),
                            deleted=ov.deleted, tools=st.app.tools, layers=[hidden])
            st.app.records.check(step="C", task=task.code, what="hidden", res=h, cell=cell, arm=arm, run=run,
                                 try_=try_no)
            no_infra(h, task.code)
            hiddens.append(h.result)
            checks.append(word)
            whys.append(why)
            if arm == "A":
                break
            if word == "pass":
                finished = True
                break
            feedback = detail or "no output"
        ov = overlay_of(copy, start)
        d = run_dir_of(root, task.code, cell, arm, run)
        staging = d.parent / f".{run}.building"
        shutil.rmtree(staging, ignore_errors=True)
        store_tree_files(staging / "overlay", copy, ov.files)
        nontest = {p: s for p, s in ov.files.items() if not matches_patterns(p, task.test_patterns)}
        nontest_del = [p for p in ov.deleted if not matches_patterns(p, task.test_patterns)]
        correct = ended == "done" and bool(hiddens) and hiddens[-1] == "pass"
        if ended != "done":
            finished = None if arm == "A" else False
        ev.write_json_atomic(staging / "deleted.json", list(ov.deleted))
        ev.write_json_atomic(staging / "meta.json", {
            "task": task.code, "cell": cell, "arm": arm, "run": run, "ended": ended, "tries": len(hiddens),
            "checks": checks, "own_reasons": whys, "hidden": hiddens, "finished": finished,
            "correct": correct, "correct_first": bool(hiddens) and hiddens[0] == "pass",
            "escaped": None if arm == "A" else bool(finished) and not correct,
            "given": given_sid, "files": sorted(ov.files), "deleted": list(ov.deleted),
            "symlinks_ignored": ov.symlinks_ignored,
            "source_unchanged": source_unchanged(ov, task.test_patterns),
            "overlay_hash": overlay_hash(ov.files, ov.deleted), "nontest_hash": overlay_hash(nontest, nontest_del),
            "task_hash": st.installed[task.code].get("task_hash"), "stored_at": ev.now(),
            **_costs(procs, st.cap)})
        _replace_dir(staging, d)
    finally:
        drop_copy(copy)
    state = "infra_failed" if ended == "infra" else ("correct" if hiddens and hiddens[-1] == "pass" else "not_correct")
    return f"{task.code} {cell} {arm} run {run}: {state} after {len(hiddens)} tries"


def own_check(st: Steps, task: Task, start: Path, copy: Path, ov: Overlay):
    """Arm C: (word, result, own_reason, detail). The own tests are the overlay's files under
    test_patterns. None -> no_tests; none the runner would run -> no_tests; not red on the start tree ->
    fail (own_not_red); else their result on the copy (start + the whole overlay)."""
    own = sorted(p for p in ov.files if matches_patterns(p, task.test_patterns))
    if not own:
        return "no_tests", None, "no_own_tests", NOTE_NO_TESTS
    run = runnable_files(own, task)
    if not run:
        return "no_tests", None, "no_runnable", NOTE_NO_RUNNABLE
    own_files = {p: copy / p for p in own}
    on_start = no_infra(run_on_copy(st.app.work, task, start, own_files, run, st.limit(task),
                                    tools=st.app.tools), task.code)
    if not on_start.red:
        return "fail", on_start, "own_not_red", with_note(NOTE_OWN_NOT_RED, on_start.detail)
    res = run_on_copy(st.app.work, task, start, {p: copy / p for p in ov.files}, run, st.limit(task),
                      deleted=ov.deleted, tools=st.app.tools)
    return res.result, res, None, res.detail


def c_units(tasks: Sequence[Task], given: Mapping, rounds: int, cells=None, arms=None) -> dict:
    """The planned step-C runs in order: round n = run n of every cell and arm, on every task, in the
    order task, cell, arm. {"units": [(round, task, cell, arm)], "left_out": [...], "pending": [...]}:
    arms B and C of a task with no fit suite are left out; with no given suite fixed yet, pending."""
    out = {"units": [], "left_out": [], "pending": []}
    for n in range(1, rounds + 1):
        for t in tasks:
            for cell, cell_arms, runs in C_PLAN:
                if (cells and cell not in cells) or n > runs:
                    continue
                for arm in cell_arms:
                    if arms and arm not in arms:
                        continue
                    unit = (n, t, cell, arm)
                    if arm in ("B", "C"):
                        g = given.get(t.code)
                        if g is None:
                            out["pending"].append(unit)
                            continue
                        if g.get("suite") is None:
                            out["left_out"].append(unit)
                            continue
                    out["units"].append(unit)
    return out


# -- fit, given and cross ---------------------------------------------------------------------------

def fit_suite(st: Steps, task: Task, cell: str, run: int) -> dict | None:
    """Score one stored suite (fit.json), or None when it is not stored. Fit = red on the start tree
    and `pass` on the reference in FIT_REFERENCE_RUNS runs out of FIT_REFERENCE_RUNS. A suite whose run
    ended after three infra errors is not fit and is not run."""
    d = suite_dir(st.app.root, task.code, cell, run)
    meta = read_json_or(d / "meta.json")
    if meta is None:
        return None
    done = read_json_or(d / "fit.json")
    if done is not None:
        return done
    sid = suite_id(cell, run)
    out = {"suite": sid, "fit": False, "start": None, "reference": [], "ended": meta.get("ended")}
    if meta.get("ended") == "done":
        files = suite_files_of(st.app.root, task.code, cell, run)
        res = st.suite_check(task, st.tdir(task) / "start", files)
        st.app.records.check(step="fit", task=task.code, what="fit_start", res=res, cell=cell, run=run,
                             try_=1, suite=sid)
        no_infra(res, task.code)
        out["start"] = res.result
        if res.red:
            for k in range(1, FIT_REFERENCE_RUNS + 1):
                r = st.suite_check(task, st.tdir(task) / "reference", files)
                st.app.records.check(step="fit", task=task.code, what="fit_reference", res=r, cell=cell,
                                     run=run, try_=k, suite=sid)
                no_infra(r, task.code)
                out["reference"].append(r.result)
                if r.result != "pass":
                    break
        out["fit"] = bool(res.red) and out["reference"] == ["pass"] * FIT_REFERENCE_RUNS
    ev.write_json_atomic(d / "fit.json", out)
    return out


def fix_given(st: Steps, task: Task, given: dict) -> str:
    """Score the task's suites; once all eight are stored and scored, fix its given suite (the first fit
    in GIVEN_ORDER) for good. A given suite already fixed is never changed."""
    fits = [fit_suite(st, task, c, r) for c, r in GIVEN_ORDER]
    stored = sum(1 for f in fits if f is not None)
    n_fit = sum(1 for f in fits if f and f["fit"])
    if task.code in given:
        g = given[task.code]["suite"]
        return f"{task.code} fix-suites: {n_fit} of {stored} fit, given {g or 'none'} (fixed earlier)"
    if stored < len(GIVEN_ORDER):
        return f"{task.code} fix-suites: {n_fit} of {stored} fit, given pending ({stored} of {len(GIVEN_ORDER)} suites stored)"
    first = next((suite_id(c, r) for (c, r), f in zip(GIVEN_ORDER, fits) if f["fit"]), None)
    given[task.code] = {"suite": first, "fixed_at": ev.now()}
    gcell, grun = (first.split("#")[0], int(first.split("#")[1])) if first else (None, None)
    st.app.records.check(step="fit", task=task.code, what="given", result="pass" if first else "fail",
                         cell=gcell, run=grun, suite=first)
    if first is None:
        return f"{task.code} fix-suites: 0 of {stored} fit, no given suite: arms B and C are left out"
    return f"{task.code} fix-suites: {n_fit} of {stored} fit, given {first}"


def cross_task(st: Steps, task: Task, given: Mapping) -> tuple[int, int]:
    """Every fit suite of the task on every stored final copy of arms A and C whose run ended normally
    and whose source is not unchanged: start + the copy's non-test files and deletions (its own test
    files left out), the suite's files written, the suite's runnable files run. One check line per
    pair; a (task, suite, non-test overlay) triple seen before reuses its result. Before the pairs, one
    `copy` line per such copy (also when its source is unchanged), once: its result is `changed` or
    `unchanged`, so the public record says which copies cross has seen and which it leaves out.
    Returns (new, reused)."""
    root = st.app.root
    path = root / "cross.json"
    done = read_json_or(path, {}) or {}
    cache = {(v.get("task"), v["suite"], v["nontest_hash"]): v for v in done.values() if v.get("suite")}
    fits = []
    for c, r in GIVEN_ORDER:
        f = read_json_or(suite_dir(root, task.code, c, r) / "fit.json")
        if f and f.get("fit"):
            fits.append((c, r))
    copies = []
    for cell, cell_arms, runs in C_PLAN:
        for arm in cell_arms:
            if arm not in ("A", "C"):
                continue
            for n in range(1, runs + 1):
                d = run_dir_of(root, task.code, cell, arm, n)
                meta = read_json_or(d / "meta.json")
                if not meta or meta.get("ended") != "done":
                    continue
                ckey = f"{task.code}|copy|{cell}|{arm}|{n}"
                if ckey not in done:
                    word = "unchanged" if meta.get("source_unchanged") else "changed"
                    st.app.records.check(step="cross", task=task.code, what="copy", result=word, cell=cell,
                                         arm=arm, run=n)
                    done[ckey] = {"copy": word}
                    ev.write_json_atomic(path, done)
                if not meta.get("source_unchanged"):
                    copies.append((cell, arm, n, d, meta))
    new = reused = 0
    start = st.tdir(task) / "start"
    for c, r in fits:
        sid = suite_id(c, r)
        files = suite_files_of(root, task.code, c, r)
        for cell, arm, n, d, meta in copies:
            key = f"{task.code}|{sid}|{cell}|{arm}|{n}"
            if key in done:
                continue
            hit = cache.get((task.code, sid, meta["nontest_hash"]))
            if hit is not None:
                res = TestResult(hit["result"], hit.get("tests"), hit.get("failed"), hit.get("seconds") or 0.0,
                                 "reused")
                reused += 1
            else:
                over = {p: d / "overlay" / p for p in meta["files"] if not matches_patterns(p, task.test_patterns)}
                dels = [p for p in meta["deleted"] if not matches_patterns(p, task.test_patterns)]
                res = st.suite_check(task, start, files, overlay=over, deleted=dels)
                new += 1
            st.app.records.check(step="cross", task=task.code, what="cross", res=res, cell=cell, arm=arm,
                                 run=n, suite=sid)
            no_infra(res, task.code)
            entry = {"task": task.code, "suite": sid, "nontest_hash": meta["nontest_hash"], "result": res.result,
                     "tests": res.tests, "failed": res.failed, "seconds": res.seconds}
            done[key] = entry
            cache[(task.code, sid, meta["nontest_hash"])] = entry
            ev.write_json_atomic(path, done)
    return new, reused


# -- progress: plan and status ----------------------------------------------------------------------

def progress(app: "App", cap: float, max_usd: float) -> dict:
    """Counts of what is stored and what is missing, and the spend; reads only the private store and
    the public record. No model call."""
    tasks = load_tasks(app.root)
    given = given_of(app.root)
    lines = read_public(app.results)
    total, unknown = spend_of(lines, cap)
    run_cost: dict = {}
    for line in lines:
        if line.get("kind") != "model":
            continue
        key = (line.get("step"), line.get("task"), line.get("cell"), line.get("arm"), line.get("run"))
        c = cap if line.get("cost_unknown") else (_num(line.get("cost_usd")) or 0.0)
        run_cost[key] = run_cost.get(key, 0.0) + c
    per = {"tasks": {}, "T": {"planned": 0, "stored": 0, "infra": 0}, "fit": {"scored": 0, "fit": 0},
           "given": {"fixed": 0, "none": 0, "pending": 0},
           "C": {"planned": 0, "stored": 0, "left_out": 0, "infra": 0, **{f"planned_{a}": 0 for a in ARMS},
                 **{f"stored_{a}": 0 for a in ARMS}},
           "cross": {"checked": sum(1 for v in (read_json_or(app.root / "cross.json", {}) or {}).values()
                                    if isinstance(v, dict) and v.get("suite"))}}
    t_costs, c_costs, remaining_c = [], {}, {}
    for t in tasks:
        inst = read_installed(app.root, t.code) or {}
        row = {"installed": bool(inst.get("ok")), "T": 0, "fit": 0, "given": None, "C": 0}
        for c, r in GIVEN_ORDER:
            per["T"]["planned"] += 1
            meta = read_json_or(suite_dir(app.root, t.code, c, r) / "meta.json")
            if meta:
                per["T"]["stored"] += 1
                row["T"] += 1
                per["T"]["infra"] += meta.get("ended") == "infra"
                t_costs.append(run_cost.get(("T", t.code, c, None, r), 0.0))
            f = read_json_or(suite_dir(app.root, t.code, c, r) / "fit.json")
            if f:
                per["fit"]["scored"] += 1
                per["fit"]["fit"] += bool(f.get("fit"))
                row["fit"] += bool(f.get("fit"))
        g = given.get(t.code)
        if g is None:
            per["given"]["pending"] += 1
            row["given"] = "pending"
        elif g.get("suite") is None:
            per["given"]["none"] += 1
            row["given"] = "none"
        else:
            per["given"]["fixed"] += 1
            row["given"] = g["suite"]
        for cell, cell_arms, runs in C_PLAN:
            for arm in cell_arms:
                for n in range(1, runs + 1):
                    if arm in ("B", "C") and g is not None and g.get("suite") is None:
                        per["C"]["left_out"] += 1
                        continue
                    per["C"]["planned"] += 1
                    per["C"][f"planned_{arm}"] += 1
                    meta = read_json_or(run_dir_of(app.root, t.code, cell, arm, n) / "meta.json")
                    if meta:
                        per["C"]["stored"] += 1
                        per["C"][f"stored_{arm}"] += 1
                        per["C"]["infra"] += meta.get("ended") == "infra"
                        row["C"] += 1
                        c_costs.setdefault(cell, []).append(run_cost.get(("C", t.code, cell, arm, n), 0.0))
                    else:
                        remaining_c[cell] = remaining_c.get(cell, 0) + 1
        per["tasks"][t.code] = row
    per["T"]["missing"] = per["T"]["planned"] - per["T"]["stored"]
    per["C"]["missing"] = per["C"]["planned"] - per["C"]["stored"]
    all_c = [x for v in c_costs.values() for x in v]
    projected = total
    known = True
    if per["T"]["missing"]:
        if t_costs:
            projected += per["T"]["missing"] * (sum(t_costs) / len(t_costs))
        else:
            known = False
    for cell, n in remaining_c.items():
        costs = c_costs.get(cell) or all_c
        if costs:
            projected += n * (sum(costs) / len(costs))
        else:
            known = False
    per["spend"] = {"total": round(total, 2), "unknown_processes": unknown,
                    "projected": round(projected, 2) if known else None, "stop_at": max_usd}
    return per


# -- the app and the commands ------------------------------------------------------------------

@dataclass
class App:
    root: Path
    results: Path
    evals_dir: Path
    work: Path
    vitest_modules: Path | None = None
    tools: Tools | None = None
    profile_fn: Callable | None = None
    current_task: str | None = None
    records: Records = field(init=False)

    def __post_init__(self):
        self.records = Records(self.results, self.root / "attempts.jsonl")

    @property
    def lock_path(self) -> Path:
        return self.evals_dir / "results" / ".evalkit.lock"


def say(text: str) -> None:
    print(text, flush=True)


def selftest_words(rep: dict) -> str:
    return ", ".join(f"{r} {rep[r]}" for r in RUNNERS)


def cmd_selftest(app: App, args) -> int:
    rep = selftest(app.work, app.vitest_modules, app.tools, app.profile_fn)
    if args.json:
        say(json.dumps({r: rep[r] for r in RUNNERS} | {"ok": rep["ok"]}))
    else:
        say(f"selftest: {selftest_words(rep)}: {'ok' if rep['ok'] else 'FAILED'}")
    return 0 if rep["ok"] else 1


def _vitest_modules_from_tasks(app: App, tasks: Sequence[Task] | None = None) -> None:
    if app.vitest_modules is not None:
        return
    if tasks is None:
        try:
            tasks = load_tasks(app.root)
        except BenchError:
            return
    for t in tasks:
        if t.runner == "vitest" and t.node_modules and vitest_reachable(t.node_modules["from"]):
            app.vitest_modules = Path(t.node_modules["from"])
            return


def cmd_install(app: App, args) -> int:
    tasks = load_tasks(app.root)
    if args.task:
        tasks = [t for t in tasks if t.code == args.task]
        if not tasks:
            raise BenchError("no_task")
    _vitest_modules_from_tasks(app)
    rep = require_selftest(app, need_vitest=any(t.runner == "vitest" for t in tasks))
    say(f"selftest: {selftest_words(rep)}: ok")
    failures = 0
    for t in tasks:
        app.current_task = t.code
        try:
            out = install_task(app, t)
        except BenchError as e:
            if e.word not in INSTALL_REASONS:
                raise
            app.records.note(t.code, e.word, e.detail)
            write_install_failure(app.root, t.code, e.word)
            out = InstallOutcome(t.code, False, e.word)
        except Exception:  # noqa: BLE001 - one broken task must not stop the others
            app.records.note(t.code, "internal", traceback.format_exc())
            write_install_failure(app.root, t.code, "internal")
            out = InstallOutcome(t.code, False, "internal")
        if out.ok:
            ref = out.reference[-1]
            say(f"{t.code} install: ok (start {out.start.result}, reference pass "
                f"{len(out.reference)}/{REFERENCE_RUNS}, {ref.tests} tests, "
                f"{max(r.seconds for r in out.reference):.1f} s)")
        elif out.reason == "check_infra":     # the runner failed: not a reason to replace the task
            failures += 1
            say(f"{t.code} install: stopped check_infra (the runner could not run; not the task)")
        else:
            failures += 1
            say(f"{t.code} install: failed {out.reason}")
        app.current_task = None
    say(f"install: {len(tasks) - failures} of {len(tasks)} tasks ok")
    return 0 if failures == 0 else 1


def _scope(app: App, args) -> list[Task]:
    """The installed tasks in scope (--task); a task whose installation is not ok is skipped, with a
    line that says so."""
    tasks = load_tasks(app.root)
    if getattr(args, "task", None):
        tasks = [t for t in tasks if t.code == args.task]
        if not tasks:
            raise BenchError("no_task")
    ok = []
    for t in tasks:
        if (read_installed(app.root, t.code) or {}).get("ok"):
            ok.append(t)
        else:
            say(f"{t.code}: not installed, skipped")
    return ok


def _cells_arg(value, allowed) -> list[str] | None:
    cells = ev.parse_csv(value)
    if cells and any(c not in allowed for c in cells):
        raise BenchError("cell_unknown")
    return cells


def _model_setup(app: App, args, tasks: Sequence[Task], cells: Iterable[str]) -> Steps:
    """What every model command does first: the harness, the cells, the version, the self-test."""
    launcher = Launcher(app.evals_dir)
    launcher.require_cells(cells)
    launcher.check_version(args.allow_version or REQUIRED_VERSION)
    _vitest_modules_from_tasks(app, tasks)
    rep = require_selftest(app, need_vitest=any(t.runner == "vitest" for t in tasks))
    say(f"selftest: {selftest_words(rep)}: ok")
    return Steps(app, launcher, args.max_usd, tasks)


def _pool(st: Steps, units: list, worker: Callable, jobs: int, label: str) -> int:
    def guarded(unit, stop):
        try:
            msg = worker(unit, stop)
        except SpendStop:
            return None
        except Cancelled:
            return None
        except CheckInfraStop as e:          # the runner failed: nothing stored, no new process starts
            with st.lock:
                first = not st.infra_stopped
                st.infra_stopped = True
            if e.detail:
                st.app.records.note(unit[1].code, "check_infra", e.detail)
            return f"{unit[1].code} stopped check_infra" if first or e.detail else None
        except Exception:  # noqa: BLE001 - one broken run must not stop the others; nothing stored
            st.app.records.note(unit[1].code if isinstance(unit[1], Task) else None, "internal",
                                traceback.format_exc())
            msg = f"{unit[1].code} error internal"
        total, _ = st.spend()
        return f"{msg} (spend ${total:.2f})"
    return ev.run_pool(st.launcher.ctx, units, guarded, jobs, label)


def cmd_write_tests(app: App, args) -> int:
    cells = _cells_arg(args.cells, T_CELLS) or list(T_CELLS)
    tasks = _scope(app, args)
    with autoupdater_off():
        st = _model_setup(app, args, tasks, cells)
        units = [(r, t, c) for t in tasks for c in T_CELLS if c in cells for r in range(1, T_RUNS + 1)
                 if read_json_or(suite_dir(app.root, t.code, c, r) / "meta.json") is None]
        say(f"write-tests: {len(units)} runs to make")
        code = _pool(st, [(u[0], u[1], u[2]) for u in units],
                     lambda u, stop: t_run(st, u[1], u[2], u[0], stop), args.jobs or st.launcher.jobs, "T")
    if st.infra_stopped:
        raise BenchError("check_infra")
    total, unknown = st.spend()
    if st.spend_stopped:
        say(f"write-tests: spend stop reached (${total:.2f} of ${st.max_usd:.2f}); no new process started")
        return 3
    say(f"write-tests: {'interrupted' if code == 130 else 'done'} (spend ${total:.2f})")
    return code


def cmd_fix_suites(app: App, args) -> int:
    tasks = _scope(app, args)
    _vitest_modules_from_tasks(app, tasks)
    rep = require_selftest(app, need_vitest=any(t.runner == "vitest" for t in tasks))
    say(f"selftest: {selftest_words(rep)}: ok")
    st = Steps(app, None, None, tasks)
    given = given_of(app.root)
    for t in tasks:
        app.current_task = t.code
        say(fix_given(st, t, given))
        ev.write_json_atomic(app.root / "given.json", given)
        app.current_task = None
    return 0


def cmd_code(app: App, args) -> int:
    cells = _cells_arg(args.cells, C_CELLS)
    arms = ev.parse_csv(args.arms)
    if arms and any(a not in ARMS for a in arms):
        raise BenchError("arm_unknown")
    rounds = args.rounds or C_ROUNDS
    tasks = _scope(app, args)
    with autoupdater_off():
        st = _model_setup(app, args, tasks, cells or C_CELLS)
        plan = c_units(tasks, given_of(app.root), rounds, cells, arms)
        for n, t, cell, arm in plan["left_out"]:
            if n == 1:
                say(f"{t.code} {cell} {arm}: left out (no fit suite)")
        pending_tasks = sorted({u[1].code for u in plan["pending"]})
        for code in pending_tasks:
            say(f"{code}: arms B and C wait for fix-suites (no given suite yet)")
        code = 0
        for n in range(1, rounds + 1):
            units = [u for u in plan["units"] if u[0] == n
                     and read_json_or(run_dir_of(app.root, u[1].code, u[2], u[3], n) / "meta.json") is None]
            if not units:
                continue
            say(f"code: round {n}, {len(units)} runs")
            code = _pool(st, units, lambda u, stop: c_run(st, u[1], u[2], u[3], u[0], stop),
                         args.jobs or st.launcher.jobs, f"C round {n}")
            if code or st.spend_stopped or st.infra_stopped:
                break
    if st.infra_stopped:
        raise BenchError("check_infra")
    total, _ = st.spend()
    if st.spend_stopped:
        say(f"code: spend stop reached (${total:.2f} of ${st.max_usd:.2f}); no new process started")
        return 3
    say(f"code: {'interrupted' if code == 130 else 'done'} (spend ${total:.2f})")
    return code


def cmd_cross(app: App, args) -> int:
    tasks = _scope(app, args)
    _vitest_modules_from_tasks(app, tasks)
    rep = require_selftest(app, need_vitest=any(t.runner == "vitest" for t in tasks))
    say(f"selftest: {selftest_words(rep)}: ok")
    st = Steps(app, None, None, tasks)
    given = given_of(app.root)
    for t in tasks:
        app.current_task = t.code
        if t.code not in given:
            say(f"{t.code} cross: pending (no given suite yet)")
            continue
        new, reused = cross_task(st, t, given)
        say(f"{t.code} cross: {new} pairs run, {reused} reused")
        app.current_task = None
    return 0


def _harness_cap(app: App) -> float:
    try:
        return float(ev.Ctx(app.evals_dir).harness["runner"]["max_budget_usd_per_run"])
    except (ev.EvalError, KeyError, TypeError, ValueError):
        return 6.0


def cmd_plan(app: App, args) -> int:
    p = progress(app, _harness_cap(app), args.max_usd if args.max_usd is not None else DEFAULT_MAX_USD)
    if args.json:
        say(json.dumps(p))
        return 0
    n_ok = sum(1 for r in p["tasks"].values() if r["installed"])
    say(f"plan: {len(p['tasks'])} tasks, {n_ok} installed")
    say(f"step T: {p['T']['stored']} of {p['T']['planned']} suites stored, {p['T']['missing']} to run"
        f" ({p['T']['infra']} ended on infra errors)")
    say(f"fix-suites: {p['fit']['scored']} suites scored, {p['fit']['fit']} fit; given fixed for "
        f"{p['given']['fixed']} tasks, none fit for {p['given']['none']}, pending {p['given']['pending']}")
    c = p["C"]
    say(f"step C: {c['stored']} of {c['planned']} runs stored (A {c['stored_A']}/{c['planned_A']}, "
        f"B {c['stored_B']}/{c['planned_B']}, C {c['stored_C']}/{c['planned_C']}), {c['missing']} to run, "
        f"{c['left_out']} left out")
    say(f"cross: {p['cross']['checked']} pairs checked")
    s = p["spend"]
    proj = f"${s['projected']:.2f}" if s["projected"] is not None else "unknown"
    say(f"spend: ${s['total']:.2f} so far ({s['unknown_processes']} processes of unknown cost charged "
        f"${_harness_cap(app):.2f} each); projected {proj}; stop at ${s['stop_at']:.2f}")
    return 0


def cmd_status(app: App, args) -> int:
    p = progress(app, _harness_cap(app), DEFAULT_MAX_USD)
    if args.json:
        say(json.dumps({"tasks": p["tasks"], "spend": p["spend"]["total"]}))
        return 0
    for code, r in p["tasks"].items():
        say(f"{code}: installed {'ok' if r['installed'] else 'no'}, T {r['T']}/{len(GIVEN_ORDER)}, "
            f"fit {r['fit']}, given {r['given']}, C {r['C']}")
    say(f"spend: ${p['spend']['total']:.2f}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="code_bench", description=__doc__.split("\n\n")[0])
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--root", help="private folder (default <evals>/private/code)")
    common.add_argument("--results", help="public record (default <evals>/results/code-runs.jsonl)")
    common.add_argument("--evals-dir", help="evals folder (default this repo's); its results/ holds the lock")
    common.add_argument("--work", help="scratch copies (default a folder in the system temp directory)")
    common.add_argument("--vitest-modules", help="a node_modules folder with vitest, for the vitest canary")
    model = argparse.ArgumentParser(add_help=False)
    model.add_argument("--task")
    model.add_argument("--cells", help="comma-separated cells (default all of the step)")
    model.add_argument("--max-usd", type=float, help=f"spend stop over all invocations (default {DEFAULT_MAX_USD:g})")
    model.add_argument("--jobs", type=int, help="model runs at a time (default harness runner.jobs)")
    model.add_argument("--allow-version", help=argparse.SUPPRESS)      # tests only
    sub = p.add_subparsers(dest="cmd", required=True)

    def add(name, fn, help_, lock=False, parents=()):
        sp = sub.add_parser(name, parents=[common, *parents], help=help_, description=help_)
        sp.set_defaults(fn=fn, lock=lock)
        return sp

    sp = add("selftest", cmd_selftest, "canaries in the sandbox (fail closed)")
    sp.add_argument("--json", action="store_true")
    sp = add("install", cmd_install, "build start/, reference/, hidden/ and run the installation check", True)
    sp.add_argument("--task")
    sp = add("plan", cmd_plan, "what is missing, the spend so far and projected; no model call")
    sp.add_argument("--json", action="store_true")
    sp.add_argument("--max-usd", type=float)
    add("write-tests", cmd_write_tests, "step T: every test-writing cell writes a suite per task", True, [model])
    sp = add("fix-suites", cmd_fix_suites, "score every suite (fit or not) and fix the given suite per task", True)
    sp.add_argument("--task")
    sp = add("code", cmd_code, "step C in rounds: every coder cell and arm on every task", True, [model])
    sp.add_argument("--rounds", type=int, help=f"run rounds 1..N (default {C_ROUNDS})")
    sp.add_argument("--arms", help="comma-separated arms (default A,B,C)")
    sp = add("cross", cmd_cross, "every fit suite on the final copies of arms A and C", True)
    sp.add_argument("--task")
    sp = add("status", cmd_status, "per task: installed, suites, given suite, step-C runs; the spend")
    sp.add_argument("--json", action="store_true")
    return p


def make_app(args) -> App:
    evals_dir = Path(args.evals_dir).resolve() if args.evals_dir else HERE.parent
    root = Path(args.root).resolve() if args.root else evals_dir / "private" / "code"
    if args.results:
        results = Path(args.results).resolve()
    elif args.root:                      # a trial root never writes into the repository's public record
        results = root / "code-runs.jsonl"
    else:
        results = evals_dir / "results" / "code-runs.jsonl"
    work = Path(args.work) if args.work else Path(tempfile.gettempdir()) / f"code_bench-work-{os.getuid()}"
    vm = args.vitest_modules or os.environ.get("CODE_BENCH_VITEST_MODULES")
    return App(root=root, results=results, evals_dir=evals_dir, work=Path(os.path.realpath(work)),
               vitest_modules=Path(vm) if vm else None)


def main(argv=None, app: App | None = None) -> int:
    args = build_parser().parse_args(argv)
    app = app or make_app(args)
    try:
        if args.lock:
            try:
                lock = ev.exclusive_lock(app.lock_path)
                lock.__enter__()
            except ev.EvalError:
                raise BenchError("locked") from None
            try:
                sweep_work(app.work)
                return args.fn(app, args)
            finally:
                lock.__exit__(None, None, None)
        return args.fn(app, args)
    except BenchError as e:
        task = e.task or app.current_task
        if e.detail and app.root.is_dir():
            app.records.note(task, e.word, e.detail)
        print(f"code_bench: error: {e.word}" + (f" {task}" if task else ""), file=sys.stderr)
        return 2
    except ev.EvalError as e:                    # harness.json or cells.json unreadable: its text has paths
        if app.root.is_dir():
            app.records.note(app.current_task, "harness", str(e))
        print("code_bench: error: harness", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("code_bench: interrupted", file=sys.stderr)
        return 130
    except Exception:  # noqa: BLE001 - the terminal gets a code word only
        task = app.current_task
        try:
            if app.root.is_dir():
                app.records.note(task, "internal", traceback.format_exc())
        except Exception:  # noqa: BLE001
            pass
        print("code_bench: error: internal" + (f" {task}" if task else ""), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
