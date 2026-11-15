# Pre-registered: who writes the tests and who writes the code (2026-11-14)

Written at 2026-11-14T17:30Z, rewritten at 17:41Z after two independent reviews of the draft and
corrected after a third (times read from the clock), before any task of this experiment is installed and before any model has
been run on one. The commit time is the record. Claude Code 2.1.325.

## Why

The owner fixed a new scope on 2026-11-14: two modes (`fast` and `balanced`), rows for building software
(plan and tests, bulk coding, review), and `fast` on the cheapest cell per finished task. Nothing about
writing code was ever measured here. Four questions:

1. **Bulk coding.** Which cell is cheapest per correct task when tests check the work: Haiku 5.5 or
   Sonnet 5.5?
2. **Tests first.** Does a coder do better when the tests exist before it starts?
3. **Who writes the tests.** A stronger model, with the test files locked against the coder; or the coder
   itself?
4. **Plan and tests.** Which cell writes the tests best for its cost: Sonnet 5.5 (`high`, `xhigh`) or
   Opus 5.5 (`medium`, `high`)? The answer also decides the tip for the main chat of a $20 plan.

Which vehicle carries bulk coding most cheaply (one agent, a clean run, a small Workflow) cannot be
measured in this harness, because every run here is one process. It gets a small test of its own in a
live session, with its own rules written before it runs, and is reported with this experiment.

## Tasks

**Six real past changes** from five of the owner's projects. Each is a change that a commit really made,
together with the tests that commit added or changed.

- *The start state* is the project's tree at the commit before the change, read with `git archive`.
  Instruction and design documents are removed from it (`CLAUDE.md`, `AGENTS.md`, `PLAN.md`,
  `QUESTIONS.md`, `HANDOFF.md`, `CHANGELOG.md`, `TDD.md`, `BDD.md`, `docs/`, `features/`, `.claude/`,
  `.github/`), so no model reads the project's own rules about tests or a note that describes the change.
  A code check then confirms that no name the change adds, and the hidden tests need, occurs in what is
  left.
- *The brief* says what the software must do after the change, from the outside. It names the source
  files the change belongs in, as a plan would, and gives every name the hidden tests import or read
  (function, field, constant, file, exact message text). It quotes no solution code.
- *The hidden tests* are the real test files of the change. No model sees them.
- *The reference* is the real source after the change. No model sees it.

**The selection is fixed.** One easy, three medium and two hard tasks by the scouts' rating; two in
Python and four in TypeScript; every project at least once. The six candidates and an ordered list of
replacements for each are in `evals/private/code/selection.json`, whose SHA-256 is
`70a7f1f73cde042ce36b55fd7d4970347bd14ed60eacea200ee2fb3619844190`. The changes are 29 to 174 source
lines in one to five files. These counts hold for the six first choices; a replacement can change them,
and the report states the final counts.

**The installation check,** run in the sandbox described below: the hidden tests are red on the start
state (defined under "A try"), they pass on the reference in three runs out of three, and one run takes
under a minute. A task that fails it is replaced by the first entry of its list that passes. At
installation the private task record also fixes, per task, which paths are test files (fixtures and
helpers under the test folders included) and which are the test runner's configuration files. Public
files name the tasks `code-01` to `code-06` with language and rating only.

## Two steps

**Step T, writing the tests.** A model gets the brief and the start state and writes test files for the
change. Cells: `sonnet-5-5@high`, `sonnet-5-5@xhigh`, `opus-5-5@medium`, `opus-5-5@high`. Two runs per cell
and task: 48 runs. Only the test files a run adds or changes are kept as its *suite*; anything else it
changed is dropped and counted.

**Step C, writing the code.** A model gets the brief and the start state and changes the source.

| Arm | What the coder gets besides the brief | What checks a try |
|---|---|---|
| **A, no tests** | nothing | nothing; one try |
| **B, locked tests** | the task's *given suite* (below), which it may read and may not change | the given suite |
| **C, own tests** | the instruction to write its tests first, then the code | the coder's own tests |

