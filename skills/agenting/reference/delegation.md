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

## What was not measured

- The bulk thresholds (5 items, 10 files, 20k tokens) are the owner's judgment.
- Teammates against a Workflow on the same job: no cost comparison was run here.
- Split-pane teammates (`teammateMode` other than in-process) were not probed; the docs say they
  ignore an agent file's `effort`.
