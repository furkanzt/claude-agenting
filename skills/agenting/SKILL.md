---
name: agenting
description: Use when writing or editing a Workflow script, choosing a model or effort for an agent() or Agent call, when the user switches agenting mode (auto/manual) or disposition (fast/balanced/quality) or opts in to workflows for this chat, or when a project has agenting/AGENTING.md. Routing table and launch procedure.
---

# Agenting

An `agent()` call with no `model`/`effort` inherits the main session's tier:
wasted spend when the session is expensive, an under-powered agent when it is
cheap. Subagents are the only way one session runs several tiers at once, so
route every call by the reasoning it needs, and look in both directions.

## Routing table

Pick by reasoning demand, not by how important the task feels.

| Task shape | Model | Effort | Test |
|---|---|---|---|
| List files, count pages, run a script, collect output | `haiku` | `low` | A regex or `ls` could nearly do it |
| Mechanical text cleanup: de-hyphenate, reflow, strip headers | `sonnet` | `low` | Output ⊆ input; nothing invented |
| Read code / prose and report what it does | `sonnet` | `medium` | Answer is present in one place |
| Turn prose into rules; classify; judge relevance | `sonnet` | `medium`–`high` | Needs judgment, source states the facts |
| Synthesize across a whole document or many files | `opus` | `xhigh` | Must relate things that are far apart |
| Decide under a "don't guess" constraint (BELİRSİZ) | `sonnet` | `xhigh` | **Calibration is the product** |
| Adversarial verify / refute a finding | `sonnet` | `high` | A confident wrong answer is expensive |

**How these cells were checked (2026-10-06).** [`evals/`](../../evals/README.md)
ran every cell of each row on real tasks, three repeats, comparing measured cost
per run. Three rows changed:

- **Mechanical cleanup, `haiku/low` → `sonnet/low`.** Haiku failed all three runs
  (it left the page headers in); Sonnet at `low` passed all three.
- **Don't-guess (BELİRSİZ) and adversarial verify, `opus` → `sonnet`.** Sonnet
  `xhigh` hallucinated on none of 102 unanswerable items, as Opus `xhigh` did
  (Haiku: 19); Sonnet `high` gave no wrong verdict in 96, as Opus `high` did.
  Both rates are bounded below about 3% (95% confidence) and Sonnet cost about
  half as much. A deep-research pass found no published open-book comparison of
  the two models and showed that the closed-book gap in the vendor cards is
  knowledge, not abstention discipline
  ([`evals/research/2026-10-06-sonnet-vs-opus-open-book.md`](../../evals/research/2026-10-06-sonnet-vs-opus-open-book.md)).
  This is a bounded null: it cannot exclude a gap of a few points, so the
  `quality` disposition keeps Opus on these rows.
- **Kept: scan, read-report, classify, synthesize.** Synthesis stays on Opus
  `xhigh` because there Sonnet does not do the same thing: Opus `xhigh` found every
  planted item in all 9 runs, Sonnet `xhigh` missed the same subtle one in 3 of 3
  on one task and reported fewer genuine extra issues. For scan, read-report and
  classify no cheaper cell cleared the plugin's evidence rules (pass every run and
  save at least 25%).
- **`haiku/low` is just `haiku`:** it ignores `effort` and thinks heavily by
  default, so on the scan task it was the costliest cell ($0.17 a run; `sonnet/high`
  also passed 3 of 3 for $0.05 but has no second-round task yet). Anthropic lists
  Haiku 4.5 for retirement no earlier than 2026-10-15; re-test scan when that moves.
- **Disposition.** `quality` keeps Opus on rows 5 to 7; `fast` uses Opus `high` for
  synthesis. See [reference/modes.md](reference/modes.md).
- **Limits.** Nine runs per cell per high-stakes row, and 102 abstention items per
  model, show large gaps, not gaps of a few points. A harder paired test (near-miss
  unanswerable items, long documents) could still find one; the harness is ready
  for it. The scan row was tested without Bash. The architecture, security, incident
  and orchestration agents were not measured and keep their pins. Method, every
  number and the places where the harness's raw output was overridden:
  `evals/results/REPORT-2026-10-06.md`.

Two questions settle almost every case:

1. **Is the answer *present*, or must it be *constructed*?** Present in one
   span → cheap. Assembled from distant or unstated pieces → expensive.
2. **What does a confident wrong answer cost?** Noticed immediately → cheap.
   Silently poisons downstream work → expensive.

When one of this plugin's agents fits, route by agent:
`{agentType: 'agenting:<name>', effort: '<its effort>'}`. The `agenting:`
prefix is part of the name, and the guard wants `effort` alongside it.

| Tier | Agents (`agenting:<name>`) |
|---|---|
| `haiku`/`low` | `scanner` |
| `sonnet`/`low` | `coder`, `tech-writer`, `git-specialist`, `text-mechanic` |
| `sonnet`/`medium` | `researcher`, `frontend-dev`, `cicd-engineer`, `performance-engineer`, `tester-tdd` |
| `sonnet`/`high` | `coder-ts`, `database-architect`, `ml-developer`, `refactoring-specialist` |
| `opus`/`high` | `coordinator`, `swarm-coordinator` |
| `opus`/`xhigh` | `reviewer`, `security-architect`, `system-architect`, `incident-responder` |

