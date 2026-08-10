# agent-routing

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

## Install

```
/plugin marketplace add furkanzt/claude-agent-routing
/plugin install agent-routing@agent-routing
```

Then verify it actually works:

```
/check-agent-routing
```

## What ships

| | |
|---|---|
| `hooks/workflow-routing-guard.py` | The two-stage gate. Parses the script with balanced parens; ignores `agent(` inside strings and comments. |
| `hooks/cache-tripwire.py` | Reports the token cost paid when a mid-session model/effort switch invalidates the prompt cache prefix. Fires once per switch, never blocks. |
| `skills/workflow-routing/` | The tier table, the decision procedure, an external-model cost comparison, and the verified tokenomics numbers below. |
| `agents/` | **20 tiered agent definitions**, every one carrying `model` + `effort`. |
| `scripts/check-setup.py` | End-to-end health check — it *runs* things rather than reading config. |
| `scripts/measure-tokenomics.py` | Recomputes the main/agent cost split, spawn tax, and effort distribution from real transcripts. |
| `commands/check-agent-routing.md` | `/check-agent-routing` |

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
prefix — see the routing skill's own habit: *pick the tier at session start,
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
