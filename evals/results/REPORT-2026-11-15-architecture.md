# Opus `xhigh` against Sonnet `xhigh` on the architecture row: report, 2026-11-15

Rules: [`PREREGISTERED-2026-11-15-architecture.md`](PREREGISTERED-2026-11-15-architecture.md), committed on
2026-11-15 at 20:27Z in one commit with the third task's entry in `evals/tasks.json` and the rule checker,
`evals/probes/architecture_analysis.py`. That commit is earlier than every run of the round, and no model had been
asked for a design on the new task before it. Record: `runs.jsonl` and `scores.jsonl` in this folder, numbers
only. Runs: 42 design runs between 20:27Z and 21:47Z and 168 judge passes between 21:47Z and 22:01Z, on Claude Code
2.1.325 with the advisor off; the 18 runs kept from 2026-11-13 were made on 2.1.323. Every figure is list price.
Commits are named by their message here, not by hash, because the hashes of unpushed commits change when they are
grouped for a push.

Audited on 2026-11-15 by four independent reviewers (the numbers, the rules, privacy and plain words, the change to
the skill), each followed by a second agent that tried to refute the findings. They found no wrong number and no
rule applied wrongly. Of 31 findings, 17 asked for a correction and 12 of those were confirmed; they are applied
here, with most of the smaller notes. Section 6, points 6 and 7, says what the audit changed outside this text.

**Words used here.** A *cell* is one model at one effort: `opus-5-5@xhigh` and `sonnet-5-5@xhigh` are the two of
this round. A *task* gives a model a real project as it stood just before a real decision, and asks for the
design. Its checklist has *C items* (rules the design must not break) and *P items* (pitfalls that really followed
the decision). One *judge pass* is one reading of one design by a judge model; a design *passes* it when it breaks
no C item and handles all P items but at most one. Every design gets four passes: two by `fable-5-1@high` and two
by `opus-5-5@high`. A run is a *solid fail* under a judge when both of that judge's passes fail it. A cell's
*fails* are its solid fails plus its slots with no valid answer (there were none). The *architecture row* is the
line of the plugin's routing table for the job "decide an architecture or approach that later work is built on":
it names the cell that does that job. A *mode* (`cheapest`, `fast`, `balanced`) is a setting of the plugin that
picks one cell for every row; "critical" is the word a user says to send one job to the most careful cell.
*Effort* is how much a model thinks before it answers; `xhigh` is the highest effort measured here.

## 1. Outcome

**All 60 planned runs exist and are judged, 30 for each model. Sonnet 5.5 at `xhigh` failed 7 of its 30 and Opus
5.5 at `xhigh` failed 10 of its 30.** Both judge models gave exactly these counts.

**All 17 fails are on one task, `design-02`:** Opus failed 10 of its 12 runs there and Sonnet 7 of 12. Every run
of both models passed `design-01` and the new task, `design-03`.

**By the rules written first, Sonnet at `xhigh` now does the architecture job in the modes `fast` and
`balanced`.** The `fast` rule asks that Sonnet have at most 2 more fails than Opus, over all runs and on each
task: it has 3 fewer. The `balanced` rule adds two conditions: Sonnet may not have more fails in total, and it
may have more fails than Opus on at most one task. It has more on none. `cheapest` already had Sonnet `xhigh`,
and "critical" keeps Opus `xhigh`; no rule changes those two.

**What this shows and what it does not.** In these runs the cheaper model was not worse, at 48% of the cost
($1.11 a run against $2.32) and 73% of the time (510 seconds against 696). It does not show that Sonnet is
better: a gap of 7 against 10 fails of 12 is one that luck alone often produces. And only one task decides the
verdict, because the new task showed no difference between the two models (section 5).

**With one hard task the rules are weaker than they looked when the owner took them.** The owner was told that
a Sonnet failing 15 points more often than Opus would still get `balanced` about 1 time in 6. With one hard task
it is about 1 time in 4, and such a Sonnet would get `fast` about 2 times in 3 (section 5). So the rules cannot
show that the two models are equal, and `fast` in particular accepts a model that is somewhat worse.

**Neither model is reliable on the hard task.** Opus passed 2 of 12 runs and Sonnet 5 of 12. The owner's bar for
work that no test checks is about 1 failed run in 10. The rules of this round compare the two cells; they do not
say that the cheaper one is good enough alone.

**What changes** (section 8): the architecture row becomes `sonnet`/`xhigh` in `fast` and in `balanced`, and the
tip that a Pro chat sees at its first start no longer sends an architecture decision to Opus.

## 2. What was run

