# The `fast` column by the owner's bar, from stored runs: reading, 2026-11-15

No model was run for this. On 2026-11-14 the owner fixed what decides a cell in `fast`, and this note reads the
stored runs of the nine document rows by that bar. Source: [`runs.jsonl`](runs.jsonl) and
[`scores.jsonl`](scores.jsonl), every valid current run of every task of a row (1,250 runs), pooled over the
rounds of 2026-10-05 to 2026-11-14. The two new rows for building software are in
[`REPORT-2026-11-15-coding.md`](REPORT-2026-11-15-coding.md).

## 1. The bar

Fixed by the owner on 2026-11-14 (measured cost per finished task, never the price list; Opus stays wherever
the difference per task is small):

- **checked work** (a test or a validator catches a wrong result): the cheapest cell per finished task, every
  retry counted, at most three tries;
- **unchecked work:** at most about 1 failed run in 10, and the documentation lists what goes wrong;
- **don't-guess and verify:** at most about 1 wrong answer in 100.

A cell is named here only with at least 9 stored runs; under that it is a lead, which is not a decision. That
floor is this note's own. Where several cheaper cells are inside the bar and differ by less than a cent a run,
the note names the one with the fewest errors and the most runs, and lists the others. That follows the
owner's bar: the stronger cell stays where the difference per task is small.

**Words used.** A *row* is one kind of task in the routing table. A *cell* is one model at one effort. A
*failed run* did not pass the task's grader. A *finished task* is one that passed its test or validator.

## 2. Outcome

**Five of the nine rows keep their `fast` cell. Three have a much cheaper cell that meets the bar: classify,
don't-guess and verify; for verify the recommendation is still to keep today's cell. The architecture row has
a lead that only the owner can take.**

| Row | `fast` today | Cost a run | Cheaper cell that meets the bar | Cost a run | What is lost |
|---|---|---|---|---|---|
| List, count | `haiku`/`medium` | $0.010 | none cheaper meets it (`low` failed 8 of 45 runs) | | |
| Mechanical cleanup | `sonnet`/`low` | $0.13 | none (Haiku `high` changed words in 3 of 9 runs, `xhigh` in 2 of 9) | | |
| Read and report | `haiku`/`medium` | $0.006 | none worth naming (`haiku`/`low` is 2% cheaper at the same record) | | |
| Classify | `sonnet`/`low` | $0.034 | `haiku`/`xhigh`; also inside the bar, on 9 runs each: `haiku`/`high` ($0.004) and `haiku`/`medium` ($0.003) | $0.010 | 4.1% wrong labels against 2.8%; 71 s against 10 s |
| Synthesize | `opus`/`high` | $1.63 | `sonnet`/`xhigh` is 10% cheaper: a small difference, so Opus stays | $1.47 | |
| Don't guess | `sonnet`/`xhigh` | $0.30 | `haiku`/`xhigh` | $0.027 | 2 of 1,056 answerable items missed or wrong against 0. Invented answers: 6 in 1,848 against 10, so no loss there |
| Verify | `sonnet`/`high` | $0.11 | `haiku`/`xhigh` | $0.016 | 1 false confirmation in 384 verdicts against 0 in 480; 87 s against 26 s |
| Architecture decision | `opus`/`xhigh` | $2.31 | no cell meets the bar; lead: `sonnet`/`xhigh` | $1.02 | not shown on 6 runs |
| UI/UX design | `opus`/`xhigh` | | no cheaper designer was measured | | |

Costs are list price per run. What is lost: where the cheaper cell does worse than today's cell on the stored
runs.

## 3. Row by row

Failed runs are runs that did not pass the task's grader. Cost and time are means per run.

**List, count** (3 tasks). `haiku`/`medium`: 0 of 45 runs failed, $0.0095, 37 s. `haiku`/`low`: 8 of 45 failed,
$0.0074. Sonnet `high`: 5 of 45 failed at $0.077. The cell stays.

