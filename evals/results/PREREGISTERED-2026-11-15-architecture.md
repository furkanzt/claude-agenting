# Pre-registered: Opus `xhigh` against Sonnet `xhigh` on the architecture row (2026-11-15)

Written at 2026-11-15T20:20Z, before any model under test has been asked for a design on the new task and before
any new run of this round. The commit time is the record. Claude Code 2.1.325.

## Why

The row "decide an architecture or approach that later work is built on" is `opus`/`xhigh` in `fast`
and in `balanced`. On 2026-11-13 Sonnet 5.5 at `xhigh` could not be told apart from it on six runs, at
44% of the cost ([`REPORT-2026-11-13.md`](REPORT-2026-11-13.md), section 5), and the rules of that round
said a cheaper cell for `balanced` was not decided: the row had two tasks and the plugin's bar asks for
three. On 2026-11-15 the owner gave the row to Sonnet `xhigh` in the new mode `cheapest` and asked for
more runs and a third task, to see whether `fast` or `balanced` can take it too.

## Question

Over three tasks, does `sonnet-5-5@xhigh` fail the row's checklist more often than `opus-5-5@xhigh`?

## What is fixed

- **Cells.** `opus-5-5@xhigh` and `sonnet-5-5@xhigh`. No other cell is run.
- **Tasks.** `design-01` and `design-02`, unchanged since 2026-11-13, and a new one, `design-03`. Each
  is a real decision from the history of one of the owner's projects, from three different
  repositories. The design of a task, its pass rule and the judging are those of
  [`PREREGISTERED-2026-11-13-think-first.md`](PREREGISTERED-2026-11-13-think-first.md), section 3,
  and are not repeated here: the material is the project just before the decision, the checklist has
  binding rules (C items) and pitfalls that really followed (P items), and a run passes one judge pass
  when it violates no C item and handles all but at most one P item.
- **Who built `design-03`.** Neither model under test. Three scouts found candidate decisions; a
  Fable 5.2 agent wrote the prompt and the checklist; one Opus 5.5 reviewer and one Sonnet 5.5
  reviewer each read it once, one to confirm every item and one to break it; a Fable 5.2 agent
  applied their findings (16 applied or applied in part, 13 rejected with a reason). The owner then
  checked the checklist and left it as it was: 4 C items and 6 P items. All of that happened before
  any model was asked for a design. The task is frozen by its hash in `evals/tasks.json`
  (`d4c8b7c9…`); it is not rebuilt, hardened or dropped after a run exists, and a task found broken is
  reported and left out for both cells. Its material is 26 files and 255,516 bytes, 16% more than
  `design-02`'s; the earlier round's limit of 70k tokens was not measured for it. Because Fable 5.2
  wrote it, it must not be used to compare a Fable cell.
