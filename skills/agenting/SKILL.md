---
name: agenting
description: Assign a model and effort level to every agent() call before running a Workflow, decide how much of that gets asked vs. decided for you, and verify what actually happened once it returns. Load this when authoring or editing a workflow script, when the workflow-routing-guard hook blocks a Workflow call, when the user asks which model/effort a task should use, when the session mode changes (manual/semi-auto/auto, via /agenting-mode or natural language), when a task looks workflow-shaped and might be worth suggesting, when reading or writing a project's agenting/AGENTING.md or agenting/log.csv, or whenever any Workflow tool call returns a result — routing, memory and verification are ends of the same responsibility. Carries the task-type → model/effort table, the confirmation procedure, the session mode and suggestion axes, the per-project precedent system, and the mandatory post-completion failure check.
---

# Agenting

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
4. **Append a row to `agenting/log.csv`**, if this project has an `agenting/`
   folder (skip silently if it doesn't — the routing still applies, there is
   just nowhere to record it). One row per resolved plan: `timestamp` now,
   `source` = `user` (answered via AskUserQuestion) / `semi-auto` / `auto`
   (self-answered under those modes — see the session mode axis below),
   `shape_key` built from every `agent()` call's `label`/`phase`, `plan_signature`
   = the tier-count signature the hook already printed, `answer` = the resolved
   tier map. Then check whether that `shape_key` now has ≥ `promotion-threshold`
   consistent `user`-sourced rows — if so, promote or refresh its line in
   `AGENTING.md`'s Learned Precedents (see "Precedent mechanics" below; this is
   the step that actually populates it — without it the memory axis never
   accumulates anything to promote).

Skip step 2 only when the user already stated the routing for this workflow in
the current conversation, or when the session mode below makes the answer yours
to give.

## Session mode — manual / semi-auto / auto

There is a second axis besides the tier table: **how much of step 2 above the
user answers, and how much you answer for them.**

The mode lives in **conversational memory only**. Nothing is written to disk, no
hook reads it, and it **resets to `manual` at the start of every new session** —
an "auto" granted yesterday does not carry into today.

| Mode | What happens at Stage 2 |
|---|---|
| `manual` *(default)* | Always ask via AskUserQuestion. Precedent shapes the **proposed default**, it never replaces the question. |
| `semi-auto` | Auto-answer only workflow shapes that match an **established precedent**. Anything novel → ask. |
| `auto` | Never ask. Decide the plan yourself from the routing table above plus this project's `agenting/AGENTING.md`, then self-record the approval. |

Set it two ways, both equivalent:

- **Natural language** — "switch to auto", "stop asking, semi-auto is fine",
  "back to manual for this one".
- **`/agenting-mode [manual|semi-auto|auto]`** — with no argument it reports the
  current mode and the suggestion-axis setting below.

**Auto does not bypass the hook.** No hook changed for this. The `PreToolUse`
gate still fires Stage 2 exactly as before; what changes is *who answers it*. In
`auto` you make the call, then run the `--approve` command the hook printed
yourself instead of handing the question to the user. Stage 1 is never
auto-answerable — an `agent()` with no `model`/`effort` at all is a defect in the
script, not a preference to be resolved.

Like the post-completion check below, this axis is **instruction-layer**: it is
carried by this file, not enforced by anything. Nothing stops you from asking in
`auto` or silently deciding in `manual` except reading this.

## The suggestion axis

Independent of mode, and tracked as its own session flag — also reset every
session.

The first time in a session that a task looks workflow-shaped, ask **once**:

> *"This task is suitable for a workflow — want suggestions like this for the
> rest of the session?"*

**Yes** → later suitable tasks get suggested without re-asking, for this session
only. **No** → drop it for the rest of the session.

A project with an `agenting/AGENTING.md` is **suggestion-eligible**. Eligibility
does not skip the ask — the per-session question still gates it each session.
The `suggestion-default` knob overrides the ask entirely (`on` / `off`).

