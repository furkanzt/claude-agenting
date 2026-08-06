---
allowed-tools: Bash(python3:*)
description: Verify agent routing is wired up and actually working (end-to-end, not config-reading)
---

## Health check output

!`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/check-setup.py" 2>&1 || true`

## Your task

Report the result above to the user, concisely.

- If everything passed, say so in one line with the counts. Do not restate every check.
- If anything FAILED, explain what is broken and what to do about it. A failing
  guard check means workflows are running unrouted — that is the whole point of
  this plugin, so treat it as urgent.
- WARN lines are advisory: a missing cheap tier or a single-tier setup means the
  routing exists but buys nothing. Mention them, don't alarm.

Do not re-run the script; the output is already above.
