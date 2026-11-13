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
