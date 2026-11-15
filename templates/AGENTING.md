# Agenting

Routing rules for this project. Claude reads this file in full before the first
Workflow of a session. Rules here override the agenting skill's routing table.

## Rules

<!-- Hand-written, one bullet per rule. Claude adds a rule only when you state
     it and ask for it to be recorded. Examples:
     - Always route the synthesis step to opus/xhigh here, even in auto mode.
     - Page-counting and OCR-cleanup agents stay on sonnet/low. -->

## Config

<!-- One `key: value` per line. A key inside this comment is not set. To set the
     disposition auto mode starts with in this project (`fast` or `balanced`),
     copy the line below under this comment. Without it a chat starts in
     `balanced`, or in your plan's disposition when the plugin can read the plan.
     - `auto-disposition-default: balanced` -->
