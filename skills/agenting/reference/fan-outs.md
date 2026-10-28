# Fan-outs: what an agent costs to start, and the levers

Evidence tags. **measured**: a count or median from `scripts/measure-tokenomics.py
anatomy` on one install's transcripts (21 days to 2026-10-07). **observed**: a
pattern in those numbers that is confounded. **external**: one other pipeline,
small sample. **untested**: a mechanism with no result yet. Every dollar and
percent here is a list price; the usage-window effect was not measured.

## What one agent costs before it does any work

- **measured:** a generic Workflow agent's first call carries a median of about
  43-45k tokens of context (Sonnet 5.5 at high, Opus 5.5 at high and xhigh; Sonnet
  5.5 at xhigh is the low outlier at 36k), about 25-27k of it written to cache
  fresh and about 17-19k read. The spawn tax in the
  overview is that first-call write: a median of about 30k tokens, about $0.22 per
  spawn at the write rates. A whole agent writes more as it works.
- **measured:** by start order, the first agent of a workflow wrote about 40k
  tokens fresh, agents 2 and 3 about 34k, agent 4 onward about 30k. Later agents
  read a shared prefix of about 19k tokens but still write most of their start-up
  fresh; this is start order, not a controlled stagger test. Workflow agents share cache only
  when model, effort, agent type, tools, schema and working directory are all
  identical (`evals/research/2026-10-05-models.md`).
- **measured:** cache writes are almost all 1-hour writes (98% of agent
  cache-write tokens).
- **measured, a fact and not advice:** advisor iterations are billed on top at the
  advisor model's own rates and are absent from the top-level usage numbers (checked
  by hand on a sample of records). In the window they were 20% of the list-price
  total, a floor: some advisor calls are not recorded. The only switch is
  session-wide (`CLAUDE_CODE_DISABLE_ADVISOR_TOOL=1`). Whether to change it is the
  user's decision; do not raise it.

## Levers, in evidence order

None of these overrides the routing table or the session's disposition.

1. **Fewer agents (external, one pipeline, small sample).** Four tasks per
   Opus/high agent cost about 70% less in list price, within noise. Sonnet leaked
   item ids across neighbouring tasks (one explicit id-isolation line fixed it in
   one sample), a batched judge step was unsafe, and a batched generation step
   coarsened its output. Batch only when the output can be validated in code
   (every input id exactly once, no foreign id), and do not batch a judge step.
   **untested here.**
2. **Typed agents with a restricted tool list (measured, one pipeline).** They
   start without the skill listing: about 10-15k tokens of first-call context
   against 36-45k for a generic agent. A controlled pilot showed the type alone
   does not cause it (a `general-purpose` agent starts like a generic one); the
   restricted tool list goes with it. On real work (Opus 5.5 at xhigh, no quality
   loss) a neutral Read-only agent cost 19% less per task than generic agents on a
   two-step pipeline and 32% less on a short, tool-free step. The full-pipeline
   figure is below the plugin's 25% bar, so no agent is shipped for it; for short,
   tool-light fan-outs an existing `agenting:` agent with a narrow tool list is the
   cheaper choice when its role fits (`evals/research/2026-10-07-launch-cost.md`).
3. **Effort (external, 4 agents on one task).** Effort pins are honoured: thinking
   tokens rose with effort (about 0.4k at low, 1.4k at medium, 1.8k at high,
   4.0-4.4k at xhigh). The table's cells were chosen against a bar (pass every
   run, save at least 25%); a lower effort than the table's cell needs that bar,
   not this note.

## Clean runs outside Workflow (measured, one pipeline)

For many self-contained tasks, `scripts/cleanrun.py` (it ships with this plugin, two
levels above this skill's base directory) runs each task as its own
`claude -p --restricted` process instead of an `agent()` call. On one pipeline (KC
grade 7, Opus 5.5 at xhigh) that cost 63% less per task at list price, with no
quality loss on that project's bar (`evals/research/2026-10-07-launch-cost.md`). The
usage-window effect is not measured, and it cannot be measured locally on an account
that other computers share; one rough, confounded reading suggested per-task window
use might be about equal. Treat the saving as list-price only.

- **Use it when all of these hold:** each task is its files plus one prompt; it needs
  no session context and no tools beyond Read; the tasks do not coordinate; the
  output can be checked in code (a validator). Otherwise use a Workflow.
- **Routing is the same decision as for `agent()`:** pick model and effort from the
  routing table; the tool takes a full model id and refuses aliases.
- **Prompt placement:** the stable rules go in the system-prompt file, the per-task
  data in the prompt, so runs that follow each other share a cached prefix. A cold,
  simultaneous first wave saves little (external: about 6%).
- **Order of use:** `cleanrun.py plan` (what runs, what resumes, the cost bound), then
  `run`, then `status`. Its money rules (soft per-run cap, `--max-usd` for new
  launches only, unknown cost charged at the cap) are in its docstring.
- **Tools that need permission:** `claude -p` cannot ask, so a tool in `--tools` such as
  WebSearch, WebFetch or Bash is denied. `--allowed-tools "WebSearch,WebFetch"` passes
  claude's allowed-tools flag; every name must also be in `--tools`, and a non-empty
  list is part of the resume key. It grants permission only: a run that calls WebFetch
  still shows a second model (a Haiku summariser) in `modelUsage`, which the model
  check rejects unless `--also-models` lists it (see the next bullet).
- **Tools that call a helper model:** by default the models in `modelUsage` must be
  exactly `--model`. `--also-models "claude-haiku-4-5-20251001"` (full ids separated by
  commas; it refuses aliases like `--model`, an id with a space in it and `--model` in
  another case) lets a run pass when `--model` is among them and every other
  model is on the list; without `--model` it still fails. This is a weaker check:
  `modelUsage` cannot show which listed model wrote the final answer, so a pass is
  evidence, not proof. It is meant for web stages, together with `--allowed-tools`. It
  was not verified against a real WebFetch run (the tests use a stub), and a web stage
  reads untrusted pages, which the kit sandbox does not constrain. A non-empty list,
  apart from `--model` itself, is part of the resume key.
- **Files in sub-directories:** a string in a task's `files` is copied flat, under its
  base name. `{"path": "src/a.pdf", "as": "sub/dir/name.pdf"}` places the file at that
  relative path inside the run's working directory instead, so two files with one base
  name can sit side by side and no flattened names or rewritten prompt paths are needed.
  `as` is refused, before any launch and by `plan` too, when it is absolute, has a `..`,
  `.` or empty segment, a backslash or a NUL, or collides with another entry's path
  ignoring case (or makes a file where another needs a directory). The validator sees
  the `as` path. A task whose files are all strings keeps its resume key; `"as": "x.md"`
  keys like the string entry `x.md`, and changing `as` reruns the task.
- **The routing guard asks the question too:** a Workflow whose untyped `agent()`
  call runs once per item (a `map` callback, a `pipeline` stage, a loop body) gets a
  "Clean-run check:" warning that never blocks it; a typed call is silent.
