# agenting

**Subagents let one session use several model tiers at once. This plugin makes that deliberate.**

A `PreToolUse` gate refuses to run a Workflow until every `agent()` call carries an explicit `model` and `effort`. In manual mode it then asks you to approve the routing plan, offering *cheaper* **and** *higher quality*, not just cheaper. When a Workflow finishes, a second hook checks its journal and warns if any agent never returned.

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

**Stage 1: routing.** Any `agent()` call missing `model`/`agentType` or missing `effort` blocks the Workflow, naming the offending line numbers. No mode bypasses this.

**Stage 2: plan approval.** In manual mode, even a fully routed Workflow blocks until you approve *this particular routing plan* in *this session*. Re-running the same plan is silent; changing any tier asks again. In auto mode (the default) Claude decides the plan itself and the gate steps aside.

```
STAGE 2/2 — PLAN APPROVAL: 9 agents, all routed. Waiting on the user
(this session is in manual mode, or has no recorded mode). Procedure: the agenting skill.

      4 agent(s)   haiku            effort: low
      3 agent(s)   sonnet           effort: medium
      2 agent(s)   opus             effort: xhigh

9 agents total.  Plan signature: haiku/lowx4|opus/xhighx2|sonnet/mediumx3
```

Single `Agent` calls are **deliberately not gated**: one agent is bounded and cheap, and every shipped definition already pins both fields.

**Finish check.** A workflow script's own summary is computed from whatever agents returned; agents that died are silently missing from it. When a Workflow completes, `workflow-finish-check.py` reads the run's `journal.jsonl` and, only if something is missing, adds a line like:

```
[agenting] Workflow "Phase 4 classify": 13 of 18 agents returned; missing: classify:MAT.7.1-1,
classify:MAT.7.2, verify:MAT.7.4-1, verify:MAT.7.6, verify:MAT.7.7. The workflow's own summary
was built without them. Read <journal> and report the real count before presenting or acting on
this result (agenting skill: "When the finish check fires").
```

**Session settings.** Three values, carried per chat across compaction and printed as one line at every SessionStart:

```
[agenting] mode=auto · disposition=balanced · workflows=not opted in (session <id>). Record changes: …
```

| Setting | Values | Meaning |
|---|---|---|
| mode | `auto` *(default)* / `manual` | Who resolves Stage 2: Claude, or you via a question |
| disposition | `fast` / `balanced` *(default)* / `quality` | How auto leans on borderline tiers. Never asked about, never suggested; changes only when you say so |
| workflows | `on` / `off` / not opted in | Makes "use workflows for this session" survive compaction. Routing is unaffected |

Change them in plain language or with `/agenting-mode` (e.g. `/agenting-mode manual quality`, `/agenting-mode workflows on`). No argument reports the recorded values.

**Project rules.** A project can keep hand-written routing rules in `agenting/AGENTING.md` at its root: a `## Rules` section (e.g. *"always route the synthesis step to opus/xhigh here"*) and a `## Config` section with one knob, `auto-disposition-default`. Claude reads it in full before the first Workflow of a session; its Rules override the disposition and the routing table. The template is `templates/AGENTING.md`.

## Install

```
/plugin marketplace add furkanzt/claude-agenting
/plugin install agenting@agenting
```

Then verify it actually works:

```
/agenting-check
```

Upgrading from 2.x: see the 3.0.0 entry in [CHANGELOG.md](CHANGELOG.md).

## What ships

| | |
|---|---|
| `hooks/workflow-routing-guard.py` | The two-stage gate (`PreToolUse` on `Workflow`). |
| `hooks/workflow-finish-check.py` | The finish check (`UserPromptSubmit`). Silent unless a finished Workflow lost agents. |
| `hooks/session-continuity.py` | `SessionStart`: seeds and re-injects mode, disposition and the workflows opt-in; also the `--record` / `--status` CLI. |
| `hooks/cache-tripwire.py` | Reports the token cost paid when a mid-session model/effort switch invalidates the prompt cache prefix. Fires once per switch, never blocks. |
| `skills/agenting/` | `SKILL.md` (routing table, launch procedure, finish-check response), `reference/modes.md`, `reference/project-rules.md`, `external-model-options.md`. |
| `templates/AGENTING.md` | The per-project rules file. |
| `agents/` | **20 tiered agent definitions**, every one carrying `model` + `effort`. |
| `commands/` | `/agenting-check`, `/agenting-mode`. |
| `scripts/check-setup.py` | End-to-end health check: it *runs* things rather than reading config. |
| `scripts/measure-tokenomics.py` | Recomputes the main/agent cost split, spawn tax, and effort distribution from real transcripts. |
| `tests/` | Pipe tests for the three stateful hooks. |

### The shipped roster

Address them as `agenting:<name>`: `agentType: 'agenting:researcher'` inside a workflow script, `subagent_type: "agenting:researcher"` for a single `Agent` call. If you still have user-level copies of the same agents from an older install, delete them; every session would list each agent twice.

