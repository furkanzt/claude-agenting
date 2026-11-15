# Who writes the tests and who writes the code: report, 2026-11-15

Rules: [`PREREGISTERED-2026-11-14-coding.md`](PREREGISTERED-2026-11-14-coding.md), committed on 2026-11-14 at
17:52Z after three independent reviews, with five addenda and one correction (section 11 says when each was
written and committed). Tool and
rule checker: `evals/probes/code_bench.py` and `evals/probes/code_bench_analysis.py`, committed before any task
was installed. Record: [`code-runs.jsonl`](code-runs.jsonl), one line per model process and per test run,
numbers only. Runs: 48 test-writing runs and 180 coding runs between 2026-11-14 22:16Z and 2026-11-15 02:35Z, all
on Claude Code 2.1.325, pinned, with the advisor off. Every figure is list price. Commits are named by their
message here, not by hash, because the hashes of unpushed commits change when they are grouped for a push.

**Words used here.** A *cell* is one model at one effort, for example `haiku-5-5@medium`. The *hidden tests*
are the tests the real change shipped with; they judge every result and no model sees them. A *suite* is a set
of tests that a model wrote from the brief; it is *fit* when it fails on the start state and passes on the
real change. The *given suite* is the one fit suite that a task's coders get; its tests are *locked*, which
means the coder may not change them. In *arm A* the coder gets no tests. In *arm B* it gets the given suite
and up to three tries. In *arm C* it writes its own tests first. A *copy* is the code a run ends with. A run
is *correct* when the hidden tests pass on its copy, *finished* when its own check (the given suite, or its
own tests) passed within three tries, and *escaped* when it is finished but not correct. A *clean run* is one
`claude -p` process with file tools only; every run of the experiment is one.

## 1. Outcome

**All 228 planned runs were made. 178 of the 180 coding runs ended correct.** The two that did not were Haiku
runs that had no tests. The whole experiment cost $80.00, against $205 expected and a stop at $224.

**Question 1, bulk coding. With locked tests in place every cell was correct in every run, and Haiku 5.5 at
`medium` was the cheapest: $0.03 per correct task.** Haiku `high` cost $0.05, Sonnet 5.5 `low` $0.16, Sonnet
`medium` $0.21 and the Opus 5.5 `high` reference $0.71. No run passed its given tests while being wrong. The
rule names `haiku-5-5@medium` for both modes.

**Question 2, tests first. No effect shown, because there was almost nothing left to fix.** Without any tests
Haiku was correct in 23 of 24 runs at each effort and Sonnet `low` in 18 of 18. With locked tests the Haiku
cells were correct at the first try in 24 of 24. That is 4 points, against the 15 the rule asks for. These six
tasks were too easy for these coders to show what tests add.

**Question 3, who writes the tests. By the rule, Haiku writing its own tests is acceptable: 24 of 24 runs
correct, 20 finished, none escaped.** It was not cheaper on average: $0.79 a run by the rules, or $0.54
without the one timed-out process that is charged at the $6 cap, against $0.53 for a Sonnet `high` suite plus
a Haiku `high` coding run. It was cheaper on five tasks and three times as expensive on the sixth, where it
spent its tries on its own failing tests although its code was right from the first try.

**Question 4, plan and tests. By the rule the cell is Opus 5.5 at `high` in both modes: it is the only cell
inside the rule's bound on wrong rejections.** Sonnet 5.5 at `high` was the cheapest cell and one of two with
12 fit suites of 12 ($0.48 a suite); Sonnet `xhigh` 12 of 12 for $1.11; Opus `high` 11 of 12 for $1.21; Opus
`medium` 8 of 12 for $0.93. The rule also asks that a writer's fit suites fail at most 1 correct copy in 10.
The two Sonnet cells failed 14% and 15%, Opus `high` 7%. Of those 74 wrong rejections 72 are on `code-05`,
where a test the project already had needed bringing up to date: none of Sonnet's four suites did that, two
of Opus's four did. On `code-03` it went the other way: three of Opus's four suites carried ten outdated tests
and are unfit for it, and Sonnet's four are fit. Four suites a model and task cannot tell a habit from chance
(section 7). Whether the row follows the rule or takes Sonnet `high`, at 40% of the price of a suite, is put
to the owner.

