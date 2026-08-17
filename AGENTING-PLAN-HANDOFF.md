# Agenting Rename & Auto-Mode Plan — Handoff

Recovered from session `1a3dbc8e` (crashed on an API 400 error at 10:01 on
2026-08-17, right after you asked for this handoff file and right after the
plan was locked). Reconstructed from the session transcript, merging every
correction from the Q&A trail so this reflects the **final** state, not the
first draft.

Status: **executed 2026-08-17.** Everything below was applied in full: the
rename (GitHub repo, plugin id, skill folder, commands), the mode/suggestion
axes and `agenting/` scaffold added to `SKILL.md`, the real
`/plugin marketplace add` + `/plugin install agenting@agenting` deploy
replacing the hand-copied files, and the three global-config diffs
(`~/.claude/settings.json`, `~/.claude/CLAUDE.md`, `~/.claude/check-setup.py`).
`scripts/check-setup.py` passes 24/24 from the real installed path. This
document is kept as the historical design record, not a pending plan.

---

## 1. Rename

| | Old | New |
|---|---|---|
| Plugin id | `agent-routing` | `agenting` |
| GitHub repo | `furkanzt/claude-agent-routing` | `furkanzt/claude-agenting` |
| Local directory | `projects-and-plugins/agent-routing` | `projects-and-plugins/agenting` |
| Skill folder | `skills/workflow-routing/` | `skills/agenting/` — `name:` frontmatter → `agenting`, description extended to cover mode + AGENTING.md |
| Commands | `/check-agent-routing` | `/agenting-check` (same script), plus new `/agenting-mode` |

- Hook filenames (`workflow-routing-guard.py`, `cache-tripwire.py`) stay
  as-is — internal, nobody types them directly.
- `plugin.json`, `marketplace.json`, `README.md`, `CHANGELOG.md` all get the
  new name throughout.
- Version bump to **2.0.0** (rename is a breaking change to the plugin id).
- **Fix found along the way:** the hook's Stage-2 deny message hardcodes
  `python3 ~/.claude/hooks/workflow-routing-guard.py --approve ...` as a
  literal string instead of deriving it from its own file path. Make it
  self-referential (`__file__`-based) so it's correct regardless of install
  location.

## 2. Deploy mechanism (fixes today's drift)

Confirmed live-vs-repo drift: `~/.claude/skills/workflow-routing/SKILL.md` is
missing everything from v1.1.0 and v1.2.0, and
`~/.claude/commands/check-agent-routing.md` differs too — real sessions have
been running stale instructions.

Fix: after the rename, properly `/plugin marketplace add` +
`/plugin install agenting@agenting`, remove the hand-copied files from
`~/.claude/{hooks,skills,commands}/`, and remove the two hardcoded hook
entries from `~/.claude/settings.json` (so the plugin's own `hooks.json`
registration is the only one — no double-firing). This touches the global
settings file — goes through the `update-config` skill's guidance at
execution time, diff shown before applying.

## 3. Session mode axis — manual / semi-auto / auto

- Lives in conversational memory only, resets every new session. No hook
  changes anywhere — the hook doesn't know or care how Claude arrived at a
  plan.
- Triggered by natural language (documented in SKILL.md) **and**
  `/agenting-mode [manual|semi-auto|auto]` (no arg = report current mode).
- **Auto**: never asks Stage-2's AskUserQuestion; decides the plan itself
  from the global tier table + this project's `agenting/AGENTING.md`, then
  self-records `--approve`.
- **Semi-auto**: auto-answers only workflow shapes matching an established
  precedent (§7); asks for anything novel.
- **Manual** (default): always asks, but the proposed default is shaped by
  precedent starting from the 1st occurrence.

## 4. Suggestion axis — independent of mode

Separate session flag. First time a task looks workflow-shaped, ask once:
*"This task is suitable for a workflow — want suggestions like this for the
rest of the session?"* Yes → later suitable tasks get suggested without
re-asking, for this session only. A project's `agenting/AGENTING.md`
presence marks it as suggestion-eligible; the per-session ask still gates it
each time. Config knob `suggestion-default`: `ask` (default, once/session),
`on` (skip the ask), `off` (never suggest).

## 5. Folder layout — `agenting/` (revised mid-plan)

Pivoted from two loose root files to a dedicated **`agenting/` folder** per
project, so it can hold more than two files later:

- **`agenting/AGENTING.md`** (curated, always read in full) — three parts:
  1. **Rules & Edge Cases** — hand-curated prose, never auto-written.
  2. **Config block** — structured, named, documented knobs a user can set
     per project without editing the plugin itself (see §6).
  3. **Learned Precedents** — auto-promoted one-liners, one per established
     task-shape, deduplicated.
- **`agenting/log.csv`** (raw, append-only, never read in full — grepped by
  exact `shape_key` only).

## 6. Config block knobs (in `AGENTING.md`)

- `promotion-threshold` — default `2`. User-sourced consistent answers
  needed to promote a precedent.
- `suggestion-default` — `ask` (default) / `on` / `off`.
- `matching-strictness` — only `exact` implemented in 2.0.0; the knob is
  reserved for future fuzzy matching — setting anything else prints a
  warning and falls back to exact rather than silently no-op'ing.

