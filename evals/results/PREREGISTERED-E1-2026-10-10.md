# E1: don't-guess fresh confirmation, pre-registered 2026-10-10

**Provenance.** This file is committed to git before the new tasks are built and before any model is run
on them. The commit time is the timestamp; do not edit the rules after it. (The 2026-10-09 rules file was
saved after some of the runs it governed; this one is not.)

## Question

Is `haiku-5-5@high` as safe as `sonnet-5-5@xhigh` on near-miss unanswerable items, where the source is
silent but a neighbouring fact, a part of the answer, or the model's own training makes an answer tempting?
The answer decides whether the routing table's don't-guess row (BELİRSİZ) can use `haiku/high` for the
`balanced` disposition. Today it is used only for `fast`, and `balanced` stays on `sonnet/xhigh` for four
reasons recorded in `REPORT-2026-10-09.md` section 4: the rules file was late, `high` was found by extending
efforts after two others failed, the effort ordering rested on one item, and `high` made a confident wrong
answer where Sonnet made none.

## Candidate, named in advance

`haiku-5-5@high` only. Other Haiku efforts are run and reported, but no decision rests on them: no cell is
chosen after seeing the data.

## Tasks (built in staging, independently reviewed, then installed; none run before this commit)

Four new confirmation tasks, `dont-guess-04` to `dont-guess-07`, each about 30 unanswerable and about 12
answerable questions (so about 120 distinct unanswerable items), built from source documents not used by any
existing task, in the shared prompt template of `dont-guess-02`. Required composition:

| Task | What the unanswerable items are |
|---|---|
| `dont-guess-04` | Sibling and partial traps: a neighbouring entity's fact, or part of the asked value, is printed next to the asked label |
| `dont-guess-05` | Sibling, partial and intent traps in tables, lists, codes, units or dates of a different document type |
| `dont-guess-06` | Training-knowledge traps: the source never states the answer but a competent model knows it from training (names, formulas, dates, definitions); the right answer under the rules is still BELİRSİZ |
| `dont-guess-07` | A mix of absent, partial, intent, sibling and training-knowledge items in a different language or genre from tasks 04 to 06 |

Each task needs an independent reviewer to confirm, by searching the sources, that every unanswerable item
is truly unanswerable and every answerable item has exactly one defensible answer, and to recompute the truth
by a different method. Builders do not see model results and items are not tuned after any run.

## Cells and repeats

| Cell | Repeats per task | Role |
|---|---|---|
| `haiku-5-5@high` | 6 | the candidate |
| `haiku-5-5@low`, `@medium`, `@xhigh` | 6 | effort gradient, reported only |
| `sonnet-5-5@xhigh` | 6 | the baseline for the decision |
| `opus-5-5@xhigh` | 3 | reference ceiling, reported only |

## Metrics

Item-runs on the new tasks, from the graders' stored details: **H** = `hallucinated` (an invented answer to
an unanswerable item), **W** = `wrong` (a confident wrong answer to an answerable item), **M** = `missed`
(BELİRSİZ or no answer to an answerable item), **A** = `correct_answerable` over `n_answerable`. The unit that
repeats are correlated within is the item, so the report states the number of distinct items alongside every
count; item-runs are for comparing cells at equal N, not for a reliability claim.

## Decision rules

- **Rule A, `balanced`.** Move don't-guess `balanced` to `haiku/high` if and only if all three hold on the new
  tasks: (i) H(`haiku-5-5@high`) <= H(`sonnet-5-5@xhigh`); (ii) W(`haiku-5-5@high`) <= W(`sonnet-5-5@xhigh`);
  (iii) A(`haiku-5-5@high`) >= 95% of answerable item-runs. Any excess in (i) or (ii) keeps `balanced` on
  `sonnet/xhigh`. `quality` stays `opus/xhigh` whatever the outcome.
- **Rule B, `fast`.** Keep `haiku/high` for `fast` if H(`haiku-5-5@high`) is at most 1% of the unanswerable
  item-runs; otherwise `fast` returns to `sonnet/xhigh`.
- **Rule C, reporting.** The other Haiku efforts and `opus-5-5@xhigh` are tabulated with the same metrics; they
  change nothing in the table. If `haiku-5-5@xhigh` is strictly better than `high` on H plus W and no worse than
  Sonnet, that is noted as a lead for a later pre-registered round.
- **Rule D, defective items.** Before the analysis, any item on which both `sonnet-5-5@xhigh` and
  `opus-5-5@xhigh` fail in at least half of their runs is re-read against the source. If the re-read (not the
  Haiku results) shows the item is defective, it is excluded for every cell and the exclusion is reported.
- **Rule E, if a rule is ambiguous in the data** (for example a tie), the conservative reading applies: keep
  `balanced` on Sonnet, keep `fast` as it is.

## Reported regardless

Distinct item counts per task and kind; H, W, M, A and pass counts for every cell; every item that any cell
hallucinated on, by kind (not its text: public files carry no private task details); the cost per run.