| Coder cell | Arms | Runs per task and arm |
|---|---|---|
| `haiku-5-5@medium` | A, B | 4 |
| `haiku-5-5@high` | A, B, C | 4 |
| `sonnet-5-5@low` | A, B | 3 |
| `sonnet-5-5@medium` | B | 3 |
| `opus-5-5@high` (reference only) | B | 1 |

That is 180 coding runs: 66 in arm A, 90 in arm B, 24 in arm C. The Opus cell is a reference and takes
part in no verdict.

**A try, and at most three.** A model has file tools only (read, search, write, edit) inside its own
fresh copy of the start state, with no `node_modules` in it. It cannot run anything. When it stops, the
harness runs the checking tests in a sandbox. If they fail and fewer than three tries are used, a new try
starts in the same copy with the failing output attached. A run's cost and time are the sum over its
tries.

- *Red on the start state* means: at least one test fails there, or a test file fails to load there only
  because a name listed in the brief is missing. A time-out counts as failing. What "loads" and "fails"
  mean is fixed for each test runner in the tool's own tests before step T.
- *Step T:* the check is "red first": the suite is red on the start state. The reference is never used
  as feedback.
- *Arm B:* before every check the given suite and the test runner's configuration files are put back as
  they were. A try that had changed one of them counts as failed, whatever the suite then says.
- *Arm C:* the coder's own tests are the test files it added or changed. A try passes its check when
  such files exist, they are red on the start state, and they load, collect at least one test and all
  pass on the coder's copy. Otherwise the try counts as failed and is told why.

**The given suite of a task** is the first suite, in the fixed order `sonnet-5-5@high` run 1, run 2,
`sonnet-5-5@xhigh` run 1, run 2, `opus-5-5@medium` run 1, run 2, `opus-5-5@high` run 1, run 2, that is
*fit* (below). Sonnet comes first because `fast` is the mode this experiment serves. If none of the eight
is fit, arms B and C are not run for that task, and every comparison between arms leaves that task out.

**Grading, all by running tests, no judge model.**

- *A run of step C.* The hidden tests run on the copy after every try, without telling the model. A run
  is **correct** when every hidden test passes after its last try, and **correct at the first try** when
  they pass after try 1. In arms B and C a run is **finished** when one of its tries passes its check as
  defined for its arm above, and **escaped** when it is finished but not correct.
- *A suite of step T* is **fit** when it is red on the start state and, on the reference, it loads,
  collects at least one test and every test passes in two runs out of two. For a fit suite, over the final copies of arms A and C of its own task (never
  arm B, whose copies were shaped by one particular suite), leaving out copies whose source is unchanged
  from the start state: it **catches** a copy that is not correct when it fails on it, and **wrongly
  rejects** a correct copy when it fails on it. To run a suite on a copy, the suite's files are put in
  place, test files the run itself had added are removed, and only the suite's files are run.

## Rules

**In every question:** a cell with no run in the arm a rule reads, no correct run, or no fit suite is
never named. If no cell can be named, the row gets no cell from this experiment and the report says so. A
question whose set of tasks is empty is "not measured". Runs that were never started because the spend
stop was reached are left out of every share and listed; they are not counted as not correct.

**Question 1, bulk coding.** In arm B, for the four Haiku and Sonnet cells: the share of correct runs, and
the cost per correct task, which is the cost of the cell's arm-B runs divided by the number of its correct
arm-B runs.

- **A cell is usable for bulk coding** when at least half of its arm-B runs are correct.
- **`fast`:** the usable cell with the lowest cost per correct task among those whose escaped runs are at
  most 1 in 10 of their finished runs; the higher share of correct runs on a tie. The owner's bar for
  checked work is "cheapest per finished task, every retry counted, at most three tries". Two things are
  this plan's additions: dividing by correct runs instead of finished ones, and the cap on escaped runs,
  taken from the owner's bar for unchecked work, because an escaped run is a wrong result that nothing
  caught. If no cell qualifies, `fast` takes the cell of `balanced` and the report says so.
- **`balanced`:** the cheapest cell whose arm-B runs are all correct. If no cell is, the cell with the
  highest share of correct runs, and the lower cost per correct task on a tie; the report then says that
  no cell was clean.
- Escaped runs are also reported per task, since one weak given suite can produce most of them.