| Time (UTC), 2026-11-15 | What |
|---|---|
| to 19:58 | The third task built: three scouts looked for candidate decisions; a Fable 5.2 agent wrote the prompt and the checklist; one Opus 5.5 reviewer and one Sonnet 5.5 reviewer each read it once, one to confirm every item and one to break it; a Fable 5.2 agent applied their findings |
| 20:00 to 20:20 | The owner was shown the checklist and the rules in plain words at 20:00, and answered at 20:20: the checklist as it was, the rules as they stand |
| 20:20 to 20:27 | The rules file written; committed at 20:27:22 with the task's entry and the rule checker (26 tests, each red-proofed) |
| 20:27 to 21:38 | 39 runs in one command, six processes at a time: `design-02` (6 Opus, 9 Sonnet) and `design-03` (12 each) |
| 21:38 to 21:47 | The 3 missing Sonnet runs on `design-01` |
| 21:47 to 21:56 | 84 passes by the pinned judge, `fable-5-1@high` |
| 21:56 to 22:01 | 84 passes by the second judge, `opus-5-5@high` |
| 22:01 | `python3 evals/probes/architecture_analysis.py` prints DECIDED |

Each cell ends with 6 runs on `design-01`, 12 on `design-02` and 12 on `design-03`. The 18 runs of 2026-11-13
(Opus 6 and 6, Sonnet 3 and 3 on the first two tasks) and their 72 judge passes are kept as they were.

All 42 new runs were valid at the first attempt. No run was refused, timed out, hit the cost cap, ended on an API
error or reported a second model, and every one ended with the stop reason `end_turn`. No judge pass needed a
second attempt. The cell hashes, the task hashes and the checklist hashes of the first two tasks are the same in
the lines of both days.

## 3. Results

Fails, counted the same by both judge models:

| Cell | `design-01` | `design-02` | `design-03` | All 30 | Mean cost per run | Mean time |
|---|---|---|---|---|---|---|
| `opus-5-5@xhigh` | 0 of 6 | 10 of 12 | 0 of 12 | **10** | $2.32 | 696 s |
| `sonnet-5-5@xhigh` | 0 of 6 | 7 of 12 | 0 of 12 | **7** | $1.11 | 510 s |

The rules, with F for a cell's fails:

| Rule | What it asks | Under `fable-5-1@high` | Under `opus-5-5@high` | Result |
|---|---|---|---|---|
| `fast`, total | F(sonnet) <= F(opus) + 2 | 7 <= 12 | 7 <= 12 | holds |
| `fast`, each task | F(sonnet, task) <= F(opus, task) + 2 | 0 <= 2, 7 <= 12, 0 <= 2 | the same | holds |
| `balanced`, total | F(sonnet) <= F(opus) | 7 <= 10 | 7 <= 10 | holds |
| `balanced`, tasks | Sonnet has more fails on at most one task | on none | on none | holds |
| "clearly worse" | F(sonnet) > F(opus) + 5 | 7 > 15: no | 7 > 15: no | not reported |

So `fast`: `sonnet-5-5@xhigh`. `balanced`: `sonnet-5-5@xhigh`. `cheapest`: `sonnet-5-5@xhigh`, as the owner
decided. "critical": `opus-5-5@xhigh`.

The two judge models agreed on every one of the 60 runs whether it is a solid fail. In 1 of the 120 pairs of run
and judge the two passes disagreed on pass or fail: an Opus run on `design-02` from 2026-11-13, which counts as
passed because a split is not a solid fail.

## 4. Reported beside the rules (used for no decision)

- **Pitfalls handled per run, as the judges counted them.** A range means the four passes did not agree.
  - `design-01` (5 pitfalls): Opus handled all five in each of its 6 runs. Sonnet handled all five in 5 runs and
    four in 1 run, which still passes.
  - `design-02` (6 pitfalls): Opus 5, 4 to 6, 3, 3, 4, 4, 3, 3, 4, 4, 4, 3 to 4. Sonnet 4, 5, 4, 5, 5 to 6, 3, 4,
    5 to 6, 4, 4, 3 to 4, 5. Mean over the judge passes: Opus 3.88 under the Fable judge and 3.71 under the Opus
    judge, Sonnet 4.42 and 4.25.
  - `design-03` (6 pitfalls): Opus handled all six in every run under the Fable judge, and under the Opus judge in
    22 of 24 passes (five in the other two). Sonnet handled all six in 11 runs; in the twelfth, three passes
    counted five and one counted six.
- **Runs that pass all four judge passes:** Opus 19 of 30 (6, 1 and 12 on the three tasks), Sonnet 23 of 30 (6, 5
  and 12).
- **Cost and time per task.** Opus: $2.49 and 752 s on `design-01`, $2.13 and 628 s on `design-02`, $2.42 and
  737 s on `design-03`. Sonnet: $1.00 and 425 s, $1.06 and 482 s, $1.22 and 580 s.
- **`design-03` alone,** the one task whose checklist no Opus agent wrote: 0 fails of 12 for each cell under each
  judge.
