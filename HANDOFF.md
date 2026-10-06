# Handoff: what is left after agenting 3.1.0

Written 2026-10-06, right after `1362672` (the 3.1.0 release) was pushed to
`origin/main`. Nothing is in flight: no background runs, no pending workflows, a
clean working tree. This file lists only what is **not done**. For what was done and
why, read `evals/results/REPORT-2026-10-06.md` first, then `CHANGELOG.md` (3.1.0).

## 1. Where things stand

The routing table was re-measured on Haiku 4.5, Sonnet 5.5, Opus 5.5 and Fable 5.1
with the new `evals/` harness (165 runs, $121.90 including judge passes). Three cells
changed; the rest held.

| Row | Default (`balanced`) | `quality` | Evidence in one line |
|---|---|---|---|
| List / count / collect | `haiku/low` | same | Haiku 3/3; `sonnet/low` 2/3, `sonnet/medium` 1/3 (silent omissions); `sonnet/high` 3/3 at ~70% less cost, **unconfirmed** |
| Mechanical cleanup | `sonnet/low` | same | Haiku 0/3 (headers left in); Sonnet 3/3 |
| Read and report | `sonnet/medium` | `sonnet/high` | every cell 3/3; no cheaper cell saved 25% |
| Classify / judge | `sonnet/medium`–`high` | `sonnet/high` | `low` saved 4%; the narrowing was never tested |
| Synthesize | `opus/xhigh` | same | Opus `xhigh` found every planted item in 9/9 runs; `opus/high` 7/9; Sonnet `xhigh` 6/9 |
| Don't guess (BELİRSİZ) | `sonnet/xhigh` | `opus/xhigh` | 0/102 hallucinations each for Sonnet and Opus (Haiku 19/102): a bounded null |
| Adversarial verify | `sonnet/high` | `opus/high` | 0/96 wrong verdicts each (Haiku 10/96): a bounded null |

`fast` uses `opus/high` for synthesis, `sonnet/low` for read-report and classify, and
the `balanced` cells elsewhere (`skills/agenting/reference/modes.md`). Agent pins: only `text-mechanic` changed
(`sonnet/low`).

## 2. Owner actions (not code)

1. **Update your own install.** The push does not reach a running install. Your
   machine is on 3.0.0 until you run `/plugin marketplace update agenting` and then
   `claude plugin update agenting@agenting` (or enable auto-update under `/plugin` →
   Marketplaces). Friends do the same; auto-update is off by default for third-party
   marketplaces. Claude Code only treats a release as new when `version` changes, and
   `plugin.json` wins over the marketplace entry, so bump both together next time.
2. **Back up `evals/private/`** (about 7.9 MB). It holds the real test material, the
   ground truth, the graders and every stored answer, and it is gitignored on purpose
   (the repo is public). If it is lost the committed scores stay valid evidence but
   nothing can be re-graded or extended, and the tasks must be rebuilt from the
   format in `evals/README.md`.
3. **Your global `~/.claude/CLAUDE.md`** says any model *or effort* switch rewrites the
   prompt cache. Claude Code's docs now say an effort change no longer does on Opus
   5.5, Sonnet 5.5 and Fable 5.1 (not on Bedrock, Google Cloud, HIPAA, or with
   experimental betas off). That file is yours; update the line only if you decide to.

## 3. Next work, in priority order

### A. When Haiku 5.5, Fable 5.5 (or any new model) ships

The point of the harness is that this costs only the missing runs.

1. `evals/cells.json`: add each cell with its **exact** `model_id`, `effort`, and a
   dated price. Do not rely on an alias: `haiku`, `sonnet`, `opus`, `fable` move when a
   release ships, which silently changes what every pin means. The harness records
   the model that actually answered and rejects a mismatch.
2. `evals/rows.json`: add the cells to the grids where they compete, with a `role`.
3. `python3 evals/evalkit.py plan --repeats 3` lists exactly what is missing. Read it.
4. `python3 evals/evalkit.py run --repeats 3 --max-usd <cap> --jobs 4`, in chunks (see
   section 5), then `judge`, `report --phase screening`, `decide`.
5. For a silent-damage row, a candidate that survives screening needs confirmation
   tasks (`run --phase confirmation --rows <row> --cells <candidate>`).
