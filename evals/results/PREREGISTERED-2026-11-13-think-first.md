# Pre-registered rules: Fable 5.2 on "think first" jobs (2026-11-13)

Written 2026-11-13T12:50Z and committed before any task material was chosen, before any task was
built and before any model output existed for these jobs. Claude Code 2.1.323. The owner approved
every threshold below in a question round on the same day; nothing here may be edited after the
first run. Corrections go in a dated addendum at the end, never in place.

## 1. Question

Claude Fable 5.2 (`claude-fable-5-2`, $8 / $40 per MTok, released 2026-11-09) costs twice Opus 5.5
per token. On the seven existing rows Opus 5.5 already passes every stored run where it is used, so
Fable is not tested there. The question is narrower: on work where a model **designs or decides
first** and cheaper models then build, does Fable 5.2 beat Opus 5.5 `xhigh` by enough to earn the
job in the `quality` or `balanced` disposition? `fast` never gets Fable.

Two new rows:

| Row id | Job | Graded by |
|---|---|---|
| `design-decision` | Decide an architecture or approach that later work is built on | Two judge models against a fixed checklist |
| `ux-design` | Design a UI/UX solution for a prototype, a new screen or a new flow, which a cheaper model then builds | The owner, blind, plus two judge models against a fixed checklist |

## 2. What is fixed for both rows

- **Built once.** Each task is built to the design in this file, reviewed by independent reviewers
  for correctness of the ground truth, and then frozen. No task is rebuilt, hardened or dropped
  after any model output for it exists. A task found to be broken (wrong truth, leaked answer) is
  reported and excluded as a whole, for every cell; it is not repaired and re-run in this round.