**Question 2, tests first.** For `haiku-5-5@medium`, `haiku-5-5@high` and `sonnet-5-5@low`, over the tasks
that have both arms: the share of runs correct *at the first try* in arm B minus the share correct in arm
A. One try against one try, so retries play no part. **Tests first helps** a cell when the difference is
at least 15 points for a Haiku cell and at least 30 for the Sonnet cell (which has fewer runs), and arm B
is ahead on more tasks than arm A is. **Tests first hurts** a cell when the difference is at most minus
15 (Haiku) or minus 30 (Sonnet) and arm A is ahead on more tasks. Otherwise **no effect shown**. What tries
2 and 3 add in arm B (the
share correct at the end minus the share correct at the first try) is reported next to it.

**Question 3, who writes the tests.** For `haiku-5-5@high`, over the tasks that have arms B and C: arm C is
**acceptable** when at least half of its runs are finished, its share of correct runs is at most 10
points below arm B's, its escaped runs are at most 1 in 10 of its finished runs, and it is behind arm B on
at most two tasks. Otherwise the tests must come from a stronger model. With fewer than four tasks that
have both arms the answer is "too few tasks to tell".

**Question 4, plan and tests.** Per test-writing cell: the number of fit suites of its 12, its mean cost
and time per suite, and the two rates. A rate is pooled over pairs of a fit suite and a copy; over fewer
than 10 such pairs it is "too few to tell" and its bound is not applied. **Cheapest** here means the
lowest cost per fit suite: the cost of the cell's 12 runs divided by its number of fit suites.

- **`fast`:** the cheapest cell with at least 10 fit suites that catches at least 80% and wrongly rejects
  at most 10%. If no cell qualifies: the cell with the most fit suites among those that wrongly reject at
  most 10%, the cheaper on a tie; if no cell stays within 10%, the cell with the lowest rate of wrong
  rejections.
- **`balanced`:** the cheapest cell with 12 fit suites and both bounds. If no cell qualifies: the cell
  with the most fit suites among those that meet both bounds; if none meets them, the most fit suites;
  the cheaper on a tie.
- **The tip for the main chat of a $20 plan** names the `fast` cell of this question. It also says that a
  long chat re-reads the whole conversation every turn, so the cheaper input price weighs more there than
  in these single tasks.

**Missing and invalid runs.** An API or infrastructure error is not a try: the same try runs again, up to
three attempts. After three failed attempts the run ends: in step C it is not correct and not finished, in
step T its suite is not fit; it is listed. A process whose cost is unknown is charged the $6 cap of one
process.

**What these rules can change.** They name cells for two new rows, each in both modes: plan and tests,
and bulk coding. The rows enter the skill only with the owner's release. The review row is not
measured here and keeps the cell of the verify row.

## What to expect, written before the runs

- **Cost.** A Haiku try costs $0.20 to $0.40, not a few cents: stored Haiku runs that read many files
  cost $0.23 to $0.42.
- **Question 1.** `haiku-5-5@high` in arm B is correct in at least two thirds of its runs on the four easy
  and medium tasks and in at most one third on the two hard ones. Its cost per correct task is at most
  half of `sonnet-5-5@low`'s. The open point is the escaped runs.
- **Question 2.** Tests first helps both Haiku cells; the difference for Sonnet `low` is smaller than
  for either Haiku cell.
- **Question 3.** Not acceptable: more than 1 in 10 of Haiku's finished runs in arm C escape.
- **Question 4.** `opus-5-5@medium` has at least 10 fit suites at a mean cost within 25% of
  `sonnet-5-5@xhigh`'s. `sonnet-5-5@high` has fewer fit suites than either Opus cell.

## Limits known beforehand

1. **Six tasks from one owner's projects,** in two languages, each a change of 29 to 174 source lines.
   Nothing here speaks for a large feature or for other languages. Correctness depends mostly on the
   task, so the six tasks, not the runs, are the real sample.
2. **The hidden tests are the judge,** and they are the tests one real change shipped with. They can pass
   wrong code and fail right code that is shaped differently. The brief gives the names they need and the
   files to change, which also tells the coder part of the design.
