# Where the work runs: main chat, one agent, clean run, Workflow, teammates

The main chat is the **decider**. Everything it reads stays in its context and is re-read on every
later turn, at the session's own tier, which is usually the most expensive one in play. So bulk work
leaves it, and it keeps the decisions and the conversation. Leaving is not free either: a worker
pays a start-up cost and knows less than the main chat. These rules say when leaving pays.

The owner fixed the two rules below on 2026-11-13. They are judgment rules, not measurements.

## Main chat or off it

Work **stays in the main chat** when any of these holds:

- it is a quick fix: about 1 to 3 files and under 50 lines;
- it is rapid prototyping, or any loop where the user looks at the result and steers the next step;
- each step depends on the step before it, so nothing can run side by side;
- the main chat needs the details afterwards, not only the result (a debugging session);
- it is one long command (a build, a test run, a download): run it in the background; it needs no
  agent.

Work **leaves the main chat** only when all three hold:

1. it can be briefed in one message, with no question to the user on the way;
2. the main chat needs only the result (a summary, a list, the changed files);
3. it is big in at least one way: about 5 or more similar items; or reading of about 10 or more
   files or 20k or more tokens that the main chat will not need again; or 2 or more independent
   parts that can run at the same time.

Time alone never decides, and in doubt the work stays. A prototype's first build may leave the chat
when it is big; the look-and-steer loop after it stays.

| Task | Where | Why |
|---|---|---|
| Fix a typo in one hook file | Main chat | Quick fix |
| Try three button styles and show each | Main chat | The user steers each step |
| Find why a test fails | Main chat | Each step depends on the last |
| A 40-minute test run | Main chat, as a background command | One long command |
| Clean 40 chapter files the same way | Off | 40 similar items, only the result matters |
| Find every use of a function across a repo | Off | Much reading, only the result matters |
| Review a big diff from three angles | Off | Independent parts |

## In `fast`: fewer agents, bulk coding kept

`fast` is where a chat on a Pro plan starts, and a small usage limit pays for every agent start
(about 44k tokens of context before any work, [fan-outs.md](fan-outs.md)). The owner fixed these on
2026-11-14; they are judgment rules, not measurements.

- **The bar for leaving the chat is twice as high:** about 10 or more similar items; or about 20
  or more files or 40k or more tokens of reading; or 4 or more independent parts.
- **Reading and exploring** runs as a Workflow or as teammates only when the user asks for one. One
  agent or a clean run still fits a job that clears the higher bar.
- **Bulk coding is not cut.** Once the main chat has the plan and the tests, the coding goes to
  cheap workers, through the smallest vehicle that fits: one agent for one piece, a clean run when
  the pieces are self-contained and a test checks each, a Workflow of fewer than 5 agents when they
  need tools. That is where a small limit gains most: the expensive model
  plans, the cheap one types.
- **The advisor:** when the `[agenting]` line shows an advisor in a `fast` chat, tell the user once,
  in one line, that each advisor call re-reads the whole conversation at the advisor's price and
  that `/advisor off` turns it off.

| Task in a `fast` chat | Where | Why |
|---|---|---|
| Read 12 files to answer one question | Main chat | Under the higher bar |
| Summarise 30 documents the same way | Off, as a clean run | 30 similar items; no Workflow needed |
| "Explore the repo and tell me how auth works" | Main chat, or one agent if it is big | Exploring gets no Workflow unless asked |
| Implement 6 functions whose tests are written | Off, to cheap workers | Bulk coding is kept |

## A prototype: throwaway or keep

| | Throwaway | Keep |
|---|---|---|
| Cells | `fast`, in either disposition | The session's own |
| Tests, review, design pass | None | As for any feature |
| What the user gets | Something to look at, soon and cheap | Code that stays |
| Afterwards | Keeping it means building it again on the keep path | Nothing more |

The user's word decides. Without one, `manual` mode asks once before building ("Throwaway, or will
you keep building on it?", with the two columns above in a sentence each), and `auto` mode decides
and says in one line which path it took:

| What the user said | Path in `auto` | Why |
|---|---|---|
| "Quick demo of the lobby screen" | Throwaway | A quick look |
| "Try an idea: what if the score pulsed?" in a new scratch file | Throwaway | One new file outside the real code |
| "Prototype the new settings page; if I like it we ship it" | Keep | It will be implemented if approved |
| "Prototype a faster matcher in `lib/match.ts`" | Keep | It changes real files |
| "Make a prototype of the report" | Keep | Unclear, so keep |

