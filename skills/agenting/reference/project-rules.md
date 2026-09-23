# Project rules: agenting/AGENTING.md

A project pins its own routing decisions in `agenting/AGENTING.md` at the
project root: a small, hand-written file, committed like `CLAUDE.md`. It has
two sections, `## Rules` and `## Config`.

## Reading it

Read the whole file at the start of any session that may run a Workflow in a
project that has it, before drafting the first script. Then:

- **Rules** override the disposition and the routing table, in every mode. In
  manual mode they shape the plan you propose; the user's answer still wins.
- **Config** `auto-disposition-default: fast|balanced|quality` is this
  project's starting disposition. Apply it with
  `--record --session <id> --disposition <value>` (see
  [modes.md](modes.md)) unless the user has already chosen a disposition in
  this session; their choice stands.
- A file written for plugin 2.x may also hold a precedents section and other
  config keys. Treat each precedent line as a Rule, ignore the other keys, and
  offer once to move the precedents under `## Rules` and delete the rest.

## Writing it

- Add a rule when the user states one and asks for it to be recorded, e.g.
  "always route the synthesis step to opus/xhigh here". One bullet per rule
  under `## Rules`, in the user's words.
- Change a Config value when the user asks.
- When the file doesn't exist yet, create it from the plugin's
  `templates/AGENTING.md`. The plugin root is the recorder path from the
  `[agenting]` line minus `hooks/session-continuity.py`.