**Mechanical cleanup** (1 task). `sonnet`/`low`: 0 of 3 failed, $0.13. Haiku 5.5 failed 2 of 3 at `low`, 3 of 3
at `medium`, 3 of 9 at `high` and 2 of 9 at `xhigh` ($0.012 to $0.023 a run): it changes words. Above 1 in 10,
so the cell stays for unchecked cleanup. A lead for checked cleanup, where a word-for-word comparison in code
catches a changed word: Haiku `high` with retries would cost about $0.024 per finished task against $0.13.
One task and nine runs; not adopted.

**Read and report** (3 tasks). `haiku`/`medium`: 0 of 15 failed, $0.006, 0 wrong of 180 answers. `haiku`/`low`
has the same record at $0.0056 against $0.0058: 2% cheaper, which is inside the noise. Nothing cheaper is
worth naming.

**Classify** (3 tasks, unchecked work).

| Cell | Runs | Failed runs | Wrong labels | A label given to an item that should get none | Cost | Time |
|---|---|---|---|---|---|---|
| `haiku`/`xhigh` | 36 | 3 (8%) | 35 of 864 (4.1%) | 16 of 144 | $0.010 | 71 s |
| `haiku`/`high` | 9 | 1 (11%) | 10 of 216 (4.6%) | 3 of 36 | $0.004 | 23 s |
| `haiku`/`medium` | 9 | 1 (11%) | 14 of 216 (6.5%) | 6 of 36 | $0.003 | 15 s |
| `sonnet`/`low` (today) | 9 | 1 (11%) | 6 of 216 (2.8%) | 3 of 36 | $0.034 | 10 s |
| `sonnet`/`medium` (`balanced`) | 36 | 1 (3%) | 15 of 864 (1.7%) | 5 of 144 | $0.033 | 11 s |

`haiku`/`xhigh` meets the bar at a third of the cost. All three of its failed runs are on one task (3 of 12
there). `haiku`/`high` and `haiku`/`medium` are cheaper again and three to five times faster. Both are inside
the bar on 9 runs each, with 1 failed run, the same as today's cell; `medium` gives more wrong labels. The
three Haiku cells differ by less than a cent a run, so the note names `xhigh`: the fewest wrong labels of the
three, on four times the runs. `haiku`/`low` is outside the bar (2 of 9 failed). Two more things the table
shows: `xhigh` is seven times slower than Sonnet, and Sonnet `medium` costs the same as Sonnet `low` with
fewer wrong labels on four times the runs.

**Synthesize** (3 tasks). `opus`/`high`: 0 of 9 failed, $1.63, 276 s, 2 of 69 planted items missed. `sonnet`/
`xhigh`: 0 of 9, $1.47, 577 s, 3 missed. Ten percent cheaper and twice as slow: the difference per task is
small, so Opus stays. A lead: `opus`/`medium` at $1.35 with 0 of 18 items missed, on 3 runs of one task.

**Don't guess** (11 tasks).

| Cell | Runs | Invented answers to unanswerable items | Runs with at least one | Answerable items missed or wrong | Cost | Time |
|---|---|---|---|---|---|---|
| `haiku`/`xhigh` | 84 | 6 of 1,848 (0.32%) | 5 | 2 of 1,056 | $0.027 | 57 s |
| `sonnet`/`xhigh` (today) | 84 | 10 of 1,848 (0.54%) | 9 | 0 of 1,056 | $0.297 | 36 s |
| `haiku`/`high` | 93 | 14 of 1,950 (0.72%) | 12 | 3 of 1,176 | $0.018 | 35 s |
| `haiku`/`medium` (7 of the 11 tasks) | 69 | 12 of 1,230 (0.98%) | 9 | 0 of 888 | $0.017 | 23 s |
| `opus`/`xhigh` ("critical") | 45 | 0 of 1,182 | 0 | 0 of 552 | $0.548 | 41 s |

`haiku`/`xhigh` is under 1 in 100, not above Sonnet on the same items and runs, and costs a tenth. `haiku`/
`high` and `haiku`/`medium` are a cent cheaper and also under 1 in 100 when all tasks are pooled, but not on
the hard ones: on the two tasks where every cell did worst (the fourth and the fifth) `high` failed 9 of 12
runs, `xhigh` 4 of 12 and Sonnet `xhigh` 9 of 12, and `medium` was not run on the four newest tasks. So the
note names `xhigh`. The rule
written before the round of 2026-10-11 kept Sonnet for `fast` because Haiku `xhigh` had 1 invented answer in
720 against Sonnet's 0 in that round; moving `fast` is the owner's overrule of that rule, on the pooled count
and the new bar.