| Tier | Agents |
|---|---|
| `haiku` / `low` | `scanner`, `text-mechanic` |
| `sonnet` / `low` | `coder`, `tech-writer`, `git-specialist` |
| `sonnet` / `medium` | `researcher`, `frontend-dev`, `cicd-engineer`, `performance-engineer`, `tester-tdd` |
| `sonnet` / `high` | `coder-ts`, `database-architect`, `ml-developer`, `refactoring-specialist` |
| `opus` / `high` | `coordinator`, `swarm-coordinator` |
| `opus` / `xhigh` | `reviewer`, `security-architect`, `system-architect`, `incident-responder` |

> **This roster is one person's opinionated setup.** Delete the ones that don't fit how you work; the gate doesn't depend on any of them.

Two are worth keeping regardless, because they encode a discipline rather than a role:

- **`scanner`** (haiku/low): counts, lists, measures. Carries a *no silent zeroes* rule: a search returning 0 must be cross-checked and the gap explained, never reported as success.
- **`text-mechanic`** (haiku/low): mechanical text repair with a hard **output ⊆ input** invariant, and a mandatory closing audit (`words in input but missing from output: 0`) that refuses delivery if it isn't zero.

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

## How enforcement works

**Parsing.** The guard reads the inline `script` (or the file at `scriptPath`), blanks out comments and string bodies while preserving offsets, then finds `agent(` calls by balanced parentheses. A key's *presence* is checked on the blanked text, so `"model: opus"` inside a prompt is not routing; its *value* is read from the raw text. `// routing: inherit` on the call's line or the line above marks deliberate inheritance.

**Stage 1** denies when any call lacks `model`/`agentType` or lacks `effort`. It is never bypassed, in any mode.

**Stage 2** builds a plan signature from the (model, effort) counts and denies until that signature's hash is approved for this `session_id`. The deny message prints the approve command with the guard's own path: `python3 "<guard>" --approve <hash> --session <id>`. Approvals live in `.routing-approvals.json`.

**Auto mode.** The guard reads this session's recorded mode from `.agenting-session-state.json`, the file `session-continuity.py` writes. Only an explicit `"auto"` drops Stage 2, and it does so with a bare `systemMessage`: no `hookSpecificOutput`, no `permissionDecision`, never `"allow"`. An allow would override your own Claude Code permission settings for the `Workflow` tool, which is not this plugin's decision to make. A missing file, a missing entry, a legacy 2.x mode or anything unreadable keeps the approval requirement, so an install where the continuity hook isn't wired up degrades to asking, not to a bypass nobody configured.

**Session state.** Keyed on `session_id`, which Claude Code keeps across compaction of the same conversation (verified: three compaction events over ~9 hours shared one id). Resume is assumed to keep the id too, by Claude Code's design; not independently verified here, and a wrong assumption would cost a fresh default, not silent data loss. `/clear` is treated as a new continuum even if the id were reused. The state lives at a fixed user-level path rather than next to the scripts because the installed plugin sits in a versioned cache directory that changes on every update.

**Finish check.** The hook parses the journal path from the notification's `<diagnostics>Per-agent results: …` line, then compares `started` and `result` records. An agent counts as missing only when neither its `agentId` nor its `key` has a result: the key is the (prompt, opts) cache key, and when the runtime restarts an interrupted agent it logs a second `started` line with the same key and a new `agentId`. A real run with 23 `started` and 18 `result` lines turned out to be complete for exactly this reason (five interrupted attempts, each restarted and returned); counting agentIds alone would have flagged it. It is silent on any error.

**State directory.** Both state files live in `~/.claude/` unless `AGENTING_STATE_DIR` points elsewhere. The tests use that variable so they never touch your real state.

## Tests

```
python3 -m pytest tests          # or, without pytest:
python3 -m unittest discover -s tests
```

Every test pipes JSON into a hook exactly as Claude Code does, with `AGENTING_STATE_DIR` set to a temporary directory. Covered: session-continuity (seeding, record/status, the workflows opt-in across compaction, legacy state, the one-line message), the routing guard (Stage 1, `agenting:<name>` agent types, manual approval round-trip, the auto-mode system message), and the finish check against three journal fixtures in `tests/fixtures/`. `scripts/check-setup.py` also honours `AGENTING_STATE_DIR`.

## Recommended settings

**`ENABLE_PROMPT_CACHING_1H`: decide by your gap pattern, not by default.**
Under a subscription, the main session gets a 1-hour cache TTL; on usage
overage that silently drops to 5 minutes unless this env var is set:

```json
{ "env": { "ENABLE_PROMPT_CACHING_1H": "1" } }
```

Under an API key (not a subscription), a 1-hour cache **write** costs 2x a
5-minute write, against a **read** that's ~0.1x either way, so the variable
is only worth turning on if the window it protects actually gets reused.
Decide by how your session is paced:

- **5–60 minute gaps between turns** (reading, thinking, back-and-forth with
  a human): turn it on. The 1h TTL is what survives the gap; a 5-min TTL
  would have already expired and forced a rewrite anyway.
- **Uninterrupted automation** (a workflow running turn after turn with no
  human-paced gap): leave it off. The 5-min TTL never lapses between calls,
  so the 2x write premium buys nothing.