- **Constraints.** One judge pass of the 240 counted a C item as broken (the Opus judge, on the split run named
  above). No run had one under both passes of a judge.

## 5. Beyond the rules (post hoc; used for no decision)

- **The new task showed no difference between the two models.** Every run of both models passed it, and all but
  5 of its 96 judge passes counted all six pitfalls as handled. The design the project really used avoided none
  of the six, so every run handled what the real decision did not. Whether the task as written makes the
  pitfalls easier to see than they were at the time, or both models are simply good at this kind of decision, one
  task cannot say. The rules expected two hard tasks ("Three tasks, two of them hard"). There was one.
- **So the verdict rests on 12 runs a cell on `design-02`.** Ten fails against seven is not a reliable
  difference. If the two models were really equal, a gap this large would still appear about 37 times in 100 by
  luck alone (Fisher's exact test, two-sided, p = 0.37).
- **How often the two rules would give Sonnet the row, with one hard task.** Worked out exactly for 12 runs a
  cell on one task, with no fails on the other two tasks, as happened. With one hard task the `balanced` rule is
  only "no more fails in total": its second condition cannot fail.

  | If the real share of fails on the hard task is | The `fast` rule gives Sonnet the row in | The `balanced` rule in |
  |---|---|---|
  | Opus 70%, Sonnet 70% (equal) | about 87 of 100 repeats | about 59 of 100 |
  | Opus 70%, Sonnet 85% (15 points worse) | about 64 of 100 | about 26 of 100 |
  | Opus 50%, Sonnet 80% (30 points worse) | about 31 of 100 | about 8 of 100 |

  The 70% is the share of fails over both cells here (17 of 24); the last line starts from 50% because a gap of
  30 points does not fit above 70%. So a Sonnet that is much worse would rarely have got `balanced` and would
  still have got `fast` about one time in three; one that is somewhat worse would have got `balanced` about one
  time in four and `fast` about two times in three.
- **Nobody is reliable on the hard task.** 17 of the 24 runs failed it, each because the design left two or
  more of the six foreseeable pitfalls open. With this few runs the real share of fails could be anywhere from
  55% to 95% for Opus and from 32% to 81% for Sonnet (95% Wilson score intervals: a range that would hold the
  real value in about 95 of 100 repeats of the experiment).
  The report of 2026-11-13 found the same with fewer runs. A second look after a design (a second designer, or a
  reviewer told to break the design) is still unmeasured.
- **The stored and the new runs on `design-02`.** Opus failed 4 of its 6 stored runs and 6 of its 6 new ones;
  Sonnet 2 of 3 and 5 of 9. The two sets were made on two versions of Claude Code. The numbers are too small to
  say whether anything moved.
- **Sonnet wrote about as much as Opus on the two tasks with 12 runs, and less on the first.** Mean output per
  run, thinking included: Sonnet 55,000, 59,000 and 72,000 tokens on the three tasks, Opus 75,000, 60,000 and
  72,000. On `design-02` and `design-03` the gap in cost is the price of a token, not less work. On `design-01`
  Sonnet wrote about a quarter fewer tokens.

## 6. Events and deviations

1. **Processes at a time.** The first command ran six processes at a time and the second three; the harness's
   default is four. Both judge commands ran six at a time. The rules fix none of this, and no run timed out.
2. **The first draft of the rules had a flaw, found before the commit.** A test of the rule checker showed that
   `balanced` could pass where `fast` failed. The `balanced` rule was changed to include the `fast` rule, the
   simulation in the rules file was redone, and the owner saw the corrected rules. No run existed yet.
3. **The simulation in the rules file does not describe what happened.** It assumes both hard tasks at the same
   share of fails. The new task had none, so its figures (for example, that `fast` passes an equal Sonnet two
   times in three) do not apply; section 5 gives the figures for one hard task.
4. **Who built `design-03`.** As the rules say: a Fable 5.2 agent wrote it and a Fable 5.2 agent applied the
   review. Neither model under test wrote it, and each read it once as a reviewer. Because Fable 5.2 built it,
   the task must not be used to compare a Fable cell. Its material is 255,516 bytes in 26 files, 16% more than
   `design-02`'s.
5. **Nothing was run again, dropped, re-judged or changed after its first run.** No task was touched after the
   commit of the rules.
6. **Three places where the rule checker did not read the rules as they are worded; none fired.** Found by the
   audit, after the runs. (a) "A run that reports a second model is listed and counts as a failed slot." The
   harness marks such a run invalid and runs the slot again, and the checker looked only for a field
   (`advisor_called`) that these two cells never carry. So a second-model run followed by a valid retry would
   have counted as an ordinary run. The checker was corrected after the audit and now counts such a slot as
   failed and lists it, with a test. The record has no invalid line, and each of the 60 runs reports one model,
   the cell's own. (b) A slot whose every attempt ended on an API error is "lost" and keeps the verdict pending;
   the rules call a slot with no valid answer after the retries a failed slot. No slot had a second attempt.
   (c) The rules say that when the spending ceiling is reached a cell is judged on the slots it has; the checker
   gives no verdict until all 60 slots are decided. The ceiling was not reached. (b) and (c) are left as they
   are.
7. **The rules file was corrected after the runs, for privacy only.** Its limits 8 and 9, as committed at
   20:27Z, named the subjects of three pitfalls of the new task. A public file must not carry that. Three
   sentences were reworded at 22:28Z and a dated note was appended to the file; no cell, task, count, rule,
   margin or ceiling was touched. The first wording exists only in an unpushed commit.
8. **The size of the new task's material was not counted in tokens.** The rules of 2026-11-13 asked for 20,000
   to 70,000 tokens of material a task; its two tasks measured about 93,000 and 84,000 and were kept. The new
   task's material is 16% larger than `design-02`'s in bytes. Every run read it without a timeout or a cost cap.

## 7. Spend (list price)

| What | Cost |
|---|---|
| 18 new Opus `xhigh` runs | $41.81 |
| 24 new Sonnet `xhigh` runs | $27.24 |
| 84 passes of the pinned judge, `fable-5-1@high` | $33.00 |
| 84 passes of the second judge, `opus-5-5@high` | $10.44 |
| **Total** | **$112.49** of the $130 ceiling |

Building the third task (scouts, builder, two reviewers, finisher) ran as agents of the live session and is not in
this figure.

## 8. What changes in the repository

- **The architecture row** ("Decide an architecture or approach that later work is built on") becomes
  `sonnet`/`xhigh` in `fast` and in `balanced`: the routing table of `skills/agenting/SKILL.md`, the table of
  `skills/agenting/reference/modes.md` and their evidence text. "critical" keeps `opus`/`xhigh`.
- **The tip of a Pro chat's first-start line** changes its second sentence, as the rules say: for an
  architecture decision it no longer names Opus, it says to raise the effort to `xhigh` and stay on Sonnet.
- **The design agent keeps its pin.** `agents/system-architect.md` is pinned to `opus`/`xhigh`, and the rules do
  not list it. It stays there, as the cell "critical" picks, and the think-first step of the skill now says to
  write `model: 'sonnet'` on the call for any other job. The other way round (pin Sonnet, name Opus for a
  critical job) would fail unsafe: a forgotten model on the call would then put a critical decision on the
  cheaper cell.
- These changes are a commit of their own, after this report and its audit.

## 9. Limits

1. **Only one task decides the verdict.** `design-01` and `design-03` were passed by every run of both cells.
   The tasks, not the runs, are the sample, and here the sample is one task. The plugin's own standard asks for
   three tasks on a row; this row has three, and one that shows a difference between cells.
2. **Twelve runs a cell on one hard task cannot show that the two cells are equal,** and the `fast` rule does
   not reliably catch even a large gap: a Sonnet 30 points worse would still get `fast` about 1 time in 3, and
   `balanced` about 1 time in 12 (section 5).
3. **This is not the plugin's usual standard.** `evalkit.py decide` asks a cheaper cell to pass every
   confirmation run. Neither cell does, so that standard cannot choose here, and this round compares the two
   cells directly. The owner asked for the comparison.
4. **Who wrote the checklists.** The checklist of `design-02` was written and reviewed by Opus agents, which can
   only help Opus. Opus still failed it more often than Sonnet.
5. **An Opus judge marks Opus's answers.** Both judge models had to agree, and they agreed on all 60 runs.
6. **Two versions of Claude Code:** 2.1.323 for the 18 stored runs, 2.1.325 for the 42 new ones.
7. **One process, read-only tools, one prompt.** A run is `claude -p` with Read, Grep and Glob. It is not the
   `system-architect` agent file, and it is not a chat that already has earlier messages.
8. **A design is judged only by reading it.** Nothing was built from any of the 60 designs, and the judges read
   only what a design says. The pitfalls were found by people and agents after the fact, and a design that
   avoids a problem nobody met gets no credit.
9. **The three tasks are small projects of one owner** (two browser games and an exam-preparation app). They say
   nothing about large systems.
10. **List price.** How a plan counts each model against its limit is not published.

## 10. Worth doing next

- **A second look after a design,** on `design-02`: one designer alone fails it more often than not, on either
  model. Two cheap designers and a reviewer may beat one expensive designer.
- **A third task that tells cells apart.** It has to be a new task: `design-03` is frozen and is not hardened
  after its runs.
- **Sonnet at `high`** was never run on this row. If it holds on `design-02`, the main chat of a Pro plan would
  not need to raise its effort for a design.
