# A clean run against a Workflow run on a read-heavy unit

Dated 2026-10-28. Every dollar is a list price: the run's own `total_cost_usd` for the clean
runs, and the cost model of `scripts/measure-tokenomics.py` over the transcripts for the
Workflow run (which reproduces the Workflow figures from their token counts). The
usage-window effect was not measured.

**Question.** The 63% saving of clean runs (`2026-10-07-launch-cost.md`) was measured on short
tasks, where the start-up is most of the cost. Does a clean run still save on tasks that each
read many pages of a book?

**Design.** One unit of a past 19-agent Workflow fan-out of that kind, run again as clean
`claude -p` processes through `scripts/cleanrun.py` (`--tools Read`, `--retries 0`). The unit has
two kinds of reader. **Reader A**: Opus 5.5 at xhigh, reads a 23-page range of a book PDF plus
three small text files and returns a structured extraction. **Reader B**: Sonnet 5.5 at high,
reads the same range and returns an inventory. The adjudicator of the unit was not re-run (its
input is a diff computed in code from the two outputs). The Workflow side is one run of the
unit. The clean side is two runs of each reader, with the prompts of the Workflow run (only
absolute paths rewritten to kit names).

**Quality gate.** `cleanrun` deletes an answer its validator rejects, after the run is paid
for, so the validator used during the runs was a gate: it rejected only a schema violation or an
empty required list. The quality check ran afterwards over the saved answers: the checks of the
owner's own pipeline for one output (verbatim match of outcome text against the source, page
coverage, text-layer cross-check of named boxes in both directions, section validity), plus a
comparison with the Workflow result. Before any spend the checks accepted the Workflow result
(0 problems) and rejected 16 or more corrupted copies of it. An independent attempt then found 21
further corruptions they accept, mostly subtle ones the owner's pipeline does not check either (a
truncated outcome sentence, a row moved to another page, a changed digit in a free-text field). So
the strict check is a floor and not proof of correctness; the comparison with the Workflow result
is the stronger evidence of equal quality.

**Spend.** 4.57 dollars in total, against a ceiling of 12 set beforehand: each run's soft cap
was set from the money already spent. Canary first (Reader B, cap 1.50), then Reader A (cap
5.50), then the repeats.

## Result

| Run | Cost | Turns/calls | Output tokens | Cache write | Cache read | Wall |
|---|---|---|---|---|---|---|
| Workflow, Reader A | 4.08 | 30 calls | 90,727 | 193,247 | 3,596,274 | n/a |
| Clean, Reader A, run 1 | 2.41 | 12 | 84,837 | 81,486 | 291,419 | 661 s |
| Clean, Reader A, run 2 | 1.78 | 13 | 54,556 | 77,156 | 371,367 | 436 s |
| Workflow, Reader B | 0.38 | n/a | n/a | n/a | n/a | n/a |
| Clean, Reader B, run 1 | 0.19 | 5 | 5,308 | 33,780 | 4,072 | 47 s |
| Clean, Reader B, run 2 | 0.19 | 5 | 6,537 | 30,201 | 7,774 | 45 s |

- **Cost.** Reader A cost 41% and 56% less than the Workflow run (49% on the mean of two);
  Reader B about 50% less in both runs. The two readers together, without the adjudicator:
  about 49% less on the mean.
- **Where it went.** Cache-read tokens fell by about 90% and cache-write tokens by about 59%
  for Reader A; output tokens fell by 6% and 40%.
- **Quality, in code.** All four saved answers passed the strict check with 0 problems. Both
  Reader A answers have the three outcomes identical to the Workflow result in the outcome text,
  the process components and the skill field, and an inventory that shares all 44 keys of the
  raw Workflow answer with no disagreement on the keep/skip decision. Both lack the same two
  rows that only the adjudicator added. Reader B returned 40 and 44 rows against the 46 of the
  accepted result; its first run was the loosest (7 rows missing, 1 extra), the second missed 2.
  The pipeline's own disagreement signal between the two readers (rows missing on one side or with
  a different decision) was 2 for the Workflow pair, 2 for each clean Reader A against the second
  clean Reader B, and 8 for each against the first one, which was the loosest.

## What this does and does not show

- **The saving is real on this unit, and large, but it is not the start-up alone.** An earlier
  list-price model, which assumed a clean run drops 26k to 40k tokens of harness context per call,
  put the saving for Reader A at 8 to 12%. The measurement is far above it. The likely reason is
  the confound below: the clean runs took 12 or 13 turns where the Workflow agent made 30 calls,
  and every turn rereads the context.
- **Confound.** The Workflow Reader A had Bash, Write and Edit and used them (32 Bash calls) to
  run its own text-layer check before answering. A Read-only clean run cannot do that. So the gap
  mixes the smaller start-up with the loss of that self-checking. These runs show no quality loss
  on the checks above, with two runs; a task that really needs such checks does not get them from a
  clean run.
- **One Workflow sample.** The Workflow side is a single run, and the cost of Reader A in the
  seven units of that fan-out ranged between 2.78 and 5.35 dollars, nearly a factor of two. The
  two clean runs differ by 26% between themselves.
- **Not measured.** The first-call context of a clean run (`--no-session-persistence` leaves no
  transcript), any other unit, the adjudicator, tasks with web tools, the usage window, and
  Linux or Windows.
- **What is not in this repo.** The task files, validators and outputs hold the owner's private
  project material and stay outside it. The method above is enough to repeat the experiment on
  another read-heavy unit.
