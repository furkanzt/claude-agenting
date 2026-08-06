---
name: workflow-routing
description: Assign a model and effort level to every agent() call before running a Workflow. Load this when authoring or editing a workflow script, when the workflow-routing-guard hook blocks a Workflow call, or when the user asks which model/effort a task should use. Carries the task-type → model/effort table and the confirmation procedure.
---

# Workflow Routing

## Why this exists

Inside a workflow script, `agent(prompt)` with no `opts.model` / `opts.effort`
**inherits the main-loop model and the session effort**. If the session is
Opus 5 at `xhigh`, an agent that only lists files runs on Opus 5 at `xhigh`.

Measured, 2026-08-06: a 16-agent recon workflow burned **4.45M subagent tokens
(~$320 at Opus list rates)** because every `agent()` call omitted both options.
Three of those agents did nothing but count files and read directory listings.

Separately measured on the same machine: **Opus was 44% of API calls but 82% of
cost.** Routing is the single largest cost lever available, and it is two
parameters per call.

## The routing table

Pick by **reasoning demand**, not by how important the task feels.

| Task shape | Model | Effort | Test |
|---|---|---|---|
| List files, count pages, run a script, collect output | `haiku` | `low` | A regex or `ls` could nearly do it |
| Mechanical text cleanup — de-hyphenate, reflow, strip headers | `haiku` | `low` | Output ⊆ input; nothing invented |
| Read code / prose and report what it does | `sonnet` | `medium` | Answer is present in one place |
| Turn prose into rules; classify; judge relevance | `sonnet` | `medium`–`high` | Needs judgment, source states the facts |
| Synthesize across a whole document or many files | `opus` | `xhigh` | Must relate things that are far apart |
| Decide under a "don't guess" constraint (BELİRSİZ) | `opus` | `xhigh` | **Calibration is the product** |
| Adversarial verify / refute a finding | `opus` | `high` | A confident wrong answer is expensive |

Two questions settle almost every case:

1. **Is the answer *present*, or must it be *constructed*?**
   Present in one span → cheap. Assembled from distant or unstated pieces → expensive.
2. **What does a confident wrong answer cost?**
   Noticed immediately → cheap. Silently poisons downstream work → expensive.

Reach for `agentType:` instead of `model:` when a defined agent already fits
(`~/.claude/agents/*.md`) — but still pass `effort:`, because those definitions
pin **both** a model and an effort — reach for `agentType:` when one already fits.

## External (non-Claude) models

Nothing here calls a non-Claude model. The `gemini-*` agents were removed
2026-08-06 (dead auth, silent fallback to Sonnet). Before proposing an external
tier, read `external-model-options.md` in this directory — it has the price
table and the volume threshold below which it isn't worth the maintenance.

## Subagents are a tier mechanism, not just a cost mechanism

The main session runs at **one** model and **one** effort. Subagents are the only
way to use several tiers at once:

```
SESSION: sonnet / medium              ← fast, cheap baseline for the conversation
   ├─ agent(…, {model:'haiku',  effort:'low'})    ← reach DOWN: don't spend sonnet on counting
   └─ agent(…, {model:'opus',   effort:'xhigh'})  ← reach UP: buy Opus only where it earns it
```

This flips the risk depending on where the session sits, and the question you ask
must flip with it:

| Session tier | Real risk | Lead with |
|---|---|---|
| opus / xhigh | over-spending on trivial work | *"drop these to haiku?"* |
| sonnet / medium | **under-powering a hard task** | ***"raise the synthesis step to opus?"*** |

**Never offer only "cheaper."** Always both directions.

## Procedure — run this before calling Workflow

1. **Draft the script** with every `agent()` call routed.
2. **Ask the user via AskUserQuestion.** Show the *task types* and the tiers you
   assigned — not a generic model-preference question. Offer three directions,
   ordered by session posture (see table above):

   > *"3 kinds of work in this workflow. Routing — confirm or change?"*
   > - **As proposed** — 4× scan (haiku/low), 3× analyze (sonnet/medium), 2× synthesize (opus/xhigh)
   > - **Higher quality** — analyze → opus/high (the synthesis is the load-bearing part)
   > - **Cheaper / faster** — analyze → haiku/low

3. **Apply the answer**, record approval with the command the hook printed, and
   re-run. Changing the plan changes its signature, so the gate re-asks — that's
   intended.

Skip step 2 only when the user already stated the routing for this workflow in
the current conversation.

## Single `Agent` calls — judgment, not a gate

`Agent` is **deliberately not hook-gated**. All 20 definitions in
`~/.claude/agents/*.md` pin both `model` and `effort`, so a routed call is
already a chosen tier, and one agent is bounded and cheap. Prompting on every
spawn costs more attention than it saves.

**But ask anyway when the tier and the task genuinely disagree** — this is the
"sometimes" the user asked for, and it is your judgment, not the hook's:

- Calling `scanner` (haiku/low) for something that needs a decision, not a count
- Calling `researcher` (sonnet/medium) for synthesis that really needs opus
- A task where a confident wrong answer would propagate silently
- The session is on a cheap tier and this one call is the hard part of the work

In those cases ask before spawning, and frame it as a tier question:
*"This is really synthesis — want `system-architect` (opus/xhigh) instead of
`researcher` (sonnet/medium)?"*

## Deliberate inheritance

If an agent genuinely should inherit the session model, mark it — the guard
skips it and the intent stays visible in the script:

```javascript
// routing: inherit
await agent("Hardest synthesis step; wants whatever the session is on", { schema: S })
```

## Enforcement — two stages

`~/.claude/hooks/workflow-routing-guard.py` runs as `PreToolUse` on `Workflow`
only. It parses the script and finds `agent()` calls, ignoring any inside
strings and comments.

| Stage | Fires when | What to do |
|---|---|---|
| **1 — rota** | any `agent()` lacks `model`/`agentType`, or lacks `effort` | Add them. Denial names the line numbers. |
| **2 — plan onayı** | all routed, but this plan is unapproved in this session | Ask the user (three directions), apply, then run the `--approve` command the hook prints, then re-run. |

Approval is keyed by **plan signature × session**. Re-running the same plan in
the same session is silent; changing any tier re-asks; a new session re-asks.

Deliberate inheritance is marked per call, not blanket-disabled:

```javascript
// routing: inherit
await agent("wants whatever the session is on", { schema: S })
```

Do not blanket-apply `// routing: inherit` or `--approve` without asking to get
past the gate — that defeats the point of both stages.
