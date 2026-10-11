# E1b: Opus versus Sonnet versus Haiku xhigh on fresh near-miss items, pre-registered 2026-10-10

**Provenance.** This file is committed to git before any E1b task is built, before the analysis tool is adapted
and before any model runs on the new tasks. The commit time is the timestamp; do not edit the rules after it.
Order of commits to expect: this file, then the analysis tool and its tests, then the installed tasks, then the
runs. (E1 followed the same order; see `REPORT-2026-10-10-E1.md`.)

## Why E1b exists

E1 (`REPORT-2026-10-10-E1.md`) found, on 120 near-miss unanswerable items, hallucinated item-runs of 11 of 720
for `haiku-5-5@high`, 10 of 720 for `sonnet-5-5@xhigh`, 5 of 720 for `haiku-5-5@xhigh` and 0 of 360 for
`opus-5-5@xhigh`. Two items carried most of it, Opus had only 3 repeats, and the E1 items are now seen. E1 was
not registered to decide Sonnet against Opus, so the table's `balanced` row was not changed. E1b asks the two
questions E1 raised, on fresh items and with equal repeats for every cell.

## Questions

1. **`balanced`.** Does `opus-5-5@xhigh` abstain materially more reliably than `sonnet-5-5@xhigh` on near-miss
   unanswerable items, enough to move the don't-guess `balanced` row to Opus?
2. **`fast`.** Does `haiku-5-5@xhigh` abstain at least as reliably as Sonnet and within the 1% safety line, so that
   it can be admitted to `fast` at about a twelfth of Sonnet's cost?

## Candidates, named in advance

`opus-5-5@xhigh` for question 1 and `haiku-5-5@xhigh` for question 2. `haiku-5-5@high` is run as a continuity
reference and reported, never decided on.

## Tasks (built in staging, independently reviewed twice, then installed; none run before the install commit)

Four new confirmation tasks, `dont-guess-08` to `dont-guess-11`, about 30 unanswerable and 12 answerable questions
each (about 120 distinct unanswerable items), in the shared prompt template of `dont-guess-02`, from source
documents used by no existing task. Weighted toward the kinds that failed in E1: per task about 9 intent, 9
partial, 9 sibling and 3 absent items (training-knowledge items produced no hallucination in E1 and are left out).
Each task has an independent reviewer who confirms by searching the sources that every unanswerable item is truly
unanswerable and every answerable item has one defensible answer; builders never see model results.

## Cells and repeats

| Cell | Repeats per task | Role |
|---|---|---|
| `opus-5-5@xhigh` | 6 | candidate for `balanced` |
| `sonnet-5-5@xhigh` | 6 | baseline for both questions |
| `haiku-5-5@xhigh` | 6 | candidate for `fast` |
| `haiku-5-5@high` | 6 | reference, reported only |

## Metrics

As in E1, on item-runs of the E1b tasks, from the graders' stored details: **H** `hallucinated`, **W** `wrong`,
**M** `missed`, **A** `correct_answerable`; per kind and per task; with the number of distinct items alongside
every count. Repeats on one item are correlated, so the item is the unit that matters.

## Decision rules

- **Rule A, move `balanced` to `opus/xhigh`** if and only if all of these hold:
  (i) H(Sonnet) is at least 1% of the unanswerable item-runs, so that the baseline has a measurable problem;
  (ii) H(Opus) <= 0.2 x H(Sonnet) at equal N;
  (iii) W(Opus) <= W(Sonnet);
  (iv) A(Opus) >= 95% of answerable item-runs;
  (v) **robustness to one item:** condition (ii) still holds after removing, one at a time, each item that Sonnet
  hallucinated on (from both cells), so no single item carries the result.
  If any condition fails, `balanced` stays `sonnet/xhigh`. `quality` stays `opus/xhigh` whatever happens.
- **Rule B, admit `haiku/xhigh` to `fast`** if and only if: (i) H(Haiku xhigh) <= H(Sonnet); (ii) H(Haiku xhigh) is
  at most 1% of the unanswerable item-runs; (iii) W(Haiku xhigh) <= W(Sonnet); (iv) A(Haiku xhigh) >= 95%. Otherwise
  `fast` stays `sonnet/xhigh`.
- **Rule C, reporting.** `haiku-5-5@high`, hallucinations by kind and by task, the E1 numbers beside the E1b
  numbers, and the pooled E1 plus E1b counts; none of these decides anything.
- **Rule D, defective items.** Before the analysis, any item that both Sonnet and Opus fail in at least half of their
  runs is re-read against the source; if the re-read (not the Haiku results) shows it is defective, it is excluded
  for every cell and the exclusion is reported.
- **Rule E, ambiguity.** If a rule is ambiguous in the data, or a cell has fewer runs than 6 per task, the
  conservative reading applies: `balanced` and `fast` stay as they are.

## Reported regardless

Distinct item counts per task and kind; H, W, M, A and pass counts for every cell; every item any cell hallucinated
on, as item id and kind only (public files carry no task content); the cost per run; and any recovery the build or
the runs needed.
