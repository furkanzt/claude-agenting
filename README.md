# agenting

**Subagents let one session use several model tiers at once. This plugin makes that deliberate.**

A `PreToolUse` gate refuses to run a Workflow until every `agent()` call carries an explicit `model` and `effort`, then asks you to approve the routing plan — offering *cheaper* **and** *higher quality*, not just cheaper.

---

## The problem

Inside a workflow script, `agent(prompt)` with no `opts.model` / `opts.effort` **inherits the main-loop model and the session effort**. Nothing warns you.

Measured on one machine, 2026-08-06: a 16-agent research workflow burned **4.45M subagent tokens (~$320 at Opus list rates)** because every `agent()` call omitted both options. Three of those agents did nothing but count files.

On the same machine, across ~45k API calls: **Opus was 44% of calls but 82% of cost.**

## The insight that shapes the design

Your main session runs at **one** model and **one** effort. Subagents are the only way to use several at once:

```
SESSION: sonnet / medium          ← fast, cheap baseline for the conversation
   ├─ agent(…, {model:'haiku',  effort:'low'})    ← reach DOWN: don't spend sonnet on counting
   └─ agent(…, {model:'opus',   effort:'xhigh'})  ← reach UP: buy Opus only where it earns it
```

So this is **not** a cost-cutting tool. Which direction is risky depends on where your session sits:

| Session tier | Real risk | The gate leads with |
|---|---|---|
| opus / xhigh | over-spending on trivial work | *"drop these to haiku?"* |
| sonnet / medium | **under-powering a hard task** | ***"raise the synthesis step to opus?"*** |

The gate **never offers only "cheaper."**

## What it does

**Stage 1 — routing.** Any `agent()` call missing `model`/`agentType` or missing `effort` blocks the Workflow, naming the offending line numbers.

**Stage 2 — plan approval.** Even when everything is routed, the Workflow blocks until you approve *this particular routing plan* in *this session*. Approval is keyed by plan signature: re-running the same plan is silent, changing any tier asks again, a new session asks again.

Single `Agent` calls are **deliberately not gated** — one agent is bounded and cheap, and every shipped definition already pins both fields. Gating those costs more attention than it saves.

```
STAGE 2/2 — PLAN APPROVAL: 9 agents, all routed. Waiting on the user.

      4 agent(s)   haiku            effort: low
      3 agent(s)   sonnet           effort: medium
      2 agent(s)   opus             effort: xhigh

9 agents total.  Plan signature: haiku/lowx4|opus/xhighx2|sonnet/mediumx3
```

## Modes and routing memory

Answering the same Stage-2 question the same way forever is its own kind of
waste. Three independent switches decide how much you get asked.

