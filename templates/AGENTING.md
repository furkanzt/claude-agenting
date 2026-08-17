# Agenting

Curated by hand and by the plugin together. Read in full at the start of any
session that considers running a Workflow in this project — unlike
`log.csv`, this file is never too big to read whole.

## Rules & Edge Cases

<!-- Hand-curated prose. Claude never auto-writes to this section; edit it
     yourself, or tell Claude the rule in conversation and ask it to record
     it here. Example: "always route the synthesis step to opus/xhigh in
     this project, even in auto mode." -->

## Config

<!-- Structured knobs. Each line is `key: value`. Unset keys use the plugin
     default shown here. -->

- `promotion-threshold: 2` — number of consistent `user`-sourced answers in
  `log.csv` needed before a task-shape is promoted to a Learned Precedent.
- `suggestion-default: ask` — `ask` (once per session, default) / `on`
  (suggest workflow-shaped tasks without asking) / `off` (never suggest).
- `matching-strictness: exact` — only `exact` is implemented; any other
  value prints a warning and falls back to `exact` rather than silently
  no-op'ing.

## Learned Precedents

<!-- Auto-promoted, one line per established task-shape, deduplicated.
     Populated once a shape_key in log.csv reaches promotion-threshold
     consistent `user`-sourced answers. Format:
       - `shape_key` → `answer`  (n user-sourced occurrences, last YYYY-MM-DD)
     "Forget that precedent" / "that was wrong, redo as X" (natural
     language) edits this section and the underlying log.csv rows
     directly — no dedicated command. -->