3. **The coder cannot run tests itself.** A real agent with a shell gets feedback as often as it likes
   inside one run; here it gets it between tries, at most twice. That is unkind to the tests-first arms.
4. **Each try is a fresh process** that reads the files again, so a retry costs more than it would inside
   one continuing session.
5. **Three or four runs a cell and task** show a large difference only. One task moves a share by 17
   points.
6. **The given suite is picked with knowledge of the reference,** which a team in the field does not have;
   the fit counts of question 4 say how often that would have mattered.
7. **Every arm-B result rests on one given suite per task,** most likely a `sonnet-5-5@high` run. Question
   1's `fast` verdict holds for tests of that quality. If question 4 names another writer, the escaped
   runs were measured with tests from a writer the skill will not use.
8. **List price is the yardstick.** How a $20 plan counts each model against its limit is not published.
9. **The scouts that found the candidate changes were Sonnet agents.** No model under test saw their
   notes, and the selection used their ratings before any model output.
10. **The sandbox guards against accidents, not against an adversary.** It denies the network and writing
    outside a run's copy; it sets no memory limit.

## How the runs are made

- **A side tool, not `evalkit.py run`:** `evals/probes/code_bench.py`. It reuses the harness's launcher,
  budget and lock, as `ux_blind.py` does, and passes the launcher a permission mode that lets a model
  write and edit files inside its copy and nothing else; `harness.json` is not changed. While it runs,
  `evalkit.py run` cannot, because they share one lock.
- **Records.** One line for every model process and one for every test run. The public file,
  `evals/results/code-runs.jsonl`, holds only the task code, cell, arm, run number, attempt, try, a
  reason from a fixed list, and numbers (test counts, seconds, tokens, cost, versions). No path, no
  test name, no output text, no exception text. Everything else stays in `evals/private/code/`.
- **Working copies.** One start tree and one reference tree per task; for every run only the files it
  changed. For a test run the tool copies the start tree, applies the files the rule in question names (a
  run's files, or only a suite's test files), adds the project's
  `node_modules` as a copy-on-write clone where the project needs one, runs, and deletes the copy. The
  owner's projects are only read.
- **The sandbox:** macOS `sandbox-exec`, no network, writing only inside the run's copy and a scratch
  folder that serves as home and temp, a time limit of five times the reference run (at least 20 s, at
  most 60 s). The tool tests its own sandbox at every start and refuses to run if a canary can reach
  the network or write outside.
- **Order of the record:** these rules; then the tool and its analysis, with tests; then the tasks, with
  their installation check; then the pilot; then step T; then the given suites are fixed; then step C.
- **Step C runs in rounds.** Round n is run n of every cell and arm on every task. A stop therefore cuts
  whole rounds and leaves every arm with the same runs, and no arm is tied to one stretch of the day.
- **Pilot,** before the rest of step T: a scripted probe of the write tools on a toy project (a new file
  in a new folder, an edit, a file with a configuration name, a path outside the copy, a `CLAUDE.md`
  inside the copy, a process that hits its cost cap). Then one task gets all eight of its step-T runs, its
  given suite is fixed from them, and it gets one run of every coder cell and arm. Pilot runs on the real
  task count as ordinary runs. Checked: the tools work as described, no instruction file
  is loaded, the cost per try, that the $6 cap really stops a process (if it can overshoot, the stop
  below is lowered by the overshoot seen), and that planted failures (a failing suite, a changed locked
  file, a short time limit) are handled as the rules say.
- **Spend.** Expected about $205 at list price: about $80 for step T and about $125 for step C. The total
  is read from the run records across invocations and checked before every process. No process starts
  once the total reaches $226; with four processes at a time and the $6 cap of a process the spend stays
  under the owner's ceiling of $250.
- **The spend is projected twice,** after the pilot and again after step T, from the costs seen so far.
  If a projection is above $226, runs are cut in this order until it fits, and the report says which: the
  Opus reference runs; `sonnet-5-5@medium`; arm C (question 3 is then "not measured"); then the runs per
  task of the Haiku cells from 4 to 3 and of `sonnet-5-5@low` from 3 to 2. The six tasks and step T are
  not cut. If the projection is still above $226 after the last cut, nothing more runs until the owner
  has decided.
