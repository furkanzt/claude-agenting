# Session settings: mode, disposition, workflows opt-in

All three belong to one chat continuum. They are keyed on `session_id`, which
survives compaction; a new conversation or `/clear` starts from the defaults
(`auto`; `balanced`, or the plan's disposition, below; and the workflows opt-in
the standing default names, else not opted in). On every SessionStart the hook
prints them in one `[agenting]` line together with the recorder path and the
session id. The same line carries `teammates=on|off`, the advisor and, when it
can be read, `plan=Pro|Max`: facts read from the environment and the settings
files, not values this plugin records.

## Recording a change

Record a change the moment the user makes it. An unrecorded change reverts at
the next compaction.

```
python3 "<recorder path from the [agenting] line>" --record --session <id> \
    [--mode auto|manual] [--disposition fast|balanced] [--workflows on|off]
```

`--status --session <id>` prints the recorded values. Use the recorder path the
`[agenting]` line prints: `${CLAUDE_PLUGIN_ROOT}` is not expanded inside a Bash
command you type yourself.

## Mode: auto | manual

| Mode | Who resolves the routing plan | What the guard does at Stage 2 | Work that fits "off the main chat" |
|---|---|---|---|
| `auto` (default) | You, from the table, disposition and project Rules | Steps aside with a system message. It never emits an allow, so the user's own permission settings for Workflow still apply. | Start it without asking; say in one line what runs where and on which tier |
| `manual` | The user, via AskUserQuestion | Denies until the approve command it printed has been run | Propose it and wait for the user's yes |

When work leaves the main chat, and by which vehicle, is in
[delegation.md](delegation.md). The mode only decides whether you ask first.

The user changes it in words ("switch to manual", "stop deciding for me",
"decide it yourself") or with `/agenting-mode auto|manual`.

A resumed or forked chat can get a new `session_id` without a new SessionStart
run, so nothing is recorded under the new id. The guard finds the mode anyway: it
follows the `[agenting]` line in the chat's own transcript to the id the chat
started under. That is why changes are recorded under the id the `[agenting]`
line prints, not under whatever id a later hook reports. The plan the guard shows
counts `agent()` call sites; a call inside a loop, `map()`, `parallel()` or
`pipeline()` runs more than once, so say so when you present it.

## Disposition: fast | balanced

Sets how auto mode leans when it decides. Users call it the mode ("fast mode",
"balanced mode"). A new chat starts in `balanced`, or in the plan's disposition
(next section), and stays where the user put it: it changes only on the user's
explicit request, in words ("go fast", "back to balanced") or with
`/agenting-mode <value>`. Claude never asks about it and never proposes a
change. That holds when auto keeps choosing opus too: under `balanced` that
means the work needs opus, and nothing counts or reports how often it happens.

Disposition is a standing lean, not a per-row pin:

| Disposition | Lean |
|---|---|
| `fast` | The cheaper pick wherever near-certainty isn't needed; still opus for a task that needs it |
| `balanced` | The routing table per task, no lean either way |

Baseline per disposition, and the cell the word "critical" picks for one job:

| Routing-table row | `fast` | `balanced` | "critical" |
|---|---|---|---|
| List / count | `haiku`/`medium` | `haiku`/`medium` | `haiku`/`medium` |
| Mechanical cleanup | `sonnet`/`low` | `sonnet`/`low` | `sonnet`/`low` |
| Read code/prose, report | `haiku`/`medium` | `haiku`/`medium` | `sonnet`/`high` |
| Prose→rules, classify, judge | `sonnet`/`low` | `sonnet`/`medium` | `sonnet`/`high` |
| Synthesize across many files | `opus`/`high` | `opus`/`xhigh` | `opus`/`xhigh` |
| Decide under BELİRSİZ | `sonnet`/`xhigh` | `sonnet`/`xhigh` | `opus`/`xhigh` |
| Adversarial verify/refute | `sonnet`/`high` | `sonnet`/`high` | `opus`/`high` |
| Architecture or approach decision | `opus`/`xhigh` | `opus`/`xhigh` | `opus`/`xhigh` |
| UI/UX design before a build | `opus`/`xhigh` | `opus`/`xhigh` | `opus`/`xhigh` |

**"critical" is a word for one job, not a setting.** When the user says a job
is critical ("critical: check these 40 answers", "this one must be right"),
route that job by the third column and say so in one line. Nothing is
recorded, and the next job is back on the session's disposition. Until 3.6.0
this column was a third disposition, `quality`; a chat recorded with it reads
as `balanced`, and its `[agenting]` line says what to say instead.

## The plan sets where a new chat starts

When the hook can read the account's plan, a chat seen for the first time starts
in `fast` on a Pro plan and in `balanced` on a Max plan. The `[agenting]` line
then reads `disposition=fast (set for the Pro plan)` and ends its facts with
`plan=Pro`, and Claude Code shows the user one line at that first start, for
example `[agenting] plan=Pro · mode=fast (set for your plan: cheaper models,
fewer agents). Change mode: /agenting-mode balanced`.

- The user is told by the hook. Add nothing and ask nothing; route by the
  disposition on the line.
- The user's own choice wins: once a disposition is recorded for the chat, the
  note is gone and the plan no longer plays a part in that chat.
