# Pre-registered: two advisor pairs against Opus alone (2026-11-14)

Written at 2026-11-14T14:47Z and revised at 2026-11-14T14:56Z after two independent reviews of the draft (both times
read from the clock), before any run of the four cells below exists. The commit time is the record.
Claude Code 2.1.325.

## The two questions

The owner asked both on 2026-11-14:

1. Does Opus 5.5 with a Fable 5.2 advisor judge better than Opus 5.5 alone?
2. Is Sonnet 5.5 with an Opus 5.5 advisor cheaper and faster than Opus 5.5 alone, while coming near
   it in quality?

## What is fixed

**Cells.** Each is the plain cell of the same name with an advisor added. The main model keeps the
harness's three read-only tools. All four carry the same extra paragraph in the system prompt: the
advisor exists, call it once before the final answer and again only if stuck, weigh its advice against
the files, and write one status line before the answer block (`ADVISOR: answered`, `ADVISOR: failed`
or `ADVISOR: not called`). The advisor's own effort cannot be set; it is whatever Claude Code uses.

| Cell | Main model | Advisor | For question |
|---|---|---|---|
| `opus-5-5@xhigh+fable-advisor` | Opus 5.5 `xhigh` | Fable 5.2 | 1 |
| `opus-5-5@high+fable-advisor` | Opus 5.5 `high` | Fable 5.2 | 1, second look |
| `sonnet-5-5@xhigh+opus-advisor` | Sonnet 5.5 `xhigh` | Opus 5.5 | 2 |
| `sonnet-5-5@high+opus-advisor` | Sonnet 5.5 `high` | Opus 5.5 | 2 |

**Tasks and runs: 33 runs.**

| Cell | Task | Runs |
|---|---|---|
| `opus-5-5@xhigh+fable-advisor` | `design-02` | 6 |
| `opus-5-5@high+fable-advisor` | `design-02` | 3 |
| `sonnet-5-5@xhigh+opus-advisor` | `synthesize-01`, `-02`, `-03` | 3 each |
| `sonnet-5-5@xhigh+opus-advisor` | `design-02` | 3 |
| `sonnet-5-5@high+opus-advisor` | `synthesize-01`, `-02`, `-03` | 3 each |
| `sonnet-5-5@high+opus-advisor` | `design-02` | 3 |

`design-01` is left out: every stored run of every cell handled 5 of its 5 pitfalls, so it cannot show
a difference. The synthesis tasks are left out of question 1 for the same reason: Opus alone found
every item in all 9 stored runs.

**Baselines: stored runs, not run again.** Same tasks (same task hashes), same graders and judges.

| Stored cell | Task | Runs | Mean cost | Mean time | Quality |
|---|---|---|---|---|---|
| `opus-5-5@xhigh` | `design-02` | 6 | $2.13 | 612 s | 4.04 of 6 pitfalls handled; 2 of 6 runs pass |
| `opus-5-5@high` | `design-02` | 3 | $1.12 | 301 s | 3.58 handled; 0 of 3 pass |
| `sonnet-5-5@xhigh` | `design-02` | 3 | $1.04 | 497 s | 4.33 handled; 1 of 3 pass |
| `opus-5-5@xhigh` | synthesis, 3 tasks | 9 | $2.38 | 539 s | 9 of 9 pass; 0 of 69 items missed |
| `opus-5-5@high` | synthesis, 3 tasks | 9 | $1.63 | 276 s | 9 of 9 pass; 2 of 69 missed |
| `sonnet-5-5@xhigh` | synthesis, 3 tasks | 9 | $1.47 | 577 s | 9 of 9 pass; 3 of 69 missed |

The `design-02` runs are from 2026-11-13 (Claude Code 2.1.323), the synthesis runs from 2026-10-05.

**How a run is scored.**

- *Cost* is the whole cost of the run, the advisor's share included. *Time* is the run's wall time as
  Claude Code reports it.
- *`design-02`:* both judges (`fable-5-1@high` and `opus-5-5@high`) score every run twice. A run's
  *handled* value is the mean of "pitfalls handled" over its four judge passes. A run *passes* when
  neither judge fails it in both of its passes. A run *violates a constraint* when one judge says so
  in both of its passes. (By these definitions the stored Opus `xhigh` runs have no violating run.)
