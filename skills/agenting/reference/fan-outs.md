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