**The vehicle test. No difference in cost shown between four single agents and one Workflow of four.** Each
way finished 4 of 4 pieces correct, at $0.029 and $0.027 a piece. The clean runs cost $0.023 on the same
pieces, also inside the rule's 25%. In this one run the single agents put 21,899 characters into the main
chat and the Workflow 7,141; part of that gap is that two of the Workflow's workers answered with one word.

**What changes: nothing until the owner releases the rows** (section 14).

## 2. What was run

| Time (UTC) | What |
|---|---|
| 2026-11-14, 17:30 to 17:52 | Rules drafted, read by three independent reviewers, corrected, committed |
| to 21:51 | The tool and its rule checker built in three stages, each checked by a second agent; 211 tests; Addendum 1 (eleven readings the tool fixed); committed before any task was installed |
| 21:55 to 22:02 | Installation of the six tasks: three attempts (section 11); Addendum 2; all six first choices pass |
| 22:03 to 22:10 | The probe on a toy project, with its own record: 17 runs, $0.93, none of them one of the 228; Addendum 3 |
| 22:16 to 22:41 | Pilot on `code-04`: its 8 test-writing runs, the fit check, one run of every coder cell and arm (9 runs); Addendum 4 |
| 22:50 to 23:28 | Step T: the other 40 test-writing runs |
| 23:29 to 23:40 | The fit check of all 48 suites (two runs on the real change for the 43 that passed the first, one for the 5 that failed it) and the six given suites fixed; committed |
| 23:46 to 02:35 | Step C: the other 171 coding runs, in four rounds, four processes at a time |
| 2026-11-15, 02:35 to 03:55 | The cross check: every fit suite on the final copies of arms A and C, 645 test runs (no model) |
| 02:42 | Addendum 5 written: the rules of the vehicle test (committed at 04:05, section 11) |
| 04:12 to 04:15 | The vehicle test in the live session: a probe call, then eight workers at once |

No process ended on an API error and no try was repeated for one. No process answered with another model than
its cell's. One coding process reached the launcher's time limit (section 11). The connection watchdog logged
674 checks between 22:50Z and 02:35Z with no failure.

## 3. The six tasks

All six first choices of the fixed selection passed the installation check; no replacement was used. Each is a
real past change from the owner's own projects, with the tests that change shipped with.

| Task | Language, rating | Tests in the hidden files | Failing on the start state | Fit suites of 8 |
|---|---|---|---|---|
| `code-01` | Python, easy | 29 | 3 | 6 |
| `code-02` | Python, medium | 96 | 3 | 8 |
| `code-03` | TypeScript, medium | 171 | 4 | 5 |
| `code-04` | TypeScript, medium | 60 | 7 | 8 |
| `code-05` | TypeScript, hard | 102 | 6 | 8 |
| `code-06` | TypeScript, hard | 242 | 41 | 8 |

Tests in the hidden files: how many tests judge a result. Failing on the start state: how many of them fail
before the change is made. Fit suites of 8: how many of the task's eight test-writing runs gave a fit suite.

The given suite of every task is `sonnet-5-5@high` run 1, the first in the fixed order, because that suite was
fit on all six.

## 4. Question 1: bulk coding with locked tests (arm B)

| Coder | Runs | Correct | Correct at the first try | Runs that needed a 2nd try | Cost per correct task | Time per run |
|---|---|---|---|---|---|---|
| `haiku-5-5@medium` | 24 | 24 | 24 | 1 | $0.028 | 75 s |
| `haiku-5-5@high` | 24 | 24 | 24 | 0 | $0.049 | 107 s |
| `sonnet-5-5@low` | 18 | 18 | 18 | 1 | $0.162 | 31 s |
| `sonnet-5-5@medium` | 18 | 18 | 17 | 4 | $0.205 | 38 s |
| `opus-5-5@high` (reference) | 6 | 6 | 6 | 0 | $0.713 | 90 s |

- **Every cell is usable, and none had an escaped run** (finished by its given tests but wrong by the hidden
  ones). By the rule `fast` takes the usable cell with the lowest cost per correct task, and `balanced` the
  cheapest cell whose runs are all correct: both are `haiku-5-5@medium`.
- **Haiku `medium` cost a sixth of Sonnet `low`** ($0.028 against $0.162) and a twenty-fifth of the Opus
  reference. It was slower than Sonnet: 75 s a run against 31 s.
- **No run needed a third try.** Six runs needed a second. In five of them the code was already correct by
  the hidden tests after the first try, and the given suite had failed it on one or two tests (1 of 95, 2 of 63,
  2 of 113 three times); the coder then changed its code to satisfy the given suite. In one (`sonnet-5-5@medium`
  on `code-06`) the first try was wrong by both and the second fixed it.
