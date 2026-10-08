# Handoff: what is left after agenting 3.2.0

Written 2026-10-06, right after `1362672` (the 3.1.0 release) was pushed to
`origin/main`. Nothing is in flight: no background runs, no pending workflows, a
clean working tree. This file lists only what is **not done**. For what was done and
why, read `evals/results/REPORT-2026-10-06.md` first, then `CHANGELOG.md` (3.1.0).

**Updated 2026-10-07 for 3.2.0.** The cost meter was fixed (a dated per-model price
table, advisor spend, 5-minute versus 1-hour writes), `scripts/measure-tokenomics.py
anatomy` was added, the README's cache claims were corrected, and fan-out guidance
was written (`skills/agenting/reference/fan-outs.md`). 3.2.0 is committed locally and
**not pushed**. Section 3G is new: the launch-cost experiments and the clean-run
evidence that waits on them. Sections 3A and 3F changed in place, and the old 3G
(external evidence) is now 3H.

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
   machine runs whatever version it last updated to (3.1.0 on 2026-10-07; check the
   SessionStart `[agenting]` line or the plugin cache folder) until you run
   `/plugin marketplace update agenting` and then
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
6. Add the model's row to `PRICES` in `scripts/measure-tokenomics.py` (exact model id,
   dated; `tests/test_tokenomics.py` checks the input prices against
   `hooks/cache-tripwire.py`, which needs the same row).
7. Write the dated findings to `evals/results/REPORT-<date>.md`, change the table in
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
- **Whether a Workflow `agent()` honours `effort`**: observed, not settled. It is not
  confirmed in Claude Code's docs, and a Workflow subagent cannot report its own
  effort. External evidence, one task and four agents (one per level): thinking tokens
  rose with the pinned effort (about 0.4k low, 1.4k medium, 1.8k high, 4.0-4.4k xhigh).
  Local transcripts show the same ordering at xhigh (median about 4.9k on Opus 5.5)
  but a much lower `high` (a few hundred tokens) on partial coverage (thinking counts
  on about a third of calls) and different tasks: unreconciled. The harness avoids the
  question by using `claude -p --effort`; the plugin's guard assumes the option works.
- **Cache behaviour on an effort switch** for subagents and Workflow requests
  (`hooks/cache-tripwire.py` measures it).

### G. Launch cost: two experiments, a conditional agent, and the clean-run evidence

What 3.2.0 settled and what it did not. The meter now exists (`measure-tokenomics.py
anatomy`); everything below needs it.

**E2 ran on 2026-10-07/08 (on list price; the window could not be measured on a shared account): clean runs -63% with no quality loss, so the shared clean-run core is due; the lean worker saved 19% on the full pipeline, below the 25% bar, so `agenting:worker` is not shipped.** Details in `evals/research/2026-10-07-launch-cost.md`.

**E1 ran on 2026-10-07: pilot positive** (restricted-tools agent -63% per agent, `general-purpose` no saving, model override honoured, byte-identical prompts write nothing fresh); results and the pre-registered E2 design are in `evals/research/2026-10-07-launch-cost.md`. The original E1 design follows for reference.