- *Synthesis:* the pinned judge scores every run twice. A run *passes* when both passes pass. Its
  *items missed* is the reference count minus the lower "found" of the two passes.
- *Advisor status of a run:* **answered** when the advisor's model appears in the run's model usage;
  otherwise **failed** when the status line or the text before the answer block says the call failed
  or timed out; otherwise **not called**.

## Rules

Every rule is applied to all runs of a cell as they come, whether or not the advisor answered. That is
what the owner gets when the pair is switched on. The runs in which the advisor answered are also
reported on their own, without a verdict.

**Question 1, on the six runs of `opus-5-5@xhigh+fable-advisor`:**

- **Not decided** when the advisor answered in fewer than 4 of the 6 runs. This comes first and
  overrides the three verdicts below. The numbers are still reported, and the failed calls are the
  finding.
- **Better** when all three hold: the mean handled value is at least 1.0 above the stored mean (so at
  least 5.04), at least 4 of the 6 runs pass, and none of the 6 runs violates a constraint.
- **Worse** when the mean handled value is at least 1.0 below the stored mean (so at most 3.04), or
  two or more runs violate a constraint.
- **No difference shown** in every other case.

A "better" is reported as "better, cause not separated" (limit 8) until a control with the same
paragraph and no advisor has been run.

The three runs of `opus-5-5@high+fable-advisor` are a second look. They are reported next to the
stored 3.58 and change no verdict. They *support* a "better" when their mean is at least 4.58.

**Question 2, for each Sonnet cell and for each of the two rows (synthesis; `design-02`), against the
stored `opus-5-5@xhigh` runs of the same tasks:**

- **Not decided** for a cell and row when the advisor answered in fewer than two thirds of its runs
  (fewer than 6 of 9 on synthesis, fewer than 2 of 3 on `design-02`). The three statements below are
  still reported; they then describe Sonnet mostly working alone.
- **Cheaper** when the mean cost is at most 75% of Opus's (synthesis $1.78, `design-02` $1.60).
  Between 75% and 100% it is "cheaper by less than a quarter". Above, "not cheaper".
- **Faster** when the mean time is at most 90% of Opus's (synthesis 485 s, `design-02` 551 s).
  Between 90% and 110% it is "about the same". Above, "slower".
- **Near in quality.** Synthesis: every run passes, no run invents an item, and at most 1 item is
  missed over the 9 runs. `design-02`: the mean handled value is at least 3.54 (0.5 below Opus's
  4.04) and no run violates a constraint.
- **The pair does what the owner asked** on a row when all three hold and the row is decided. Each
  of the three is reported whatever the outcome.

Every threshold is computed from the unrounded stored mean; the rounded value is shown.

Two more comparisons are reported without a rule: against the stored `opus-5-5@high` runs (Opus alone
at a lower effort is also "Opus only"), and against the stored `sonnet-5-5@xhigh` runs (what the
advisor adds to Sonnet `xhigh`; no stored run of Sonnet `high` alone exists on these tasks). The output
of `evals/evalkit.py decide` is quoted for the synthesis row only: for `design-decision` it screens on
`design-01`, which is not run here, so its line for these cells stays "incomplete" by design.

**A slot with no valid run after three attempts** counts as a run that failed: it does not pass, its
handled value is 0, it misses every reference item, its advisor did not answer, and its time is the
time limit. Its cost is unknown, so it is left out of the cost mean and listed on its own.
**No routing cell changes by these rules.** A row could change only by the owner's decision after
the report.

## What to expect, written before the runs

- **Question 1: no difference shown.** Fable 5.2 alone handled fewer pitfalls on this task than Opus
  `xhigh` (it passed 0 of 9 runs), so its advice is unlikely to add what Opus misses.
- **Question 2, Sonnet `xhigh` with Opus.** Quality: near on `design-02` (Sonnet alone already is);
  on synthesis only if the advisor catches the one item Sonnet misses alone in at least 2 of the 3
  runs of that task. Cost: one read of the whole conversation by Opus is about $1, so about $2.5 on
  synthesis (not cheaper) and about $2.0 on `design-02` (cheaper by less than a quarter). Time: slower
  on synthesis (Sonnet alone takes 577 s); about the same or slower on `design-02` (alone 497 s).
