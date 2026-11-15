# How each cell of the routing table was measured

Read this before changing a cell of the routing table in [../SKILL.md](../SKILL.md) or citing one
of its numbers. The method is in [`evals/README.md`](../../../evals/README.md); each round's full
record is its `evals/results/REPORT-<date>.md`. Every cost is a list price measured per run.

## First sweep, 2026-10-06

[`evals/`](../../../evals/README.md)
ran every cell of each row on real tasks, three repeats, comparing measured cost
per run. Three rows changed:

- **Mechanical cleanup, `haiku/low` → `sonnet/low`.** Haiku failed all three runs
  (it left the page headers in); Sonnet at `low` passed all three.
- **Don't-guess (BELİRSİZ) and adversarial verify, `opus` → `sonnet`.** Sonnet
  `xhigh` hallucinated on none of 102 unanswerable items, as Opus `xhigh` did
  (Haiku: 19); Sonnet `high` gave no wrong verdict in 96, as Opus `high` did.
  Both rates are bounded below about 3% (95% confidence) and Sonnet cost about
  half as much. A deep-research pass found no published open-book comparison of
  the two models and showed that the closed-book gap in the vendor cards is
  knowledge, not abstention discipline
  ([`evals/research/2026-10-06-sonnet-vs-opus-open-book.md`](../../../evals/research/2026-10-06-sonnet-vs-opus-open-book.md)).
  This is a bounded null: it cannot exclude a gap of a few points, so a job the
  user calls critical gets Opus on these rows (until 3.6.0 that was the `quality`
  disposition; where this file says `quality`, read "critical").
- **Kept: scan, read-report, classify, synthesize** (scan and read-report moved on
  2026-10-09, below). Synthesis stays on Opus `xhigh` because there Sonnet does not
  do the same thing: Opus `xhigh` found every planted item in all 9 runs, Sonnet
  `xhigh` missed the same subtle one in 3 of 3 on one task and reported fewer
  genuine extra issues. For classify no cheaper cell cleared the plugin's evidence
  rules (pass every run and save at least 25%).
- **Haiku 4.5 ignored `effort`** (on the scan task it was the costliest cell, $0.17 a
  run). Haiku 5.5 does not; see the next block.
- **Disposition.** "critical" gets Opus on rows 5 to 7; `fast` uses Opus `high` for
  synthesis. See [reference/modes.md](modes.md).
- **Limits.** Nine runs per cell per high-stakes row, and 102 abstention items per
  model, show large gaps, not gaps of a few points. A harder paired test (near-miss
  unanswerable items, long documents) could still find one; the harness is ready
  for it. The scan row was tested without Bash. The architecture, security, incident
  and orchestration agents were not measured and keep their pins. Method, every
  number and the places where the harness's raw output was overridden:
  `evals/results/REPORT-2026-10-06.md`.

## Re-check with Haiku 5.5, 2026-10-09

The `haiku` alias now means Haiku 5.5
(`claude-haiku-5-5`, CLI 2.1.295): it honours `effort`, costs $0.10/$0.50 per MTok
for prompts up to 100k tokens (5x above that), and retires no sooner than
2027-10-07. Every row was re-run against its four effort cells, with six new tasks.
At three runs per task the harness named a Haiku 5.5 cell on six rows; 12-repeat
checks (verify, dont-guess, scan, classify; the rules and when each was written:
[`evals/results/PREREGISTERED-2026-10-09.md`](../../../evals/results/PREREGISTERED-2026-10-09.md))
and judgment overrides changed five of the six:

- **Scan, `haiku/low` → `haiku/medium`.** Exact in 36 of 36 runs over three tasks at
  $0.009 a run; `low` (the old pin, which the alias had turned into Haiku 5.5) 30 of
  36; Sonnet `high` 32 of 36 at $0.076; Haiku 4.5 2 of 6 on the new tasks.
- **Read and report, `sonnet/medium` → `haiku/medium`.** 9 of 9 on three exact-answer
  tasks at $0.006 a run against $0.118. The tasks do not separate cells (Haiku 4.5
  passes too), so effort is Anthropic's default, and open-ended reports were not
  measured; "critical" stays `sonnet/high`. The `researcher` agent keeps
  `sonnet/medium`: tracing and dependency mapping is wider than what was measured.
