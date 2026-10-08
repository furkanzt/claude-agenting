# Launch cost of a Workflow agent: E1 result and E2 pre-registration

Dated 2026-10-07. Every dollar is a list price, computed by
`scripts/measure-tokenomics.py`'s cost model from the run's own transcripts.

## E1: controlled launch-cost pilot (run 2026-10-07)

**Question.** Do typed agents with a restricted tool list start smaller than a
generic `agent()` call, and is the cause the agent type or the tool list?

**Design.** One Workflow, run in a chat with workflows opted in. Four arms of five
agents each, interleaved and started strictly one after another (G, T, GP, GS, G, T,
...). Every agent got the same trivial task (a sum, one call, no tools, a
one-field schema, checked in code); all on Sonnet 5.5 at medium.

- **G**: generic `agent({model: 'sonnet', effort: 'medium'})`, prompts differing only
  in the two numbers.
- **T**: `agentType: 'agenting:researcher'` (tool list restricted to Bash, Read, Grep,
  Glob; no Skill tool).
- **GP**: `agentType: 'general-purpose'` with `model: 'sonnet'` (typed, all tools).
- **GS**: generic, with a byte-identical prompt for all five.
- **Probe**: `agentType: 'agenting:researcher'` with `model: 'opus'`.

**Pre-registered rule** (HANDOFF 3G): T shows at least 15k fewer first-call context
tokens, at least 25% lower list cost per agent, and an equal pass rate. A pass is a
pilot result and needs a replication before any guidance or agent changes.

**Result.** 21 of 21 agents answered correctly.

| Arm | First-call context | Written fresh | Read from cache | Cost per agent (median) |
|---|---|---|---|---|
| G | 35,925 | 16,929 | 18,994 | $0.0720 |
| GP | 36,274 | 16,929 | 19,343 | $0.0721 |
| T | 9,685 | 6,333 | 3,350 | $0.0265 (-63%) |
| GS | 35,925 | 0 | 35,923 | $0.0077 (-89%) |

The first agent of each arm wrote everything fresh (G $0.144, T $0.039, GP $0.076) and
is included in the medians above as one of five.

- **Rule: passed** (26k fewer tokens, -63%, 5 of 5). Status: pilot positive; the E2
  lean-worker arm is the replication on real work.
- **The type is not the cause.** GP is typed and starts like G. The smaller start goes
  with the restricted tool list: T carries no skill listing and no deferred-tools
  block. T also differs in its persona text, which E2 removes with a neutral agent.
- **A model given alongside an agentType is honoured**: the probe ran on
  `claude-opus-5-5` with T's small context (9,679 tokens).
- **New: about 17k tokens of harness context sit after the task prompt in the cache
  order.** Prompts that differed only by two numbers each rewrote 16,929 tokens;
  byte-identical prompts rewrote none. Any per-task text in the prompt therefore
  invalidates those 17k for every agent. **Bounded by E2:** a second generic 02b run sent
  byte-identical prompts minutes after the first and cost the same ($0.429 against $0.420),
  so the saving held only within one workflow run, on one-call agents. Something per
  run in the harness context appears to break the shared prefix. Not a usable lever.

**Limits.** One call per agent on a trivial task, so the saving per call on a long
agent (fewer tokens re-read on every call) is not shown here; five agents per arm;
Sonnet only (plus one Opus probe).

## E2: usage-window effect, pre-registered before any run

**Question.** Per task, how much of the owner's 5-hour usage window does each arm use,
and does the list-price saving carry over to the window?

**Arms** (same tasks, model and effort: Opus 5.5 at xhigh, the production cell):

- **W**: the production Workflow arms (generic `agent()`).
- **L**: the same Workflow with `agentType: 'lean-worker'`, a neutral user-level agent
  (`~/.claude/agents/lean-worker.md`: tools Read only, a three-line neutral body).
- **R**: clean `claude -p --restricted` runs (the KC clean runner, rules verbatim in
  `--system-prompt`).

**Work.** KC grade 7, steps 01b (UT generation) and 02b (KC formation), about 12 GKCs
per block, written to a throwaway state directory; production data is untouched.
Blocks run in a balanced order (W L R R L W), each block one arm, back to back.
Expected spend about $70 list.