- **Claude Code 2.1.325.** Every invocation checks the version and stops if it differs; the automatic
  updater is switched off for the processes the tool starts, and the advisor is off for every run.

## Addendum 1: readings fixed with the tool, before any run (2026-11-14, 21:42Z)

Written after the tool and its analysis were built and tested, and before any task was installed or any
model run was made. No number of the plan changes. Each point says how the tool reads a sentence above
that could be read two ways, or states a limit more exactly.

1. **"Loads" (red on the start state, fit).** Every test file handed to the test runner must load. One
   file that fails to load for another reason than a listed missing name makes the run a load error,
   even when another file has a failing test. The exact reading per test runner is in the docstring of
   `evals/probes/code_bench.py` and in its tests.
2. **Question 4, "fewer than 10 such pairs".** Each rate is counted over its own pairs: the catch rate
   over pairs of a fit suite and a copy that is not correct, the wrong-rejection rate over pairs of a fit
   suite and a correct copy. A rate with fewer than 10 pairs of its own is "too few to tell".
3. **Running a suite on a copy.** Every path under the task's test patterns is first put back to the
   start state: test files the run added are removed, as written above, and a start-state test file
   that the run changed or deleted is restored too. A suite is judged on the copy's source only.
4. **Correct at the first try, for a run that ended on infrastructure errors.** Such a run is not
   correct and not finished, as written. It still counts as correct at the first try when its hidden
   tests passed after try 1, because that try was measured.
5. **A run that was cut** (by the spend stop, by a test runner that could not start, or by the
   operator) is made again from try 1 in a fresh copy. The cost of the cut part counts in the spend
   total and is listed in the report. It is not part of the run's cost.
6. **A test runner that cannot start** (the sandbox refuses, a program is missing) is not a result. The
   tool stops, stores nothing for that run and makes it again at the next start.
7. **Rounds and the spend stop.** The stop is checked before every process, so it can leave the round
   in progress partly done. To keep rounds whole, a round is started only when the projection says it
   fits under the stop. If the stop still cuts a round, the report lists the runs that were never made.
8. **A process that answered with another model than its cell's** counts as a try, as everywhere in
   the harness. The report lists every such process.
9. **Arm B's locked files** are the given suite's files and the test runner's configuration files named
   in the task record, including names that do not exist at the start (a `conftest.py` that a coder
   might add).
10. **Scratch copies** live in the system's temporary folder, outside the repository, because pytest
    reads its configuration from the folders above a project.
11. **Limit 10, more exactly.** The sandbox also denies signals to processes outside it, and the tool
    kills the processes a test leaves behind. A run whose output passes 64 MB is stopped and counts as
    a time-out. The sandbox does not hide the names and sizes of files in the home folder (only their
    contents), everything outside the home folder can be read, name lookups through system services
    were not tested, and a test file that ends the test runner on purpose with a success code reads as
    passed.

## Addendum 2: the leak check corrected at installation, before any model run (2026-11-14, 22:02Z)

**What happened.** The first installation attempt stopped all six tasks at the leak check. As first
built, the check counted a listed name as "added by the change" whenever the task's own source files
did not have it before the change. But a task's list holds every name the hidden tests need, and many
of those already exist elsewhere in the project: an existing file that a test reads, an existing field
that a test checks. The change does not add those.

**The corrected reading,** now in the tool with its tests. A listed name is added by the change when
the project does not have it yet: it occurs neither in the before version of the task's source files
nor in the text or the path of any other file of the start state that is not prose (code, tests, data,
configuration). The check confirms that no added name occurs in a prose file that is left (Markdown,
plain text, a file with no ending), in its text or in its path.

**What was looked at before correcting.** For every listed name of the six tasks, where it occurs in
the start state. No name that a project's code, tests and data lack occurs in any prose file. The
stopped names were existing paths, existing fields and common words.

**Result.** All six first choices pass the installation check; no task was replaced.

| Task | Language, rating | Tests in the hidden files | Failing on the start state | One reference run |
|---|---|---|---|---|
| `code-01` | Python, easy | 29 | 3 | 4.3 s |
| `code-02` | Python, medium | 96 | 3 | 8.9 s |
| `code-03` | TypeScript, medium | 171 | 4 | 0.9 s |
| `code-04` | TypeScript, medium | 60 | 7 | 2.1 s |
| `code-05` | TypeScript, hard | 102 | 6 | 0.5 s |
| `code-06` | TypeScript, hard | 242 | 41 | 2.7 s |