Every tier here is a Claude model. Before proposing a non-Claude one, read
[external-model-options.md](external-model-options.md).

## Procedure: before calling Workflow

1. **Project rules.** If the project root has `agenting/AGENTING.md`, follow
   [reference/project-rules.md](reference/project-rules.md) before drafting.
2. **Draft** the script. Done when every `agent()` call has `model` or
   `agentType`, and `effort`, or is marked `// routing: inherit` (below).
3. **Resolve by mode.** The session's `[agenting]` line from SessionStart names
   the mode; `--status` on the recorder it names gives ground truth.
   - **auto** (default): decide the plan yourself, without asking. Start from
     the table, apply the session's disposition (under `balanced` the table
     *is* the baseline; for `fast` or `quality` see
     [reference/modes.md](reference/modes.md)), then the project's Rules.
     Run the Workflow; the guard lets it through with a note.
   - **manual**: put the plan to the user with AskUserQuestion, naming the
     task types and the tiers you assigned, in three directions. Lead with the
     direction that fits the session's tier: on `sonnet`/`medium` the risk is
     under-powering, so lead with the upgrade; on `opus`/`xhigh` the risk is
     over-spending, so lead with the downgrade. Always offer both.

     > *"3 kinds of work in this workflow. Routing: confirm or change?"*
     > - **As proposed**: 4× scan (haiku/low), 3× analyze (sonnet/medium), 2× synthesize (opus/xhigh)
     > - **Higher quality**: analyze → opus/high (the synthesis is the load-bearing part)
     > - **Cheaper / faster**: analyze → haiku/low

     Apply the answer, run the `--approve` command the guard printed, and
     re-run. When the user already stated this workflow's routing earlier in
     the conversation, apply that instead of asking.
4. Done when the Workflow is running with every call routed, and in manual
   mode with the plan the user chose.

**What the guard denies.** `workflow-routing-guard.py` runs before every
Workflow. Stage 1, in every mode: an `agent()` call missing `model`/`agentType`
or `effort`, reported by line number; fix the script. Stage 2, in manual mode
or when no mode is recorded: a routed plan not yet approved in this session;
ask, apply, run its `--approve` command. Changing any tier asks again. In auto
mode Stage 2 steps aside with a system message.

## Deliberate inheritance

When one agent genuinely should take the session's tier, mark that call. The
guard skips it and the intent stays visible in the script:

```javascript
// routing: inherit
await agent("Hardest synthesis step; wants whatever the session is on", { schema: S })
```

Mark calls one at a time. Ask the user before marking several: blanket
inheritance switches Stage 1 off.

## Single Agent calls: judgment, not a gate

The `Agent` tool is not gated: every `agenting:` agent pins its model and
effort, and one agent is bounded. Spawn it as `subagent_type: "agenting:<name>"`.
Ask before spawning when the tier and the task disagree:

- `agenting:scanner` (haiku/low) for something that needs a decision, not a count
- `agenting:researcher` (sonnet/medium) for synthesis that needs opus
- a task where a confident wrong answer would propagate silently
- the session is on a cheap tier and this call is the hard part of the work

Frame it as a tier question: *"This is really synthesis. Want
`agenting:system-architect` (opus/xhigh) instead of `agenting:researcher`
(sonnet/medium)?"*

## Session settings

Three values carried per session by the SessionStart hook: mode
(`auto`|`manual`), disposition (`fast`|`balanced`|`quality`) and the workflows
opt-in (`on`|`off`). When the user changes any of them, in words or with
`/agenting-mode`, read [reference/modes.md](reference/modes.md) and record the
change before replying.

## When the finish check fires

The `workflow-finish-check.py` hook reads every finished Workflow's
`journal.jsonl` and stays silent when all agents returned. When some did not,
the prompt carries `[agenting] Workflow "<name>": R of N agents returned;
missing: …`. The workflow's result was computed without those agents, so:

1. **Hold the result.** Present nothing from it as final yet.
2. **Find the cause of each gap.** Read the last records of
   `agent-<agentId>.jsonl` beside the journal (the agentId is on the missing
   agent's `started` line):
   - a synthetic zero-token stop right after the agent said it was submitting:
     a session-limit kill; the work was likely done and only the return lost
   - `[Request interrupted by user]`: the run was interrupted
   - an `is_error` record: read the error itself before guessing ("permission"
     inside a skill description is not a denial)
3. **Recover only the missing pieces**, fixing the cause first: a batch that
   died of oversized context needs a smaller scope, not the same prompt again.
   `resumeFromRunId` (printed in the notification) replays agents whose prompt
   and opts are unchanged.
4. **Report** "R of N agents completed; missing: … because …".

Done when the user has the real count and a cause for every missing agent,
before either of you acts on the result.
