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
2. **Typed agents without a skill listing (observed, confounded).** They started
   at about 15k tokens of context (one Opus group 29k), against 36-45k for generic
   agents on the same models; typed agents that did carry a listing started near
   37k. The groups differ in task, session and tools. The plugin's agents all
   restrict their tools, which may be why they carry no listing, but the script
   does not measure that: a hypothesis under test, not a saving.
3. **Effort (external, 4 agents on one task).** Effort pins are honoured: thinking
   tokens rose with effort (about 0.4k at low, 1.4k at medium, 1.8k at high,
   4.0-4.4k at xhigh). The table's cells were chosen against a bar (pass every
   run, save at least 25%); a lower effort than the table's cell needs that bar,
   not this note.