- A project whose `agenting/AGENTING.md` names an `auto-disposition-default`
  made its own choice: the plan does not start chats there
  ([project-rules.md](project-rules.md)).
- No plan on the line means it could not be read (the fields are not
  documented): the chat starts in `balanced`, as before.
- List price is the yardstick behind `fast`. How a plan counts each model
  against its usage limit is not published, so "cheaper" here is a stand-in for
  "uses less of the limit".

`fast` and `balanced` are the measured cells (2026-10-06 and 2026-10-09, `evals/`).
For verification and BELİRSİZ `fast` and `balanced` use Sonnet: on the first round's items it matched
Opus on every measured run at about half the cost, and the closed-book gap in the vendor cards is knowledge, not
abstention discipline. That was a bounded null, and a later one was less clean: on 120 harder near-miss
unanswerable items (2026-10-10, `evals/results/REPORT-2026-10-10-E1.md`) Sonnet `xhigh` hallucinated 10 of 720
item-runs and Opus `xhigh` none of 360, so "critical" picks Opus; a pre-registered round on 120 fresh items (2026-10-11,
`evals/results/REPORT-2026-10-11-E1b.md`) then found Sonnet and Opus both clean (0 of 720 each), so `balanced` stays Sonnet. Haiku 5.5 does not get BELİRSİZ: at `high` it
hallucinated 11 of 720 on the same items, the same as Sonnet within noise and above the 1% line the pre-registered
rule set for `fast`, so `fast` reverted to Sonnet; `haiku`/`xhigh` made 5 of 720 there and 1 of 720 on the fresh items (Sonnet 0),
which failed the pre-registered "no more than Sonnet" test by one item-run, so `fast` stays Sonnet (moving it to `haiku`/`xhigh`,
13 times cheaper, would be the owner's overrule of that rule).
Training-knowledge traps did not trip any cell. The 16x cost gap holds for prompts under the 100K-token tier
(about 4x on input above it). A pinned effort is applied to Workflow
`agent()` calls and to plugin agents (checked 2026-10-09 from the effort recorded in
the subagent transcripts); an unpinned Haiku agent runs at its default `medium`, not
the session's effort. List/count uses Haiku 5.5 at `medium` in both dispositions (`low`
missed 6 of 36 exact-count runs). Read-and-report uses Haiku 5.5 at `medium` for
`fast` and `balanced` (measured on exact-answer lookups only); "critical" picks
`sonnet`/`high`. For
synthesis Sonnet does not match Opus (it missed a subtle planted item in 3 of 3
runs on one task), so `balanced` keeps `opus`/`xhigh`; `fast` uses
`opus`/`high`, which saves about a third and missed one planted item in 2 of 9
runs.

The two think-first rows are `opus`/`xhigh` in both dispositions (2026-11-13,
`evals/results/REPORT-2026-11-13.md`). On the architecture row every cell passed the easier task in
every run, and on the harder one Fable 5.2 passed 0 of 9 runs, Opus `xhigh` 2 of 6, Sonnet `xhigh`
1 of 3 and Opus `high` 0 of 3, so no cheaper cell earned `fast` and Fable 5.2 was not adopted. On the
UI/UX row the owner, blind, preferred the page built from Opus's design to the one from Fable 5.2's
in 8 of 12 pairs. No designer below Opus `xhigh` was tested for that row.

Deviate from the baseline per task, silently and in either direction, whenever
that task's own stakes call for it, including a different model rather than
only a different effort. A `fast` session still sends one calibration-critical
call to `opus`/`xhigh`; a `balanced` session may send one unusually consequential
classify call to opus. That latitude is what lets auto run unattended.

Precedence, strongest first: project Rules (`agenting/AGENTING.md`), then
disposition, then the routing table. A project's `auto-disposition-default`
sets its starting disposition (see [project-rules.md](project-rules.md)).

In manual mode the disposition stays recorded but unused: the plan you propose
follows the routing table and the project's Rules. It applies again once the
user switches back to auto.

## Workflows opt-in: on | off

Outside ultracode, Claude Code runs a Workflow only after the user opts in in
their own words. This flag makes a session-wide opt-in survive compaction. It
leaves routing unchanged.

- When the user says something like "use workflows for this session", record
  `--workflows on`. The `[agenting]` line then says so after every compaction,
  and you run Workflows for substantive tasks for the rest of this chat without
  asking again.
- When the user withdraws it ("no more workflows"), record `--workflows off`.
- Record `on` only from the user's own words. A one-off "use a workflow for
  this" covers that task alone and is not recorded; a task that merely looks
  workflow-shaped is not an opt-in.
- **Standing default.** When the user asks for Workflows in every chat
  ("always use workflows", `/agenting-mode workflows always`), record it once
  with `--record-default --workflows on` (no `--session`). Every chat that
  starts afterwards is seeded with it and its `[agenting]` line reads
  `workflows=on (standing: ...)`. `--record-default --workflows unset`
  (`/agenting-mode workflows never-default`) removes it. A chat that already
  has a record keeps its own value, and a per-chat `--workflows on|off` wins
  for that chat.
- Only a Workflow needs the opt-in. One agent, a clean run and teammates start
  under the mode alone. Without an opt-in, use those and say once that a
  Workflow would fit.
