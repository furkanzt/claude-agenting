# Pre-registered: stage 1 of the Antigravity model screen (2026-11-19)

Written on 2026-11-19, before any eval task has been run through Antigravity. The commit time is the
record. Antigravity CLI (`agy`) 1.5.12, user plan Google AI Pro.

## Why

The owner now also works in Google Antigravity, and the agenting plugin is being ported to it (a new
repository, `antigravity-agenting`). In Antigravity, a helper agent can only run on the chat's own model
(`inherit`) or on two Gemini tiers (`flash` and `pro`). There are two separate usage meters, one for Claude
and one for Gemini, plus a weekly meter for Gemini 4 Argon. On 2026-11-19 the owner decided that the routing
for Antigravity is set **from measurements, not guesses**. Stage 1 is the first round: a cheap screen of every
model family. Stage 2 is sized from stage 1's real cost and needs the owner's approval before it starts.

## Question

On each row's screening task, how often does each Antigravity model get the answer right? And what does
one run cost, in tokens and in meter percent?

## What is fixed

- **Instrument.** `evals/probes/agy_bench.py`. Each run executes
  `agy --agent eval-runner --model <id> --settings '{"allowNonWorkspaceAccess":false}' -p=<prompt>`
  in a fresh copy of the task material. agy has no `--system-prompt` or `--tools` flag, so the
  eval-runner agent file supplies two things: the system prompt, which is the Claude runner's text from
  `harness.json` word for word, and the tools, which are `read_file` and `run_command` (none for inline
  tasks). The guard hook `evals/agy/eval_hook.py` runs before every tool call. It allows reads and a
  read-only shell allowlist (`find`, `grep`, `ls`, `wc`, `cat` and similar) inside the run directory, and
  denies everything else. No file of the instrument sits inside the run directory.
- **Global state, frozen for the round.** The old global rules file `~/.gemini/GEMINI.md` was removed
  before the first run. Nothing is installed into `~/.gemini/config` until stage 1 ends: no plugin, no
  rules, no hooks. The global skill list stays as it is.
- **Tasks.** Each row's screening task, unchanged: `scan-01`, `cleanup-01`, `read-report-01`,
  `classify-01`, `synthesize-01`, `dont-guess-01`, `verify-01`, `design-01`.
- **Cells** (`evals/agy/bench.json`):
  - Gemini 4 Neon, Gemini 4 Argon, Gemini 4 Hydrogen and Gemini 3.8 Flash, each at Medium.
  - Gemini 4 Hydrogen at High and at XHigh. These two stand in for the helper tiers `flash` and `pro`.
    A probe showed those tiers run as `gemini-4-hydrogen-tiered-high` and `-xhigh`, which `--model`
    cannot select.
  - Claude Sonnet 5.5 and Claude Opus 5.5, each at Medium.
  - GPT-OSS 120B is not run: Google marks it for removal, and it draws on the Claude meter.
- **Repeats.** Two per Gemini cell. One per Claude cell: these are spot checks against the 1,260 Claude
  Code runs, not a re-measure. That makes 6 × 8 × 2 + 2 × 8 × 1 = 112 runs.
- **Grading.** Code-graded tasks are graded at once by their own graders. The two judge-graded tasks
  (`synthesize-01` and `design-01`) are judged afterwards by the pinned judge in Claude Code, which runs on
  the owner's Claude plan, not on an Antigravity meter.

## Rules

1. **Validity.** A run is invalid in any of these cases, and an invalid run is retried in a later
   invocation:
   - it times out;
   - its output is not JSON;
   - its status is not SUCCESS (a quota error is recorded as `quota`);
   - its response is empty;
   - it left no hook log;
   - the hook log names another model;
   - its workspace is not its own run directory;
   - a second conversation started in its directory.

   A denied tool call does not make a run invalid. It is counted.
2. **Stop lines.** Before each run the bench reads `agy -p /usage`. It starts no run on a meter whose
   weekly remaining is below 70% (Claude) or 40% (Gemini and Argon). A quota error stops that pool for the
   invocation. Runs are sequential.
3. **Cost.** Tokens come from the run's JSON `usage` (input, output, thinking, cache read). Meter percent is
   reported only as the drop over a whole block of runs, because the meter shows whole percents and the
   owner's own use moves it too.
4. **Pass.** A run passes when its task's registered pass rule holds, the same rule as for the Claude
   runs.

## What this can change

Nothing in the routing on its own. Stage 1 produces a report: pass counts and tokens per (row, cell),
and the meter drop per pool. From that report the owner sizes stage 2 (which cells, which efforts, how many
runs). The Antigravity routing table is decided after stage 2, with the decision bar in `evals/README.md`.

## Limits known beforehand

- **This instrument is not the Claude Code instrument.** The model is the same, but the tools (agy's
  `read_file` and a guarded shell instead of Read, Grep and Glob), the harness prompt around the system
  prompt, and the global skill list all differ. The Claude spot checks measure that difference. They do
  not remove it.
- **Two repeats** show only large gaps.
- **The helper tiers are measured through stand-ins.** `gemini-4-hydrogen-high` is not proven identical to
  `gemini-4-hydrogen-tiered-high`.
- **Antigravity sends the task material to Google.** The owner approved this on 2026-11-19 for all 30 tasks.
- **agy can update itself.** Each run records the version. A version change within the round is reported.

## Note added during the round (no rule changed)

Written while stage 1 ran, before any result was read.

- **The Orchestrator models are not run.** "Orchestrator (Neon)" and "Orchestrator (Argon)" plan with
  one model and hand the work to Gemini 4 Hydrogen helpers. A run that starts a second conversation is
  invalid by rule 1, so this instrument cannot measure them as one cell. They are a vehicle, not a model,
  and are left for a separate decision.
- **The helper tiers are not run through real helpers here.** Stage 1 measures `gemini-4-hydrogen-high`
  and `-xhigh` directly, as stand-ins. A small check that a real helper (`model: flash` or `pro` in an
  agent file) gives the same results is part of sizing stage 2, so it is put to the owner then.
- **Public record.** `results/agy-runs.jsonl` carries each run's agy `conversation_id`. That id moves
  to the private side before the file is committed.
