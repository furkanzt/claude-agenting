---
allowed-tools: Read, Bash(python3:*)
description: Report or set this chat's agenting mode (auto/manual), disposition (fast/balanced/quality) and workflows opt-in (workflows on/off)
---

## Argument

$ARGUMENTS

## Your task

Report or change this session's agenting settings. They are persisted per
session by `hooks/session-continuity.py`, whose exact path and this session's
id are in the `[agenting]` line from SessionStart. Use that path as printed:
`${CLAUDE_PLUGIN_ROOT}` is not expanded in a Bash command you type.

- **No argument:** run `python3 "<that path>" --status --session <session_id>`
  and report its values in one or two lines.
- **Argument:** any mix, in any order, of
  - a mode: `auto` | `manual`
  - a disposition: `fast` | `balanced` | `quality`
  - `workflows on` | `workflows off`

  Record what it names in one call —
  `python3 "<that path>" --record --session <session_id> [--mode …] [--disposition …] [--workflows …]`
  — then confirm in one line. An unrecorded change reverts at the next
  compaction.
- **Anything else:** say which tokens are valid (the list above).

When reporting or confirming, add one short line per value set:

- **auto** (default): Claude decides each Workflow's routing itself and the
  guard's approval step steps aside.
- **manual**: Claude asks you to confirm each new routing plan.
- **balanced** (default) / **fast** / **quality**: how auto leans on borderline
  tiers: the routing table as is, cheaper, or more certain. Changes only when
  you ask.
- **workflows on**: you opted in to Workflows for this chat; substantive tasks
  run as Workflows without asking again. **off** withdraws it.

The agenting skill's `reference/modes.md` has the full rules; keep this reply
to the status and the change.