- **No coder changed a locked file** in any of its 96 tries.
- **A coding run cost $0.01 to $0.13 for Haiku,** $0.04 to $0.44 for Sonnet and $0.44 to $0.98 for Opus. By
  task, the mean cost of an arm-B run:

| Coder | `code-01` | `code-02` | `code-03` | `code-04` | `code-05` | `code-06` |
|---|---|---|---|---|---|---|
| `haiku-5-5@medium` | $0.015 | $0.034 | $0.011 | $0.031 | $0.030 | $0.046 |
| `haiku-5-5@high` | $0.018 | $0.044 | $0.024 | $0.040 | $0.049 | $0.116 |
| `sonnet-5-5@low` | $0.085 | $0.167 | $0.078 | $0.201 | $0.304 | $0.137 |
| `sonnet-5-5@medium` | $0.136 | $0.178 | $0.171 | $0.205 | $0.388 | $0.154 |
| `opus-5-5@high` | $0.443 | $0.617 | $0.512 | $0.977 | $0.939 | $0.792 |

## 5. Question 2: tests first (arm B at its first try against arm A)

| Coder | Arm A, no tests: correct | Arm B, locked tests: correct at the first try | Difference | The rule asks for | Tries 2 and 3 add in arm B | Cost of a run, A and B |
|---|---|---|---|---|---|---|
| `haiku-5-5@medium` | 23 of 24 | 24 of 24 | +4.2 points | 15 | 0 | $0.016 and $0.028 |
| `haiku-5-5@high` | 23 of 24 | 24 of 24 | +4.2 points | 15 | 0 | $0.022 and $0.049 |
| `sonnet-5-5@low` | 18 of 18 | 18 of 18 | 0 | 30 | 0 | $0.146 and $0.162 |

**No effect shown** in any of the three cells. The tasks were too easy for these coders to show an effect;
that is not the same as "tests do not help". With 23 of 24 correct there was at most one run a cell where
tests could make a difference. Arm B had no wrong run, and one run cannot show that the tests were the reason.

The two runs that were not correct were both Haiku runs on `code-02` with no tests:

- one left a syntax error in the file it changed, so all 96 hidden tests failed. Any test run would have
  shown it, also a run of the project's old tests;
- one differed from the brief in one detail, and 1 of 96 hidden tests failed.

With locked tests a Haiku run cost about twice a run without them (it reads the test file and writes more),
which is one to three cents.

## 6. Question 3: who writes the tests (`haiku-5-5@high`, arm C against arm B)

| | Arm B: locked tests from Sonnet `high` | Arm C: the coder writes its own tests first |
|---|---|---|
| Runs | 24 | 24 |
| Correct | 24 | 24 |
| Correct at the first try | 24 | 24 |
| Finished (its check passed within three tries) | 24 | 20 |
| Escaped | 0 | 0 |
| Runs with 1, 2, 3 tries | 24, 0, 0 | 18, 2, 4 |
| Cost of a run | $0.049, plus $0.48 for the suite | $0.79 by the rules (one process charged at the $6 cap); $0.54 without it |
| Time of a run | 107 s, plus 131 s for the suite | 549 s, not counting the timed-out process |

- **Acceptable by the rule:** at least half finished (20 of 24), the share of correct runs not more than 10
  points below arm B (equal), escaped runs at most 1 in 10 of the finished (0 of 20), behind arm B on no task.
- **Every extra try in arm C was caused by the coder's own tests.** Its code already passed the hidden tests
  after the first try in all 24 runs. In six runs the coder's own tests failed on its own correct code (1 to 6
  failing tests of 51 to 185); two runs repaired them at the second try, four never did.
- **Cost by task.** Arm C was cheaper than a Sonnet `high` suite plus an arm-B run on five tasks ($0.13 to
  $0.27 against $0.27 to $0.70). On `code-03` it was about three times as expensive ($2.34 against $0.82).
  Three of its four runs there used all three tries, at $0.5 to $1.3 a try. Each of those tries read 5 to 13
  million cached tokens over 54 to 99 turns. Above 100,000 tokens of context Haiku 5.5's list price per token
  is five times higher, and eight of the ten tries with a known cost on this task were above it on average.
  One of those processes reached the time limit.
- **What this does not show:** how good Haiku's tests are as a check. No arm-C run had wrong code, so its
  tests never had anything to catch, and they were not run against the reference.

