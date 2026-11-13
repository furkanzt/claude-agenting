# Pre-registered: a cheaper worker with a Fable advisor, on the synthesis row (2026-11-13)

Written at 2026-11-13T20:45Z (read from the clock), before any run of the cell below exists. Claude Code 2.1.323.

## Question

The routing table was measured with each model working alone. The owner asked whether an advisor
changes what a cheaper model can do. One case is tested: on "Synthesize across a whole document or
many files" Sonnet 5.5 `xhigh` alone missed a subtle planted item in 3 of 3 runs on one task, and
Opus 5.5 `xhigh` found every planted item in 9 of 9 runs. Does Sonnet 5.5 `xhigh` with a Fable 5.2
advisor match Opus 5.5 `xhigh` alone, for less?

## What is fixed

- **Cell.** `sonnet-5-5@xhigh+fable-advisor`: Sonnet 5.5 at `xhigh`, started with a Fable 5.2 advisor,
  and told in its system prompt to call it once before the final answer and again only if stuck.
  Every other cell of the harness runs with the advisor switched off.
- **Tasks and runs.** The row's three stored tasks, `synthesize-01` to `-03`, three runs each: 9
  runs. The same instrument, graders and judge as the stored runs of the row.
- **Baseline.** The stored runs of `opus-5-5@xhigh` on the same three tasks (9 runs, mean $2.38 a
  run at list price). They are not run again.
- **Cost.** A run's cost is the whole cost, the advisor's share included.

## Rule

The harness's own bar, as `evals/evalkit.py decide` applies it to any cheaper candidate: the cell
passes every run on every task, and its mean cost per run is at least 25% below the baseline's
(at most about $1.79).

- **If both hold:** the synthesis row gains one conditional cell, used only when the session line
  says the advisor is Fable: `sonnet`/`xhigh` with the advisor allowed. Without an advisor the row
  stays `opus`/`xhigh`.
- **Otherwise:** nothing changes, and the docs say the pairing was measured and not adopted.

Reported whatever the outcome: in how many runs the advisor was called and what its share of the
cost was, and whether the item that Sonnet missed alone was found.

## What to expect, written before the runs

Sonnet `xhigh` alone cost $1.47 a run on these tasks. One advisor call re-reads the whole
conversation, uncached, at $8 per million tokens, so it should add about $0.50 or more. The cost
half of the rule is therefore likely to fail even if the quality half holds.

## Limits

One pairing, one row, three tasks, nine runs, and one instruction for when to call the advisor. A
different instruction, effort or advisor model is a different cell.