6. Write the dated findings to `evals/results/REPORT-<date>.md`, change the table in
   `skills/agenting/SKILL.md`, `README.md` and `reference/modes.md`, add a CHANGELOG
   entry, bump `version` in `.claude-plugin/plugin.json` and `marketplace.json`, run
   `python3 -m pytest tests -q`, commit.

**Haiku 4.5 specifically.** Anthropic lists it for retirement no earlier than
2026-10-15 (no notice had been issued on 2026-10-05). Scan is the only row still on
it. If it retires or a successor ships, re-test scan; `sonnet/high` is the standing
candidate (3/3 at $0.052 a run against Haiku's $0.175).

### B. Tighten the Sonnet-versus-Opus comparison on abstention and verification

Both rows moved to Sonnet on a bounded null: 0 of 102 against 0 of 102 hallucinations
bounds each rate below ~3% at 95%, but at that size the power to detect a 3-point gap
is about 8.5% (about 40% for 5 points). To tighten it:

- Build a harder paired set (near-miss unanswerable items where the document gives the
  sibling value, a range, or an intent but not the answer; long or multi-document
  context), about 100 or more items per type, same items to both models, and test the
  discordant pairs exactly. Use the builder-then-blind-auditor pattern in section 5.
- If any gap appears, `python3 evals/evalkit.py decide` flips the row back; the rows
  already have `fast`/`quality` cells to fall back to.
- The deep-research note lists what it could not establish:
  `evals/research/2026-10-06-sonnet-vs-opus-open-book.md` (open questions).

### C. Scan needs a second task, with Bash

Scan was tested with Read, Grep and Glob only; the real `scanner` agent has Bash, which
would probably make both models exact. A second scan task whose subjects get Bash
(sandboxed copy, no path to the private truth) would settle `sonnet/high`. Until then
scan stays on `haiku/low` (which is just `haiku`: Haiku ignores `effort`).

### D. Classify: the narrowing was never tested as a decision

The 3.0 cell was `medium`–`high`; the harness took `medium` as the baseline, and the
table kept the range. Label errors over 72 labels per cell: `sonnet/medium` 4,
`sonnet/high` 4, `sonnet/low` 1, `opus/low` 0 (at about 2x the cost). Two confirmation
tasks with `sonnet/high` as the baseline would settle it; the potential saving is small.

### E. Agents that were never measured

The measurement covered the seven routing rows only. `reviewer`, `security-architect`,
`system-architect`, `incident-responder` (all `opus/xhigh`) and `coordinator`,
`swarm-coordinator` (`opus/high`) keep their pins on judgment alone. Each is a job
shape the harness has no task for; measuring them means writing tasks first.

### F. Assumptions to verify in real use

- **Haiku's cost** depends on thinking being on (8,000 to 18,000 thinking tokens a
  run in `claude -p`). Subagents inherit the session's thinking setting; measure a
  real subagent run before relying on "Haiku is not cheap".
- **Whether a Workflow `agent()` honours `effort`** is not confirmed in Claude Code's
  docs, and a Workflow subagent cannot report its own effort. The harness avoids this
  by using `claude -p --effort`; the plugin's guard assumes the option works.
- **Cache behaviour on an effort switch** for subagents and Workflow requests
  (`hooks/cache-tripwire.py` measures it).

### G. External evidence to watch

Grounded or open-book benchmark rows for the 5.5 models (Vectara HHEM, FACTS
Grounding, HalluHard, Artificial Analysis Omniscience accuracy and hallucination
components at matched effort). Any of them could change the abstention decision.

## 4. Harness follow-ups (engineering debt)

- `evals/evalkit.py` is 1,566 lines. Split it (ids and index, grading, runner, judge,
  report and decide, CLI); the 192 tests make that safe.
- **Grader id coverage.** It hashes `grader.py` and the threshold for code tasks and
  `rubric.md` only for judge tasks. It does **not** cover `truth.json`, and for judge
  tasks not `grader.py`, the threshold or the judge system prompt. Fixing it orphans
  stored judge scores (re-judging costs about $20), so introduce it as an opt-in
  `grader_id_version: 2` for new tasks.