## 7. Question 4: plan and tests (step T)

| Test writer | Fit suites of 12 | Mean cost | Mean time | Cost per fit suite | Catches a wrong copy | Wrongly rejects a correct copy |
|---|---|---|---|---|---|---|
| `sonnet-5-5@high` | 12 | $0.48 | 131 s | $0.48 | 4 of 4, too few to tell | 24 of 176 (14%) |
| `sonnet-5-5@xhigh` | 12 | $1.11 | 361 s | $1.11 | 4 of 4, too few to tell | 26 of 176 (15%) |
| `opus-5-5@medium` | 8 | $0.93 | 148 s | $1.39 | 4 of 4, too few to tell | 12 of 116 (10.3%) |
| `opus-5-5@high` | 11 | $1.21 | 216 s | $1.32 | 4 of 4, too few to tell | 12 of 161 (7%) |

Catches: pairs of a fit suite and a wrong copy where the suite failed the copy. Wrongly rejects: pairs of a
fit suite and a correct copy where the suite failed the copy. The copies are the final copies of arms A and C.

- **All 48 suites were red on the start state at the first try.** Five were not fit: one or more of their
  tests fail on the real change. They are both `opus-5-5@medium` suites on `code-01` (1 of 47 and 1 of 49
  tests), both on `code-03` (10 of 187 and 10 of 185), and one `opus-5-5@high` suite on `code-03` (10 of 181).
- **The cross check:** each of the 43 fit suites ran on each final copy of arms A and C of its task, 645
  pairs. All 90 copies had changed source. Only 2 of them were not correct, so each cell's catch rate rests
  on 4 pairs: every suite failed both wrong copies, and by the rules that is too few to tell.
- **By the rule, `fast` is `opus-5-5@high`:** it is the only cell with at least 10 fit suites that wrongly
  rejects at most 1 correct copy in 10. For `balanced` no cell has 12 fit suites inside the bound; the rule's
  second step, the most fit suites among the cells inside it, names `opus-5-5@high` again.
- **Where the wrong rejections are: 72 of the 74 are on `code-05`, on one behaviour the brief leaves open.**
  The two readings of the brief differ only for data stored before the change. The real change takes one
  reading. 12 of the 15 correct copies take the other: 8 of the 11 written without tests and all 4 written by
  a coder that tested itself. A test the project already had fits the real change's reading only once its
  set-up data is brought up to date. Six of the eight fit suites of this task kept that test as it stood, so
  it fails on those 12 copies. One of the six, the given suite, also wrote a new test that asks for the real
  change's reading. Two suites, one of each Opus cell, brought the test's set-up data up to date, as the
  hidden tests do, and reject nothing. So on this task none of Sonnet's four suites made the update and two
  of Opus's four did.
- **On the other five tasks** the only wrong rejections are 2, both of `sonnet-5-5@xhigh` on one copy of
  `code-01`. Without `code-05` every cell is at 0% or 1%. One suite moves a cell's rate by up to 7 points.
- **What the same point cost where the coder saw the tests.** The given suite of `code-05` is one of the six.
  In arm B its check failed at the first try in 3 of 15 runs, all three of them Sonnet coding runs, and
  passed at the second; no run ended wrong. Over all six tasks the given suites failed a copy that the
  hidden tests passed in 5 of 96 checks.
- **The five unfit suites, looked at after the verdict. Not a rule result.** The rule counts an unfit suite
  in the fit count and in the cost per fit suite, and leaves it out of the rate of wrong rejections. Run on
  the same correct copies, each of the five fails all 15 of its task. The three on `code-03` fail the same
  ten tests: tests the project already had, which the real change makes outdated, and which these suites
  carried along as they stood. The fourth Opus suite on that task brought them up to date. Sonnet's four
  suites did not carry them. The two on `code-01` each fail one new test of their own. Counted over all 12
  suites of a cell, fit or not, the suite fails a correct copy in 24 of 176 pairs (14%) for
  `sonnet-5-5@high`, 26 of 176 (15%) for `sonnet-5-5@xhigh`, 27 of 176 (15%) for `opus-5-5@high` and 72 of
  176 (41%) for `opus-5-5@medium`.
- **The two tasks together.** Each model family left tests of the project outdated on one task. Sonnet did on
  `code-05`, in 4 of 4 suites: the suites stay fit and reject 12 of 15 correct copies. Opus did on `code-03`,
  in 3 of 4 suites: the suites are unfit and reject every correct copy. Four suites a family and task cannot
  tell a habit from chance.