**The cache-cost tripwire** (`hooks/cache-tripwire.py`) reports the token
cost paid when a model or effort change mid-session invalidates the cache
prefix. The habit it backs: *pick the tier at session start, switch at
boundaries, not mid-task.* It fires once per switch (state tracked per session)
and never blocks a prompt.

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

## History

**Why the finish check became a hook.** On 2026-08-06/07 three workflows each
reported a coherent-looking summary after completing, built by
`.filter(Boolean)` over whatever *did* return. One run's headline numbers
("6 DÜZELTİLECEK, 12 EDİTÖRE SORULACAK") looked like a finished audit; it was
built from 38 of 122 agents, the other 84 having died mid-run. It was caught
only because the user asked. Version 1.1.0 added a checklist to the skill;
because nothing forced the skill to be re-read at completion time, 3.0.0 moved
the check into a hook.

**Disposition is never asked about: two rejected drafts.** The first draft
asked for a disposition at every SessionStart, in every project, including ones
that never run a Workflow: far too eager. The second asked lazily, once, right
before auto's first self-decided plan: better targeted, still an ask. The
owner's answer was simpler than either: default to `balanced` and stay there.
`balanced` already picks cheap or expensive per task, so there is usually
nothing to ask. A drift tracker ("you keep picking opus, switch to quality?")
was floated and rejected too: if the work needs opus, `balanced` choosing opus
is the mechanism working. *"If it works, it works."*

**Per-project memory became a rules file.** In 2.x the plugin logged every
resolved routing plan per project and promoted repeated answers into
precedents automatically. 3.0.0 replaced that with the hand-written
`agenting/AGENTING.md` described above.

**The auto-mode drop is not an allow.** In 2.1.0 the Stage-2 bypass was first
implemented as `permissionDecision: "allow"`; a review caught that this would
override the user's own permission settings for `Workflow`, and it shipped as a
bare `systemMessage` instead.

## Verified facts (measured 2026-08-10)

Measured from three weeks of transcripts. `scripts/measure-tokenomics.py`
recomputes them from whatever transcripts exist now. Figures are as of the
measurement date.

- **Dedup method:** in transcript JSONL, a line is NOT one API call. Take the
  LAST line per `message.id` (duplication factor: main session 2.06x, agents
  2.42x).
- Total shadow cost **$2,439** (main $992 / agents $1,447) at list price; under
  a subscription this is a consumption indicator, not a bill.
- Main session: 4,917 calls, avg context **407k**, ~74% of cost is cache-read.
- Agents: 17,454 calls, ~1,700 agents, avg context **60k**, $0.083/call.
- **Spawn tax** (first call's cache-write): median 17k ≈ **$0.11**; three-week
  total ~$190. Delegation break-even: **~2-3 turns**. An agent pays for itself
  by keeping context OUT of the main session; one or two calls of legwork
  don't justify a spawn.
- **Cache key includes model+effort:** a mid-session switch rewrites the whole
  prefix (see `cache-tripwire.py`'s docstring for the measured case). At the
  time, Claude Code showed a confirmation dialog for effort changes; model
  changes were silent.
- Under subscription, the main session gets a 1-hour cache TTL; **on overage
  it silently drops to 5 minutes** (`ENABLE_PROMPT_CACHING_1H` prevents this).
  A subagent always starts cold with its own cache, 5-minute TTL.
- Same-type agent fan-out opened simultaneously is all cold; staggered by a
  few seconds, later ones ride the first one's system-prompt cache.
- Effort distribution (cut at the skill's birth, 2026-08-06T22:31): subagent
  `max` 57% → **1%**, `high` 15% → **57%**.
- Limits: the **Opus limit was never hit**; the binding constraint is the
  shared session limit (one incident, 2026-08-06 13:54, pre-skill fan-out).
  Switching models does not restore the shared limit.
- Price ratio, dated: Sonnet's input price was 2.5x cheaper than Opus's during
  Sonnet's introductory pricing, which ended 2026-08-31. Since then it is
  1.67x ($3 vs $5 per MTok list). Re-check current pricing before relying on it.
- Vector DB decision: **no** for audit work (comprehensiveness can't be
  established via similarity search, and the bill is already re-read-weighted);
  for kazanım (learning-outcome) mapping, a ready ~100-200 record JSON table is
  enough.

## Why the health check runs things instead of reading config

On the machine this was built for, four separate things were found configured-but-dead in a single afternoon:

- a CLI's `status` command printed a healthy cached record while its auth had been dead 99 days
- a regex returned **0** matches on the largest file in a corpus and reported success; it was the right pattern for five of six files and the wrong one for the sixth
- a live hook imported a module that had been deleted, throwing on every invocation
- a second-vendor CLI was installed with model configs but no auth, and its agents silently fell back to a paid model

Every one of them looked correct in the config file.

**Configured ≠ working. Only an end-to-end call proves anything.** So `check-setup.py` feeds the guard a real unrouted script and asserts it blocks; it executes the hook rather than checking it's listed.

## License

MIT, see [LICENSE](LICENSE).
