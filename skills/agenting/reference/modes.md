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
    [--mode auto|manual] [--disposition cheapest|fast|balanced] [--workflows on|off]
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

## Disposition: cheapest | fast | balanced

Sets how auto mode leans when it decides. Users call it the mode ("fast mode",
"balanced mode"). A new chat starts in `balanced`, or in the plan's disposition
(below), and stays where the user put it: it changes only on the user's
explicit request, in words ("go fast", "cheapest mode", "back to balanced") or
with `/agenting-mode <value>`. Claude never asks about it and never proposes a
change. That holds when auto keeps choosing opus too: under `balanced` that
means the work needs opus, and nothing counts or reports how often it happens.

Disposition is a standing lean, not a per-row pin:

| Disposition | Lean |
|---|---|
| `cheapest` | The cheapest cell that passes the owner's bar on every row, with what it loses written down below; the agent rules of `fast` |
| `fast` | The cheaper pick wherever near-certainty isn't needed; still opus for a task that needs it; fewer agents ([delegation.md](delegation.md)) |
| `balanced` | The routing table per task, no lean either way |

Baseline per disposition, and the cell the word "critical" picks for one job:

| Routing-table row | `cheapest` | `fast` | `balanced` | "critical" |
|---|---|---|---|---|
| List / count | `haiku`/`medium` | `haiku`/`medium` | `haiku`/`medium` | `haiku`/`medium` |
| Mechanical cleanup | `sonnet`/`low` | `sonnet`/`low` | `sonnet`/`low` | `sonnet`/`low` |
| Read code/prose, report | `haiku`/`medium` | `haiku`/`medium` | `haiku`/`medium` | `sonnet`/`high` |
| Prose→rules, classify, judge | `haiku`/`xhigh` | `sonnet`/`low` | `sonnet`/`medium` | `sonnet`/`high` |
| Synthesize across many files | `opus`/`high` | `opus`/`high` | `opus`/`xhigh` | `opus`/`xhigh` |
| Decide under BELİRSİZ | `haiku`/`xhigh` | `haiku`/`xhigh` | `haiku`/`xhigh` | `opus`/`xhigh` |
| Adversarial verify/refute | `haiku`/`xhigh` | `sonnet`/`high` | `sonnet`/`high` | `opus`/`high` |
| Architecture or approach decision | `sonnet`/`xhigh` | `opus`/`xhigh` | `opus`/`xhigh` | `opus`/`xhigh` |
| UI/UX design before a build | `opus`/`xhigh` | `opus`/`xhigh` | `opus`/`xhigh` | `opus`/`xhigh` |
| Plan a build and write its tests | `sonnet`/`high` | `sonnet`/`high` | `opus`/`high` | `opus`/`high` |
| Bulk coding against tests that exist | `haiku`/`medium` | `haiku`/`medium` | `haiku`/`medium` | `sonnet`/`low` |
| Review a build | `haiku`/`xhigh` | `sonnet`/`high` | `sonnet`/`high` | `opus`/`high` |

**"critical" is a word for one job, not a setting.** When the user says a job
is critical ("critical: check these 40 answers", "this one must be right"),
route that job by the last column and say so in one line. Nothing is
recorded, and the next job is back on the session's disposition. Until 3.6.0
this column was a third disposition, `quality`; a chat recorded with it reads
as `balanced`, and its `[agenting]` line says what to say instead.

**The owner's bar** (2026-11-14) decides a cell in `cheapest` and `fast`. It
reads the measured cost per finished task, never the price list:

- checked work (a test or a validator catches a wrong result): the cheapest
  cell per finished task, every retry counted, at most three tries;
- unchecked work: at most about 1 failed run in 10, with what goes wrong
  written down;
- don't-guess and verify: at most about 1 wrong answer in 100.

`cheapest` takes the cheapest cell inside that bar. `fast` keeps a safer cell
on three rows, by the owner's choice: classify, verify (with review) and the
architecture decision.

**What `cheapest` gives up,** from the stored runs
(`evals/results/REPORT-2026-11-15-fast-column.md`):

- Classify on Haiku `xhigh`: 4.1% wrong labels (35 of 864) against Sonnet
  `low`'s 2.8%, a label on an item that should get none in 16 of 144, and 3 of
  36 runs failed, all on one task. 71 seconds a run against 10.
- Verify on Haiku `xhigh`: 1 false "confirmed" in 384 verdicts against 0 in
  480, and every Haiku mistake sits on one task of three. 87 seconds against
  26. Review follows verify and was not measured itself.
- The architecture decision on Sonnet `xhigh` rests on six runs: 2 failed, the
  same share as Opus `xhigh`'s 4 of 12.
- Haiku at `xhigh` is the slowest cell of its rows. `cheapest` means cheaper at
  list price, not quicker.

## The plan sets where a new chat starts

When the hook can read the account's plan, a chat seen for the first time starts
in `fast` on a Pro plan and in `balanced` on a Max plan. The `[agenting]` line
then reads `disposition=fast (set for the Pro plan)` and ends its facts with
`plan=Pro`, and Claude Code shows the user one line at that first start, for
example `[agenting] plan=Pro · mode=fast (set for your plan: cheaper models,
fewer agents). Tip: run this chat on Sonnet at high effort (/model sonnet, then
/effort high). For a design decision use Opus at xhigh effort, in a new chat or
at a break in the work: every model switch throws away the chat's cache, so do
not switch back and forth. Change mode: /agenting-mode [cheapest|fast|balanced]`.