- **Don't guess stays `sonnet/xhigh`** for `fast` and `balanced`. On 2026-10-09 Haiku 5.5 `high` looked as safe
  as Sonnet (0 hallucinations in 408 items) and was held to `fast`; a pre-registered round on 120 fresh near-miss
  items (2026-10-10) then gave `haiku/high` 11 hallucinated item-runs of 720, Sonnet `xhigh` 10 of 720 and Opus
  `xhigh` 0 of 360, so `fast` reverted by the rule written beforehand. Training-knowledge traps tripped no cell.
  A second pre-registered round (E1b, 2026-10-11, 120 fresh items, 6 repeats in every cell) found Sonnet `xhigh` and
  Opus `xhigh` both clean (0 of 720) and Haiku `xhigh` at 1 of 720 on one item: Rule A needs a Sonnet baseline of at
  least 1% to move `balanced` to Opus, Rule B needs Haiku `xhigh` no worse than Sonnet for `fast`, so both rows stay
  `sonnet/xhigh`. Haiku `xhigh` is 13 times cheaper; moving `fast` to it would be the owner's overrule of Rule B.
- **Kept: cleanup** (Haiku 5.5 `high` passed 6 of 9 and altered at least one word in 7
  of 9 runs; Sonnet `low` altered none in 3), **classify** (`xhigh` gave 35 wrong labels
  in 864 against Sonnet `medium`'s 15, and a kazanım to a NONE item 16 times in 144
  against 5), **verify** (`medium` false-confirmed one finding in 6 of 12 runs; `xhigh`
  once in 36), **synthesize** (`medium` 3 of 3, then 3 of 6).
- **`low` was the weakest or tied-weakest effort** on scan, verify, dont-guess, cleanup
  and classify.
- **Limits.** Same harness (no Bash, one prompt shape, `effort` passed explicitly; subagents
  do apply a pinned effort, checked on 2026-10-09 from the effort recorded in their
  transcripts), 3 tasks per row (cleanup 1),
  Sonnet baseline runs #1 to 3 from an older CLI, the adopted cell is the best of four
  efforts, and prompts stayed far below the 100k tier. 36 of 36 bounds a per-run failure
  below about 8% but counts runs, not tasks. `evals/results/REPORT-2026-10-09.md`.

## Think-first round, 2026-11-13

Claude Fable 5.2 (`claude-fable-5-2`, $8 / $40 per MTok, twice Opus 5.5) was not tested as a worker:
Opus 5.5 already passes every stored run where the table uses it. It was tested where a model
decides or designs first and cheaper models build. The rules were committed before any task existed
([`evals/results/PREREGISTERED-2026-11-13-think-first.md`](../../../evals/results/PREREGISTERED-2026-11-13-think-first.md));
the full account is [`evals/results/REPORT-2026-11-13.md`](../../../evals/results/REPORT-2026-11-13.md).
Claude Code 2.1.323, list prices.

- **Architecture or approach decision: stayed `opus`/`xhigh` in this round; `sonnet`/`xhigh`
  below "critical" since the architecture round of 2026-11-15 (last section).** Two real
  decisions from the owner's projects, each with a checklist of binding constraints and of pitfalls
  that really followed. A run passes when it violates no constraint and misses at most one pitfall.
  Two judge models (Fable 5.1 `high`, Opus 5.5 `high`), two passes each, agreed on every count.

  | Cell | Easier task, runs passed | Harder task, runs passed | Mean cost per run |
  |---|---|---|---|
  | `fable-5-2` `low` | 3 of 3 | 0 of 3 | $2.63 |
  | `fable-5-2` `medium` | 3 of 3 | 0 of 3 | $2.86 |
  | `fable-5-2` `high` | 3 of 3 | 0 of 3 | $3.51 |
  | `opus-5-5` `xhigh` | 6 of 6 | 2 of 6 | $2.31 |
  | `opus-5-5` `high` | 3 of 3 | 0 of 3 | $1.34 |
  | `sonnet-5-5` `xhigh` | 3 of 3 | 1 of 3 | $1.02 |

  "Passed" means not failed by both passes of a judge. No Fable cell was free of failures and Opus
  `xhigh` had four, the case the rules call "both fail" and mark "no cell passed these tasks": no
  cell reached zero failures over both tasks, and the easier task separated nothing. So nothing
  moved, in `balanced` and for "critical". Neither cheaper cell was clean, so `fast` stays
  `opus`/`xhigh` too. A Fable advisor had helped build the tasks; that could only help Fable, and
  Fable still did not pass the harder task. On that one task no cell was reliable: one designer
  alone missed two or more of six foreseeable pitfalls in 18 of 21 runs. One task is not a rule.