**The mode axis** controls Stage 2. As of 2.1.0 it defaults to **`auto`** (was
`manual`), and it's carried by a `SessionStart` hook
(`hooks/session-continuity.py`) rather than conversational memory — it's keyed
on `session_id`, which stays stable across compaction of the same conversation
(verified empirically) and is assumed stable across resume too (by Claude
Code's own design, not independently checked here), so the mode survives
instead of silently reverting the moment a compaction summary doesn't happen
to mention it. A genuinely new conversation (or `/clear`) gets a fresh id and
starts back at `auto`. Set it in plain language, or with `/agenting-mode`,
which takes any mix of a mode token (`manual`/`semi-auto`/`auto`), a
disposition token (`fast`/`balanced`/`quality`), and a suggestion token
(`on`/`off`), space-separated in any order — e.g. `/agenting-mode manual
fast` sets both at once. No argument reports all three, read from the
recorded state, not recalled.

| Mode | Stage 2 behavior |
|---|---|
| `auto` *(default, 2.1.0+)* | Never asks about the plan. Decides from the tier table, this session's disposition (below), and this project's `agenting/AGENTING.md`; the enforcement gate itself then drops its approval requirement — no `--approve` round-trip at all. |
| `semi-auto` | Auto-answers only shapes matching an established precedent; asks for anything novel (still needs `--approve`, like `manual`). |
| `manual` | Always asks. The proposed default is shaped by precedent from the **1st** occurrence onward. |

**The `auto`-mode gate change is new in 2.1.0.** Before, `auto` only changed
*who* answered Stage 2 — Claude still had to run the hook's `--approve`
command manually after deciding. Now `workflow-routing-guard.py` reads the
recorded mode directly and, when it's explicitly `auto`, prints a plain
`systemMessage` note instead of denying — **it never sets
`permissionDecision: "allow"`**, because that would override your own Claude
Code permission settings for the `Workflow` tool itself (an allowlist, a
non-default permission mode, etc.), which isn't this plugin's decision to
make. The `--approve` round-trip disappears; whatever your own permission
settings would otherwise do about running `Workflow` at all is untouched
either way. A session with **no** recorded mode does *not* get this — only an
explicit `auto` does, so an install where the continuity hook isn't wired up
keeps requiring the approve step rather than silently granting a bypass
nobody configured.

**Nothing gets asked at session start, ever, as of 2.1.0.** An earlier
version of this asked the disposition question immediately when any Claude
Code session opened, in every project — including ones that never touch a
Workflow. That's gone: the `SessionStart` hook now only *silently* seeds
`auto` as the default mode and carries forward whatever's already recorded.

**The disposition axis** only matters in `auto`, defaults to `balanced`, and
is **never asked about at all** — not at session start, not lazily, not
ever. That's a deliberate simplification, settled after two rejected drafts
that both still asked something: `balanced` already picks cheap vs.
expensive per task automatically, so most of the time there is nothing to
ask. It's a standing cost/accuracy target, not a fixed per-row pin: `fast`
targets ~90–95% reliability (default cheap, still reaches for `opus` when
one task genuinely needs it), `balanced` (default) targets ~95–99% (follows
the baseline table per task shape, no continuum-wide lean), `quality`
targets ~99%+ (defaults toward paying for certainty even where cheaper could
plausibly work). **Per-task deviation from the baseline, in either
direction, never needs to ask** — that's the entire point of a philosophy
instead of a rulebook: `auto` can run unattended on this basis. Changing the
disposition itself is entirely your call — natural language or
`/agenting-mode <disposition>`, which can be combined with a mode token in
one call (e.g. `/agenting-mode manual fast`); recorded independently of
mode, so setting it while in `manual`/`semi-auto` is valid and just sits
stored, unused — it never biases what `manual`'s AskUserQuestion proposes —
until you switch back to `auto`. Claude never proposes a change, and
deliberately does **not** track or surface a pattern of frequent
`quality`/`fast` picks as a reason to reconsider it: if `balanced` keeps
picking `opus` because the work needs it, that's the mechanism working, not
a signal. A project's `agenting/AGENTING.md` knob `auto-disposition-default`
can pin something other than `balanced` — same kind of target, not a rigid
rule either. An established Learned Precedent always outranks disposition.

Every other question in this system fires **lazily**, exactly once per chat
continuum, right when it first becomes relevant — never up front. (Except
disposition, above, which isn't asked at all.)

**The suggestion axis** is now persisted the same way (previously it reset
every session). Asked once, lazily, the first time a task in this
conversation actually looks workflow-shaped: *want suggestions like this for
the rest of this chat continuum?* Say yes and later suitable tasks are
suggested without re-asking, carried across compaction. Config knob:
`suggestion-default: ask` (default, lazy per-continuum ask) / `on` / `off`
(pins it, skips the ask).

**Where the memory lives.** First use in a project scaffolds two files:

| | |
|---|---|
| `agenting/AGENTING.md` | Curated, **always read in full**. Hand-written *Rules & Edge Cases*, a *Config* block of named knobs, and auto-promoted *Learned Precedents* one-liners. |
| `agenting/log.csv` | Raw, append-only, **never read in full** — grepped by exact `shape_key`. Columns: `timestamp,source,shape_key,plan_signature,answer`. |

`shape_key` is task-type composition only — the *question*, e.g.
`scan:x4|analyze:x3|synthesize:x2` — carrying no tier information. The
existing plan signature is logged alongside it for cross-reference and is
**not** the matching key. `AGENTING.md` is always committed; whether
`log.csv` is committed or gitignored is asked once, when the scaffold is
created.

**Precedent.** An exact `shape_key` match with **≥2 consistent
`user`-sourced answers** gets promoted to *Learned Precedents*, and
`semi-auto` / `auto` apply it. Rows written by `semi-auto` or `auto` stay in
the log as audit trail but **don't vote** — the system can't launder its own
guesses into precedent. Conflicting answers for one shape aren't consistent,
so it asks again and the newest answer becomes the latest data point. To
undo one, say so: *"forget that precedent"* / *"that was wrong, redo as X"*
edits the entries directly. No command.

Other knobs: `promotion-threshold: 2`, `auto-disposition-default: balanced`, and
`matching-strictness: exact` — only `exact` is implemented; any other value
warns and falls back rather than silently no-op'ing. Full mechanics live in
the `agenting` skill.

## Install

```
/plugin marketplace add furkanzt/claude-agenting
/plugin install agenting@agenting
```

Then verify it actually works:

```
/agenting-check
```

## What ships

| | |
|---|---|
| `hooks/workflow-routing-guard.py` | The two-stage gate. Parses the script with balanced parens; ignores `agent(` inside strings and comments. The Stage-2 approve command it prints is self-referential — its own path, not a hardcoded one. As of 2.1.0, Stage 2 drops its approval requirement (a plain `systemMessage`, never `permissionDecision:"allow"`) when `session-continuity.py`'s state file explicitly records this session's mode as `auto`; a missing entry does not trigger this, and the user's own Claude Code permission settings for `Workflow` are never overridden either way. |
| `hooks/cache-tripwire.py` | Reports the token cost paid when a mid-session model/effort switch invalidates the prompt cache prefix. Fires once per switch, never blocks. |
| `hooks/session-continuity.py` | `SessionStart` hook. Never asks anything itself — silently seeds `auto` as the default mode and `balanced` as the default disposition for a new chat continuum (disposition is never asked about at all, only ever explicitly set), then re-injects whatever's recorded (mode, disposition, suggestion) on every later firing instead of letting it get lost to compaction. The suggestion axis is the one exception with a lazy ask, driven by the `agenting` skill's procedure the first time it's relevant. Also read (not written) by `workflow-routing-guard.py` to decide whether Stage 2 can drop its approval requirement in `auto` mode. State: `~/.claude/.agenting-session-state.json`, keyed by `session_id`. |
| `skills/agenting/` | The tier table, the decision procedure, the mode and precedent mechanics, an external-model cost comparison, and the verified tokenomics numbers below. |
| `templates/` | The per-project scaffold shipped with the plugin: `AGENTING.md` and an empty `log.csv` with its header. |
| `agents/` | **20 tiered agent definitions**, every one carrying `model` + `effort`. |
| `scripts/check-setup.py` | End-to-end health check — it *runs* things rather than reading config. |
| `scripts/measure-tokenomics.py` | Recomputes the main/agent cost split, spawn tax, and effort distribution from real transcripts. |
| `commands/agenting-check.md` | `/agenting-check` |
| `commands/agenting-mode.md` | `/agenting-mode` |

### The shipped roster

| Tier | Agents |
|---|---|
| `haiku` / `low` | `scanner`, `text-mechanic` |
| `sonnet` / `low` | `coder`, `tech-writer`, `git-specialist` |
| `sonnet` / `medium` | `researcher`, `frontend-dev`, `cicd-engineer`, `performance-engineer`, `tester-tdd` |
| `sonnet` / `high` | `coder-ts`, `database-architect`, `ml-developer`, `refactoring-specialist` |
| `opus` / `high` | `coordinator`, `swarm-coordinator` |
| `opus` / `xhigh` | `reviewer`, `security-architect`, `system-architect`, `incident-responder` |

> **This roster is one person's opinionated setup.** Installing the plugin adds all 20 to your agent list. Delete the ones that don't fit how you work — the gate doesn't depend on any of them.

Two are worth keeping regardless, because they encode a discipline rather than a role:

- **`scanner`** (haiku/low) — counts, lists, measures. Carries a *no silent zeroes* rule: a search returning 0 must be cross-checked and the gap explained, never reported as success.
- **`text-mechanic`** (haiku/low) — mechanical text repair with a hard **output ⊆ input** invariant, and a mandatory closing audit (`words in input but missing from output: 0`) that refuses delivery if it isn't zero.

## Choosing a tier

Two questions settle almost every case:

1. **Is the answer *present*, or must it be *constructed*?** Present in one span → cheap. Assembled from distant or unstated pieces → expensive.
2. **What does a confident wrong answer cost?** Noticed immediately → cheap. Silently poisons downstream work → expensive.

| Task shape | Model | Effort |
|---|---|---|
| List files, count pages, collect output | `haiku` | `low` |
| Mechanical text cleanup (output ⊆ input) | `haiku` | `low` |
| Read code/prose and report what it does | `sonnet` | `medium` |
| Turn prose into rules; classify; judge | `sonnet` | `medium`–`high` |
| Synthesize across a document or many files | `opus` | `xhigh` |
| Decide under a "don't guess" constraint | `opus` | `xhigh` |
| Adversarially verify a finding | `opus` | `high` |

## Deliberate inheritance

Sometimes an agent genuinely should take the session's tier. Mark it, and the gate skips it while the intent stays visible in the script:

```javascript
// routing: inherit
await agent("wants whatever the session is on", { schema: S })
```

## Recommended settings

Two things worth turning on deliberately once this plugin (or its hooks) are
in place, plus one template worth copying into each project's own `CLAUDE.md`.

**`ENABLE_PROMPT_CACHING_1H` — decide by your gap pattern, not by default.**
Under a subscription, the main session gets a 1-hour cache TTL; on usage
overage that silently drops to 5 minutes unless this env var is set:

```json
{ "env": { "ENABLE_PROMPT_CACHING_1H": "1" } }
```

Under an API key (not a subscription), a 1-hour cache **write** costs 2x a
5-minute write, against a **read** that's ~0.1x either way — so the variable
is only worth turning on if the window it protects actually gets reused.
Decide by how your session is paced:

- **5–60 minute gaps between turns** (reading, thinking, back-and-forth with
  a human) — turn it on. The 1h TTL is what survives the gap; a 5-min TTL
  would have already expired and forced a rewrite anyway.
- **Uninterrupted automation** (a workflow running turn after turn with no
  human-paced gap) — leave it off. The 5-min TTL never lapses between calls,
  so the 2x write premium buys nothing.

**The cache-cost tripwire** (`hooks/cache-tripwire.py`) reports the token
cost paid when a model or effort change mid-session invalidates the cache
prefix — see the `agenting` skill's own habit: *pick the tier at session start,
switch at boundaries, not mid-task.* It fires once per switch (state tracked
per session) and never blocks a prompt.

**Per-project delegate-rule template.** Once a codebase has files/reads that
routinely run large (generated docs, extracted corpora, long logs), name the
threshold explicitly in that project's `CLAUDE.md` rather than leaving it to
judgment call each time:

```markdown
## Delegate large reads

Reads expected to exceed ~20k tokens (e.g. `docs/**/extracted/*.txt`) must
not be `Read` directly into the main session — delegate to a one-shot agent
that returns line-referenced findings instead. Targeted short reads (a
specific offset/limit, a known section) stay allowed in the main session.
```

Adjust the threshold and the glob to the project; the point is a named,
written rule instead of a per-session guess about what's "too big."

## Why the health check runs things instead of reading config

On the machine this was built for, four separate things were found configured-but-dead in a single afternoon:

- a CLI's `status` command printed a healthy cached record while its auth had been dead 99 days
- a regex returned **0** matches on the largest file in a corpus and reported success — it was the right pattern for five of six files and the wrong one for the sixth
- a live hook imported a module that had been deleted, throwing on every invocation
- a second-vendor CLI was installed with model configs but no auth, and its agents silently fell back to a paid model

Every one of them looked correct in the config file.

**Configured ≠ working. Only an end-to-end call proves anything.** So `check-setup.py` feeds the guard a real unrouted script and asserts it blocks; it executes the hook rather than checking it's listed.

## License

MIT — see [LICENSE](LICENSE).
