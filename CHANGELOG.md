# Changelog

## 3.0.0 — 2026-09-23

### Migration from 2.x
- **`semi-auto` → `manual`.** Only `auto` and `manual` remain. A session whose
  state still records `semi-auto` is read as `manual` by both
  `session-continuity.py` and `workflow-routing-guard.py`, never as `auto`.
  `--mode semi-auto` is rejected.
- **`agenting/log.csv` is no longer written or read.** Existing files can be
  deleted. `templates/log.csv` is gone.
- **Learned Precedents become Rules.** `agenting/AGENTING.md` now has two
  sections, `## Rules` (hand-written) and `## Config`. When Claude meets a 2.x
  file it treats each precedent line as a Rule and offers once to move them
  under `## Rules`. The `promotion-threshold`, `matching-strictness` and
  `suggestion-default` knobs are gone; `auto-disposition-default` remains.
- **The suggestion axis is replaced by the workflows opt-in.** `--suggestion`
  is gone; `--record --session <id> --workflows on|off` records that the user
  opted in to Workflows for this chat. An old `suggestion` value is ignored,
  not converted: it recorded a different consent. It is dropped from the entry
  on the next `--record`.
- **Agents are addressed as `agenting:<name>`.** With the user-level copies
  removed, the plugin's agents are the only ones: `agentType:
  'agenting:researcher'` in a workflow script, `subagent_type:
  "agenting:researcher"` for a single `Agent` call. Delete any user-level
  copies left from an older install.
- **New hook, `workflow-finish-check.py`** on `UserPromptSubmit`, registered in
  `hooks/hooks.json`. Nothing to configure.

### Added
- **`hooks/workflow-finish-check.py`.** When a Workflow's completion
  notification arrives, it reads the run's `journal.jsonl` and, if any started
  agent has no result, adds `[agenting] Workflow "<name>": R of N agents
  returned; missing: <up to 8 labels>…` telling Claude to report the real count
  before presenting the result. Silent when every agent returned, on any other
  prompt, and on any error. An agent counts as missing only when neither its
  `agentId` nor its `key` has a result: the owner's reference run (23 started,
  18 result lines) turned out to be five interrupted attempts, each restarted
  under the same key and returned, so an agentId-only count would have raised
  a false alarm on a complete run. This replaces the skill's post-completion
  checklist, which ran only when someone remembered it (the gap 1.1.0 flagged).
- **Workflows opt-in** (`on`/`off`), persisted per session and re-injected
  after compaction. Outside ultracode, Claude Code runs a Workflow only after
  the user opts in in their own words; this flag makes a session-wide opt-in
  durable. It does not change routing.
- **`AGENTING_STATE_DIR`**: redirects both state files
  (`.agenting-session-state.json`, `.routing-approvals.json`) away from
  `~/.claude/`. Honoured by both hooks and `scripts/check-setup.py`.
- **`tests/`**: pipe tests for session-continuity, the routing guard and the
  finish check (`python3 -m pytest tests` or `python3 -m unittest discover -s
  tests`), with trimmed journal fixtures.

### Changed
- **SessionStart output is one line** (1,289 → 430 characters with the same
  install path and session id): `[agenting] mode=… · disposition=… ·
  workflows=… (session <id>). Record changes: … Load the agenting skill before
  authoring a Workflow.` `--status` prints the same summary.
- **The skill was restructured** along the writing-great-skills method:
  `SKILL.md` (38,073 → 7,811 characters) keeps the routing table, the launch
  procedure, deliberate inheritance, single `Agent` calls and the finish-check
  response; modes, disposition and the workflows opt-in moved to
  `reference/modes.md`, the rules file to `reference/project-rules.md`;
  history, enforcement internals and the dated verified facts moved to the
  README. The description went from 1,383 to 312 characters, dropping the
  triggers the hooks now cover by naming the skill in their own output.
- The guard's Stage-1 message shows both routing forms, including
  `agentType: 'agenting:<name>'`; Stage 2 names the mode and the skill.
- `scripts/check-setup.py`: updated for the one-line message, `--workflows`
  and the two-section template; the `log.csv` template check is gone; a new
  check keeps the removed 2.x vocabulary from resurfacing.

## 2.1.0 — 2026-09-18

### Changed
- **Session mode default flipped `manual` → `auto`.** Stage 2 now self-decides
  by default instead of always asking; switch back with `/agenting-mode
  manual` or plain language. It's now **persisted per chat continuum** (see
  `hooks/session-continuity.py` below) instead of conversational-memory-only,
  so a mode change survives compaction instead of depending on a compaction
  summary happening to mention it.
- **Stage 2's enforcement gate itself now drops its approval requirement in
  `auto` mode.** Before this release, `auto` only changed *who* answered
  Stage 2 — the `PreToolUse` hook still denied every new plan until an
  explicit `--approve` was run, a mechanical round-trip regardless of mode.
  `workflow-routing-guard.py` now reads this session's recorded mode and,
  only when it's explicitly `"auto"`, prints a plain `systemMessage` note
  instead of denying — with **no `permissionDecision` field, deliberately
  never `"allow"`**: this hook's job is routing approval only, and
  `permissionDecision: "allow"` would override the user's own Claude Code
  permission settings for the `Workflow` tool itself, a separate, user-owned
  decision this plugin has no business making for them. A **missing** entry
  does **not** trigger this — an install where the new hook isn't wired up
  degrades safely to the pre-2.1.0 approval-required behavior. `semi-auto`/
  `manual` are unaffected; Stage 1 (routing presence) is never bypassable by
  any mode.
- **The suggestion axis (want workflow suggestions this session?) is now
  persisted the same way** instead of resetting every session — still asked
  lazily, once, the first time a task looks workflow-shaped.

### Added
- **`hooks/session-continuity.py`** — a new `SessionStart` hook (fires on
  `startup`/`resume`/`compact`/`clear`) that carries mode, disposition, and
  the suggestion axis in a small per-`session_id` state file
  (`~/.claude/.agenting-session-state.json`, same directory as the routing
  guard's own `.routing-approvals.json`). It never asks anything itself: it
  silently seeds defaults for a session_id it has never seen, and silently
  re-injects whatever's already recorded on every later firing. Verified
  empirically before building on it: `session_id` stays stable across
  compaction of the same conversation (checked three compaction events
  spanning ~9 hours in a real transcript, all one id); resume
  (`--resume`/`--continue`) is *assumed* stable by Claude Code's own design
  but not independently checked — if that assumption is ever wrong, the
  failure mode is a fresh default or one re-ask, not silent data loss.
  `/clear` is handled explicitly as a fresh continuum.
- **Auto disposition axis** (`fast` / `balanced` / `quality`, default
  `balanced`) — a standing cost/accuracy target, not a per-row pin: `fast`
  ~90–95% reliability (default cheap, still reaches for `opus` when one task
  needs it), `balanced` ~95–99% (follows the baseline table per task shape,
  the routing table's existing per-task variance), `quality` ~99%+ (defaults
  toward paying for certainty). `auto` has standing, silent authority to
  deviate from the baseline per task in either direction — including a
  different model, not just a different effort — whenever that task's own
  stakes call for it, specifically so it can run unattended without asking
  permission on ordinary judgment calls. **This axis is never asked about,
  anywhere, ever** — it defaults to `balanced` and only changes on explicit
  user request (natural language or `/agenting-mode <disposition>`); Claude
  never proposes a change, and there is deliberately no tracking of how often
  `quality`/`fast`-tier picks happen — a project needing `opus` a lot under
  `balanced` is the mechanism working, not a signal. New project Config knob:
  `auto-disposition-default` (`fast`/`balanced`/`quality`, no `ask` value —
  there's no ask to skip) overrides the global `balanced` default per project.
- **`/agenting-mode`** now reports and sets all three axes, reads ground
  truth via the hook's `--status` flag instead of conversational recall, and
  requires each change to be persisted via `--record` (an unpersisted change
  reverts on the next compaction — the command's own instructions say so).

### Design notes
- Mode is no longer purely instruction-layer — the hook mechanically
  re-injects it every `SessionStart`, and the guard mechanically reads it to
  enforce the `auto` bypass (the guard never reads disposition; that value
  only ever shapes what tiers Claude itself writes into a script, not
  anything the gate checks). Disposition's *default* is likewise
  hook-enforced (seeded `balanced`, never left unset), but a project's
  `auto-disposition-default` pin, the suggestion axis's lazy ask, and
  whether Claude actually honors any of this remain instruction-layer, same
  as the post-completion verification check.
- **Disposition's ask mechanism went through three designs in one session
  before landing on "no ask at all," each corrected directly by the user
  rather than guessed at:** (1) asked unconditionally at every `SessionStart`
  regardless of relevance — rejected as too eager; (2) moved to a lazy ask
  right before `auto`'s first self-decided plan, with silent per-task
  deviation but a permission-ask if a task "disagreed with" a pinned
  default — rejected because that still needed a human check-in on ordinary
  per-task judgment, defeating the entire point of a disposition; a
  pattern-level drift tracker was floated to replace that per-task ask and
  also rejected — "if it works, it works," no tracking, no escalation; (3)
  final: no ask, no tracking, `balanced` by default, changed only on
  explicit request. A separate, unrelated defect was caught by a second
  advisor pass in the same session: the gate's new bypass had first been
  implemented as `permissionDecision: "allow"`, which overrides the user's
  own Claude Code permission settings for `Workflow`, not just this plugin's
  routing opinion — fixed to a bare `systemMessage` with no
  `permissionDecision` field, matching the pre-existing pass-through cases.
- The installed plugin lives in a **versioned** cache directory
  (`~/.claude/plugins/cache/agenting/agenting/<version>/`), confirmed by
  inspection to be a real copy, not a symlink to this working tree — so the
  new state file's path is fixed at `~/.claude/`, not relative to the hook
  script, or it would orphan on every version bump.

## 2.0.0 — 2026-08-17

### Renamed
- **Plugin id `agent-routing` → `agenting`.** GitHub repo, local directory,
  and skill folder (`skills/workflow-routing/` → `skills/agenting/`) follow.
  `/check-agent-routing` → `/agenting-check` (same script). Hook filenames
  (`workflow-routing-guard.py`, `cache-tripwire.py`) are unchanged — internal,
  nobody types them directly.
- The hook's Stage-2 `--approve` command is now **self-referential**
  (`SELF_PATH = os.path.abspath(__file__)`) instead of a hardcoded
  `~/.claude/hooks/workflow-routing-guard.py` string, so it prints the right
  command regardless of where the plugin is actually installed.

### Added
- **Session mode axis** (`manual` / `semi-auto` / `auto`) — how much of the
  Stage-2 approval question you answer yourself vs. hand to the user. Lives in
  conversational memory only, resets every session, set by natural language or
  the new **`/agenting-mode`** command.
- **Suggestion axis** — an independent, also session-only opt-in for Claude to
  proactively flag workflow-shaped tasks, gated by a once-per-session ask
  unless overridden by the `suggestion-default` config knob.
- **Per-project routing memory** — a project-root `agenting/` folder:
  `AGENTING.md` (curated, always read in full: hand-written Rules & Edge
  Cases, a structured Config block, and auto-promoted Learned Precedents) and
  `log.csv` (raw, append-only, grepped by exact `shape_key`, never read
  whole). Shipped scaffold templates at `templates/AGENTING.md` and
  `templates/log.csv`. A task-shape reaching `promotion-threshold` (default 2)
  consistent `user`-sourced answers gets promoted to a Learned Precedent that
  `semi-auto`/`auto` then apply without asking; `semi-auto`/`auto` rows stay
  in the log as an audit trail but never vote, so the system can't launder its
  own guesses into precedent.
- **`scripts/check-setup.py`** — new "Rename integrity" section: the two new
  commands exist, no stale `agent-routing` string survives anywhere in the
  plugin, the shipped scaffold templates are well-formed, and the
  self-referential `--approve` fix actually holds against the real hook.

### Design notes
- Most of this release is **instruction-layer, not hook-enforced** — the mode
  axis, the suggestion axis, and the precedent-promotion logic all live in the
  `agenting` skill and are honored only when it's loaded, the same honesty
  `check-setup.py` already applies to the post-completion verification section
  added in 1.1.0. Only what's mechanically checkable (files exist, templates
  parse, the guard's own behavior) got a real assertion.
- `log.csv`'s schema deliberately splits `shape_key` (the task-type
  composition — the question) from `answer` (the resolved tier map). An
  earlier draft keyed precedents on tiers directly; caught in design review
  before shipping, because that bakes the answer into the key, so no two
  routings of the same shape could ever conflict and the promotion threshold
  would measure nothing but its own repetition.
- Deploy mechanism fixed alongside the rename: install is now a real
  `/plugin marketplace add` + `/plugin install agenting@agenting` rather than
  the hand-copied `~/.claude/{hooks,skills,commands}/` setup that had already
  drifted stale (live `SKILL.md` was missing the 1.1.0 and 1.2.0 sections).

## 1.2.0 — 2026-08-10

### Added
- **`hooks/cache-tripwire.py`** — a `UserPromptSubmit` hook that reports the
  token cost paid when a mid-session model or effort switch invalidates the
  prompt cache prefix. Compares the session's current tier against the last
  tier this hook already reported (tracked in a small per-session state file
  next to the script); fires once per distinct switch, never blocks. Measured
  case: a sonnet/high → opus/max switch mid-session rewrote 66,975 tokens on
  the very next turn.
- **`scripts/measure-tokenomics.py`** — recomputes the main/agent cost split,
  average context size, spawn tax, and effort distribution from real
  `~/.claude/projects` transcripts, using the same dedup method (last line per
  `message.id`, not raw line count) used to derive the numbers now documented
  in the `workflow-routing` skill's "Verified facts" section.
- **"Verified facts (2026-08-10)"** section in the `workflow-routing` skill —
  dedup method, spawn-tax median (~$0.11/spawn, ~2-3 turn break-even for
  delegating), cache-key-includes-effort behavior, and the effort-distribution
  shift since this skill shipped (subagent `max` 57% → 1%, `high` 15% → 57%).
- **"Recommended settings" section in the README** — when
  `ENABLE_PROMPT_CACHING_1H` is worth the 2x cache-write premium (paced,
  human-gap sessions) versus not (uninterrupted automation), and a
  copy-paste "delegate large reads" rule template for a project's own
  `CLAUDE.md`.

## 1.1.0 — 2026-08-07

### Added
- **Post-completion verification section in the `workflow-routing` skill.**
  Routing was covered end to end but only up to launch; nothing said what to
  do once a `Workflow` call returns. Prompted by a real incident: three
  workflows each reported a coherent-looking summary after completing, built
  by silently filtering out every agent that didn't return — one run's
  headline numbers were computed from 38 of 122 agents, the other 84 having
  died mid-run with no trace in the summary. Caught only because the user
  asked directly. The new section is a standing checklist — read
  `agents_done` vs `agent_count`, cross-check the raw `journal.jsonl` against
  the tool result's own claims, distinguish a live queued agent from a dead
  one by transcript mtime, read a stalled agent's last few records before
  assuming failure vs. a session-limit kill, and recover missing pieces by
  scope rather than blindly re-running the same call.
- Noted explicitly that this is a skill, not a hook: nothing forces a re-read
  of it at workflow-completion time the way `workflow-routing-guard.py`
  forces routing at launch time. If it keeps getting skipped in practice, a
  `PostToolUse` hook on `Workflow` mirroring the existing gate is the durable
  fix — flagged as a future option, not built yet.

## 1.0.0 — 2026-08-06

First release.

### Added
- **Two-stage `PreToolUse` gate on the Workflow tool.**
  Stage 1 denies any Workflow whose `agent()` calls lack `model`/`agentType` or
  lack `effort`, naming the offending line numbers. Stage 2 denies until the
  user approves that specific routing plan in that session; approval is keyed by
  plan signature, so a repeat is silent and a change re-asks.
- **20 tiered agent definitions**, every one carrying both `model` and `effort`,
  spanning `haiku/low` through `opus/xhigh`.
- **`scanner`** (haiku/low) — inventory agent with a no-silent-zeroes rule.
- **`text-mechanic`** (haiku/low) — mechanical text repair with an
  output ⊆ input invariant and a mandatory closing audit.
- **`workflow-routing` skill** — tier table, decision procedure, and the rule
  that the gate must always offer *higher quality* as well as *cheaper*.
- **`external-model-options.md`** — cost comparison against non-Claude tiers,
  with the volume threshold below which a second vendor is not worth its
  maintenance.
- **`scripts/check-setup.py`** and **`/check-agent-routing`** — an end-to-end
  health check that runs the guard rather than reading configuration.

### Design notes
- Single `Agent` calls are deliberately **not** gated: one agent is bounded and
  cheap, and every shipped definition already pins both fields.
- The gate is not a cost-cutting tool. On a cheap session the risk is
  *under-powering*, so the approval prompt leads with the upgrade option there
  and with the downgrade option on an expensive session.
- `// routing: inherit` marks a call that should take the session's tier, so
  deliberate inheritance stays visible in the script instead of being invisible.
