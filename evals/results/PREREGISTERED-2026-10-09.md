# Vetting rules, Haiku 5.5 round (2026-10-09)

**Provenance, read this first.** This file was saved at 13:15Z on 2026-10-09, AFTER some
of the extensions it describes had run, so it is not a pre-registration for all of them.
What was fixed when:

- Verify (`medium`, `xhigh`) and dont-guess (`low`, `medium`) at 12 repeats under "adopt
  only if the cell stays perfect": announced in the working conversation before the runs
  (12:35Z to 12:56Z), not in this file.
- Cleanup (`high`, `xhigh` to 9 repeats) and read-report-01 (`low`, `medium` to 9
  repeats), 12:26Z to 12:32Z: no rule was written beforehand. They were checks on candidates
  the bar accepted, and cleanup was kept on Sonnet by a judgment override.
- Dont-guess `high` and `xhigh` (13:17Z) and the Sonnet baselines (13:14Z onward): added
  after `low` and `medium` had failed. A cell found by extending further efforts after the
  first candidates failed carries a forking-path risk, which is why dont-guess `balanced`
  was not moved (report, sections 4 and 6).
- Scan (13:31Z), classify (14:01Z) and the read-report tasks 02 and 03: rules in this file
  before their runs. The classify rule was written after seeing nine-run data.

The bar itself (`evals/README.md`, "The decision bar") is unchanged; these rules only say
when to *adopt* a cell the bar accepted. The table states the rules as applied.

Why vetting exists: the bar reads three runs per task, and a silent-damage candidate is
the best of several cells (here four efforts), so a clean sheet can be luck. Extra repeats
(`run --repeats N`, which adds runs `#4..N`) can turn a MOVE into a KEEP; they never turn a
KEEP into a MOVE, and `decide` still reads runs `#1..3` only.

| Row | Candidate(s) vetted | Repeats | Rule: adopt only if |
|---|---|---|---|
| adversarial-verify | `haiku-5-5@medium`, `haiku-5-5@xhigh` | 12 per task, 3 tasks | the cell stays perfect: every run passes, no false confirm. One miss keeps `sonnet/high`. |
| dont-guess | `haiku-5-5@low`, `haiku-5-5@medium` (and `high`, `xhigh`) | 12 per task, 3 tasks | the cell stays perfect: every run passes, zero hallucinations. One miss keeps `sonnet/xhigh`. |
| scan | `haiku-5-5@low` / `medium` / `high` / `xhigh` | 12 per task, 3 tasks | the cell stays perfect: all six sub-answers exact in every run. |
| classify | `haiku-5-5@xhigh` | 12 per task, 3 tasks | its runs scoring below 0.9 are no more numerous than `sonnet-5-5@medium`'s at the same N, AND its total wrong labels are at most 1.5x Sonnet's. A perfect-every-run rule would reject Sonnet itself, so classify is compared, not judged alone. |
| read-report | `haiku-5-5@low` / `medium` / `high` | 3 repeats on 2 new tasks (confirmation phase) plus the 9 on read-report-01 | pooled over the three tasks its failed runs are at most `sonnet-5-5@medium`'s plus 1 (the bar's `noticed_extra_misses`). |

The Sonnet baselines are run at the same N as the Haiku candidates so the comparison is
symmetric (dont-guess `sonnet-5-5@xhigh`, verify `sonnet-5-5@high`, scan `sonnet-5-5@high`,
classify `sonnet-5-5@medium`, read-report `sonnet-5-5@medium`).

Where the data hold a `fast` question (a cheaper cell that fails the adopt rule but has a
small measured error rate), the report states the rate and leaves `balanced` and `quality`
unchanged. `quality` is not touched by this round.

## Addendum: the CLI 2.1.296 canary (2026-10-09, evening)

Claude Code updated from 2.1.295 to 2.1.296. A canary re-ran the cells most sensitive to CLI behaviour as new
runs #13 to #15 (fresh run ids, `cli_version` 2.1.296): scan (`haiku-5-5@low`, `haiku-5-5@medium`,
`sonnet-5-5@high`), dont-guess (`haiku-5-5@medium`, `haiku-5-5@high`) and adversarial-verify (`haiku-5-5@medium`,
`sonnet-5-5@high`), 9 runs per cell over the three tasks.

**Provenance.** The rule was stated in the working conversation at 20:48Z, before any 2.1.296 eval run, and its
time was recorded in a scratch file; it was written into this repository file only after the runs, so, as with
the verify and dont-guess rule above, this file is a record and not a pre-registration.

**Rule.** For each (row, cell), compare the pass count on runs #13 to #15 with the pass count on runs #1 to #12 of
the same cell. Flag the cell only if the new rate is lower with Fisher exact one-sided p < 0.05. This detects a
gross change (a tool, alias or effort behaviour that broke), not a small shift: 9 runs cannot see one.

**Outcome.** 63 runs, all valid, $2.24; 0 of 7 cells flagged (lowest p 0.511). The report's section 11 and
`HANDOFF.md` section 2a hold the table.

