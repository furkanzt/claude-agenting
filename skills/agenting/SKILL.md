---
name: agenting
description: Use when deciding whether bulk work leaves the main chat, starting a teammate, writing or editing a Workflow script, planning a fan-out of many agents, choosing a model or effort for an agent() or Agent call, when the user switches agenting mode (auto/manual) or disposition (cheapest/fast/balanced), calls a job critical or throwaway, opts in to workflows for this chat, or when a project has agenting/AGENTING.md.
---

# Agenting

An `agent()` call with no `model`/`effort` inherits the main session's tier:
wasted spend when the session is expensive, an under-powered agent when it is
cheap. Subagents are the only way one session runs several tiers at once, so
route every call by the reasoning it needs, and look in both directions.

The main chat is the **decider**: it keeps the decisions and the conversation,
hands bulk work to cheaper workers, and gives each worker a tier from the table
below. Two questions come before any routing.

## Where the work runs

**1. Main chat, or off it?** Work stays in the main chat when any of these
holds: a quick fix (about 1 to 3 files, under 50 lines); rapid prototyping, or
any loop where the user looks at the result and steers the next step; each step
depends on the one before; the main chat needs the details afterwards, not only
the result; one long command (run it in the background, it needs no agent).
Work leaves only when all three hold:

1. it can be briefed in one message, with no question to the user on the way;
2. the main chat needs only the result (a summary, a list, the changed files);
3. it is big in at least one way: about 5 or more similar items; or reading of
   about 10 or more files or 20k or more tokens that the main chat will not
   need again; or 2 or more independent parts that can run at once.

Time alone never decides, and in doubt the work stays. In `auto` mode start
off-chat work without asking and say in one line what runs where; in `manual`
mode propose it and wait.

**In `fast` and `cheapest`** every agent start draws on a small usage limit, so
the bar for leaving is twice as high: about 10 or more similar items; or about
20 or more files or 40k or more tokens of reading; or 4 or more independent
parts. Reading and exploring runs as a Workflow or as teammates only when the
user asks for one. Bulk coding still leaves the chat: once the main chat has
the plan and the tests, the coding goes to the bulk-coding row's workers
(`agenting:bulk-coder`) through the smallest vehicle that fits.

**2. Which vehicle?** The cheapest that fits:

| Vehicle | Fits when |
|---|---|
| One agent (`Agent`, no `name`) | One question or one piece of work; only its summary returns |
| Clean run (`scripts/cleanrun.py`) | Many similar items, each self-contained, read-only, output checkable in code |
| Workflow | Many items or stages that need tools or the web, or a later stage that depends on an earlier one |
| Teammates (`Agent` with a `name`) | 3 to 5 long-running workers that must talk to each other or be steered while they work |

**3. Think first?** One model decides before the builders start, when all three
hold:

