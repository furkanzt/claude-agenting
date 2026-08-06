# Changelog

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
