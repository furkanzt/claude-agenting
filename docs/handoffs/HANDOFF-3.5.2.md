# Handoff: agenting 3.5.2 (fan-out view)

Date: 2026-11-03. Status: **pushed** to `origin/main`. Installed on the owner's machine via
`claude plugin update agenting@agenting` (3.5.0 → 3.5.2; a restart applies it, `/reload-plugins` is not enough).

Master handoff for the whole plugin: [../../HANDOFF.md](../../HANDOFF.md). This file covers only the fan-out view
(`hooks/fanouts/`) since 3.5.0.

## What changed

| Release | Commit (on main) | What |
| --- | --- | --- |
| 3.5.1 | `79ff092` | `/fanouts` is registered `immediate`, so it runs while a turn is in flight (as `/rename` does). A queued call's unknown effort no longer hides a phase's shared effort in the column title. |
| 3.5.1 | `cc9a226` | Version bump, CHANGELOG, HANDOFF. |
| 3.5.2 | `c1dbe66` | Each band row is a plain `Button` with a digit `hotkey` (1–3), drawn by the engine as `1: ◯ name …`. Typing the digit into an empty prompt presses that row and opens the pane, idle or mid-turn. The row is clipped to the band's width (`bandRow()` in `view.ts`), so it no longer wraps beside a docked pane. |
| 3.5.2 | `bd6351f` | Version bump (plugin.json, marketplace.json), CHANGELOG, HANDOFF. |
| — | `b007ee7` | HANDOFF: 3.5.1 and 3.5.2 marked as pushed. |

Why: the owner could not make `ctrl+x tab, enter` work; it was the only keyboard way into the pane. Probable cause (not
verified): holding ctrl through the tab sends ctrl+tab, which the terminal takes. A digit needs no chord.

## Where the code is

- `hooks/fanouts/register.tsx`: the band hook (`ui.render` on `AbovePrompt`, rows with `hotkey={String(i + 1)}`),
  `panelRow()` (uses `bandRow`), the pane, `/fanouts` (`command.register`, `immediate: true`).
- `hooks/fanouts/view.ts`: `bandRow()`, `clip()`, `HOTKEY_CELLS = 3`, `bandStats()`, `bandFanouts()`.
- `hooks/fanouts/look.ts`: glyphs and words copied from Claude Code 2.1.317.
- `scripts/fanout_scan.py`: the read-only scanner (unchanged in these releases).
- `features/fanout-view.feature`: new scenarios: "Typing a band row's digit into an empty prompt…" and
  "Beside a docked pane the band row is clipped, never wrapped".
- `README.md` (Keys paragraph) and `skills/agenting/reference/fan-outs.md` describe the digit.

## Tests and checks (at 3.5.2)

- `python3 scripts/quality/run_plugin_tests.py`: 48 pass (`tests/fanouts.test.tsx`). Two new tests:
  "each band row carries its digit…" and "beside a docked pane the band row is clipped…".
- Red-proof done: removing `hotkey` fails the band-row test and the digit test; removing the clip fails the clip test.
- `python3 -m pytest tests -q`: 615 passed (run before the HANDOFF-only commit).
- `python3 -m pytest tests/test_catalogue_integrity.py`: 49 pass.
- Matrix regenerated: 831 scenarios, 582 armed, 249 gap (pre-existing gaps, unchanged).
- `claude plugin validate .`: passes with two warnings that predate this work: root `CLAUDE.md` is not loaded as
  context, and no plugin icon.

## How it was checked on a real screen

Harness (not in the repo): `scratchpad/screen/drive.py`, a pty + pyte driver for a hidden
`claude --model haiku --plugin-dir <repo>` session. Demo runs: `scratchpad/demo/bin/clean_runtime.mjs`
(a fake runtime, no model cost). Captured with the repo's code at 120 columns:

- Idle: the row reads `1: ◯ show-me  ██░░…  2/14 · 39s · ↓ 334.0k tokens · clean fan-out`; `1` opened the pane; esc
  closed it; the prompt stayed empty.
- Mid-turn (Haiku counting to 1500): `1` opened the pane; esc closed it; `/fanouts` opened it at once.

Not yet checked: a real wide terminal (the user's own), Ghostty's `█░` bar with the digit, and the `1` key with a
survey on screen (the band yields to surveys by design).

## Known limits and open items

1. **A `1` typed as the first character of an empty prompt opens the pane** while a row shows. It cannot type the
   message starting with "1". This is the trade-off the owner accepted; revisit if it bites.
2. **Keyboard: ctrl+x tab, enter** still works but was not the fix; the digit replaced it as the main way in.
3. **Keybinding route, unverified:** `~/.claude/keybindings.json` accepts `"command:<name>"` in the Chat context
   (read from the 2.1.317 engine source). It was not tried on a screen. A mod cannot ship its own key binding.
4. **Engine version drift:** the look is copied from 2.1.317. A newer Claude Code may change the bar, the digit
   prefix or the `/workflows` layout. The pane shows a dim note when the running version differs.
5. **Scanner limits** (unchanged): it reads `ps` and the run folders; it writes nothing; a run whose folder cannot be
   resolved shows as `unknown`.
6. **Working tree, not committed (on purpose):** `.gitignore` carries an impeccable change from another task. Never
   commit it with this work. Engine-written `tsconfig.json` and `.claude-plugin/types/` appear whenever
   `--plugin-dir` loads the repo; delete them before any commit.

## How to re-check after a change

1. `python3 scripts/quality/run_plugin_tests.py` (48 tests).
2. `python3 -m pytest tests -q` (about 100 s).
3. `claude plugin validate .` (two known warnings).
4. Screen check: start a demo run
   `node <scratchpad>/demo/bin/clean_runtime.mjs demo_workflow.js --out <scratchpad>/demo/runs/<unique-name>`
   (check `ps` first: two runs writing to one folder corrupt each other), then drive `claude --plugin-dir <repo>`
   with the harness: type `1`, esc, `/fanouts`.

## Push and release

Pushed. For the next release: bump `plugin.json` and `marketplace.json` together in its own commit, add a CHANGELOG
entry, and push with `CLAUDE_SKIP_SQUASH_GUARD=1 git push` after squashing the unpushed commits into bites (see
HANDOFF.md section 9). Owner's machine: `claude plugin marketplace update agenting`, then
`claude plugin update agenting@agenting`, then restart.

## Commands for a colleague

```
claude plugin marketplace update agenting
claude plugin update agenting@agenting     # then restart Claude Code
```
