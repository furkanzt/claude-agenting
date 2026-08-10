# Changelog

## 1.2.0 — 2026-08-10

### Added
- **`hooks/cache-tripwire.py`** — a `UserPromptSubmit` hook that reports the
  token cost paid when a mid-session model or effort switch invalidates the
  prompt cache prefix. Compares the session's current tier against the last
  tier this hook already reported (tracked in a small per-session state file
  next to the script); fires once per distinct switch, never blocks. Measured
  case: a sonnet/high → opus/max switch mid-session rewrote 66,975 tokens on
  the very next turn.
- **`scripts/measure-tokenomics.py`** — recomputes the main/agent cost split,
  average context size, spawn tax, and effort distribution from real
  `~/.claude/projects` transcripts, using the same dedup method (last line per
  `message.id`, not raw line count) used to derive the numbers now documented
  in the `workflow-routing` skill's "Verified facts" section.
- **"Verified facts (2026-08-10)"** section in the `workflow-routing` skill —
  dedup method, spawn-tax median (~$0.11/spawn, ~2-3 turn break-even for
  delegating), cache-key-includes-effort behavior, and the effort-distribution
  shift since this skill shipped (subagent `max` 57% → 1%, `high` 15% → 57%).
- **"Recommended settings" section in the README** — when
  `ENABLE_PROMPT_CACHING_1H` is worth the 2x cache-write premium (paced,
  human-gap sessions) versus not (uninterrupted automation), and a
  copy-paste "delegate large reads" rule template for a project's own
  `CLAUDE.md`.

## 1.1.0 — 2026-08-07

### Added
- **Post-completion verification section in the `workflow-routing` skill.**
  Routing was covered end to end but only up to launch; nothing said what to
  do once a `Workflow` call returns. Prompted by a real incident: three
  workflows each reported a coherent-looking summary after completing, built
  by silently filtering out every agent that didn't return — one run's
  headline numbers were computed from 38 of 122 agents, the other 84 having
  died mid-run with no trace in the summary. Caught only because the user
  asked directly. The new section is a standing checklist — read
  `agents_done` vs `agent_count`, cross-check the raw `journal.jsonl` against
  the tool result's own claims, distinguish a live queued agent from a dead
  one by transcript mtime, read a stalled agent's last few records before
  assuming failure vs. a session-limit kill, and recover missing pieces by
  scope rather than blindly re-running the same call.
- Noted explicitly that this is a skill, not a hook: nothing forces a re-read
  of it at workflow-completion time the way `workflow-routing-guard.py`
  forces routing at launch time. If it keeps getting skipped in practice, a
  `PostToolUse` hook on `Workflow` mirroring the existing gate is the durable
  fix — flagged as a future option, not built yet.

## 1.0.0 — 2026-08-06

First release.

### Added
- **Two-stage `PreToolUse` gate on the Workflow tool.**
  Stage 1 denies any Workflow whose `agent()` calls lack `model`/`agentType` or
  lack `effort`, naming the offending line numbers. Stage 2 denies until the
  user approves that specific routing plan in that session; approval is keyed by
  plan signature, so a repeat is silent and a change re-asks.
- **20 tiered agent definitions**, every one carrying both `model` and `effort`,
  spanning `haiku/low` through `opus/xhigh`.
- **`scanner`** (haiku/low) — inventory agent with a no-silent-zeroes rule.
- **`text-mechanic`** (haiku/low) — mechanical text repair with an
  output ⊆ input invariant and a mandatory closing audit.
- **`workflow-routing` skill** — tier table, decision procedure, and the rule
  that the gate must always offer *higher quality* as well as *cheaper*.
- **`external-model-options.md`** — cost comparison against non-Claude tiers,
  with the volume threshold below which a second vendor is not worth its
  maintenance.
- **`scripts/check-setup.py`** and **`/check-agent-routing`** — an end-to-end
  health check that runs the guard rather than reading configuration.

### Design notes
- Single `Agent` calls are deliberately **not** gated: one agent is bounded and
  cheap, and every shipped definition already pins both fields.
- The gate is not a cost-cutting tool. On a cheap session the risk is
  *under-powering*, so the approval prompt leads with the upgrade option there
  and with the downgrade option on an expensive session.
- `// routing: inherit` marks a call that should take the session's tier, so
  deliberate inheritance stays visible in the script instead of being invisible.
