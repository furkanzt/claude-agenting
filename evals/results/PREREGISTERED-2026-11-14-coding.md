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