**Measurement.** A script reads the 5-hour gauge (`~/.claude/scripts/claude-usage.py`,
whole percent) before and after each block, after it settles; this chat stays idle
while a block runs, apart from launching the Workflow blocks. Outcome per arm: window
points per task (and per list dollar), plus list cost per task from the transcripts
(W, L) or the runner's ledger (R). Nothing in the plugin reads the window; this is an
experiment script.

**Decision rules** (bar: the plugin's 25% materiality threshold):

1. If L saves at least 25% of window per task against W with no quality loss, ship
   `agenting:worker` and upgrade the fan-out guidance from "under test" to measured.
2. If R saves at least 25% of window per task against W with no quality loss, build
   the shared clean-run core in agenting (HANDOFF 3G).
3. If both pass and L captures at least two-thirds of R's saving, recommend the worker
   as the default for fan-outs and keep clean runs for very large, context-free
   batches.

**Quality bar** (the KC bar, "same quality, not same output"): every hard gate passes
in every run, and 01b coverage of the committed UTs and 02b grouping agreement with
the committed KCs fall within the W arm's run-to-run noise.

**Known limits, stated in advance.** The gauge reads whole percent, so a block's
reading carries up to about one point of rounding at each end. One grade, one model,
one pipeline. The Workflow blocks are launched from a chat, which uses a little window
itself.

## E2 result (run 2026-10-07 and 2026-10-08)

**What changed from the pre-registration, and why.** The usage-window measurement
could not be made. Two attempts were contaminated: other Claude Code sessions on this
machine spent about as much as each block during the block, and the owner then
reported that other computers share the account, which no local check can see. A
DNS outage also voided one block. The owner decided to drop the window arm and
apply the same decision rules to **list price**, with the quality bar unchanged.
A second deviation: the pre-registered 02b quality check (grouping agreement with
the committed KCs) needs every arm to group the same UTs, which is not true when
each arm regenerates its own 01b. It was therefore run as a separate 02b-only test
on the committed UTs of 12 GKCs (generic arm twice, for its run-to-run noise).
One clean-run 02b test first ran on the wrong model (the project had switched its
default 02b routing in between); it was rerun pinned to Opus 5.5 at xhigh and the
first run is excluded.

**List cost per GKC** (Opus 5.5 at xhigh in every arm; from each arm's own
transcripts or the runner's ledger):

| | Generic Workflow (W) | Lean worker (L) | Clean run (R) |
|---|---|---|---|
| 01b + 02b, separate GKCs per block | $1.669 (n=36) | $1.358 (-19%, n=12) | $0.611 (-63%, n=24) |
| 02b only, identical inputs | $0.420 and $0.429 (two runs) | $0.287 (-32%) | $0.157 (-63%) |

**Quality** (KC bar: hard gates plus agreement within the generic arm's noise):

- Hard gates: no failure in any arm, in either test.
- 01b coverage of the committed UTs (Sonnet 5.5 matcher): W 91%, L 95%, R 91%;
  per-GKC medians 1.00, 0.95, 1.00 with overlapping ranges.
- 02b grouping agreement with the committed KCs (adjusted Rand index): W 0.75 and
  0.79, L 0.79, R 0.76. The two W runs agree with each other at 0.79. L and R are
  within the generic arm's own noise.

**Decision rules, applied to list price:**

1. Lean worker: **not met.** -19% per task on the full pipeline is below the 25% bar.
   The 02b-only test shows -32%: the fixed start-up cost is a larger share of a
   short, tool-light agent. Recorded as a secondary result, not the decision.
2. Clean runs: **met** (-63%, no quality loss). Build the shared clean-run core.
3. Not applicable (rule 1 not met). L captures 29% of R's saving.

**Limits.** List price only: the usage-window effect remains unmeasured, and on an
account shared with other computers it cannot be measured locally. One grade, one
pipeline, one model and effort; 12 to 36 GKCs per arm; the 01b arms ran on different
GKC sets of similar size (about 1.5 textbook pages per GKC in each arm).