A throwaway that the user then wants to keep is not patched into shape: it is built again on the
keep path, with the throwaway as the reference for what it should do.

## The four vehicles

Pick the cheapest that fits.

| Vehicle | Fits when | What it costs |
|---|---|---|
| **One agent** (`Agent`, no `name`) | One question or one piece of work; only its summary returns | One start-up, about 44k tokens of context for a generic agent ([fan-outs.md](fan-outs.md), measured, list price) |
| **Clean run** (`scripts/cleanrun.py`) | Many similar items, each self-contained, read-only, output checkable in code | The least per item ([fan-outs.md](fan-outs.md)) |
| **Workflow** | Many items or stages that need tools or the web, or a later stage that depends on an earlier one | One start-up per `agent()` call; needs the Workflows opt-in |
| **Teammates** (`Agent` with a `name`, agent teams on) | 3 to 5 long-running workers that must talk to each other or be steered while they work | The most: each teammate is a full session that keeps its context until it is shut down |

Only the Workflow needs an opt-in (this chat's, or the standing default; see [modes.md](modes.md)).
Without one, use the vehicles that need none and say once that a Workflow would fit.

## By mode

- `auto`: start the off-chat work without asking, and say in one line what runs where and on which
  tier.
- `manual`: propose the same plan and wait for the user's yes.

## Teammates

Teammates are Claude Code agent teams: experimental, off by default, switched on with
`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`. While they are on, every `Agent` call that carries a
`name` starts a teammate (unless it is a fork or passes `isolation`), also when nobody asked for a
team. Claude Code's docs: agent teams "use significantly more tokens than a single session", "Use
Sonnet for teammates", "Start with 3-5 teammates for most workflows", "Shut down teammates when
their work is done" (code.claude.com/docs/en/agent-teams and /costs, read 2026-11-13).

**What sets a teammate's tier** (measured 2026-11-13 on Claude Code 2.1.323, from the effort each
agent's transcript records):

| Start | Effort asked on the call | Effort it ran at |
|---|---|---|
| Named, no agent file, `model: haiku` | `xhigh` | `medium` (the settings default for that model) |
| Named, no agent file, `model: haiku` | `low` | `medium` |
| Unnamed, `model: haiku` | `xhigh` | `xhigh` |
| Unnamed, `model: haiku` | `low` | `low` |
| Named, from `agenting:coder` (file: `sonnet`/`low`) | none | `low` |
| Named, from `agenting:coder` (file: `sonnet`/`low`) | `xhigh` | `low` |

So a teammate takes its **model** from the call or its agent file, and its **effort only from an
agent file**. An effort written on a teammate's call is ignored. One sample per row; the recorded
field is the evidence. A `Workflow` `agent()` call applied its `model` and `effort` in all nine of
nine probes the same day, including an `effort` that overrode a typed agent's file.

Rules that follow:

- **Start each teammate from the `agenting:` agent whose tier fits its role.** The file sets the
  model and the effort. Workers are the Sonnet agents unless the routing table says otherwise; the
  lead is the main chat.
- **A worker that no `agenting:` agent fits** (it needs the web, say) starts without a name, as a
  one-off agent with `model` and `effort` on the call.
- **Shut each teammate down when its part is done** (`TaskStop` with its name). An idle teammate
  still holds its context.
- **Give the brief in the start prompt.** A teammate loads the project's instructions and skills
  but none of the lead's conversation.

**When teammates are off** (the `[agenting]` line says `teammates=off`) and a job fits them: run it
as a Workflow, and tell the user once in this chat, in one line and never as a question, that the
job fits teammates and that they turn on by adding `"CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"`
under `"env"` in `~/.claude/settings.json` (experimental; more tokens than subagents).

## The advisor

The advisor is a server-side tool. A session gets one from the `advisorModel` setting, the `/advisor`
command or the `--advisor` flag. Claude Code's docs say: "Subagents inherit the configured advisor",
and "There is no setting to cap or force advisor calls; if you want Claude to consult more or less
often during a task, say so in your instructions" (code.claude.com/docs/en/advisor, read 2026-11-13).
Each call re-reads the agent's whole conversation, uncached, at the advisor model's price. So every
Workflow agent, one-off agent and teammate of such a session can call it.

**The Workflow figure.** In one Workflow of 11 agents the advisor (Fable 5.2) was called 19 times, all
by the 8 Opus agents, and was 23.94 of 58.01 dollars at list price.

**The reviewer test** (measured 2026-11-13 on Claude Code 2.1.323, under a session whose advisor was
Fable 5.2; one read-only review task over two source files of about 450 lines; each agent started once):

| Arm | Agents | Agents that called the advisor | Calls |
|---|---|---|---|
| Opus `high`, no sentence (5 from an agent file, 3 `general-purpose`) | 8 | 8 | 8 |
| Opus `high`, with the sentence (5 in the agent file, 3 in the prompt) | 8 | 0 | 0 |
| Sonnet `medium`, no sentence | 3 | 0 | 0 |

An advisor call cost 0.60 dollars on average (8 calls, 4.77 dollars). An Opus agent's own work cost
0.33 dollars on average (16 agents, 5.28 dollars). So one advisor call cost more than the agent's
whole review.

**The rule (the owner's, 2026-11-13).** Workers work alone; the advisor is for the decider. The
decider is the main chat, and the one design agent (`agenting:system-architect`) when a design step
runs as an agent. The one exception is a call marked `// advisor: allowed` in a Workflow script, or
a prompt line `advisor: allowed` on an `Agent` start. Because workers never call the advisor, the
routing table holds whether the session has an advisor or not: its cells were measured with each
model working alone.

**How each vehicle is covered.** The sentence is in [SKILL.md](../SKILL.md) (section "The advisor is
for the decider"); the two guards only run while the session has an advisor.

- **Agent files:** every `agenting:` agent except `system-architect` carries the sentence.
- **Workflow prompts:** the Workflow guard denies a script when at least one `agent()` call is
  neither typed `agenting:` nor marked `// advisor: allowed` and the script carries the sentence
  nowhere. The denial prints a line to paste, `const ALONE = "..."`, to append to every worker
  prompt. The Agent guard denies a start that is not a fork and not an `agenting:` agent unless its
  prompt carries the sentence or a line `advisor: allowed`.
- **Clean runs:** `scripts/cleanrun.py` starts every process with `CLAUDE_CODE_DISABLE_ADVISOR_TOOL=1`.
- **The session line** shows `advisor=off`, or `advisor=<model>` with a reminder that agents inherit
  it and workers work alone. Both hooks read the state the same way: off when that variable is
  truthy (`1`, `true`, `yes`), else the first non-empty `advisorModel` in the project's
  `.claude/settings.local.json`, the project's `.claude/settings.json`, then `~/.claude/settings.json`,
  else off.

**The switches that exist.** The sentence in the prompt or agent file works (0 of 8 called it).
`CLAUDE_CODE_DISABLE_ADVISOR_TOOL=1` in a process's environment removes the advisor for that process.
Removing `advisorModel` (or `/advisor off`) removes it for the whole session, the main chat
included. There is no per-agent switch. Two things that failed in single probes: a permissions deny
rule for `advisor`, and the `--disallowedTools` flag. Neither stopped the call.

**To turn the advisor off entirely,** set `CLAUDE_CODE_DISABLE_ADVISOR_TOOL` to `1` under `"env"` in
`~/.claude/settings.json`, or remove `advisorModel`.

## What was not measured

- The bulk thresholds (5 items, 10 files, 20k tokens) are the owner's judgment.
- Teammates against a Workflow on the same job: no cost comparison was run here.
- Split-pane teammates (`teammateMode` other than in-process) were not probed; the docs say they
  ignore an agent file's `effort`.
- The advisor test used one task and at most 5 agents per arm, each started once.
- A worker with an advisor against a stronger worker alone was compared twice, on single read-only
  tasks: Sonnet with a Fable advisor on synthesis (2026-11-13), and Sonnet with an Opus advisor on
  synthesis and on one decision task (2026-11-14). Neither replaced Opus on synthesis, and on the
  decision task Sonnet alone was already near Opus ([evidence.md](evidence.md)). Opus with a Fable
  advisor was compared with Opus alone on that decision task: no difference shown, 47% more cost. No long chat,
  no other row and no other instruction about when to call the advisor was measured.
- An advisor call can fail. In the first comparison 3 of 8 runs report a call that timed out; in the
  second, 2 of 33 calls failed. A run goes on without the advice, and only the model's own words say so.
- The sentence was not tested on teammates, or on the built-in Explore and Plan agents.
- An advisor given only on the command line (the `--advisor` flag, or `--settings` with inline JSON)
  is not seen by the hooks, which read the environment variable and the settings files only.
  Measured 2026-11-13 in a real session started with inline settings: the line said `advisor=off`
  and a bare agent start passed. With the advisor named in a settings file, the same session's line
  said `advisor=fable`, the bare start was denied, and the model added the sentence and succeeded
  without asking the user.