- **UI/UX design before a build: `opus`/`xhigh`, and a design pass is not the default.** Four briefs
  from the owner's games; Sonnet 5.5 `medium` built every page; the owner chose blind between two
  pages per pair, 24 pairs. Design by Fable 5.2 `high` against design by Opus 5.5 `xhigh`: the owner
  preferred Fable's page in 4 of 12 pairs (the bar was 10). Design by Fable against no design pass:
  the designed page in 9 of 12 (the bar was 10), so a design pass is on request. On the checklist two judge models scored Fable's
  designs 0.875 and Opus's 0.802. The choices cluster by brief (one brief went 3 to 0 for Fable, three
  went to Opus), so this is closer to four observations than to twelve. An Opus design pass against
  no design pass was not compared.
- **No stored run shows a sign of an advisor call.** A harness run could reach a configured advisor
  until 2026-11-13 (it is a server-side tool that no tool list removes). A run that calls it reports
  a second model and thousands of uncached input tokens (checked on one probe). Every run of this
  round reports one model, and its Fable runs record 6 to 26 uncached input tokens. The 1,167 runs
  stored in October report one model each too; they predate Fable 5.2, and October's versions of
  Claude Code were not re-tested. The harness now switches the advisor off for every run. What an advisor does to worker
  agents in real sessions, and the rule that follows: [delegation.md](delegation.md).
- **A cheaper worker with an advisor: measured twice, not adopted.** First, Sonnet 5.5 `xhigh` with
  a Fable 5.2 advisor on the three synthesis tasks (rule committed first, 8 valid runs). A run in
  which the advisor answered cost $3.19, $2.00 of it the advisor; Opus `xhigh` alone costs $2.38. The
  advisor answered in 4 of 8 runs; in 3 of the others Sonnet called it and the call timed out
  (corrected on 2026-11-14 from the stored answers; the first report said "called in 4 of 8").
  No gain was shown. Second, on 2026-11-14 (`evals/results/REPORT-2026-11-14-advisor-pairs.md`,
  33 runs, rules committed first), Sonnet with an Opus 5.5 advisor against Opus `xhigh` alone:
  - *Synthesis, 9 runs a cell.* Sonnet `xhigh` with the advisor cost $2.59 (Opus alone $2.38), took
    695 s (539 s) and missed the same 3 of 69 items that Sonnet misses alone, although the advisor
    answered every time. Sonnet `high` with the advisor cost $1.90 and took 422 s, but 2 of 9 runs
    failed. Opus `high` alone costs $1.63, takes 276 s and missed 2 of 69.
  - *The harder decision task, 3 runs a cell.* Both pairs were cheaper than Opus `xhigh` alone (the
    `xhigh` pair only just: $1.59 against a bar of $1.60), faster, and near it in quality (4.08 and
    4.17 of 6 pitfalls handled against 4.04). Sonnet `xhigh` alone had handled 4.33 for $1.04, so
    the advisor added cost and no measured quality.
  No cell of the table depends on an advisor.
- **A stronger advisor for the decider: no gain measured.** Opus 5.5 `xhigh` with a Fable 5.2
  advisor on the harder decision task (6 runs against 6 stored runs alone, same report): 4.08 of 6
  pitfalls handled against 4.04, no run passed against 2 of 6, $3.13 a run against $2.13 and 709 s
  against 612 s (60% more cost in the 5 runs where the advisor answered). At `high` the cost nearly
  doubled ($2.16 against $1.12) for 4.08 against 3.58, which is below the margin set beforehand.
  One task with six runs a side shows a large difference only (a gain under about 1 pitfall of 6 is
  not excluded), and a single task is not a long chat. Across both pairs the advisor answered in 31 of 33
  runs and was 42% of the cost of those runs.
