# Two advisor pairs against Opus alone: report, 2026-11-14

Rules: [`PREREGISTERED-2026-11-14-advisor-pairs.md`](PREREGISTERED-2026-11-14-advisor-pairs.md), committed at
14:58Z, before any run of the four cells ("evals: pre-register two advisor pairs against Opus alone, before any
run"). Analysis tool: `evals/probes/advisor_pairs_analysis.py`, committed at 15:22Z, when 8 of the 33 runs existed
and none was judged ("evals: the rule checker for the advisor-pairs test, before any judge pass of its runs").
Runs: 33, between 14:59Z and 16:39Z; 96 judge passes between 16:45Z and 16:58Z; all on Claude Code 2.1.325,
pinned. Every run was valid on its first attempt. Commits are named by their message and time here, not by hash,
because the hashes of unpushed commits change when the commits are grouped for a push.

## 1. Outcome

**Question 1. No difference shown: Opus 5.5 with a Fable 5.2 advisor did not judge measurably better than Opus
5.5 alone.** On the harder design task it handled 4.08 of 6 pitfalls on average; Opus alone handled 4.04. None of
its 6 runs passed by the rule; 2 of the 6 stored runs of Opus alone did. A run cost $3.13 against $2.13 (47%
more) and took 709 s against 612 s; in the 5 runs where the advisor answered it was 60% more cost and 23% more
time. Six runs a side on one task can show a large difference only: a gain of less than about 1 pitfall of 6 is
not excluded.

**Question 2. Sonnet 5.5 with an Opus 5.5 advisor does not replace Opus on synthesis. On the design task it was
cheaper, faster and near Opus in quality, but so was Sonnet alone.**

- **Synthesis, 9 runs a cell.** Sonnet `xhigh` with the advisor cost $2.59 a run (Opus alone $2.38), took 695 s
  (539 s) and missed 3 of 69 items (0). That is the same count as Sonnet alone: 1 of 7 on `synthesize-03` in
  all 3 runs, the task on which Sonnet alone misses one hard item, although the advisor answered every time.
  Sonnet `high` with the advisor cost $1.90 and took 422 s, but 2 of its 9 runs did not pass and it missed 5
  items.
- **`design-02`, 3 runs a cell.** Both Sonnet pairs were cheaper than Opus alone (the `xhigh` pair only just:
  $1.59 against a bar of $1.60), faster, and near it in quality (4.08 and 4.17 handled against 4.04). Sonnet
  `xhigh` alone, with no advisor, had handled 4.33 for $1.04. The advisor added about $0.55 a run and no measured
  quality.

**No routing cell changes by these rules.** The `design-02` numbers (Sonnet alone near Opus at about half the
cost, on 3 runs) are a lead for the owner's decision, not a rule result.

## 2. What was run

| Time (UTC) | What |
|---|---|
| 14:47 to 14:56 | Rules drafted; two independent reviewers read the draft; their findings were applied (the commit message of the rules lists the main ones) |
| 14:58 | Rules, the four cells and the limits of the test committed |
| 14:59 to 15:13 | Pilot: one run of each cell on `design-02`. All valid, the advisor answered in all four, every status line outside the answer block, the setting `opus` reported under `claude-opus-5-5` |
| 15:13 to 15:27 | The other 6 `design-02` runs of three cells |
| 15:22 | Analysis tool committed (built by one agent, verified by a second, three gaps closed) |
| 15:27 to 15:47 | The other 5 runs of `opus-5-5@xhigh+fable-advisor` |
| 15:47 to 16:39 | 18 synthesis runs of the two Sonnet cells |
| 16:45 to 16:58 | Judging: 60 passes on the 15 `design-02` runs (two judges, two passes each), 36 on the 18 synthesis runs |

Four runs at a time throughout, since no advisor call failed in the pilot. The connection watchdog logged 316
checks between 14:59:00Z and 16:45:00Z with no failure and no gap. It only tests that the API host accepts a
connection: the two failed advisor calls of section 5 fall inside windows with no failed check. The owner's
settings file had the same modification time before the pilot and after the last run.

## 3. Question 1: Opus with a Fable advisor on `design-02`

A run's *handled* value is the mean of "pitfalls handled" (of 6) over its four judge passes. A run *passes* when
neither judge fails it in both of its passes.

| | Runs | Handled per run | Mean | Pass | Cost | Time |
|---|---|---|---|---|---|---|
| Opus `xhigh` alone (stored, 2026-11-13) | 6 | 5, 5.25, 3, 3, 4, 4 | 4.04 | 2 of 6 | $2.13 | 612 s |
| Opus `xhigh` with a Fable advisor | 6 | 4.5, 4, 4.5, 4, 3.5, 4 | 4.08 | 0 of 6 | $3.13 | 709 s |
| Opus `high` alone (stored) | 3 | 3.25, 4, 3.5 | 3.58 | 0 of 3 | $1.12 | 301 s |
| Opus `high` with a Fable advisor | 3 | 4.25, 4, 4 | 4.08 | 0 of 3 | $2.16 | 395 s |

- **Verdict by the rule: no difference shown.** "Better" needed a mean of at least 5.04, at least 4 passing runs
  and no violating run. The mean rose by 0.04.
- **The pass counts are within noise.** Each judge alone passed 1 of the 6 advised runs in both of its passes, a
  different run each, so no run passed by the rule. Of the stored runs the Fable judge passed 2 and the Opus
  judge 1.
- **One advised run violates a constraint** by the rule (the Opus judge said so in both passes; the Fable judge
  in neither). No stored run does. "Worse" needed two.
- **By judge.** Fable judge: 4.00 with the advisor against 4.17 alone. Opus judge: 4.17 against 3.92.
- **The advisor answered in 5 of the 6 runs.** In the sixth the call failed, the run cost $1.77 and handled 3.5.
  The five answered runs alone: 4.20 handled, 0 pass, $3.40, 750 s.
- **Second look, Opus `high`:** 4.08 against 3.58 alone. That is 0.5 more, below the 1.0 that the rules set for
  "supports a better", and no run passed in either group. The cost nearly doubled.
- **What the advisor cost here:** $1.27 a run on `xhigh` and $1.03 a run on `high`, over the runs in which it
  answered, on top of Opus's own $2.13 and $1.12. The number of calls in a run is not recorded.

## 4. Question 2: Sonnet with an Opus advisor

**Synthesis.** Items found per run as the pinned judge counted them (the lower of its two passes), then mean cost
and time:

| Task (items) | Opus `xhigh` alone | Opus `high` alone | Sonnet `xhigh` alone | Sonnet `xhigh` + Opus advisor | Sonnet `high` + Opus advisor |
|---|---|---|---|---|---|
| `synthesize-01` (6) | 6, 6, 6; $1.98; 420 s | 6, 6, 6; $1.27; 226 s | 6, 6, 6; $0.95; 344 s | 6, 6, 6; $1.84; 435 s | 5, 6, 6; $1.33; 216 s |
| `synthesize-02` (10) | 10, 10, 10; $2.54; 661 s | 10, 9, 10; $1.68; 325 s | 10, 10, 10; $1.32; 565 s | 10, 10, 10; $2.48; 663 s | 10, 9, 10; $1.85; 376 s |
| `synthesize-03` (7) | 7, 7, 7; $2.62; 535 s | 7, 6, 7; $1.92; 277 s | 6, 6, 6; $2.14; 822 s | 6, 6, 6; $3.44; 988 s | 6, 6, 6; $2.52; 674 s |
| All 9 runs | $2.38; 539 s; 0 missed | $1.63; 276 s; 2 missed | $1.47; 577 s; 3 missed | $2.59; 695 s; 3 missed | $1.90; 422 s; 5 missed |

The three alone columns are stored runs of 2026-10-05; three of the Opus `high` runs of `synthesize-03` are from
just after midnight UTC on 2026-10-06. The 8 runs of Sonnet `high` in which the advisor answered, on their own:
$1.94, 417 s, 6 of 8 pass, 4 of 62 items missed, 1 run invents an item.

**`design-02`:**

| | Runs | Handled per run | Mean | Pass | Cost | Time |
|---|---|---|---|---|---|---|
| Opus `xhigh` alone (stored) | 6 | 5, 5.25, 3, 3, 4, 4 | 4.04 | 2 of 6 | $2.13 | 612 s |
| Sonnet `xhigh` alone (stored) | 3 | 4, 5, 4 | 4.33 | 1 of 3 | $1.04 | 497 s |
| Sonnet `xhigh` + Opus advisor | 3 | 4, 4, 4.25 | 4.08 | 0 of 3 | $1.59 | 480 s |
| Sonnet `high` + Opus advisor | 3 | 4, 4.75, 3.75 | 4.17 | 1 of 3 | $1.11 | 342 s |

**The verdicts, each against the stored Opus `xhigh` runs of the same tasks:**

| Cell | Row | Advisor answered | Cost | Time | Quality | Does what the owner asked |
|---|---|---|---|---|---|---|
| Sonnet `xhigh` + Opus | synthesis | 9 of 9 | not cheaper (109%) | slower (129%) | not near (3 items missed) | no |
| Sonnet `xhigh` + Opus | `design-02` | 3 of 3 | cheaper (75%) | faster (78%) | near (4.08) | yes |
| Sonnet `high` + Opus | synthesis | 8 of 9 | cheaper by less than a quarter (80%) | faster (78%) | not near (2 runs do not pass, 5 missed, 1 run invents an item in one of its two judge passes) | no |
| Sonnet `high` + Opus | `design-02` | 3 of 3 | cheaper (52%) | faster (56%) | near (4.17) | yes |

- **The "cheaper" of Sonnet `xhigh` on `design-02` sits on the line:** $1.588 against a bar of $1.596.
- **What the advisor added to Sonnet `xhigh`** (the only Sonnet cell with stored runs alone): on `design-02` 53%
  more cost, the same time, and a mean of 4.08 against 4.33. On synthesis 76% more cost, 21% more time and the
  same 3 missed items.
- **Against Opus `high` alone,** the cheapest Opus cell with stored runs: on synthesis both pairs cost more and
  took longer ($2.59 and $1.90 against $1.63; 695 s and 422 s against 276 s) and neither found more. On
  `design-02` Sonnet `high` with the advisor cost the same as Opus `high` alone ($1.11 against $1.12), took
  14% longer and handled 4.17 against 3.58.
- **The harness's own `decide`, synthesis row** (it reads the screening task `synthesize-01` first):
  `sonnet-5-5@xhigh+opus-advisor ... cheaper by only 7% (needs 25%): not worth a move` and
  `sonnet-5-5@high+opus-advisor ... failed 1 screening run(s); silent-damage needs every run`.

## 5. The advisor itself

- **It answered in 31 of the 33 runs.** Two calls failed, one of each advisor model: Fable for an Opus `xhigh`
  run on `design-02`, Opus for a Sonnet `high` run on `synthesize-03`. Both runs said so in their status line
  and finished valid.
- **Every status line matched the usage:** 31 "answered" with the advisor's model in the run's usage, 2 "failed"
  without it, none inside an answer block.
- **Its cost.** $0.95 a run on average over the 31, which is 42% of the cost of those runs. By cell: Fable for
  Opus `xhigh` $1.27, Fable for Opus `high` $1.03, Opus for Sonnet on synthesis $1.02 and $0.96, Opus for Sonnet
  on `design-02` $0.60 and $0.44.

## 6. Expectations against results

| Written beforehand | Result |
|---|---|
| Question 1: no difference shown | No difference shown |
| Sonnet `xhigh` + Opus, quality: near on `design-02`; on synthesis only if the advisor catches the one hard item | Near on `design-02`; the item was missed in 3 of 3 runs |
| Sonnet `xhigh` + Opus, cost: about $2.5 on synthesis, about $2.0 on `design-02` | $2.59 and $1.59. The second was lower than expected and landed on the "cheaper" line |
| Sonnet `xhigh` + Opus, time: slower on synthesis; about the same or slower on `design-02` | Slower on synthesis; **faster** on `design-02` (78%). The expectation was wrong there |
| Sonnet `high` + Opus: cheaper by less than a quarter on synthesis, close to the line on `design-02`, faster on both, quality open | 80% on synthesis; **52%** on `design-02`, well under the line, so the expectation was wrong there; faster on both; not near on synthesis |
| "Opus `high` alone ($1.63, 276 s on synthesis) will be hard to beat on cost and time" | Held on synthesis (the pairs cost $2.59 and $1.90 and took 695 s and 422 s). On `design-02` Sonnet `high` with the advisor cost the same ($1.11 against $1.12), took 14% longer and handled 4.17 against 3.58 |

## 7. Deviations and events

1. **The analysis tool was committed with 8 runs stored and no judge pass,** which is what the rules require
   (the tool before any judge pass). The stored answer blocks were checked for a status line at 16:45Z, before
   the first judge pass at 16:46Z: none had one. The plugin installed on the machine stayed at 3.5.3 until
   17:09Z, after the last judge pass.
2. **The tool differs from its builder's version in three points,** all changed before its commit on the findings
   of the agent that verified it: a failed slot takes the test's own limits whatever `harness.json` says, a run
   judged under another rubric than the baselines makes the result pending, and a failed slot lists its attempts.
   None of the three came into play: no slot failed and every run was judged under the baselines' rubric.
3. **`harness.json` is back at 1,200 s and $6 a run:** changed in the working tree at 17:04Z, after the last
   judge pass, and committed with this report. Under the old limits every run of this test would also have been
   valid: the slowest took 1,138 s and the dearest cost $3.75.
3a. **The rules file dates the stored synthesis runs 2026-10-05.** Three of the nine Opus `high` runs are from
   00:02Z to 00:05Z on 2026-10-06. No number changes.
4. **The session that ran the test was in use while it ran.** The owner and the operator's Fable session were in
   an interview, and one research agent (Sonnet) and two helper workflows (Opus and Sonnet) ran on the same
   account. That is load on the same API limits and can have lengthened runs. The load on the days of the stored
   baselines is unknown, so every time ratio carries that uncertainty.
5. **Spend was $99.51 against an expected $110,** well under the $130 stop.

## 8. Correction to the report of 2026-11-13, section 12

That section says the Fable advisor of `sonnet-5-5@xhigh+fable-advisor` "was called in 4 of 8 valid runs" and
that "the model did not follow the instruction every time". The stored answers show otherwise:

- **In 4 runs the advisor answered. In 3 of the other 4 Sonnet did call it and the call timed out:** the text
  before the answer block says so in each (`synthesize-02` runs 2 and 3 in English, `synthesize-03` run 1 in
  Turkish). The fourth, `synthesize-03` run 3, does not mention the advisor. So the instruction was followed in
  at least 7 of 8 runs, and the advisor failed to answer in at least 3.
- **The long runs of that test (up to 1,110 s) and its two attempts that ended at the 1,200 s limit** fit a call
  that hangs before it fails. That is a reading, not a measurement: no log shows the calls.
- **Claude Code 2.1.323 holds for the 8 valid runs.** The second timed-out attempt and the 16 judge passes ran on
  2.1.325, as their stored lines say; the file time of that version's binary on the machine is 21:35Z.

The verdict of that section stands: the pairing was not cheaper and showed no gain. In today's test, with an Opus
advisor and with a Fable advisor for Opus, 2 of 33 calls failed.

## 9. Limits

1. **Question 1 rests on one task, six runs a side.** It can show a large difference only, and it showed none.
2. **`design-02` separates the cells poorly.** Of the 27 runs scored on it across the seven cells of sections 3
   and 4, 18 handled between 3.75 and 4.5 of its 6 pitfalls, and no run handled all 6 in every pass. A task on which every cell lands near 4
   cannot tell a small gain from none.
3. **The stored baselines are from other days and Claude Code versions** (2.1.323 for `design-02`; the synthesis
   runs are from 2026-10-05). Time also depends on the load of the API on the day (section 7, point 4).
4. **Single tasks with three read-only tools are not a long chat.** In a long chat the advisor reads a much longer
   conversation at every call, which costs more, and nothing here says whether its advice is then worth more.
5. **When to call the advisor was our instruction,** once before the final answer. Claude Code's own wording
   about the advisor is not in play, because the harness replaces the system prompt.
6. **The cells add an instruction as well as an advisor.** Since no gain was found, the missing control matters
   less; it would have mattered for a "better".
7. **No stored run of Sonnet `high` alone** exists on these tasks, so what the advisor added to that cell cannot
   be said. Only the comparison with Opus alone is made.
8. **The checklist of `design-02` was built with a Fable advisor in the loop.** That could have favoured Fable's
   advice; the result gives no sign that it did.
9. **One judge is a Fable model.** The two judges are reported side by side in section 3 and disagree on single
   runs, not on the picture.
10. **Advisor calls can fail: 2 of 33 did here.** The rules count such runs as they come, so a pair's numbers
    describe the pair as it works, not the advisor's advice alone. Sections 3 and 4 give the answered-only
    lines where they differ.

## 10. Spend

| What | List price |
|---|---|
| 33 runs | $73.68 |
| 96 judge passes ($10.68 and $3.84 on `design-02`, $11.31 on synthesis) | $25.83 |
| **The test** | **$99.51** |
| Review of the rules (two agents) | $2.45 |
| Building and verifying the analysis tool (two agents) | $5.78 |

The two helper rows are priced from the agents' transcripts at list price and are not part of the test's
ceiling.

## 11. What changes

- **The routing table and the dispositions: nothing by these rules.** The owner decides whether the
  `design-02` lead (Sonnet alone near Opus at half the cost, 3 runs) is worth a test of its own.
- **The skill's evidence reference and the delegation reference** carry these results and the correction of
  section 8.
- **For a main chat on Opus with a Fable advisor,** which is how the owner works: this test showed no
  difference on `design-02`, the only task of this test with room to show one, at 47% more cost and 16% more time
  (60% and 23% in the runs where the advisor answered). A gain of less than about 1 pitfall of 6 cannot be
  excluded with six runs a side, and single tasks do not settle the question for a long chat (limit 4).