The hidden files hold the project's older tests too, so most of their tests pass before the change. A
run is correct only when all of them pass.

**What this reading does not catch.** A note that describes a change without using a new name, which a
check by names never could. And a comment in a code file that names a function ahead of time; the
first version caught that only outside the task's own source files.

## Addendum 3: the pilot's probe on a toy project, before any run on a real task (2026-11-14, 22:10Z)

The rules ask for a scripted probe of the write tools on a toy project before the first real run. It ran
through the tool itself, on a toy task with its own record (not `code-runs.jsonl`): 8 test-writing runs,
the fit check, one round of all coder cells and arms (9 runs), the cross check and the analysis. Then a
separate two-run test with a half-cent cost cap, and a separate six-process check of instruction files.
Cost of all of it: $0.93. None of these runs is one of the 228 planned runs.

| Checked | Result |
|---|---|
| A new file in a new folder, and an edit | Worked in every run. |
| A path outside the copy | Refused in 28 of 29 processes; the other one did not try it. Nothing was written outside. |
| An instruction file in the folder (`CLAUDE.md`, `CLAUDE.local.md`, `AGENTS.md`) | Not loaded: 6 of 6 processes (3 Haiku, 2 Sonnet, 1 Opus) asked for it without tools had none in context. A model can still read such a file with its read tool, as any file. |
| A locked file changed in arm B (planted: the brief asked for a file the task record locks) | Put back, and the try counted as failed, in 15 of 15 tries. The hidden tests still ran. |
| A process that hits its cost cap | Stopped, recorded with the reason `budget_cap` and its cost. It counts as a try and its files are checked. It overshot: $0.011 against a cap of $0.005, one more turn than the cap allowed. |
| Every command end to end | 8 of 8 toy suites fit, 9 of 9 coding runs correct, 32 cross pairs, the analysis read the record. |

Two changes follow, both made before any run on a real task:

1. **The spend stop is $224, not $226.** A process can pass its cap by one turn. One turn of the
   largest model on these tasks is put at $0.50 at most, and four processes run at a time.
2. **The note after a locked file was changed now names the files that were put back.** In the toy, a
   coder that was not told which file had been refused changed it again in every try.

Not probed with a real model: a failing given suite and a time limit that is too short. Both are
covered by the tool's tests, which make real sandboxed test runs with a stand-in model.

## Addendum 4: the pilot on one real task, and a guard against an outage (2026-11-14, 22:43Z)

**The pilot** ran on `code-04`, as ordinary runs: its eight test-writing runs, the fit check, and one run
of every coder cell and arm.

- Step T: 8 runs, $7.83, 11 minutes with four at a time. All eight suites were red on the start state
  at the first try, and all eight are fit. The given suite is the first in the fixed order.
- Step C: 9 runs, $1.84, 8 minutes. All nine are correct.
- No API error, no refused write, no instruction file, no time-out.

**Projection** by the tool's `plan` command from these costs: about $70 for all 228 runs, against the
$205 expected and the $224 stop. Nothing is cut. A Haiku coding run cost $0.02 to $0.13 here, not the
$0.20 to $0.40 written under "What to expect".

**One guard added before the rest of the runs,** because they run unattended for hours. The rules say
an API or infrastructure error is not a try and the same try runs again, up to three attempts. The tool
made those attempts one right after the other, so an outage of a minute could have ended every run in
flight and every run after it. Now:

1. The tool waits 30 seconds before the second attempt of a try and 120 seconds before the third.
2. When a run still ends on three such attempts, it is stored as the rules say, and the command starts
   no new model process. The runs it had in flight are made again at the next start.

This changes no rule and no count. It limits what an outage can cost to the runs that were in flight.

## Addendum 5: the rules of the vehicle test, before it runs (2026-11-15, 02:42Z)

Written after step C had ended and while the cross check was still running. The rules above promise this
test "with its own rules written before it runs". Nothing of it has run. One number it will be compared
with is already known and is named below.