**Verify** (3 tasks).

| Cell | Runs | Wrong verdicts | False confirmations | Cost | Time |
|---|---|---|---|---|---|
| `haiku`/`xhigh` | 36 | 1 of 384 (0.26%) | 1, in 1 run | $0.016 | 87 s |
| `sonnet`/`high` (today) | 45 | 0 of 480 | 0 | $0.107 | 26 s |
| `haiku`/`medium` | 45 | 8 of 480 (1.67%) | 8, in 8 runs | $0.008 | 35 s |
| `opus`/`high` ("critical") | 9 | 0 of 96 | 0 | $0.216 | 34 s |

By the number `haiku`/`xhigh` is under 1 in 100. `haiku`/`high` is at the edge of the bar: 1 wrong verdict of
96 on 9 runs, at $0.011. Every false confirmation of every Haiku 5.5 cell is on the same one task of three.
Verify is the step that catches what the other rows let through, and the bar was agreed on 2026-11-14 with
Haiku kept out of verify. The recommendation is to keep `sonnet`/`high`; the owner decides.

**Architecture or approach decision** (2 tasks). On the harder task no cell meets the bar: `opus`/`xhigh`
failed 4 of 6 runs there, `sonnet`/`xhigh` 2 of 3, `opus`/`high` 3 of 3. Over both tasks: `opus`/`xhigh` 4 of
12 failed, $2.31, 682 s, 55 of 66 pitfalls handled; `sonnet`/`xhigh` 2 of 6 failed, $1.02, 459 s, 28 of 33.
The same share of failed runs at under half the cost, on six runs. A lead, as the report of 2026-11-14 said.

**UI/UX design.** Only Opus cells and Fable 5.2 cells (the vendor's larger model, measured in the report of
2026-11-13) were measured as designers. The cell stays.

## 4. Limits

1. **Pooled over rounds.** The runs of a cell come from several days and several versions of Claude Code
   (2.1.290 to 2.1.325). Within a row every cell saw the same tasks, but not always the same number of runs.
2. **Few tasks.** Three tasks a row for most rows, one for cleanup, two for the architecture row. Where all
   failures of a cell sit on one task (classify, verify), the share over all runs understates that task.
3. **The bar counts runs and items, not what a wrong result costs later.**
4. **List price.** How a $20 plan counts each model against its limit is not published.
5. **Speed.** Haiku at `xhigh` is the slowest cell of its rows. `fast` here means cheaper at list price, not
   quicker. How much lighter that is on a $20 plan's usage limit is not published (limit 4).

## 5. What changes

The owner decided on 2026-11-15. Released in 3.7.0.

- **A third mode, `cheapest`, below `fast`.** It takes the cheapest cell inside the bar on every row and
  keeps `fast`'s agent rules. No plan starts a chat there; the user chooses it. Its losses are listed in
  `skills/agenting/reference/modes.md`.
- **Classify:** `fast` keeps `sonnet`/`low`. `cheapest` takes `haiku`/`xhigh`.
- **Don't guess:** `haiku`/`xhigh` in `cheapest` and `fast`, and in `balanced` as well. The owner asked
  whether a cell that invents fewer answers at a tenth of the cost is not simply better, and moved
  `balanced` on the pooled count. That overrules the rule of 2026-10-11 for both modes. A job called
  "critical" stays on `opus`/`xhigh`.
- **Verify:** `fast` keeps `sonnet`/`high`. `cheapest` takes `haiku`/`xhigh`. The review row follows verify.
- **Architecture decision:** `fast` keeps `opus`/`xhigh`. `cheapest` takes `sonnet`/`xhigh` on six runs.
  The owner asked for more runs and a third task before another mode moves; that is a round of its own,
  with its own rules.
- **Synthesize, list, cleanup, read and UI/UX design:** no change. `cheapest` has `fast`'s cell there.