The two axes are orthogonal. `auto` does not mean "suggest workflows", and
suggestions-on does not mean "decide the routing without asking."

## Per-project memory — the `agenting/` folder

Two files at the project root, split deliberately by **how they are read**:

| File | Read | Content |
|---|---|---|
| `agenting/AGENTING.md` | **In full**, at the start of any session that might run a Workflow | Curated rules, config knobs, promoted precedents |
| `agenting/log.csv` | **Never in full** — grepped by exact `shape_key` | Raw, append-only, one row per resolved routing decision |

That split is the point: the curated file stays small enough to always read, so
the log is free to grow without ever costing context.

### `AGENTING.md` — three sections

Shipped as `templates/AGENTING.md` in this plugin. Its structure is fixed:

1. **Rules & Edge Cases** — hand-curated prose. **Claude never auto-writes
   here.** The user edits it, or states the rule in conversation and asks for it
   to be recorded. E.g. *"always route the synthesis step to opus/xhigh in this
   project, even in auto mode."*
2. **Config** — structured `key: value` knobs, one per line. Unset keys use the
   plugin default.
3. **Learned Precedents** — auto-promoted one-liners, deduplicated, one per
   established task shape:
   `` - `shape_key` → `answer`  (n user-sourced occurrences, last YYYY-MM-DD) ``

### Config knobs

| Knob | Default | Meaning |
|---|---|---|
| `promotion-threshold` | `2` | Consistent **user-sourced** answers needed before a shape is promoted to a Learned Precedent |
| `suggestion-default` | `ask` | `ask` (once per session) / `on` (suggest without asking) / `off` (never suggest) |
| `matching-strictness` | `exact` | Only `exact` is implemented in 2.0.0. Any other value **prints a warning and falls back to `exact`** — it must not silently no-op |

### `log.csv` — schema

Shipped as `templates/log.csv` (header only). Five columns:

| Column | What it holds |
|---|---|
| `timestamp` | when the decision was resolved |
| `source` | `user` / `semi-auto` / `auto` — who answered |
| `shape_key` | **the question**: task-type composition only, e.g. `scan:x4\|analyze:x3\|synthesize:x2`, built from each `agent()` call's label/phase. **No tier information.** |
| `plan_signature` | the hook's existing tier-count signature (`haiku/lowx4\|opus/xhighx2\|…`), kept untouched for cross-reference only |
| `answer` | **the answer**: the resolved tier map, e.g. `scan=haiku/low;analyze=sonnet/medium` |

Comma is the column delimiter — use `|` and `;` inside fields, **never** commas.

**Why `shape_key` carries no tiers.** The obvious design keys precedents on the
whole plan, tiers included. It was caught in design review before it shipped,
and it is worth stating what it would have done: if the key contains the tiers,
the key contains the answer. The same task shape routed two different ways
produces two *different* keys, each holding one answer and each therefore
trivially self-consistent. Conflicting answers become structurally
undetectable, the `promotion-threshold` consistency test can never fail, and
every guess promotes itself as precedent. Splitting the key (the question) from
the `answer` column is the only arrangement in which "is this consistent?" is a
question that can come back *no*.

**Only `source: user` rows vote** toward the promotion threshold. `semi-auto`
and `auto` rows stay in the log as an audit trail, but they don't count — for
the same reason: otherwise the system launders its own guesses into precedent
and the threshold measures nothing but its own repetition.

### Log & git

`agenting/log.csv` is **committed to git by default**. It is gitignored only if
the user says so — asked **once**, at scaffold-creation time, the first time the
CSV is created in a project. `agenting/AGENTING.md` is always committed and is
not part of that question.

### Precedent mechanics

- **Match is exact**, on `shape_key`. Grep the log for that key; never read the
  whole file.