- **Limits.** Two decision tasks and four briefs, all from one owner's projects; twelve runs or
  twelve pairs show a large gap only; both judge models come from one vendor; a clean read-only run
  is not a design agent inside a session.

## Coding experiment, the owner's bar and `cheapest`, 2026-11-15

Three records: the coding experiment
([`PREREGISTERED-2026-11-14-coding.md`](../../../evals/results/PREREGISTERED-2026-11-14-coding.md),
[`REPORT-2026-11-15-coding.md`](../../../evals/results/REPORT-2026-11-15-coding.md)), a reading of the
stored runs by the owner's bar
([`REPORT-2026-11-15-fast-column.md`](../../../evals/results/REPORT-2026-11-15-fast-column.md)), and
the owner's decisions of 2026-11-15. Claude Code 2.1.325, list prices.

- **Bulk coding against tests that exist: `haiku`/`medium` in every disposition.** Six real changes
  from the owner's projects (two Python, four TypeScript), the tests each change shipped with as the
  hidden judge, and a suite written by another model as the coder's locked tests, three tries.

  | Coder | Runs correct | Cost per correct task | Time per run |
  |---|---|---|---|
  | `haiku-5-5` `medium` | 24 of 24 | $0.028 | 75 s |
  | `haiku-5-5` `high` | 24 of 24 | $0.049 | 107 s |
  | `sonnet-5-5` `low` | 18 of 18 | $0.162 | 31 s |
  | `sonnet-5-5` `medium` | 18 of 18 | $0.205 | 38 s |
  | `opus-5-5` `high` | 6 of 6 | $0.713 | 90 s |

  No run passed its given tests while being wrong. Without any tests the Haiku cells were correct in
  23 of 24 runs each and Sonnet `low` in 18 of 18: "tests first" showed no effect by the rule (4
  points against the 15 it asks for), because there was almost nothing left to fix. "critical" picks
  `sonnet`/`low`: the next cell up that was correct in every run with and without tests.