- **Question 2, Sonnet `high` with Opus.** No stored run of Sonnet `high` exists on these tasks, so
  this is a guess: cheaper by less than a quarter on synthesis, close to the line on `design-02`,
  faster on both. Quality is open. Opus `high` alone ($1.63, 276 s on synthesis) will be hard to beat
  on cost and time.

## Limits known beforehand

1. **Question 1 rests on one task with six runs a side.** It can show a large difference only.
2. **The checklist of `design-02` was built with a Fable advisor in the loop** (addendum 2 of the
   think-first rules). That could favour Fable's advice. It weakens a "better", not a "no difference".
3. **The baselines are stored runs** from other days and Claude Code versions. Time also depends on
   the load of the API on the day.
4. **These are single tasks with three read-only tools,** not a long chat. In a long chat the advisor
   reads a much longer conversation each time it is called.
5. **When to call the advisor is our instruction.** The harness replaces the system prompt, so Claude
   Code's own wording about the advisor is not in play.
6. **Advisor calls can fail.** Found on 2026-11-14 in the stored answers of yesterday's pairing test:
   in at least 3 of its 8 runs Sonnet did call the Fable advisor and the call timed out. The report of
   2026-11-13 counted those runs as "advisor not called". This is why the status line exists.
7. **One judge is a Fable model.** Both judges are reported side by side.
8. **The cells add an instruction as well as an advisor.** The paragraph makes the model stop before
   its final answer and weigh a second opinion. A gain could come from that pause and not from what
   the advisor says, and the stored baselines ran without the paragraph. No control separates the two
   here. It weakens a "better", not a "no difference".
9. **No stored run of Sonnet `high` alone** exists on these tasks, so for that cell the advisor's own
   contribution cannot be separated; only the comparison with Opus alone is made.

## How the runs are made

- **Claude Code 2.1.325 for every run and judge pass,** pinned through the `PATH` so that an update
  during a batch cannot mix versions. The plugin installed on this machine stays at 3.5.3 until the
  last judge pass, as it was for the stored `design-02` runs.
- **Limits for this test:** 1,800 s a run (was 1,200) and $10 a run (was $6). Yesterday two attempts
  of the pairing cell ended at 1,200 s, and an Opus run with a Fable advisor may cost more than $6.
  No stored baseline run came near either old limit (slowest 890 s, dearest $3.15), so the baselines
  would be the same under the new ones. Both values go back after the test.
- **Commands.** Runs are launched only with the tasks named: `--rows design-decision --tasks
  design-02` (with `--repeats 6` for `opus-5-5@xhigh+fable-advisor`, `--repeats 3` for the others) and
  `--rows synthesize --tasks synthesize-01,synthesize-02,synthesize-03 --repeats 3`. A plan without
  `--tasks` would add `design-01` runs that these rules do not ask for. Judge passes are launched with
  the same `--tasks` and with `--cells` naming the cells of this test, the second judge on `design-02`
  only (`--judge-cell opus-5-5@high`).
- **Pilot first:** one run of each cell on `design-02`. Pilot runs count as ordinary runs. Checked
  before the rest starts: the run is valid, the advisor's usage is reported under the expected model
  (`claude-fable-5-2`, `claude-opus-5-5`), and the status line is outside the answer block. If the
  setting `opus` resolves to another model, the cell's setting becomes the full model id and its pilot
  run is made again. If an advisor call fails in the pilot, the rest runs two at a time instead of
  four.
- **Before judging,** the stored answer blocks are checked for a status line that slipped inside; the
  count is reported.
- **Outage evidence** as in addendum 4 of the think-first rules: the connection watchdog runs, and an
  invalid attempt with no answer whose window holds a failed check, a sleep or a gap is set aside and
  run again.
- **Spend:** expected about $110 at list price for the 33 runs and their judge passes. The total is
  kept by hand across commands, since `--max-usd` caps one command only. No new run is launched once
  the known costs reach $130. An attempt whose cost is unknown (a timeout) is listed on its own and
  bounded by the $10 cap; nothing more is launched once the known costs plus $10 for each such
  attempt reach $150.
- **Order of the record:** these rules, then the runs. The analysis tool
  (`evals/probes/advisor_pairs_analysis.py`) is committed before any judge pass of these runs exists.
