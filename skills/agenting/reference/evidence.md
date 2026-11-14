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
  This is a bounded null: it cannot exclude a gap of a few points, so the
  `quality` disposition keeps Opus on these rows.
- **Kept: scan, read-report, classify, synthesize** (scan and read-report moved on
  2026-10-09, below). Synthesis stays on Opus `xhigh` because there Sonnet does not
  do the same thing: Opus `xhigh` found every planted item in all 9 runs, Sonnet
  `xhigh` missed the same subtle one in 3 of 3 on one task and reported fewer
  genuine extra issues. For classify no cheaper cell cleared the plugin's evidence
  rules (pass every run and save at least 25%).
- **Haiku 4.5 ignored `effort`** (on the scan task it was the costliest cell, $0.17 a
  run). Haiku 5.5 does not; see the next block.
- **Disposition.** `quality` keeps Opus on rows 5 to 7; `fast` uses Opus `high` for
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
  measured; `quality` stays `sonnet/high`. The `researcher` agent keeps
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

- **Architecture or approach decision: stays `opus`/`xhigh`, in every disposition.** Two real
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
  moved, in `quality` and in `balanced`. Neither cheaper cell was clean, so `fast` stays
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