- **Plan a build and write its tests: `opus`/`high` in `balanced`, `sonnet`/`high` in `fast` and
  `cheapest`.** Twelve suites a cell. A suite is usable when it fails before the change and passes
  on the real change.

  | Test writer | Usable suites | Cost a suite | Rejects correct code (usable suites) | The same over all 12 suites |
  |---|---|---|---|---|
  | `sonnet-5-5` `high` | 12 of 12 | $0.48 | 14% | 14% |
  | `sonnet-5-5` `xhigh` | 12 of 12 | $1.11 | 15% | 15% |
  | `opus-5-5` `medium` | 8 of 12 | $0.93 | 10.3% | 41% |
  | `opus-5-5` `high` | 11 of 12 | $1.21 | 7% | 15% |

  The pre-registered rule allows 10% in the fourth column and names `opus`/`high` for both modes.
  `balanced` follows it. `fast` and `cheapest` take `sonnet`/`high` by the owner's overrule: each
  family left tests of the project outdated on one task (Sonnet's stayed usable and rejected correct
  code; Opus's became unusable), the last column counts both, and four suites a family and task
  cannot rank them. The last column is not in the rules.
- **Review a build: the verify row's cell in every disposition.** Not measured.
- **The tests are the cost.** With Sonnet `high` writing them and Haiku `medium` coding, 94% of a
  task's cost is the suite. A coder that writes its own tests (Haiku `high`) was acceptable by the
  rule, 24 of 24 correct, but no cheaper ($0.79 a run by the rules), and on one task it spent its
  tries on its own failing tests.
- **Which vehicle carries the workers made no difference to their cost.** Four pieces, one worker
  each, Haiku `medium`: single `Agent` calls $0.029 a piece, one Workflow $0.027, clean runs $0.023;
  all correct. In that one run the Workflow put 7,141 characters into the main chat and the four
  single agents 21,899. A single typed `Agent` call took the model and effort named on the call (5
  of 5 starts).
- **Don't-guess: `haiku`/`xhigh` in every disposition, the owner's overrule.** Pooled over eleven
  tasks:

  | Cell | Runs | Invented answers | Answerable items missed or wrong | Cost a run | Time |
  |---|---|---|---|---|---|
  | `haiku-5-5` `xhigh` | 84 | 6 of 1,848 | 2 of 1,056 | $0.027 | 57 s |
  | `sonnet-5-5` `xhigh` | 84 | 10 of 1,848 | 0 of 1,056 | $0.297 | 36 s |
  | `opus-5-5` `xhigh` | 45 | 0 of 1,182 | 0 of 552 | $0.548 | 41 s |

  The rule of 2026-10-11 kept Sonnet on one round (Haiku `xhigh` 1 of 720, Sonnet 0); `evalkit.py
  decide` still says keep, because it asks a new cell to pass every run. The owner moved the row on
  the pooled count. "critical" stays `opus`/`xhigh`.
- **`cheapest` is read from stored runs, not from a new round.** The owner's bar (the cheapest cell
  per finished task for checked work; about 1 failed run in 10 for unchecked work, with the losses
  written down; about 1 wrong answer in 100 for don't-guess and verify) names Haiku `xhigh` for
  classify (3 of 36 runs failed, 4.1% wrong labels against 2.8%) and for verify (1 false
  confirmation in 384 against 0 in 480), and the owner gave the architecture row to Sonnet `xhigh`
  there on six runs, before the architecture round (next section) gave it to `fast` and `balanced`
  too. `fast` keeps the safer cell on classify and verify.
- **Limits.** Six coding tasks whose brief already named the files; 178 of 180 coding runs correct,
  so the coders are told apart by cost, not by skill; two test suites a cell and task; one vehicle
  run; the document rows pooled over several rounds and versions; list price throughout.

## Architecture round, 2026-11-15

Opus 5.5 `xhigh` against Sonnet 5.5 `xhigh` on the architecture row, after the owner asked whether
`fast` or `balanced` can take the cell `cheapest` has. Rules committed before any run
([`PREREGISTERED-2026-11-15-architecture.md`](../../../evals/results/PREREGISTERED-2026-11-15-architecture.md));
the full account is
[`REPORT-2026-11-15-architecture.md`](../../../evals/results/REPORT-2026-11-15-architecture.md); the
rule checker is `evals/probes/architecture_analysis.py`. Three real decisions from three of the
owner's repositories, 30 runs a cell, 60 in all (18 kept from 2026-11-13, 42 new), four judge passes a run by
two judge models. A run fails under a judge when both of that judge's passes fail it. Claude Code
2.1.325 for the new runs, list prices.

- **Architecture or approach decision: `sonnet`/`xhigh` in `cheapest`, `fast` and `balanced`;
  "critical" stays `opus`/`xhigh`.**

  | Cell | Task 1, runs failed | Task 2, runs failed | Task 3 (new), runs failed | All 30 | Mean cost per run | Mean time |
  |---|---|---|---|---|---|---|
  | `opus-5-5` `xhigh` | 0 of 6 | 10 of 12 | 0 of 12 | 10 | $2.32 | 696 s |
  | `sonnet-5-5` `xhigh` | 0 of 6 | 7 of 12 | 0 of 12 | 7 | $1.11 | 510 s |

  Both judge models gave these counts and agreed on all 60 runs. The rules: Sonnet takes `fast`
  with at most 2 more fails than Opus in total and on each task, and `balanced` when it also has no
  more fails in total and is behind on at most one task. Both hold.
- **What carries the verdict, and what does not.** All 17 fails are on one task; the new task was
  passed by every run of both cells, so it separated nothing. Seven against ten fails of twelve is
  a gap that chance produces easily (p = 0.37). With one hard task and 12 runs a cell, a Sonnet
  that failed 15 points more often than Opus would still have taken `balanced` about one time in
  four, and one that failed 30 points more often about one time in twelve. The round shows that the
  cheaper cell was not worse; it does not show that it is better.
- **Neither cell is reliable alone on the hard task:** Opus passed 2 of 12 runs, Sonnet 5 of 12. The
  owner's bar for unchecked work is about 1 failed run in 10. A second look after a design was not
  measured.
- **Limits.** One process with read-only tools and one prompt: not the `system-architect` agent
  file, not a main chat with a conversation behind it. A design is judged on paper; nothing was
  built from one. The checklist of the hard task was written by Opus agents. Two versions of Claude
  Code. The third task was built by a Fable 5.2 agent and must not be used to compare a Fable cell.