- **Judging.** Four passes a run: two by `fable-5-1@high` (the harness's pinned judge) and two by
  `opus-5-5@high`. A judge sees the prompt, the checklist and one answer, never which cell wrote it.
  A run is a **solid fail** under one judge model when both of that judge's passes fail it. A run
  slot with no valid answer after the harness's retries is a **failed slot**. A cell's **fails** under
  a judge are its solid fails plus its failed slots.
- **Both judges must agree.** Every count is made twice, once per judge model, and a rule fires only
  if it fires under both.
- **Runs.** Each cell ends with 6 runs on `design-01`, 12 on `design-02` and 12 on `design-03`: 30
  a cell. The 18 runs stored on 2026-11-13 are kept (Opus 6 and 6, Sonnet 3 and 3), so 42 runs are
  new: 18 of Opus and 24 of Sonnet. `design-01` gets the fewest because every cell passed every run
  of it.
- **Instrument.** `evals/evalkit.py run` and `judge`, the same harness and settings as on
  2026-11-13: `claude -p --restricted`, read-only file tools, the advisor switched off for every
  child. A run that reports a second model is listed and counts as a failed slot.
- **The rules below** were shown to the owner in plain words before this file was committed, and the
  owner took them as they stand, with the limit in point 1 of the last section.
- **Spending ceiling.** $130 at list price for the runs and both judges. Work stops and is reported
  when it is reached; a cell is then judged on the slots it has, and a rule that needs all 30 is
  "not decided".

## Rules

`F(cell)` is a cell's fails over all 30 runs under one judge; `F(cell, task)` is the same on one task.

- **`fast`.** Sonnet `xhigh` takes the row in `fast` when `F(sonnet) <= F(opus) + 2` and, on each
  task, `F(sonnet, task) <= F(opus, task) + 2`. Otherwise `fast` stays `opus`/`xhigh`.
- **`balanced`.** Sonnet `xhigh` takes the row in `balanced` when the `fast` rule holds and, on top of
  it, `F(sonnet) <= F(opus)` and Sonnet has more fails than Opus on at most one of the three tasks.
  Otherwise `balanced` stays `opus`/`xhigh`.
- **`cheapest`** is Sonnet `xhigh` by the owner's decision of 2026-11-15 and no rule here moves it.
  If `F(sonnet) > F(opus) + 5`, the report says that Sonnet was clearly worse and puts the row in
  `cheapest` back to the owner.
- **"critical"** stays `opus`/`xhigh`.
- **Reported beside the rules, used for no decision:** P items handled per run, the share of runs
  that pass all four judge passes, the measured mean cost and time per run, and the result on the
  12 new Opus runs and 12 new Sonnet runs of `design-03` alone, the one task whose checklist no
  Opus agent wrote.

## What this can change

The architecture row in `fast` and in `balanced`: the routing table of `skills/agenting/SKILL.md`
(which is `balanced`), the table of `reference/modes.md`, and their evidence text. If `fast` moves,
the second sentence of the tip that a Pro chat sees changes with it, because it would no longer be
true: instead of naming Opus for a design decision it says to raise the effort to `xhigh` and stay
on Sonnet.

## Limits known beforehand

1. **Thirty runs a cell show a large difference only.** A simulation of the two rules, with both
   hard tasks at the same share of fails: if the two cells were equal, the `fast` rule would pass
   Sonnet two times in three and the `balanced` rule about half the time. If Sonnet's real share of
   fails were 15 points above Opus's, `fast` would still pass it about three times in ten and
   `balanced` about one time in six; at 30 points, one time in twenty and one in sixty. So the rules
   can show that Sonnet is clearly worse. They cannot show that the two are equal.
2. **This is not the plugin's usual bar.** `evalkit.py decide` asks a cheaper cell to pass every
   confirmation run. Opus `xhigh` itself did not on 2026-11-13 (4 fails of 12), so that bar cannot
   choose here, and this round compares the two cells directly. The owner asked for the comparison.
3. **Three tasks, two of them hard.** `design-01` separated nothing in the earlier round. The tasks,
   not the runs, are the sample.
4. **Who wrote the checklists.** The checklists of `design-01` and `design-02` were written and
   reviewed by Opus agents; their P items are what Opus reviewers held to be foreseeable. That can
   only help Opus. `design-03` was written by a Fable agent and read once by each model under test.
5. **An Opus judge marks Opus's answers.** That is why both judge models must agree.
6. **Two versions of Claude Code.** The 18 stored runs were made on 2.1.323, the new ones on 2.1.325.
7. **List price.** How a plan counts each model against its limit is not published.
8. **The pitfalls were found by people and agents after the fact.** A design that avoids a problem
   nobody met gets no credit, and the judges read only what a design says. On `design-03` one of the
   six P items comes from a real incident; the other five are defects of the decision as it was
   built, found afterwards by an audit or a review and repaired before a loss was recorded.
   `design-02` holds the same kind of item. One of the five is weaker than the rest: its fix arrived
   before the defect could do any harm.
9. **Two P items of `design-03` go together.** A design that misses the one will usually miss the
   other, and then fails on one blind spot.

## Correction, 2026-11-15T22:28Z (after the runs; no rule changed)

An audit of the report found that limits 8 and 9, as committed at 20:27Z, named the subjects of three
P items of `design-03` and said where each came from. That is private task detail, and a public file
must not carry it. Three sentences were reworded to say the same without the subjects. Nothing else in
this file was touched: no cell, task, count, rule, margin or ceiling. The first wording exists only in
the unpushed working commit of 20:27Z, and it must not reach the pushed history (`HANDOFF.md` says how).

The same audit found one place where the rule checker did not read a rule as this file words it. "A
run that reports a second model is listed and counts as a failed slot": the harness marks such a run
invalid and runs the slot again, and the checker looked only for a field that these two cells never
carry. The checker now counts a slot with such a run as failed even when the retry is valid. No run of
the record reported a second model, so no count changed. The report's section 6 has the details.
