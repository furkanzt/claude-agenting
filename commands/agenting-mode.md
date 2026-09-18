---
allowed-tools: Read, Bash(python3:*)
description: Report or set this chat continuum's mode (manual/semi-auto/auto), auto-disposition (fast/balanced/quality), and workflow-suggestion axis (on/off)
---

## Argument

$ARGUMENTS

## Your task

This command controls three axes carried by the `SessionStart` hook
`hooks/session-continuity.py`, persisted per chat continuum (keyed on
`session_id`, surviving compaction — not conversational memory, and not a
project file):

- **mode**: `manual` / `semi-auto` / `auto` (default `auto`)
- **disposition**: `fast` / `balanced` / `quality` (default `balanced` —
  **never asked about**, only ever set by explicit user request; see the
  `agenting` skill for why)
- **suggestion**: `on` / `off` (unset until asked or pinned — this is the
  one axis of the three with a lazy ask)

All three reset only when a genuinely new chat continuum starts (`/clear`, or
a fresh session).

Use the exact `session-continuity.py` path this session's `SessionStart`
`additionalContext` already gave you (it re-prints on every compaction, so
it is always available without guessing) — do not reconstruct the path from
`${CLAUDE_PLUGIN_ROOT}` yourself; that variable is substituted by the harness
inside a command file's own `!`-executed lines, not inside prose you retype
into a fresh Bash call, and a wrong guess there fails silently.

- **No argument**: get ground truth rather than relying on recall — run
  `python3 "<that path>" --status --session <session_id>` and report all
  three axes from that output verbatim (disposition always has a concrete
  value; suggestion may say "not yet set" if it hasn't been asked yet). One
  or two lines, no elaboration unless asked.
- **Argument matches a mode** (`manual`/`semi-auto`/`auto`) **and/or a
  disposition** (`fast`/`balanced`/`quality`) **and/or a suggestion value**
  (`on`/`off`), space-separated in any order: apply whichever axis(es)
  matched, then persist immediately —
  `python3 "<that path>" --record --session <session_id> [--mode <value>] [--disposition <value>] [--suggestion <value>]`.
  Confirm the change in one line. Do not skip the persist step — an
  unpersisted change reverts on the next compaction.
- **Any other argument**: say it isn't a valid value for any of the three
  axes and list all of them.

When reporting or confirming, briefly restate what the values do so a user
invoking this cold gets a useful one-screen answer:

- **auto** (default mode) — never asks about a routing plan; decides it from
  the global tier table, this session's disposition, and the project's
  `agenting/AGENTING.md`, then the gate itself drops its approval requirement
  (no `--approve` needed; your own Claude Code permission settings for
  `Workflow` are untouched either way).
- **semi-auto** — auto-answers only workflow shapes that match an established
  precedent (≥ `promotion-threshold` consistent user-sourced answers for that
  `shape_key`); asks for anything novel, same as `manual` for that case.
- **manual** — always asks via Stage-2's AskUserQuestion; the proposed
  default is shaped by precedent once one exists.
- **balanced** (default, never asked about) — `auto`'s self-decisions follow
  the routing table as proposed, no bias.
- **quality** — `auto` biases borderline `sonnet`-tier calls up to
  `sonnet`/`high` when unsure. Only set by explicit request, never suggested.
- **fast** — `auto` biases borderline `sonnet`-tier calls down to
  `sonnet`/`low` when unsure. Only set by explicit request, never suggested.
- **suggestion on/off** — whether workflow-shaped tasks get proactively
  flagged for the rest of this continuum; independent of mode and
  disposition.

Do not duplicate the full precedent/promotion/disposition mechanics here —
that lives in the `agenting` skill. This command is a status line and a
switch, not the explainer.