**E1, a controlled launch-cost test (about $2-3 list).** Question: do
typed agents (the plugin's all restrict their tools) start much smaller than generic
`agent()` calls, and is the cause the type or the restricted tool list? Local
transcripts say about 15k tokens of first-call context for typed agents without a
skill listing against 36-45k for generic ones (typed agents that carry a listing
start near 37k), but the groups differ in task, session and tools. Design: one throwaway
Workflow in a chat where the owner has opted in to workflows (Claude does not propose
running it). Arms of five agents each, interleaved, one trivial task, one schema, one
deterministic output check: generic `agent({model, effort})`; `agenting:researcher`
(restricted tools, pinned sonnet/medium); a `general-purpose` agent (typed, all tools)
to separate "typed" from "tools restricted"; and the generic arm again with
byte-identical prompts. Report the first agent of each arm separately from the rest.
Side probe: does `message.model` honour an explicit model given with an `agentType`?
Pre-registered rule: the restricted-tools arm shows at least 15k less first-call
context, at least 25% lower total list cost per agent, and an equal pass rate. A pass
means "pilot positive": replicate it once, or run it on one real fan-out shape, before
changing any guidance or adding an agent. State in `evals/README.md` that this measures
launch cost and sits outside the routing-cell bar. Check that `message.model` equals
the routed full id in every arm.

**Open, to deal with in detail later (owner, 2026-10-08): the experimental `~/.claude/agents/lean-worker.md`** (tools Read, three-line neutral body, pinned sonnet/medium; created for E2). It is kept for now. It missed the 25% bar on the full pipeline (-19%) but saved 32% on a short, tool-free step. Decide whether it stays user-level, moves into the plugin for short steps only, or goes.

**A lean worker agent, only if E1 passes twice and the owner approves.**
`agents/worker.md`: tools Read (optionally Grep, Glob), a three-line neutral body,
model and effort pinned like the other 20. One worker if the model override holds,
otherwise one per tier. Update every hard-coded "20 agents" (`plugin.json`, the
marketplace entry, README, `scripts/check-setup.py`) and the tier table in `SKILL.md`.

**E2, the usage-window effect (about $35-40 list; owner's call, recommended: later, on
real recurring work).** The clean-run results below are list-price figures. One rough
reading on the owner's 5-hour window was about 0.6 points per list-dollar for clean
runs against about 0.24 for Workflow agents, confounded by the main session's own use;
taken at face value, per-task window use would be about equal. Protocol: arm W
(Workflow agents) against arm R (sequential `claude -p` clean runs with the rules
verbatim in `--system-prompt`), same tasks, model and effort, A-B-B-A blocks of about
$8-10 list each, the owner reading the window percentage by hand before and after each
block with the main session idle. Step 0 costs nothing: check how finely the readout
resolves and how noisy it is, and size the blocks to match. Claude never reads, asks
about or tracks the window; nothing in the plugin does.

**Clean `claude -p` runs: the evidence, kept here until E2 reports** (one external
pipeline, Opus 5.5 at xhigh, list price, small samples, quality judged by proxies and
no blind judge run). Step A: $1.16 against $0.72 per task for the Workflow agent and
the clean run (-38%, n=6 against 12); step B: $0.52 against $0.23 (-55%, n=24 each).
With the rule files verbatim in `--system-prompt` (a stable cached prefix): step A
$0.66 cold or $0.48 warm, step B $0.19. A cold, simultaneous first wave saved only about
6%; runs have to follow each other to share the cached prefix. One run in the Workflow
arm emitted only 530 output tokens and stays in the mean. Do not quote the single
cache-warmth pair ($0.54 against $0.16) or the single end-to-end task as general
figures.

**Invariants for any clean runner** (lessons from the one built on this evidence):
the answering model must equal the routed full model id (`modelUsage`), so alias drift
invalidates a run; unknown cost is charged at the per-run cap, never zero; `--max-usd`
stops only new launches, so the worst-case overshoot is jobs times the per-run cap;
one exclusive lock; atomic writes; the resume key includes a validator version (or
resume re-validates); the whole process group is killed on timeout and Ctrl-C and
nothing new launches after it; the usage gate fails closed; old and new prompts are
rendered and diffed before trusting a prompt migration (a rule pointer was lost
once); and a process-group test needs its own helper timeout, or a regression shows
up as a hung suite instead of a failure.

**Deferred: a shared clean-run core** (`scripts/cleanrun.py`: `Stop`, `kill_group`,
`build_cmd`, `call_claude`, `parse_call`, `Budget`, `exclusive_lock`, atomic writes,
`run_pool`, imported by `evalkit.py` and vendored by project runners, with tests on
`tests/fixtures/fake_claude.py`). About 600 lines and no cost effect on its own, and it
touches `evalkit.py`'s 192-test surface. Build it when E2 favours clean runs (or the
owner accepts a list-price-only benefit) and a recurring fan-out of about 20 or more
context-free, code-validatable tasks exists, or a second runner would otherwise copy
the kill, lock and budget code. A validator version in `evalkit.py`'s resume key and
refusing a spawn after `kill_all` (section 4) belong with it.

**Meter caveats.** Advisor and thinking figures are floors: `usage.iterations` and
thinking counts are present on about a third of calls. Three price rows are partly
derived (`claude-opus-5` and `claude-fable-5` writes, `claude-sonnet-5` cache reads);
`claude-opus-4-8` is unpriced. Transcript field names are undocumented; run
`anatomy` by hand after a Claude Code update before trusting a new number.

### H. External evidence to watch

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
| Cost meter | `python3 scripts/measure-tokenomics.py` (overview) and `python3 scripts/measure-tokenomics.py anatomy` (launch cost); prices in `PRICES`, dated `PRICES_AS_OF` |
| Fan-out guidance | `skills/agenting/reference/fan-outs.md` |
| Tests | `python3 -m pytest tests -q` (253) |
| Health check | `python3 scripts/check-setup.py` (37 checks) |
| Earlier design record | `AGENTING-PLAN-HANDOFF.md` (executed 2026-08-17, historical) |