- **Promotion:** ≥ `promotion-threshold` (default 2) consistent, `user`-sourced
  answers for a shape → promote it to Learned Precedents in `AGENTING.md`.
  `semi-auto` and `auto` then apply it without asking.
- **A single occurrence already counts** — from the 1st, it soft-biases the "as
  proposed" default shown in `manual`, and in `semi-auto` when the shape is
  novel. It just doesn't auto-apply.
- **Conflicting answers for the same `shape_key` are not consistent** → ask
  again; the newest answer becomes the latest data point.
- **Correction is conversational.** "Forget that precedent" / "that was wrong,
  redo as X" → edit the `AGENTING.md` entry and the underlying `log.csv` rows
  directly. There is no dedicated command for this.

### Scaffold creation — one atomic beat

The first time this plugin is used in a project, do all four in one go, not
spread over turns:

1. **Ask the git-tracking question** (commit `log.csv`, or gitignore it).
2. **Write `agenting/AGENTING.md`** from `templates/AGENTING.md`, with the
   Config block filled in — including that answer.
3. **Write `agenting/log.csv`** from `templates/log.csv` (header only).
4. **Append a `.gitignore` entry** if "gitignore" was chosen.

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

## After a Workflow returns — verify before reporting done

This is the other half of routing responsibly: choosing the tier is only useful
if you then check the tier actually finished the work. **Do this on every
Workflow completion, unprompted** — not only when the user asks "did the
agents finish?" A tool result that looks like a clean summary can be sitting on
top of a run that lost most of its agents.