- **Cost.** A suite from `opus-5-5@high` costs $1.21 and one from `sonnet-5-5@high` $0.48, which is 40% of
  it. Per fit suite it is $1.32 against $0.48, 2.75 times as much. It takes 216 s against 131 s.

## 8. What a finished task costs from end to end

Not a rule result: the sums the owner asked for, from the tables above. One task, one suite, one coding run.

| Path | Tests | Code | Cost of the task | Correct in this experiment |
|---|---|---|---|---|
| No tests | none | Haiku `medium` | $0.016 | 23 of 24 |
| No tests | none | Sonnet `low` | $0.146 | 18 of 18 |
| The coder tests itself | Haiku `high` | Haiku `high` | $0.79 by the rules; $0.54 without the one timed-out process | 24 of 24 (20 finished) |
| Locked tests | Sonnet `high`, $0.48 | Haiku `medium`, $0.028 | $0.51 | 24 of 24 |
| Locked tests | Sonnet `high`, $0.48 | Sonnet `low`, $0.162 | $0.64 | 18 of 18 |
| Locked tests | Sonnet `high`, $0.48 | Opus `high`, $0.713 | $1.19 | 6 of 6 |
| Locked tests | Opus `high`, $1.21 a suite ($1.32 a fit suite) | Opus `high`, $0.713 | $1.92 ($2.03 per fit suite) | not run (suites from this writer were not given) |

- **On the tests-first path the tests are the cost, not the coding:** with Sonnet `high` writing them and Haiku
  `medium` coding, 94% of a task's cost is the suite. The briefs here already named the files and the names,
  which keeps the coding cheap.
- **Moving the coding from Sonnet `low` to Haiku `medium` saves $0.13 a task.** Moving the test writing from
  Opus `high` to Sonnet `high` saves $0.73 a task ($0.84 counted per fit suite).
- **The cheapest path, no tests on Haiku, got 1 run in 24 wrong,** and nothing in that path notices.

## 9. The vehicle test

**No difference in cost shown.** Four single agents and one Workflow of four each finished 4 of 4 pieces
correct, at $0.029 and $0.027 a piece.

Rules: Addendum 5. Record: [`vehicle-runs.jsonl`](vehicle-runs.jsonl). The question was: when the main chat
hands bulk coding to cheap workers, does it matter whether it starts them as single `Agent` calls or as one
Workflow? The pieces are the four tasks whose tests run with one command and nothing to install (`code-01`,
`code-02`, `code-03`, `code-05`). One worker a piece and vehicle, all eight started in one message. Each
worker read a task file, worked on its own copy outside the repository, and could run one command: the given
suite on its copy, in the tool's sandbox.

| Piece | Single agent: cost | Calls | Time | Workflow: cost | Calls | Time | Clean run, mean of 4: cost | Time |
|---|---|---|---|---|---|---|---|---|
| `code-01` | $0.021 | 9 | 54 s | $0.019 | 5 | 44 s | $0.015 | 32 s |
| `code-02` | $0.023 | 11 | 130 s | $0.027 | 11 | 135 s | $0.034 | 141 s |
| `code-03` | $0.009 | 8 | 31 s | $0.017 | 7 | 33 s | $0.011 | 18 s |
| `code-05` | $0.062 | 16 | 123 s | $0.046 | 15 | 107 s | $0.030 | 81 s |
| **Per correct piece** | **$0.0290** | | | **$0.0272** | | | **$0.0226** | |

Calls: requests the worker sent to the model. Time: from the worker's first line to its last. Clean run: the
16 stored arm-B runs of `haiku-5-5@medium` on these four tasks, four a task.

- **All eight copies pass the given suite and the hidden tests.** The single agents ran 5 checks, one of them
  failed and was fixed; the Workflow's workers ran 4, none failed.
- **By the rule, no difference shown.** The Workflow was 6% cheaper per correct piece than the single agents;
  the rule asks for 25%. The clean runs were 22% cheaper than the single agents and 17% cheaper than the
  Workflow, which is also less than the rule asks for.
- **Every worker ran as the plugin's `coder` agent on Haiku 5.5 at `medium`,** read from each transcript. The
  agent's own file says Sonnet at `low`; the probe call before the launch showed that a single typed `Agent`
  call takes the model and the effort named on the call. No piece was left out.