**Question.** The plan and the locked tests exist. Four pieces of coding go to Haiku 5.5 at `medium`.
Which vehicle costs less per correct piece: four single `Agent` calls, or one Workflow with four agents?
And how far are both from a clean run?

**Pieces.** `code-01`, `code-02`, `code-03` and `code-05`: the four tasks whose tests need no installed
packages, so one command can run them. Each piece is the task as arm B has it: the brief, the start
state, and the task's given suite in place and locked.

**The two live vehicles,** in this chat (a live session, not the pinned command-line run):

- *Agents:* four `Agent` calls sent in one message, one piece each.
- *Workflow:* one Workflow whose script starts four agents at once, one piece each.

Both are launched in the same message, so all eight workers start cold and none can read what another
has just cached. Every worker is the plugin's `coder` agent with the model set to `haiku` and the effort
to `medium`. Its launch prompt is one sentence that names a task file. The task file holds the brief,
arm B's instruction, the suite's paths and the working rules, the same text in both vehicles. Each worker
has its own fresh copy in a folder outside the repository.

**What a worker may do.** It has the `coder` agent's tools, a shell included. It may run one command, as
often as it likes: a private script that runs the given suite on its copy in the tool's sandbox, exactly
as arm B checks a try (locked files are put back first, and a changed locked file counts as a failed
check), and prints the result with the output's tail. It is told to stop at a passing check or after
three failed ones, and to run nothing else that changes or runs anything.

**Grading,** after all eight have ended, by the same sandboxed test runs as step C: the given suite and
the hidden tests on each final copy. A piece is **correct** when every hidden test passes.

**Cost,** from each worker's own transcript: every API call after removing streamed duplicates, at list
price per category (input, cache read, 5-minute and 1-hour cache write, output), with the price table of
`scripts/measure-tokenomics.py`. Also reported per worker: the model and effort that answered, the number
of calls, the size of the first call's context and how much of it was written to cache fresh, the number
of checks it ran, and the time from its first to its last line. What the main chat spends on launching
and on reading the results is reported as sizes in characters, not priced: this chat runs on a model a
$20 plan does not have.

**Reading rule.** The cost per correct piece of a vehicle is the cost of its four workers divided by its
number of correct pieces. One vehicle **is cheaper** than the other when its cost per correct piece is at
least 25% lower and it has no fewer correct pieces. Otherwise **no difference shown**. The same rule
compares each live vehicle with the clean run: the 16 stored arm-B runs of `haiku-5-5@medium` on these
four tasks, which cost $0.023 a run on average and were all correct (known when this was written). That
comparison is between different settings, and the report says so: a clean run has file tools only, a
fixed short system prompt, and the harness reruns the tests between tries; a live worker has a shell and
whatever this chat's setup loads into an agent.

**The worker's model and effort are checked twice.** Before the launch, one probe call (a one-word
answer, no work) shows whether an unnamed `Agent` call of the `coder` agent takes the model and the effort
written on the call; on 2026-11-13 that was measured for Workflow calls and for agents without a file, not
for this case. If it does not, both vehicles use the generic worker (no agent type) with `model: haiku` and
`effort: medium`. After the run, each worker's transcript names the model and effort that answered. A
worker that ran on another model or effort is listed and its piece is left out of both vehicles'
figures; with fewer than three pieces left, the answer is "not measured".

**What this can change.** Only the sentence of the skill that says through which vehicle bulk coding
goes. No cell.

**Limits.** One run of four pieces per vehicle shows a large difference only. One agent definition. This
Mac's own instruction files and plugins are loaded into every live worker, so their start-up differs from
a fresh install's. The live session runs Claude Code 2.1.323, the clean runs ran on 2.1.325. List price;
how a $20 plan counts a worker against its limit is not published. Expected cost: under $2.

**Correction to Addendum 5, written after the vehicle test (2026-11-15, 04:18Z).** The last paragraph
says that the live session runs Claude Code 2.1.323. It ran 2.1.325, the version of the clean runs: every
worker's transcript records it, and the session had moved to it on 2026-11-14. No rule depends on that
sentence; the limit it names does not apply.