**Why this is a standing rule, not a one-off:** on 2026-08-06/07, three
workflows each reported a coherent-looking `ozet` (summary) after completing —
but the summaries were built by `.filter(Boolean)` over whatever *did* return,
silently dropping everything that didn't. One run's headline numbers ("6
DÜZELTİLECEK, 12 EDİTÖRE SORULACAK") looked like a finished audit. It was
built from 38 of 122 agents; the other 84 died mid-run and are invisible in
that summary unless you go look. The failure was caught only because the user
asked directly — this section exists so that stops being necessary.

### The check, every time

1. **Read the tool result's own `<usage>` and `<failures>` blocks first.**
   `agents_done` vs `agent_count` is the headline number — if they don't
   match, the `result`/`ozet` was built from a subset, not from what was
   asked for. A `<failures>` list with real entries means agents errored; an
   empty summary and a full `<failures>` list is not a contradiction, it's
   the norm.
2. **Don't stop at the summary the workflow computed.** It was written by the
   same script whose agents just died — it does not know what it's missing.
   Cross-check against the raw journal:
   `<transcriptDir>/journal.jsonl` — one `{"type":"started",...}` and one
   `{"type":"result",...}` per agent, keyed by `agentId`. `started - result`
   is what's actually missing, independent of anything the script's return
   value claims.
3. **For anything in `started - result`, find out why before assuming it
   simply hasn't run yet.** Read the tail of `agent-<id>.jsonl` in the same
   transcript dir:
   - Last few records are recent (seconds old) → still genuinely running,
     not a failure. Check `agent-*.jsonl` mtimes against `now` to tell a live
     agent from an abandoned one — a large concurrency queue (workflows cap
     at `min(16, cores-2)`, as low as 6 on an 8-core machine) can leave
     most of a batch legitimately queued, which looks identical to "stuck"
     until you check timestamps.
   - Last record is old and the agent never produced a result → read what
     it was doing right before it stopped. A synthetic `stop_reason` with a
     zero-token message right after the agent said something like "submitting
     findings" is a session-limit kill, not a bug in the agent's work — the
     work was likely done, only the return trip was lost.
   - An explicit `is_error` record → read the actual error message before
     guessing; "permission" false positives are common (a skill description
     in the system prompt containing the word "permission" is not a denial).
4. **If real work was lost, don't just retry with the identical prompt.**
   Diagnose why first — a batch that died from oversized per-agent context
   needs smaller scope on retry, not a rerun of the same call. Prefer
   recovering only the specific missing pieces (by finding, by page range,
   by severity) over re-running the whole workflow from scratch.
5. **Report the real count to the user before either of you acts on the
   result.** "X of Y agents completed; here's what's missing and why" — not
   the workflow's own possibly-partial summary presented as if it were final.

### Scope of this rule vs. its enforcement

This section is a **skill**, which means it only helps if it gets reloaded at
the right moment — unlike the `PreToolUse` gate in `hooks/`, nothing forces a
re-read of this file when a `Workflow` call returns. Treat "check the
workflow that just finished" as owed on every completion the same way "route
every `agent()` call" is owed on every launch, even though only the second one
is backed by a hook that can refuse to proceed. If this keeps getting skipped
in practice, the more durable fix is a `PostToolUse` hook on `Workflow` that
surfaces `agents_done < agent_count` the same way `workflow-routing-guard.py`
surfaces missing routing — ask before adding one, since that changes the
plugin's enforcement surface rather than just its guidance.

## Deliberate inheritance

If an agent genuinely should inherit the session model, mark it — the guard
skips it and the intent stays visible in the script:

```javascript
// routing: inherit
await agent("Hardest synthesis step; wants whatever the session is on", { schema: S })
```

## Verified facts (2026-08-10)

Measured from three weeks of transcripts (dedup method below). These numbers
back the routing table and the enforcement above — cite them, don't re-derive
them.

- **Dedup method:** in transcript JSONL, a line is NOT one API call — take the
  LAST line per `message.id` (duplication factor: main session 2.06x, agents
  2.42x).
- Total shadow cost **$2.439** (main $992 / agents $1,447) at list price; under
  a subscription this is a consumption indicator, not a bill.
- Main session: 4,917 calls, avg context **407k**, ~74% of cost is cache-read.
- Agents: 17,454 calls, ~1,700 agents, avg context **60k**, $0.083/call.
- **Spawn tax** (first call's cache-write): median 17k ≈ **$0.11**; three-week
  total ~$190. Delegation break-even: **~2-3 turns**. Rule: an agent pays for
  itself by keeping context OUT of the main session — don't open an agent for
  1-2 calls of legwork.
- **Cache key includes model+effort:** a mid-session switch rewrites the whole
  prefix (measured; see `cache-tripwire.py`'s docstring for the exact numbers).
  Claude Code now shows a confirmation dialog for effort changes; model changes
  are silent.
- Under subscription, the main session gets a 1-hour cache TTL; **on overage
  it silently drops to 5 minutes** (`ENABLE_PROMPT_CACHING_1H` env var prevents
  this). A subagent always starts cold with its own cache, 5-minute TTL.
- Same-type agent fan-out opened SIMULTANEOUSLY is all cold; staggered by a
  few seconds, later ones ride the first one's system-prompt cache.
- Effort distribution (cut at this skill's birth, 2026-08-06T22:31): subagent
  `max` 57% -> **1%**, `high` 15% -> **57%**. ADR 0009 is working.
- Limits: the **Opus limit was never hit** (every matching mention in the
  transcripts is this session's own quotes of it); the binding constraint is
  the shared session limit — one incident, 2026-08-06 13:54 (pre-skill
  fan-out). Switching models does not restore the shared limit.
- Sonnet's input price is cheaper than Opus's by 2.5x until 2026-08-31, then
  1.67x.
- Vector DB decision: **NO** for audit work (comprehensiveness can't be
  established via similarity search, and the bill is already re-read-weighted);
  for kazanım (learning-outcome) mapping, a ready ~100-200 record JSON table is
  enough.

## Enforcement — two stages

The agenting plugin's `workflow-routing-guard.py` hook (installed by the plugin
itself, registered in its own `hooks/hooks.json`) runs as `PreToolUse` on
`Workflow` only. It parses the script and finds `agent()` calls, ignoring any inside
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