- **A `coder` worker starts with a small context:** 14,728 tokens in a single agent and 15,082 in the
  Workflow. Seven of the eight sent about 10,400 of them for the first time, which stores them in the cache
  at the higher write price, and read the rest from the cache; the first Workflow worker sent all 15,080.
  The generic Workflow agent starts with about 44,000 (the skill's section on fan-outs).
- **`code-05` is where the cost went.** Above 100,000 tokens of prompt Haiku 5.5's list price is five times
  higher. Only this piece's two workers passed that size: 3 calls of the single agent and 1 of the
  Workflow's worker. That is most of the distance between the two vehicles, and it is one piece.
- **What reached the main chat, in this one run.** The four single agents put 21,899 characters into the
  main chat: their launch calls 1,360, the launch results 4,408, four reports 12,541 and four end notices
  3,590. The Workflow put 7,141: its script 796, the launch result 1,390 and one end notice with all four
  answers, 4,955. Part of the gap is the workers' own choice: two of the Workflow's four workers answered
  with one word, and all four single agents wrote a full report. The main chat reads that text again on
  every later turn, at its own model's price.
- **Limits.** One run a piece and vehicle. One agent definition, list price. This Mac's instruction files and
  plugins were loaded into every live worker; a clean run has file tools only and a fixed short system
  prompt. A live worker has a shell and checks itself inside one run; a clean run hears from its tests only
  between tries. Addendum 5 expected every worker to start with an empty cache; seven of the eight read
  4,391 to 4,625 tokens from a cache that the probe call or another worker had written, which is worth about
  $0.001 a worker. The sizes on the main chat's side are characters, not cost.
- **For the skill:** the sentence on vehicles cannot say that one of them makes a worker cheaper. It can say
  what was seen: no difference in cost per piece shown, and in this run a Workflow that returned less text
  to the main chat.

## 10. Expectations against results

| Written beforehand | Result |
|---|---|
| A Haiku try costs $0.20 to $0.40 | Wrong, by about ten times: $0.01 to $0.13 in arms A and B. Only a try that also writes tests reached that range ($0.25 at the first try, $0.39 over all tries, up to $1.30) |
| Question 1: `haiku-5-5@high` correct in at least two thirds of its runs on the easy and medium tasks, at most one third on the two hard ones | Wrong for the hard tasks: 24 of 24, the hard tasks included |
| Its cost per correct task at most half of `sonnet-5-5@low`'s | Held: $0.049 against $0.162 |
| "The open point is the escaped runs" | Not a prediction. None escaped in any cell |
| Question 2: tests first helps both Haiku cells; smaller for Sonnet `low` | Wrong: no effect shown in any cell (+4 points for each Haiku cell and 0 for Sonnet, against the rule's 15) |
| Question 3: not acceptable, more than 1 in 10 finished runs escape | Wrong: acceptable, none escaped |
| Question 4: `opus-5-5@medium` has at least 10 fit suites at a cost within 25% of `sonnet-5-5@xhigh`'s | Wrong on the suites: 8 fit. The cost held: $0.93 against $1.11 |
| `sonnet-5-5@high` has fewer fit suites than either Opus cell | Wrong: 12 of 12, more than either |

Of the seven predictions six were wrong and one held. In five of the six the cheaper models did better than
expected; in the sixth Opus `medium` gave fewer fit suites than expected.

## 11. Deviations and events

1. **Installation took three attempts,** before any model run. The first stopped on a typing error in one
   task record (two folder names ended in a slash). The second stopped all six tasks at the leak check, which
   counted names the projects already had as added by the change. Addendum 2 states the corrected reading and
   what was checked by hand before correcting; it was written after the check it corrects had stopped.
2. **The spend stop was lowered from $226 to $224** after the toy probe showed that a process can pass its cost
   cap by one turn (Addendum 3). The plan said to lower it by the overshoot seen. That was $0.006: a process
   cost $0.011 against a test cap of $0.005. The stop was lowered by an estimate instead: four processes at
   a time, each passing its cap by one turn of the largest model at $0.50. The spend stayed far below the
   stop.
3. **The pilot did not plant every failure with a real model.** A failing given suite and a time limit that is
   too short were covered by the tool's tests, not by a model run (Addendum 3). The cap was probed at $0.005,
   not at $6.
4. **A guard against an outage was added after the pilot** (Addendum 4): a wait before a repeated attempt, and
   no new process after a run that ended on three API errors. It was never used: no attempt was repeated.
5. **One process of 244 reached the launcher's time limit:** the second try of a `haiku-5-5@high` arm-C run on
   `code-03`. By the rules it counts as a try, its files were checked, and its unknown cost is charged at the
   $6 cap, which is 7.5% of the whole spend. The known costs sum to $74.00.
6. **Nothing was cut.** The tool projected about $70 after the pilot and $67.66 after step T, against the stop at
   $224. Step C ran as one command over all four rounds, not as four commands; the tool starts a round only
   when the projection fits under the stop, which is what the rule asks.
7. **Three test-writing processes changed a file that was not a test file** (two of `sonnet-5-5@xhigh`, one of
   `sonnet-5-5@high`); the change was dropped and counted, as the rules say. Six processes had a tool call
   refused (four in step T, all of `sonnet-5-5@xhigh`, and two in step C).
8. **Addendum 5 was written at 02:42Z, after step C, and committed at 04:05Z, after the cross check had
   ended.** The plan takes the commit time as the record. By then the clean-run figure it compares with and
   all four verdicts were known. The vehicle test itself ran after the commit, at 04:12Z. The addendum also
   says that the live session ran Claude Code 2.1.323. That was wrong: every worker's transcript records
   2.1.325, the version of the clean runs. A correction is appended to the rules.
9. **In the vehicle test seven of the eight workers did not start with an empty cache,** which Addendum 5 had
   expected (section 9). It is worth about $0.001 a worker.
10. **The cross check ran 80 minutes without an event:** 645 pairs, no time limit reached, no failure of the
   runner. After its verdict was read, two things were looked at with private re-runs that wrote nothing to
   the record and changed no result: which test fails on `code-05` (six suites, with the full output kept),
   and what the five unfit suites do on the correct copies of their tasks (section 7).
11. **This report was audited before the owner saw its figures,** by four independent reviewers: a recount
   from the record, a review against the rules, a recount of the note on the `fast` column, and a read for
   privacy and plain language. Their corrections are in the commit after the draft's. The largest: the
   draft's account of question 4 leaned towards Sonnet, and section 7 and section 14 now give both sides.

## 12. Limits

1. **A ceiling.** 178 of 180 coding runs were correct. Questions 1 and 3 could therefore not separate the
   cells by correctness, only by cost, and question 2 had nothing to measure. Harder or larger tasks could
   order the cells differently. Nothing here says Haiku codes as well as Sonnet or Opus in general.
2. **Six tasks from the owner's own projects,** in two languages, each a change of 29 to 174 source lines in
   one to five files. Nothing here speaks for other languages or for a large feature. The tasks, not the
   runs, are the sample.
3. **The brief names the files to change and every name the hidden tests need.** That is a finished plan. The
   coders here did the typing after the thinking; a vaguer brief was not tested.
4. **The hidden tests are the judge.** They pass any code they do not exercise, and five times they passed a
   copy that the given suite had failed. Three of the five are the open point of `code-05` (section 7), where
   both readings of the brief can be defended; the other two were not examined. Question 4's rate of wrong
   rejections always counts the hidden tests as right.
5. **The coder could not run anything.** A real agent has a shell and checks itself inside one run. Here a
   coder heard from its tests only between tries, at most twice, which works against the arms with tests.
6. **Every arm-B result rests on one given suite per task,** a `sonnet-5-5@high` run. Question 4's rule names
   `opus-5-5@high`. If the skill follows the rule, question 1's escaped runs were measured with tests from a
   writer the skill does not use, and the path "Opus `high` tests, Haiku code" was never run. Arm B also says
   nothing about which writer is better: no other writer's suites were given.
7. **Three or four runs a cell and task** show a large difference only. One task moves a share by 17 points.
8. **List price.** How a $20 plan counts each model against its limit is not published.
9. **The review row was not measured.**
10. **Question 4 rests on two suites a cell and task.** One suite moves a cell's rate of wrong rejections by
   up to 7 points, which is the whole distance between the Sonnet cells and `opus-5-5@high`. That holds in
   both directions: one more Opus `high` suite like the six on `code-05` would put that cell at 15% too.
11. **Each try is a fresh process** that reads the files again, so a retry costs more than it would inside
   one session. Arm C's cost figures carry that.
12. **The given suite was to be picked with knowledge of the real change,** which a team in the field does not
   have. Here the first suite in the fixed order was fit on all six tasks, so the pick never used that
   knowledge. The five unfit suites show what a team without it would have met.
13. **The scouts that found and rated the tasks were Sonnet agents.** No model under test saw their notes.
   Their ratings put two tasks at hard; no coder cell found them hard.
14. **The sandbox guards against accidents, not against an adversary.**

## 13. Spend

| What | List price |
|---|---|
| Step T, 48 runs | $44.67 |
| Step C, 180 runs (196 processes), known costs | $29.33 |
| One process of unknown cost, charged at the cap | $6.00 |
| **The experiment** | **$80.00** |
| The probe on the toy project (its own record) | $0.93 |
| The vehicle test: eight workers $0.225, the probe $0.003 (not part of the experiment's spend) | $0.23 |

Expected beforehand: about $205, $80 of it for step T and $125 for step C. Step T came in $35 under and step C
$90 under. Most of that is the Haiku tries, which cost a tenth of what was expected, and Sonnet's coding runs.

## 14. What changes

Nothing enters the skill before the owner releases it. By the rules, the two new rows would read:

| Row | `fast` | `balanced` | From |
|---|---|---|---|
| Plan and write the tests | `opus`/`high` | `opus`/`high` (no cell met the full rule; second step) | Question 4 |
| Bulk coding against tests that exist | `haiku`/`medium` | `haiku`/`medium` | Question 1 |
| Review | the verify row's cell | the verify row's cell | not measured |

- **The tip for the main chat of a $20 plan** names question 4's `fast` cell: by the rule, Opus at `high`
  effort. The rules add: a long chat re-reads the whole conversation every turn, so the cheaper input price
  weighs more there than in these single tasks. The rule ties the tip to that cell, so another cell for the
  row means another tip.
- **Put to the owner before anything is written into the skill:** whether the plan-and-tests row follows the
  rule (`opus`/`high`) or takes `sonnet`/`high`.
  - *For the rule.* It was written before the runs. `opus-5-5@high` is the only cell inside the one bound on
    the quality of tests that the data could test (the catch rate was too few to tell for every cell), and
    both Sonnet cells are over it by 4 to 5 points. On `code-05` two of Opus's four suites brought the old
    test up to date and none of Sonnet's four did. The copies that the Sonnet suites turned away there came
    from the cheap coders (11 Haiku copies, 1 of Sonnet `low`), the coders this row's tests are written for.
  - *For Sonnet `high`.* 12 fit suites of 12 against 11, at 40% of the price of a suite: $0.48 against
    $1.21, $0.73 less a task. On `code-03` three of Opus's four suites carried outdated tests and are unfit.
    Counted over all 12 suites of a cell, the two cells turn away the same share of correct copies, 14% and
    15% (section 7; that count is not in the rules).
  - *What neither side can claim.* Each family's lapse is on one task, with four suites a family: one suite
    more or less on either side changes the order. Arm B does not compare writers: only Sonnet `high` suites
    were given. With them 90 of 90 runs ended correct; without any tests 64 of 66 did.
  - Taking Sonnet `high` would be the owner's overrule of the rule, and the report of the release will say
    so.
- **The owner's release, 2026-11-15 (in 3.7.0):**
  - *Bulk coding:* `haiku`/`medium` in every mode, as the rule says. A new agent, `bulk-coder`, carries the
    arm-B way of working: tests it may not change, one check command, at most three failed checks.
  - *Plan and write the tests:* `balanced` follows the rule, `opus`/`high`. `fast` takes `sonnet`/`high`,
    and so does `cheapest`, a third mode the owner added below `fast`. That is the owner's overrule of the
    rule for those two modes, on the reading in section 7: over all twelve suites of a cell the two
    writers turn away the same share of correct copies, and Sonnet `high` costs 40% of Opus `high`.
  - *Review:* the verify row's cell in every mode.
  - *The tip* names `fast`'s cell: Sonnet at `high` effort. The owner added two things to it: Opus at
    `xhigh` for a design decision, and a warning that every switch of model throws away the chat's cache.
  - *The vehicle sentence* says what section 9 saw and no more.
- **Readings for the skill's text, not rule results:**
  - With a brief that already names the files and the names, the tests are where the money goes on the
    tests-first path: 94% of a task's cost here (section 8).
  - A cheap coder that writes its own tests was acceptable here but no cheaper on average, and it can spend
    its tries on its own failing tests (section 6).
  - Without any tests Haiku got 1 run in 24 wrong. That is inside the owner's bar for unchecked work (about
    1 in 10), and nothing in that path notices the wrong run.
