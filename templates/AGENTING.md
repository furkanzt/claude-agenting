# Agenting

Routing rules for this project. Claude reads this file in full before the first
Workflow of a session. Rules here override the agenting skill's routing table.

## Rules

<!-- Hand-written, one bullet per rule. Claude adds a rule only when you state
     it and ask for it to be recorded. Examples:
     - Always route the synthesis step to opus/xhigh here, even in auto mode.
     - Page-counting and OCR-cleanup agents stay on haiku/low. -->

## Config

<!-- One `key: value` per line. Delete a line to use the plugin default. -->

- `auto-disposition-default: balanced` — `fast` / `balanced` / `quality`: the
  disposition auto mode uses in this project unless you set one for the session.