- **Judge calibration** was run only on `synthesize-01` (two answers with known
  judgments). `synthesize-02` and `-03` have calibration answers that were never run.
- The two judge passes use one model and agree almost always: one opinion, not two. A
  second judge model, or a human re-read of a sample, would help.
- Score details still allow flat scalar keys (such as `q7: true`) that could reveal an
  item. Only dict and list values are dropped; a strict key allowlist is the fix.
- A process spawned after Ctrl-C has already called `kill_all` is not killed until its
  own timeout.

## 5. Operating notes and lessons

- **Instrument.** Do not use Workflow subagents as test subjects: they inherit the
  session's context and carry an `advisor` tool that consults a stronger model.
  `claude -p --restricted` in an empty directory sees no CLAUDE.md (probe: the model
  reported none with an 8.5 KB user-level file present), hooks, memory or advisor, and
  returns exact cost, thinking tokens and the answering model.
- **Cost and limits.** Screening of 30 cells (90 runs) cost about $42; the confirmation
  round about $41 plus $11 of judging; a synthesis run is $1 to $3.6, other tasks under
  $1. The first big sweep hit the account's usage limit once, so run in chunks and use
  `--max-usd`. Results are append-only; an interrupted `run` resumes with `plan`.
- **Building a task.** One builder per task, then a blind auditor that solves the task
  before opening the truth; 3 of 7 first builds had a blocker. The rules that came out
  of it: every item must have exactly one defensible answer (enumerate the readings
  that would make the opposite answer defensible; run a counterfactual for every named
  cause); graders must be linear-time, never crash, and use `details.error` only for
  internal faults; pre-register thresholds before any run; titles and pass rules must
  not reveal the true/false split; confirmation pass rules must never be looser than
  the screening rule.
- **Statistics.** What counts is tasks, not runs: repeats on one task are correlated.
  Zero failures in 9 runs still allows a per-run failure rate near 28% at 95%.
- **Pushing.** Squash unpushed commits into bites first, then
  `CLAUDE_SKIP_SQUASH_GUARD=1 git push`. Squashing here also keeps the early
  per-item score details out of public history; check the net diff for `evals/private`,
  absolute local paths, and per-item keys in `evals/results/scores.jsonl` first.

## 6. Decisions made after seeing the data

Documented in the report; listed here so nobody tunes them silently.

- The 25% materiality threshold (`harness.json` `decision.min_saving_fraction`).
  Without it read-report would have moved to Haiku (19% cheaper, 10x slower) and
  classify would have gone to confirmation for a 4% saving. Treat it as fixed.
- Scan was reclassified from "noticed" to silent-damage after every Sonnet failure was
  a silently dropped list item.
- The synthesis confirmation tasks allowed one missed item while the screening task
  required all; the report compares cells on the strict basis too.
- Cells were added after the plan (`opus@low`, `opus@medium` on more rows, a Sonnet
  `low` plus "think first" variant, `sonnet@medium` and `sonnet@high` on scan, Haiku as
  a weak control).
- `decide`'s raw output was overridden once, on synthesis (it says MOVE_TO Sonnet).

## 7. Where everything is

| What | Where |
|---|---|
| Findings, tables, overrides, follow-up | `evals/results/REPORT-2026-10-06.md` |
| Method, formats, decision bar, known limits | `evals/README.md` |
| Model facts, prices, effort, Claude Code mechanics | `evals/research/2026-10-05-models.md` |
| Sonnet-versus-Opus abstention research | `evals/research/2026-10-06-sonnet-vs-opus-open-book.md` |
| Cells, grids, harness config | `evals/cells.json`, `evals/rows.json`, `evals/harness.json` |
| Every run and score (public, aggregates only) | `evals/results/runs.jsonl`, `scores.jsonl` |
| CLI | `python3 evals/evalkit.py --help` (plan, run, judge, grade, report, decide, selfcheck, manifest, status, sanitize) |
| Real task material, truth, graders, answers | `evals/private/` (gitignored; back it up) |
| Tests | `python3 -m pytest tests -q` (192) |
| Health check | `python3 scripts/check-setup.py` (37 checks) |
| Earlier design record | `AGENTING-PLAN-HANDOFF.md` (executed 2026-08-17, historical) |