- **Who builds and marks.** Builders and reviewers are Opus 5.5 and Sonnet 5.5 agents. No Fable
  model builds a task, reviews a task or writes a checklist. The judge models are
  `fable-5-1@high` (the harness's pinned judge) and `opus-5-5@high`.
- **Same instrument for every cell.** `claude -p --restricted` through `evals/evalkit.py` or the
  probe tools, all runs on Claude Code 2.1.323 or later, every cell fresh on the new tasks.
- **Cells.** `fable-5-2@low`, `fable-5-2@medium`, `fable-5-2@high` (new), `opus-5-5@xhigh`,
  `opus-5-5@high`, `sonnet-5-5@xhigh`, and `sonnet-5-5@medium` as the builder in `ux-design`.
- **A failed run.** A run with no valid answer after the harness's retries counts as failed. For a
  Fable cell, a run slot in which any attempt was refused by a safety classifier, or was answered by
  a different model than the cell names, counts as failed even if a later attempt succeeded.
- **Spending ceiling.** $300 at list price for everything in this round: device checks, building and
  reviewing tasks, runs, both judges and the UI stages. Work stops and is reported when it is reached.

## 3. Row `design-decision`

### Tasks

Two tasks, `design-01` and `design-02`, each a real decision from the history of one of the owner's
projects, from two different repositories.

- **Material.** The project's files as they were at the commit before the decision was made,
  extracted read-only by commit id. 20k to 70k tokens. Nothing written after the decision. The
  material is searched for any trace of the later outcome before the task is frozen.
- **Prompt.** The decision question as it stood, asking for a design: the decision, the reasons, the
  options rejected and why, **at most six risks** in order of importance, each with a mitigation,
  and what to verify. The prompt does not say this is a test and does not hint at what happened.
- **Checklist (the ground truth).** Written before any model output:
  - **C items, binding constraints:** 4 to 6 rules stated in the material that a design must not
    violate, each with the file and line where the material states it.
  - **P items, foreseeable pitfalls:** 4 to 6 problems that really happened after the real decision
    (the evidence stays in the private truth file). An independent reviewer confirms for each that
    the material alone holds the facts needed to foresee it; an item that fails this is removed
    before the freeze. A design handles a P item when its decision avoids the problem by
    construction, or when it names the problem among its risks with a mitigation specific to this
    project.
- **Pass rule for one run under one judge pass:** the design violates no C item **and** handles
  all but at most one P item.

### Judging

Each run is judged four times: two passes by `fable-5-1@high` and two passes by `opus-5-5@high`.
A judge sees the task prompt, the checklist and one answer, never the material's later history and
never which cell wrote the answer.

- **Solid fail.** Under one judge model, a run is a *solid fail* when both of that judge's passes
  fail it. A split (one pass, one fail) is not a solid fail. This is deliberately stricter evidence
  than the harness's `decide`, which fails a run on a split: the rule below counts failures, so a
  failure must be reproducible. A run with no answer block is a solid fail.
- **Both judges must agree on the rule.** Every count below is computed twice, once per judge
  model. A rule fires only if it fires under both.

### Runs

Stage 1: every cell runs each task 3 times (36 runs), and `opus-5-5@xhigh` runs repeats 4 to 6 as
well (6 more), so the Opus `xhigh` count is always out of 12.

Stage 2, only where it can still matter:

- A Fable cell runs repeats 4 to 6 only if it has no solid fail in stage 1 under either judge
  **and** `opus-5-5@xhigh` has at least 4 solid fails of 12 under both judges.
- `opus-5-5@high` and `sonnet-5-5@xhigh` run repeats 4 to 6 only if they have no solid fail in
  stage 1 under either judge.

### Rules

There are no older tasks for this row, so "all tasks" means these two.

- **Rule Q (`quality`).** A Fable cell takes the row in `quality` if it has 0 solid fails in its 12
  runs and `opus-5-5@xhigh` has at least 4 solid fails in its 12 runs.
- **Rule B (`balanced`).** A Fable cell takes the row in `balanced` if it has 0 solid fails in its
  12 runs and `opus-5-5@xhigh` has at least 6 solid fails in its 12 runs, with at least one on each
  task.
- **Which Fable effort.** Among the Fable cells that qualify, the one with the lowest measured mean
  cost per run.
- **`fast`.** The cheapest by measured mean cost per run of `opus-5-5@high` and `sonnet-5-5@xhigh`
  that has 0 solid fails in 12 runs; if neither does, `opus-5-5@xhigh`. Never a Fable cell.
- **Otherwise** the row is `opus-5-5@xhigh` in `balanced` and `quality`, and the table says
  "Fable 5.2 measured, not adopted".
- **Both fail.** If `opus-5-5@xhigh` has at least 4 solid fails and no Fable cell reaches 0 solid
  fails, nothing moves; the row stays `opus-5-5@xhigh`, marked "no cell passed these tasks".
- **A cheaper non-Fable cell for `balanced`** is not decided in this round: the plugin's bar needs
  two confirmation tasks beyond a screening task, and this row has two tasks in all. The numbers
  are reported.

## 4. Row `ux-design`

### Briefs

Four briefs, `ux-01` to `ux-04`, each a prototype, new screen or new flow for one of the owner's
real games, described in a few sentences the way the owner would describe it, with at least three
UI/UX choices that depend on each other. Each brief carries the description, the game's conventions
and existing style as material, and a checklist of 8 yes/no items written before any model output.

### Arms

| Arm | Design pass | Builder |
|---|---|---|
| F | `fable-5-2@high` writes a design brief | `sonnet-5-5@medium` builds one HTML page from that brief |
| O | `opus-5-5@xhigh` writes a design brief | the same builder, same instructions |
| D | none | the same builder builds straight from the description |

The design brief has a fixed shape: the screens and what is on each, the flow, every state, the
words, the main action, the assumptions made. Every arm's builder gets the same description and
material. Each built page is one self-contained HTML file with no network requests. Before the
owner sees a page, comments, titles and generator marks are removed so that nothing names its arm.

Only `fable-5-2@high` is tested as the Fable designer: each further effort level would cost the
owner another 12 pairs.

### Pairs

24 pairs, each of two pages built from the same brief, and no page appears in more than one pair:

- **Block 1, 12 pairs: F against O** (3 per brief).
- **Block 2, 12 pairs: F against D** (3 per brief, from separate F runs).

So the round needs 24 F pages, 12 O pages and 12 D pages. The 24 pairs are shown in one shuffled
order with left and right chosen at random per pair; the order and sides are stored privately. The
owner picks the better page in every pair, with no tie option. A session that does not cover all
24 pairs gives no verdict.

### Checklist score

Each block-1 page is read (as HTML source, with the description and the brief's checklist) once by
`fable-5-1@high` and once by `opus-5-5@high`. An item is credited when both say yes. A page's score
is credited items divided by 8; an arm's score is the mean over its 12 block-1 pages. Arm F's score
is "not below" arm O's when `mean_F >= mean_O - 0.05`.

### Rules

- **Rule UQ (`quality`).** `fable-5-2@high` is the UI/UX designer in `quality` if the owner prefers
  the F page in at least 10 of the 12 block-1 pairs **and** F's checklist score is not below O's.
- **Rule UB (`balanced`).** The same in `balanced` at 11 of 12 or more, with the same checklist
  condition.
- **Otherwise** the designer is `opus-5-5@xhigh` in both.
- **`fast`** uses the Opus designer at `xhigh`. No cheaper designer was tested and none is claimed.
- **Rule UD (the design pass itself).** A design pass before the build is the default for UI
  prototypes if the owner prefers the F page in at least 10 of the 12 block-2 pairs. If the designer
  by rule UQ or UB is Opus, the default design pass uses Opus, on the assumption that a design the
  owner did not prefer less than Fable's also beats no design pass. If rule UD fails, the design
  pass is not a default; it stays available on request, and the docs say no benefit was measured.

## 5. What these rules cannot show

- Twelve runs or twelve pairs show a large gap only. By chance alone, 0 against 4 solid fails
  happens about one time in twenty, and 10 of 12 blind preferences about one time in fifty.
- Two decision tasks and four briefs, all from one owner's projects, are a narrow sample.
- Both judge models come from one vendor; the owner's blind choice is the only judgment from
  outside it, and it covers `ux-design` only.
- The instrument is a clean, read-only run with a neutral system prompt. A real design agent in a
  session has more context and tools.
- The session that wrote these rules and orchestrates the round runs on Fable 5.2. That is why no
  Fable model builds or marks anything, and why the rules were fixed before the tasks existed.

## Addendum 1, 2026-11-13T13:35Z: clarifications made before the first run

Written before any task was installed and before any model output existed for these rows. Each
point says how a rule above is carried out; none changes a threshold.

1. **How a refusal is recognised.** By the CLI's own result fields, checked on Claude Code 2.1.323:
   `stop_reason` equal to `refusal`, or `safety_stops` above 0. An API error, a rate limit, a
   usage limit or a timeout is not a refusal: the attempt is invalid and retried, and it does not
   fail a slot by itself. "Answered by a different model" is the harness's `model_mismatch`.
2. **A failed Fable slot in `ux-design`.** Section 2 applies to the designer runs of arm F. A pair
   whose F page comes from a failed F slot counts as "F not preferred" in its block, whatever the
   owner picked. The owner's raw count and the counted number are both reported; rules UQ, UB and
   UD use the counted number.
3. **"Not below".** `mean_F >= mean_O - 0.05` is computed with exact fractions, not floats.
4. **A builder rule added for every arm alike.** Pages are shown in frames sandboxed without
   same-origin, where browser storage throws. The builder prompt therefore forbids browser storage,
   and a page that uses it is rejected and rebuilt, like a page with a network request.
5. **Blinding check.** A built page that names a model or the vendor is rejected and rebuilt.
6. **Counting for the rules of section 3.** A cell's fail count under a judge is its solid fails
   under that judge plus its failed slots; a failed slot counts under both judges. A cell with any
   fail under either judge is out of rules Q, B and `fast`. A disposition is reported only when
   every cell that could still take it has all 12 slots decided.

## Addendum 2, 2026-11-13T15:05Z: deviations found before the first run, and what they cost the test

Written after the tasks were built and reviewed, before any task was installed and before any model
output existed for these rows. Three things did not go as sections 2 and 3 say.

1. **A Fable model advised the builders.** Section 2 says no Fable model builds a task, reviews a
   task or writes a checklist. The builders, refuters and finishers were Opus 5.5 agents and the
   verifiers Sonnet 5.5 agents, as stated. But Workflow agents carry an advisor tool, and in this
   install the advisor is `claude-fable-5-2`. The transcripts show 19 advisor calls: 7 by the three
   builders, 3 by the two refuters, 9 by the three finishers, none by the three Sonnet agents. The
   advice itself is not readable. So the model under test had a say in its own tasks and briefs.
2. **Who found the pitfalls.** Section 3 asks for problems that really happened after the decision.
   In `design-01`, four of the five P items come from one commit, 26 minutes after the decision and
   before any deploy, whose message says an advisor pass found them; the fifth was reported by the
   owner. In `design-02` the six P items come from an audit and from later fix commits, on a
   feature that was live. All eleven are real defects of the decisions as built. But most were
   first noticed by AI review passes, some of them by an advisor model, so the checklists lean
   toward what such a reviewer notices.
3. **Material size.** Section 3 says 20k to 70k tokens. Measured with one counting call each, the
   material is about 93k tokens (`design-01`) and 84k tokens (`design-02`); the builders estimated
   at 4 bytes per token and the real ratio is about 2.6. The tasks are kept as built: every file
   left carries an anchor of the checklist.

**What follows for row `design-decision`.** Points 1 and 2 can only help a Fable cell. So:

- If no Fable cell satisfies rule Q or B, the result stands as written: the row is `opus-5-5@xhigh`
  and the table says "Fable 5.2 measured, not adopted".
- If a Fable cell does satisfy rule Q or B, the result is recorded as **provisional** and the row
  does not move. It would move only after the same rule holds on two fresh tasks whose P items
  come from field reports and that are built with no Fable model in the loop, the advisor included.
- The `fast` rule compares two non-Fable cells and is not affected.

**What follows for row `ux-design`.** A Fable advisor was consulted by the brief builder and the
brief finisher (5 of the 19 calls). The briefs are descriptions of what the owner wants, both
designers get the same one, and the judge is the owner, blind. The checklist condition can only hold
Fable back. Rules UQ, UB and UD stand as written.

**Checked for the same reason.** A run in the harness cannot read outside its working directory:
a Read of an absolute path outside it was refused and logged (`--restricted`, Claude Code 2.1.323).
So the paths to the live repositories that the material mentions cannot leak later history.

**Order and budget.** The `ux-design` runs go first, then stage 1 of `design-decision`; stage 2
runs only as far as the ceiling of section 2 allows. Spent before the first run: about $61 at list
price ($58 for building and reviewing the tasks, $24 of it advisor calls; $3 for device checks).

## Addendum 3, 2026-11-13T15:40Z: infrastructure errors, page checks and run order

Written while the designer runs of `ux-design` were in progress, before any page was built and
before any `design-decision` run. None of these points changes a threshold.

1. **An API or infrastructure error is not the model's failure.** Section 2 says a run with no
   valid answer after the harness's retries counts as failed. That was written for a model that
   cannot answer within the limits, not for an outage. An attempt is an infrastructure error when
   the CLI reports an API error status, or when the call failed with no model output and was not a
   refusal. Such attempts do not use up a slot's retries, the slot is run again later, and a batch
   stops at the first one. A slot that could never be completed for that reason is reported as
   "not run": it is neither a pass nor a fail, and a rule that needs it stays undecided. A timeout
   of the harness, a missing answer and a refusal keep their meaning.
2. **Builder rules added for every arm alike, before any build.** The frames the owner sees allow
   scripts only. The builder prompt therefore also forbids modal dialogs, form submission, page
   navigation and the History API, and a page that uses them is rejected and rebuilt.
3. **A render check before any pair is made.** Every built page is loaded in a headless browser
   inside the same sandboxed frame. A page with an uncaught script error on load or on a first
   click, or one that renders nothing, is rejected and rebuilt within the same retry cap. The check
   works by page id and never reads which arm a page belongs to.
4. **Order of stage 1.** One run per cell on `design-01` first, to see run time and cost against
   the harness limits (1200 s, $6 a run). If a cell needs more time than that, the limit is raised
   for every cell of the row before the rest run. Then the twelve `opus-5-5@xhigh` runs and their
   judging, then the other cells.
5. **Stage 2 within the ceiling.** The `fast` candidates come first, because only they can still
   change a cell: under addendum 2 a Fable result can be provisional at most. Stage 2 for a Fable
   cell is put to the owner before it is run.

## Addendum 4, 2026-11-13T17:55Z: limits in the pilot, and outages

Written after the 36 designs and 41 of the 48 pages of `ux-design` were stored, before any checklist
call, before the owner saw any page and before any `design-decision` run. None of these points
changes a threshold. Points 1 to 3 close a gap in addendum 3, point 4.

1. **A limit is not part of a run's identity.** A run id is made of the harness version, the task,
   the task's fingerprint, the cell and the repeat number. Raising the time limit or the per-run
   cost cap keeps every stored run.
2. **When a limit is raised.** The pilot is one run per cell on `design-01`. A limit is doubled for
   every cell of the row (1200 s to 2400 s, $6 to $12) when any pilot attempt ended at that limit,
   or when any valid pilot run used more than three quarters of it (900 s, $4.50). The cost cap is
   treated exactly like the time limit. After the pilot the limits are frozen for the row.
3. **A pilot attempt that ended at a limit** counts as one of its slot's three attempts, like any
   invalid attempt. The slot keeps its two other attempts under the raised limit.
4. **What happened.** On 2026-11-13 at about 17:40Z, during the page builds, four builder processes
   stopped making progress at the same time: each had run for 16 minutes where the same kind of
   build had taken 6 to 7, each used almost no CPU, and their connections had been reopened
   together. The operator interrupted the batch before the time limit. The tool does not log an
   interrupted attempt, so nothing was counted and the four pages are built again. The builder is
   not a model under test. No log of the interruption itself exists; this is the reason for point 5.
5. **Outage evidence, from now on, for both rows.** The harness cannot tell a dead connection from
   a slow model: it would log a timeout, and addendum 3 says a timeout keeps its meaning. So:
   - while a paid batch runs, a watchdog logs every 20 s whether a TCP connection to the API host
     opens (it sends no data), and the system's own sleep log is kept;
   - a batch starts only after a check passes; `design-decision` runs go in batches of at most 8;
   - after each batch every invalid attempt is looked at before the next batch starts;
   - an invalid attempt **that has no answer** (a timeout, or an error ending) is an infrastructure
     error in the sense of addendum 3, point 1, when its time window contains a system sleep, a
     failed watchdog check, or a gap in the watchdog log of more than 60 s. The tools cannot see
     this themselves, so the attempt's line is moved, unedited, from the log to a set-aside file,
     the slot is run again, and the report lists every such line with its evidence. This is decided
     from the time window and the logs alone;
   - a timeout with no such evidence counts as before, and a run with a valid answer is never set
     aside;
   - the operator may interrupt a batch only on the same evidence (a failed check, a gap or a
     sleep) and only when every running process has stopped making progress.
