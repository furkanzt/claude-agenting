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
| `skills/workflow-routing/` | The tier table, the decision procedure, and an external-model cost comparison. |
| `agents/` | **20 tiered agent definitions**, every one carrying `model` + `effort`. |
| `scripts/check-setup.py` | End-to-end health check — it *runs* things rather than reading config. |
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