1. later work is built on the choice (a data model, an API shape, a game rule, a
   screen's layout and flow);
2. at least two options would work, and the files do not settle which;
3. a wrong choice is expensive to undo (about a day of rework, or it reaches
   players or production).

Otherwise just build. The one who thinks first is the main chat, when it already
runs on the model the routing table names for that job; otherwise ONE design
agent on that model: `agenting:system-architect` for an architecture or approach
decision, `agenting:ux-designer` for a UI/UX design. It returns the decision, the
reasons, the rejected options and the risks. Give the user the decision in 2 to 3
lines; then the builders start (`manual` mode: after the user's yes).

- **A UI prototype** is cheap to redo, so condition 3 fails and it gets no design
  pass by this rule; an extra rule that would have given it one fell short of its
  bar. Run a design pass for it when the user asks for one: it is not the default.
  Then the designer writes a brief (screens, flow, every state, the words, the
  main action, the assumptions), the builders follow it, small steering stays in
  the main chat, and a rejected direction goes back to the designer.
- **Fable 5.2 thinks first only when the user asks for it.** It was measured on
  both jobs and took neither row.

**4. A prototype: throwaway or keep?** Two ways to build one.

- **Throwaway:** the `cheapest` cells, no tests, no review, no design pass, in
  any disposition. When you deliver it, say that it is a throwaway and that
  keeping it means building it again on the keep path.
- **Keep:** the session's normal build path, as for any feature.

The user's word decides ("throwaway", "quick demo", "just to see it"; or "we
will keep this", "implement it if I approve"). Without one: in `manual` mode
ask once before building, with one sentence on what each path costs and gives;
in `auto` mode decide, and say in one line which path you took. Throwaway when
the user wants a quick look (quick, try, idea, demo) or the work is one new
file outside the real code. Keep when it changes real files or will be
implemented if approved. Unclear: keep.

Examples, what each vehicle costs and the teammate rules:
[reference/delegation.md](reference/delegation.md).

## The advisor is for the decider

Workers work alone: only the main chat, and the one design agent
(`agenting:system-architect`), may call the `advisor` tool. Every other agent
carries this sentence, verbatim, in its file or its prompt:

```
Work alone. The `advisor` tool belongs to the lead that started you, so do not call it: decide from the brief and the files, and when something blocks you, say so in your result.
```

- **Workflow:** define `const ALONE` as that sentence without its two backticks and
  end every worker prompt with it. A call that must reach the advisor gets the
  comment `// advisor: allowed`.
- **Agent start:** an `agenting:` agent already has it; for any other type put the
  sentence in the prompt, or the line `advisor: allowed`. A fork is exempt.
- The `[agenting]` line shows `advisor=off`, or `advisor=<model>` with a reminder.

The evidence is in [reference/delegation.md](reference/delegation.md).

## Routing table

Pick by reasoning demand, not by how important the task feels. The cells were
measured with each model working alone, so they hold with or without an advisor:
workers work alone.

| Task shape | Model | Effort | Test |
|---|---|---|---|
| List files, count pages, run a script, collect output | `haiku` | `medium` | A regex or `ls` could nearly do it |
| Mechanical text cleanup: de-hyphenate, reflow, strip headers | `sonnet` | `low` | Output ⊆ input; nothing invented |
| Read code / prose and report what it does | `haiku` | `medium` | Answer is present in one place |
| Turn prose into rules; classify; judge relevance | `sonnet` | `medium`–`high` | Needs judgment, source states the facts |
| Synthesize across a whole document or many files | `opus` | `xhigh` | Must relate things that are far apart |
| Decide under a "don't guess" constraint (BELİRSİZ) | `haiku` | `xhigh` | **Calibration is the product** |
| Adversarial verify / refute a finding | `sonnet` | `high` | A confident wrong answer is expensive |
| Decide an architecture or approach that later work is built on | `opus` | `xhigh` | "Think first?" holds, and the choice is a structure |
| Design a UI/UX solution before a prototype, screen or flow is built | `opus` | `xhigh` | "Think first?" holds, and the choice is what the user sees |
| Plan a build and write its tests, before cheaper workers code | `opus` | `high` | The tests fix what "done" means for everyone after |
| Bulk coding against tests that exist | `haiku` | `medium` | A test run says pass or fail |
| Review a build before it is called done | `sonnet` | `high` | Verify's job on code: a confident wrong "fine" is expensive |

**How the cells were measured.** [`evals/`](../../evals/README.md) ran every
cell of each row on real tasks and compared measured cost per run: a first sweep
on 2026-10-06, a re-check with Haiku 5.5 on 2026-10-09, and a round on the two
think-first rows on 2026-11-13, where Fable 5.2 was measured and not adopted.
A coding experiment on 2026-11-14 and 2026-11-15 set the two build rows (the
review row was not measured and follows verify), and on 2026-11-15 the owner
moved don't-guess to Haiku `xhigh` on the pooled runs.
The numbers behind each row, what changed and the limits are in
[reference/evidence.md](reference/evidence.md); read it before changing a cell
or citing a number. Two limits to carry: two or three tasks per row show large
gaps only, and the security, incident and orchestration agents were not measured
and keep their pins. This table is `balanced`. `fast` and `cheapest` take a
cheaper cell on some rows, and a job the user calls critical gets the careful
one: [reference/modes.md](reference/modes.md).

**The build rows work as one path.** A stronger model plans and writes the
tests; `agenting:bulk-coder` codes until they pass, at most three tries, and
may not change them; a reviewer reads the result. With tests in place Haiku at
`medium` was correct in 24 of 24 runs at about 3 cents a task, and the tests
were 94% of a task's cost, so the saving is in who writes the code, not in
skipping the tests. Without any tests Haiku got 1 run in 24 wrong and nothing
in that path notices. A coder that writes its own tests was acceptable but no
cheaper, and can spend its tries on its own failing tests.

Two questions settle almost every case:

1. **Is the answer *present*, or must it be *constructed*?** Present in one
   span → cheap. Assembled from distant or unstated pieces → expensive.
2. **What does a confident wrong answer cost?** Noticed immediately → cheap.
   Silently poisons downstream work → expensive.

When one of this plugin's agents fits, route by agent:
`{agentType: 'agenting:<name>', effort: '<its effort>'}`. The `agenting:`
prefix is part of the name, and the guard wants `effort` alongside it. None of these agents has
`WebSearch` (only `coordinator` has `WebFetch`; `researcher` has Bash, Read, Grep and Glob), so for
research on the web use `agentType: 'general-purpose'` at the same model and effort.

| Tier | Agents (`agenting:<name>`) |
|---|---|
| `haiku`/`medium` | `scanner`, `bulk-coder` |
| `sonnet`/`low` | `coder`, `tech-writer`, `git-specialist`, `text-mechanic` |
| `sonnet`/`medium` | `researcher`, `frontend-dev`, `cicd-engineer`, `performance-engineer`, `tester-tdd` |
| `sonnet`/`high` | `coder-ts`, `database-architect`, `ml-developer`, `refactoring-specialist` |
| `opus`/`high` | `coordinator`, `swarm-coordinator` |
| `opus`/`xhigh` | `reviewer`, `security-architect`, `system-architect`, `ux-designer`, `incident-responder` |

Every tier here is a Claude model. Before proposing a non-Claude one, read
[external-model-options.md](external-model-options.md).

## Procedure: before calling Workflow

1. **Project rules.** If the project root has `agenting/AGENTING.md`, follow
   [reference/project-rules.md](reference/project-rules.md) before drafting.
2. **Clean run or Workflow?** Settle it before drafting, for any script that
   fans out over many items (an `agent()` call inside `map`, `pipeline` or a
   loop). A task belongs in a clean run (`scripts/cleanrun.py`, see
   [reference/fan-outs.md](reference/fan-outs.md)) when all four hold:
   - it is self-contained: its files plus one prompt, no session context;
   - it needs no tool beyond Read (no web, no Bash, no other agent);
   - the tasks do not coordinate: none reads another's result within one
     batch. A later stage that takes earlier outputs as its files is the next
     batch, not coordination;
   - its output can be checked in code (a validator).

   All four hold: default to `cleanrun.py plan`, then `run`, and say so in one
   line. One fails (web stages, a refuter launched per flagged item, a stage
   that needs the session): write the Workflow, and name the condition that
   failed.
   A clean run is four small files and three commands. `tasks.jsonl` holds one
   `{"id", "prompt", "files"}` per line (a file that needs a folder is
   `{"path": "reports/q3.txt", "as": "q3/report.txt"}`), `rules.md` the system
   prompt, `schema.json` the answer shape and `check.py` a
   `validate(output, task)` that returns a list of problems. From that folder:
   `python3 "<plugin>/scripts/cleanrun.py" plan --tasks tasks.jsonl
   --system-prompt rules.md --schema schema.json --model <full id> --effort
   <effort> --validator check.py --out-dir out --tools Read`, read its cost bound,
   then the same with `run --max-usd N`, then `status --out-dir out`. A task that
   lists `files` needs `--tools Read` to open them (without it `plan` and `run`
   refuse). `<plugin>` is two
   levels above this skill's base directory. A complete example, with the files
   written out, is in [reference/fan-outs.md](reference/fan-outs.md).
3. **Draft** the script. Done when every `agent()` call has `model` or
   `agentType`, and `effort`, or is marked `// routing: inherit` (below).
4. **Resolve by mode.** The session's `[agenting]` line from SessionStart names
   the mode; `--status` on the recorder it names gives ground truth.
   - **auto** (default): decide the plan yourself, without asking. Start from
     the table, apply the session's disposition (under `balanced` the table
     *is* the baseline; for `fast`, and for a job the user calls critical, see
     [reference/modes.md](reference/modes.md)), then the project's Rules.
     Run the Workflow; the guard lets it through with a note.
   - **manual**: put the plan to the user with AskUserQuestion, naming the
     task types and the tiers you assigned, in three directions. Lead with the
     direction that fits the session's tier: on `sonnet`/`medium` the risk is
     under-powering, so lead with the upgrade; on `opus`/`xhigh` the risk is
     over-spending, so lead with the downgrade. Always offer both.

     > *"3 kinds of work in this workflow. Routing: confirm or change?"*
     > - **As proposed**: 4× scan (haiku/low), 3× analyze (sonnet/medium), 2× synthesize (opus/xhigh)
     > - **Higher quality**: analyze → opus/high (the synthesis is the load-bearing part)
     > - **Cheaper / faster**: analyze → haiku/low

     Apply the answer, run the `--approve` command the guard printed, and
     re-run. When the user already stated this workflow's routing earlier in
     the conversation, apply that instead of asking.
5. Done when a fan-out's form (clean run or Workflow) is chosen with its reason
   stated, and a Workflow is running with every call routed, in manual mode
   with the plan the user chose.

**What the guard denies.** `workflow-routing-guard.py` runs before every
Workflow. Stage 1, in every mode: an `agent()` call missing `model`/`agentType`
or `effort`, reported by line number; fix the script. It reads the options
object's own keys in the source, so routing inside a spread (`...lens.route`) is
invisible to it: for per-item routing write `agentType: lens.agentType, model:
lens.model, effort: lens.effort`. When the items are a `const` array literal the
call iterates (`map`, `forEach`, `flatMap`, `pipeline`'s first stage, `for...of`)
and nothing can change them (the list and the loop variable are only read), each
item is read and one without a model or effort is named; otherwise only presence
is checked, so every item must set them. A literal `undefined` or `null` does not
count. A script with an `agent` call that it cannot read to the end (a string,
template, `${` or comment that never closes) is denied as unreadable. A script where a
template literal closes and a name, number, quote or backtick follows on the same line
is denied too, as a stray backtick: a backtick inside the template text (Markdown around
a word) ended it early. Put a backslash before that backtick, or use double quotes. A
pair whose text starts with an operator, `.` or `-` still parses and is not caught. Stage 2, in manual mode
or when no mode can be found for the session (a resumed chat's new id is looked
up through the `[agenting]` line in its own transcript first): a routed plan not
yet approved in this session; ask, apply, run its `--approve` command. Changing
any tier asks again. In auto mode Stage 2 steps aside with a system message.
Once Stage 1 passes, the guard also warns, never blocks, when a call site with no
`agentType` runs once per item (inside `map`, `forEach`, `flatMap`, a `pipeline`
stage, `Array.from`, or a `for` or `while` body): a paragraph starting
"Clean-run check:" names the count and the clean-run conditions of step 2. A
typed call (web stages use `general-purpose`) and a literal list of calls are
silent. The warning changes no decision and no plan hash; an approved plan and a
Stage 1 denial carry none.

## Deliberate inheritance

When one agent genuinely should take the session's tier, mark that call. The
guard skips it and the intent stays visible in the script:

```javascript
// routing: inherit
await agent("Hardest synthesis step; wants whatever the session is on", { schema: S })
```

Mark calls one at a time. Ask the user before marking several: blanket
inheritance switches Stage 1 off. For an `Agent` call the mark is a line
`routing: inherit` in the prompt.

## Agent starts: what the agent guard denies

`agent-routing-guard.py` runs before every `Agent` call and denies a start that
would take its tier by accident. Fix the call and retry; the user is not asked.

- **A one-off agent** (no `name`) needs a `model` and an `effort`, on the call
  or pinned by its agent file. Every `agenting:` agent pins both: spawn it as
  `subagent_type: "agenting:<name>"`.
- **A teammate** (a `name`, while agent teams are on) takes its model from the
  call or its agent file, and its effort **only from an agent file**: an
  `effort` written on a teammate's call is ignored (measured on Claude Code
  2.1.323). Start it from the `agenting:` agent whose tier fits its role, or
  drop the name to start a one-off agent. Shut each teammate down (`TaskStop`
  with its name) when its part is done.
- **A fork** passes: it copies the main chat on purpose.

The guard checks that a tier is set, not that it fits. These are the usual
mismatches:

- `agenting:scanner` (haiku/medium) for something that needs a decision, not a count
- `agenting:researcher` (sonnet/medium) for synthesis that needs opus
- a task where a confident wrong answer would propagate silently
- the session is on a cheap tier and this call is the hard part of the work

In `auto` mode pick the agent that fits. In `manual` mode ask it as a tier
question: *"This is really synthesis. Want `agenting:system-architect`
(opus/xhigh) instead of `agenting:researcher` (sonnet/medium)?"*

When the `[agenting]` line says `teammates=off` and a job fits teammates, run
it as a Workflow and tell the user once in this chat how to turn them on; the
wording is in [reference/delegation.md](reference/delegation.md).

## Fan-outs: what each agent costs to start

Every `agent()` call pays a start-up cost before it does any work. In one
install's transcripts (21 days, list price, measured) a generic Workflow agent's
first call typically carried about 44k tokens of context, about 25-27k of it
written to cache fresh, and later agents in a workflow still wrote most of that
fresh. Effort pins are
honoured, but the routing table and the session's disposition set effort, not
this section. Before fanning out to many agents, read
[reference/fan-outs.md](reference/fan-outs.md): what is measured, what is only
observed, and the levers that exist (fewer agents with code-side validation;
`agenting:` agents with a narrow tool list; and, for many self-contained tasks,
clean `claude -p` runs through `scripts/cleanrun.py`, 63% cheaper per task on one
pipeline). Every figure there is a list price; the usage-window effect was not measured.
When a Workflow fans out untyped calls, the guard's clean-run warning says so
without blocking: in manual mode it is part of the Stage 2 denial, read before
the launch; in auto mode its `systemMessage` is shown to the user only, and its
`additionalContext` reaches the model with the Workflow launch result, after
the agents have started (checked for the main session; a Workflow launched from
inside a subagent may not deliver it).

## Session settings

Three values carried per session by the SessionStart hook: mode
(`auto`|`manual`), disposition (`cheapest`|`fast`|`balanced`; a new chat
starts in the plan's when the plan can be read, never in `cheapest`) and the workflows
opt-in (`on`|`off`, seeded from the standing default when the user set one).
When the user changes any of them, in words or with `/agenting-mode`, read
[reference/modes.md](reference/modes.md) and record the change before replying.
The same line reports `teammates=on|off`, read from the environment, which the
user changes in their settings and not through this plugin.

## When the finish check fires

The `workflow-finish-check.py` hook reads every finished Workflow's
`journal.jsonl` and stays silent when all agents returned. When some did not,
the prompt carries `[agenting] Workflow "<name>": R of N agents returned;
missing: …`. The workflow's result was computed without those agents, so:

1. **Hold the result.** Present nothing from it as final yet.
2. **Find the cause of each gap.** Read the last records of
   `agent-<agentId>.jsonl` beside the journal (the agentId is on the missing
   agent's `started` line):
   - a synthetic zero-token stop right after the agent said it was submitting:
     a session-limit kill; the work was likely done and only the return lost
   - `[Request interrupted by user]`: the run was interrupted
   - an `is_error` record: read the error itself before guessing ("permission"
     inside a skill description is not a denial)
   - the message says a missing agent has a later attempt with the same label
     that returned: a retry under a changed prompt (for example after a resume)
     gets a new key. Check in the journal that this label names one item in the
     script; if it does, that work is done. If the script gives one label to
     several items, it is a real gap.
3. **Recover only the missing pieces**, fixing the cause first: a batch that
   died of oversized context needs a smaller scope, not the same prompt again.
   `resumeFromRunId` (printed in the notification) replays agents whose prompt
   and opts are unchanged.
4. **Report** "R of N agents completed; missing: … because …".

Done when the user has the real count and a cause for every missing agent,
before either of you acts on the result.
