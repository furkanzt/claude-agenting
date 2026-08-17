---
allowed-tools: Read
description: Report or set the session's workflow-approval mode (manual/semi-auto/auto)
---

## Argument

$ARGUMENTS

## Your task

This command controls the **session mode axis** — conversational memory only,
never written to any file, hook, or config. It resets to `manual` every new
session.

- **No argument**: report the current mode for this session (default `manual`
  if none has been set yet), plus the current suggestion-axis setting. For the
  suggestion setting, read the `suggestion-default` knob from this project's
  `agenting/AGENTING.md` Config block if that file exists; default to `ask`
  only if the file or the key is absent. One or two lines, no elaboration
  unless asked.
- **Argument is `manual`, `semi-auto`, or `auto`**: set the session mode to
  that value for the rest of this conversation. Confirm the change in one
  line, and explicitly note it is session-only — it does not persist and does
  not touch any hook or file.
- **Any other argument**: say it isn't a valid mode and list the three
  options.

When reporting or confirming, briefly restate what the three modes do so a
user invoking this cold gets a useful one-screen answer:

- **manual** (default) — always asks via Stage-2's AskUserQuestion; the
  proposed default is shaped by precedent once one exists.
- **semi-auto** — auto-answers only workflow shapes that match an established
  precedent (≥ `promotion-threshold` consistent user-sourced answers for that
  `shape_key`, default 2); asks for anything novel.
- **auto** — never asks; decides the plan itself from the global tier table
  and the project's `agenting/AGENTING.md`, then self-records the approval.

Do not duplicate the full precedent/promotion mechanics here — that lives in
the `agenting` skill. This command is a status line and a switch, not the
explainer.