- The user is told by the hook. Add nothing and ask nothing; route by the
  disposition on the line.
- The user's own choice wins: once a disposition is recorded for the chat, the
  note is gone and the plan no longer plays a part in that chat.
- No plan starts a chat in `cheapest`. Only the user's word or a project's
  default sets it, because it runs classify and verify on the cell with the
  most mistakes.
- A project whose `agenting/AGENTING.md` names an `auto-disposition-default`
  made its own choice: the plan does not start chats there
  ([project-rules.md](project-rules.md)).
- No plan on the line means it could not be read (the fields are not
  documented): the chat starts in `balanced`, as before.
- The tip's model and effort are `fast`'s cell for planning and writing tests.
  Its warning is a fact about the cache: the cache belongs to one model, so a
  switch makes the next turn pay the full input price for the whole chat.
- List price is the yardstick behind `fast` and `cheapest`. How a plan counts
  each model against its usage limit is not published, so "cheaper" here is a
  stand-in for "uses less of the limit".

## Where the cells come from

`fast` and `balanced` are the measured cells (2026-10-06 and 2026-10-09, `evals/`); `cheapest` is read from the
same stored runs by the owner's bar (2026-11-15).
For verification `fast` and `balanced` use Sonnet: on the first round's items it matched
Opus on every measured run at about half the cost, and the closed-book gap in the vendor cards is knowledge, not
abstention discipline. "critical" picks Opus.

For BELİRSİZ every disposition uses Haiku 5.5 at `xhigh` since 2026-11-15. Pooled over 84 runs on eleven tasks it
invented 6 answers in 1,848 unanswerable items against Sonnet `xhigh`'s 10 on the same items and runs, at a tenth
of the cost; it missed or got wrong 2 of 1,056 answerable items (Sonnet 0) and takes 57 seconds a run against 36.
That is the owner's overrule of two earlier readings, on the pooled count. On 120 harder near-miss unanswerable
items (2026-10-10, `evals/results/REPORT-2026-10-10-E1.md`) Haiku `high` hallucinated 11 of 720 item-runs, Sonnet
`xhigh` 10 of 720 and Opus `xhigh` none of 360; `haiku`/`xhigh` made 5 of 720 there. On 120 fresh items
(2026-10-11, `evals/results/REPORT-2026-10-11-E1b.md`) Sonnet and Opus were both clean (0 of 720 each) and
`haiku`/`xhigh` made 1 of 720, which failed the pre-registered "no more than Sonnet" test of that round by one
item-run. Haiku at `high` stays out: on the two hardest tasks it failed 9 of 12 runs, `xhigh` 4 of 12. "critical"
picks Opus `xhigh`, which invented none of 1,182.
Training-knowledge traps did not trip any cell. The 16x cost gap holds for prompts under the 100K-token tier
(about 4x on input above it). A pinned effort is applied to Workflow
`agent()` calls and to plugin agents (checked 2026-10-09 from the effort recorded in
the subagent transcripts); an unpinned Haiku agent runs at its default `medium`, not
the session's effort. List/count uses Haiku 5.5 at `medium` in every disposition (`low`
missed 6 of 36 exact-count runs). Read-and-report uses Haiku 5.5 at `medium` in every
disposition (measured on exact-answer lookups only); "critical" picks
`sonnet`/`high`. For
synthesis Sonnet does not match Opus (it missed a subtle planted item in 3 of 3
runs on one task), so `balanced` keeps `opus`/`xhigh`; `fast` and `cheapest` use
`opus`/`high`, which saves about a third and missed one planted item in 2 of 9
runs.

The two think-first rows are `opus`/`xhigh` in `fast` and `balanced` (2026-11-13,
`evals/results/REPORT-2026-11-13.md`). On the architecture row every cell passed the easier task in
every run, and on the harder one Fable 5.2 passed 0 of 9 runs, Opus `xhigh` 2 of 6, Sonnet `xhigh`
1 of 3 and Opus `high` 0 of 3, so no cheaper cell earned `fast` and Fable 5.2 was not adopted;
`cheapest` takes Sonnet `xhigh` there on those six runs, by the owner's choice. On the
UI/UX row the owner, blind, preferred the page built from Opus's design to the one from Fable 5.2's
in 8 of 12 pairs. No designer below Opus `xhigh` was tested for that row.

The three build rows come from the coding experiment of 2026-11-14 and 2026-11-15
(`evals/results/REPORT-2026-11-15-coding.md`), six real changes from the owner's projects.
Bulk coding is Haiku 5.5 at `medium` in every disposition: with tests in place it was correct in 24 of 24 runs
at $0.03 a task, against $0.16 for Sonnet `low` and $0.71 for Opus `high`. For the plan and the tests, Sonnet
`high` wrote a usable suite in 12 of 12 runs at $0.48 and Opus `high` in 11 of 12 at $1.21. The pre-registered
rule named Opus `high` for both modes, because Sonnet's usable suites rejected correct code in 14% of pairs
against 7% and the rule allows 10%. `balanced` follows the rule. `fast` and `cheapest` take Sonnet `high` by the
owner's overrule of 2026-11-15: counted over all twelve suites of each, usable or not, the two reject about the
same share (14% and 15%), and four suites a model and task cannot rank them. Review was not measured and follows
verify. Limits to carry: six tasks whose brief already named the files, 178 of 180 coding runs correct, so the
cells are told apart by cost, not by skill.

## Deviating, and what wins

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
