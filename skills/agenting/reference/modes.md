# Session settings: mode, disposition, workflows opt-in

All three belong to one chat continuum. They are keyed on `session_id`, which
survives compaction; a new conversation or `/clear` starts from the defaults
(`auto`, `balanced`, not opted in). On every SessionStart the hook prints them
in one `[agenting]` line together with the recorder path and the session id.

## Recording a change

Record a change the moment the user makes it. An unrecorded change reverts at
the next compaction.

```
python3 "<recorder path from the [agenting] line>" --record --session <id> \
    [--mode auto|manual] [--disposition fast|balanced|quality] [--workflows on|off]
```

`--status --session <id>` prints the recorded values. Use the recorder path the
`[agenting]` line prints: `${CLAUDE_PLUGIN_ROOT}` is not expanded inside a Bash
command you type yourself.

## Mode: auto | manual

| Mode | Who resolves the routing plan | What the guard does at Stage 2 |
|---|---|---|
| `auto` (default) | You, from the table, disposition and project Rules | Steps aside with a system message. It never emits an allow, so the user's own permission settings for Workflow still apply. |
| `manual` | The user, via AskUserQuestion | Denies until the approve command it printed has been run |

The user changes it in words ("switch to manual", "stop deciding for me",
"decide it yourself") or with `/agenting-mode auto|manual`.

## Disposition: fast | balanced | quality

Sets how auto mode leans when it decides. It starts at `balanced` and stays
where the user put it: it changes only on the user's explicit request, in words
("quality mode", "go fast on this one") or with `/agenting-mode <value>`. Claude
never asks about it and never proposes a change. That holds when auto keeps
choosing opus too: under `balanced` that means the work needs opus, and nothing
counts or reports how often it happens.

Disposition is a standing reliability target, not a per-row pin:

| Disposition | Target | Lean |
|---|---|---|
| `fast` | ~90–95% | The cheaper pick wherever near-certainty isn't needed; still opus for a task that needs it |
| `balanced` | ~95–99% | The routing table per task, no lean either way |
| `quality` | ~99%+ | Pay for extra certainty even where a cheaper tier could plausibly do the job |

Baseline per disposition:

| Routing-table row | `fast` | `balanced` | `quality` |
|---|---|---|---|
| List / count / mechanical | `haiku`/`low` | `haiku`/`low` | `haiku`/`low` |
| Read code/prose, report | `sonnet`/`low` | `sonnet`/`medium` | `sonnet`/`high` |
| Prose→rules, classify, judge | `sonnet`/`low` | `sonnet`/`medium` | `sonnet`/`high` |
| Synthesize across many files | `opus`/`xhigh` | `opus`/`xhigh` | `opus`/`xhigh` |
| Decide under BELİRSİZ | `opus`/`xhigh` | `opus`/`xhigh` | `opus`/`xhigh` |
| Adversarial verify/refute | `opus`/`high` | `opus`/`high` | `opus`/`high` |

Deviate from the baseline per task, silently and in either direction, whenever
that task's own stakes call for it, including a different model rather than
only a different effort. A `fast` session still sends one calibration-critical
call to `opus`/`xhigh`; a `quality` session may send one unusually consequential
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