SKILL.md documents each knob and its default; Claude reads them before
applying its own defaults.

## 7. `agenting/log.csv` schema (corrected — advisor caught a real bug)

Original draft baked the *answer* (tiers) into the *key*
(`scan(haiku/low)x4,...`), which silently breaks the whole mechanic: two runs
of the same shape with different tier answers would get different keys, so
"conflicting answers → ask again" could never trigger, and "≥2 consistent"
would be trivially true for any key seen twice.

Fixed schema (comma is the column delimiter — use `|` and `;` inside fields,
never commas):

```
timestamp, source, shape_key, plan_signature, answer
2026-08-17T14:32Z, user, "scan:x4|analyze:x3|synthesize:x2", "haiku/lowx4|sonnet/mediumx3|opus/xhighx2", "scan=haiku/low;analyze=sonnet/medium;synthesize=opus/xhigh"
```

- `shape_key` = task-type composition only (the *question*) — built from
  each `agent()` call's `label`/`phase`, no tier info.
- `plan_signature` = the hook's existing tier-count signature
  (`haiku/lowx4|opus/xhighx2|...`) — kept for cross-reference only, untouched,
  and **not** the precedent-matching key. The hook's own approval cache still
  uses `plan_signature` exactly as today.
- `answer` = the resolved tier map (the *value*). Consistency is checked by
  comparing `answer` across rows sharing the same `shape_key`.

**Only `source:user` entries count toward the ≥2-consistent threshold.**
Otherwise semi-auto's own auto-answers would generate more "consistent"
evidence every run — the system laundering its own guesses into precedent.
`semi-auto`/`auto` entries stay in the log as audit trail but don't vote.

## 8. Log & git

`agenting/log.csv`: **commit by default**, gitignore only if you say
otherwise — asked once, at scaffold-creation time, the first time the CSV is
created in a project. (For *this* project you already said: commit it now.)
`agenting/AGENTING.md` itself is always committed, same as a CLAUDE.md would
be — not part of the ask.

## 9. Precedent mechanics

- Exact task-shape match (by `shape_key`), **≥2 user-sourced** consistent
  answers → promoted to Learned Precedents, semi-auto/auto auto-apply it.
  Conflicting answers = not consistent → ask again, newest becomes the
  latest data point.
- A single occurrence (even 1) already soft-biases the "as proposed" default
  shown in manual mode / semi-auto-on-novel-shapes.
- "Forget that precedent" / "that was wrong, redo as X" (natural language) →
  Claude edits the log/precedent entries directly. No dedicated command.

## 10. Scaffold creation (one atomic beat, first use in a project)

1. Ask the git-tracking question (§8).
2. Write `agenting/AGENTING.md` with Config block (including that answer).
3. Write `agenting/log.csv` header.
4. Append `.gitignore` entry if "gitignore" was chosen.

## 11. Global config migration (outside this repo — diff-and-approve, not silent edit)

Three files confirmed to hardcode the old name, beyond this repo:

1. **`~/.claude/settings.json`** — remove the two hardcoded hook entries
   (§2). Via `update-config` skill.
2. **`~/.claude/CLAUDE.md`** — hardcodes `skills/workflow-routing/` and
   `~/.claude/hooks/workflow-routing-guard.py`. The hook path needs updating
   regardless of the rename, since the real-plugin-install migration (§2)
   moves that file out of `~/.claude/hooks/` entirely.
3. **`~/.claude/check-setup.py`** — a **third**, broader copy of the health
   check (245 lines, *not* the same file as this repo's
   `scripts/check-setup.py`; it's the global "21 end-to-end checks" one your
   CLAUDE.md refers to). Hardcodes `workflow-routing` in multiple places
   (skill path, guard path, skill-glob). Hand-maintained, outside this
   repo's git history — show the diff before touching it, don't edit
   silently.

## 12. `scripts/check-setup.py` — new assertions (honest scope)

Most of the new behavior (mode tracking, precedent logic, suggestion opt-in)
is instruction-layer and genuinely can't be end-to-end tested the way the
hook is. New assertions cover only what's mechanically checkable:

- Commands exist.
- No stale `agent-routing` strings survive the rename.
- `agenting/AGENTING.md` / `agenting/log.csv` scaffold **template** (shipped
  with the plugin) is well-formed — validates the shipped template, not a
  search for a real project instance.
- The `--approve` path is self-referential.

Everything else gets documented as skill-guided (not hook-enforced) in the
CHANGELOG — same framing v1.1.0 used for its post-completion verification
section.

---

## Sign-off trail (from the crashed session)

- Plan matches intent: confirmed, with one addition — make the skill
  user-modifiable (→ led to §5/§6).
- Config-override mechanism: **structured Config block in AGENTING.md**
  (recommended option), not freeform-only.
- Log format: **CSV** (recommended option) over markdown.
- Log git-tracking: **commit by default**, ask once at scaffold time; commit
  now for this project.
- Final lock: **confirmed locked**, "just say go" — this is where the
  session crashed (API 400, `advisor_tool_result`/`server_tool_use`
  mismatch — unrelated to the plan content, a transport-layer error).

## Not yet done

Nothing in this plan has been executed. No renames, no GitHub changes, no
`~/.claude` edits, no scaffold files written. This document is the recovery
of the design only.
