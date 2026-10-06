# evals: measuring which (model, effort) cell can carry each routing row

The routing table in `skills/agenting/SKILL.md` assigns each kind of delegated
job a model and an effort. This directory measures whether a cheaper cell can do
a job as well as the current one, and keeps the evidence so that **a new model
release costs only the runs that are missing**, never a full re-test.

Everything here is stdlib Python plus the `claude` CLI. No API key is needed:
runs go through `claude -p` on the user's own login.

## Vocabulary

| Term | Meaning |
|---|---|
| **row** | One job type from the routing table (`rows.json`). Seven of them. |
| **cell** | A model plus an effort, e.g. `opus-5-5@xhigh` (`cells.json`). |
| **task** | One concrete, gradable job for a row: a prompt, optional material, a ground truth and a grader. |
| **run** | One cell attempting one task once. Three repeats per (task, cell) by default, because one run of one model is noisy: a probe on 2026-10-05 had Opus 5.5 answer 115, 116 and 115 at low, medium and xhigh on the same question. |
| **screening** | The first round: one task per row, every cell in the row's grid. |
| **confirmation** | A second, larger round on new tasks for a candidate that survived screening on a silent-damage row. |
| **harness version** | An integer in `harness.json`. Bumped when the runner prompt or flags change, which invalidates every stored run. |
| **task hash** | sha256 over a task's prompt and material. Changes when either changes, which invalidates that task's runs only. |

## Layout

```
evals/
  README.md            this file
  harness.json         harness version, runner flags + system prompt, judge pin, repeats
  cells.json           every cell: exact model id, effort, list price (dated)
  rows.json            the seven rows: tier, baseline cell, grid, task ids
  tasks.json           PUBLIC manifest of tasks (id, row, grading, task hash). Generated.
  evalkit.py           the CLI (plan, run, judge, grade, report, decide, selfcheck, manifest, status, sanitize)
  research/            dated research notes (primary-source facts)
  results/
    runs.jsonl         PUBLIC, append-only: one line per run (cost, tokens, model verified). No content.
    scores.jsonl       PUBLIC, append-only: one line per grading of a run. Counts only, no content.
    REPORT-*.md        dated findings and the decision taken
  private/             GITIGNORED. Real project material lives here and must never be committed.
    tasks/<id>/        task.json, prompt.md, material/, truth.json, grader.py, rubric.md (judge rows)
    answers/<run_id>.json   the subject's full answer, the usage block
    work/              per-run scratch directories, deleted after each run
```

`private/` holds copies of real files from the owner's projects (Turkish MEB
content, game code). The plugin repo is public, so nothing in `private/` is ever
committed, and `runs.jsonl` / `scores.jsonl` carry numbers only. **If `private/`
is lost, the stored scores stay valid evidence but cannot be re-graded or
extended with new tasks.** Back it up like any other working data.

## How a run executes (the instrument)

Why not Workflow subagents: the 2026-10-05 smoke test showed Workflow subagents
inherit the session's context (they described the main conversation's request)
and carry an `advisor` tool that consults a stronger model. Either would
contaminate a capability measurement, and the effort a subagent runs at cannot
be read from inside it. `claude -p --restricted` in an empty directory sees no
CLAUDE.md, memory, hooks, skills, plugins or advisor, and returns the exact cost,
token and thinking-token counts and the model that answered.

One run is one process:

```
claude -p <prompt> --model <cell.model_id> [--effort <cell.effort>] \
  --restricted --strict-mcp-config --no-session-persistence --disable-slash-commands \
  --tools "<Read,Grep,Glob | empty>" --system-prompt <harness system prompt + cell.system_append, if any> \
  --max-budget-usd <cap> --output-format json
```

with the working directory set to a fresh copy of the task's `material/` (the
truth and grader are never in it). The default Claude Code system prompt makes
models try to call tools that are absent, so the harness replaces it with a
short neutral one (stored in `harness.json`, part of the harness version).

A run is **valid** only if: the process exited normally, the JSON parsed,
`is_error` is false, and `modelUsage` names exactly the cell's `model_id`
(an alias that drifted to a newer model must not be recorded under the old
cell). Invalid runs are logged with `valid:false`, are not counted, and
`plan` re-issues them (at most 2 retries).

**Haiku 4.5 ignores effort.** Probe 2026-10-05: 15,259 thinking tokens at `low`,
18,149 at `xhigh` on one prompt. Its cell has `effort: null` and the runner
omits `--effort`. So `haiku/low` in the plugin is `haiku`.

**Answer protocol.** Every prompt ends by requiring the final answer between two
marker lines, `===ANSWER===` and `===END===`. The runner extracts the last such
block from the final text. A missing block is a graded failure (score 0), not an
invalid run.

## Task format (private)

`private/tasks/<id>/`:

| File | Contents |
|---|---|
| `task.json` | `{"id","row","phase":"screening"|"confirmation","title","delivery":"files"|"inline","pass_threshold":0..1,"pass_rule":"human-readable","grading":{"type":"code"|"judge","rubric":"rubric.md"|null},"notes":"how built, what is planted"}` |
| `prompt.md` | The exact user prompt. For `files` delivery it names the files in the working directory and says to work only from them. Ends with the answer protocol. Must not hint that this is a test or reveal the truth. |
| `material/` | Files copied into the run's working directory. Empty for `inline` delivery (content is in the prompt). |
| `truth.json` | Ground truth. Computed by script where it can be, otherwise planted and independently audited. |
| `grader.py` | **Code tasks:** `def grade(answer: str, truth: dict) -> {"score": float 0..1, "passed": bool, "details": {...}}`. **Judge tasks:** `def score_judgment(judgment: dict, truth: dict) -> {"score","passed","details"}`, so the arithmetic is code and only the reading is the judge's. Stdlib only. `details` holds counts, never answer text. `passed` follows the task's `pass_rule` (for plain score tasks, `score >= pass_threshold`; a composite rule such as "zero invented answers AND at least 11 of 12 correct" is allowed). |
| `rubric.md` | Judge tasks only: the frozen rubric, reference key points included, and the exact JSON the judge must return. |
| `fixtures/` | Code tasks: `perfect.txt` (must score 1.0 and pass) and `flawed_*.txt` (each must fail). Judge tasks: `judgment_perfect.json` and `judgment_flawed_*.json`. Used by `evalkit.py selfcheck`. |

Thresholds are set **before** any run and recorded in `task.json`.

## Result formats (public, append-only)

`results/runs.jsonl`, one object per run:

```
{"run_id","harness_version","task_id","task_hash","cell_id","cell_hash","repeat",
 "model_id_expected","model_id_observed","valid","invalid_reason",
 "effort","input_tokens","output_tokens","thinking_tokens","cache_read_tokens",
 "cost_usd","duration_ms","num_turns","cli_version","ts"}
```

`cost_usd` is `null` with `"cost_unknown": true` when a run was killed or its output
could not be parsed (it is then charged to `--max-usd` at the per-run cap, never
counted as free). `cli_version` is `claude --version` at the time of the run.

`run_id = sha1("{harness_version}|{task_id}|{task_hash}|{cell_hash}|{repeat}")[:16]`, where `cell_hash` is the sha8 of the canonical JSON of `{cell_id, model_id, effort, system_append}`. Changing any of those re-runs that cell only; a new prompt-variant cell (e.g. `sonnet-5-5@low+think`) is just another cell.

`results/scores.jsonl`, one object per grading of a run. It is public, so `details`
keeps only scalar aggregates (counts, booleans, short strings); `evalkit.py
sanitize` strips dict and list values from older lines, and `grade`/`judge`
never write them:

```
{"run_id","grader_id","score","passed","details","ts"}
```

`grader_id` is `code:<sha8 of grader.py + threshold>` or
`judge:<judge_cell>:<sha8 of rubric>:<pass index>`. A run's effective score is
its latest score for the task's *current* grader id (judge rows: the mean of the
judge passes). Re-grading appends; it never edits, and never re-runs a cell.

## What counts as "already tested" (the no-retest rule)

A (task, cell, repeat) is skipped by `plan` if `runs.jsonl` holds a **valid** run
with the same `run_id`. It is re-run only when:

1. the harness version changed (runner prompt or flags), or
2. the task hash changed (prompt or material), or
3. the cell's definition changed (`model_id`, `effort` or `system_append`: its `cell_hash`).

A changed **grader** or **rubric** triggers re-grading of stored answers, not
re-running. A changed **judge** does the same. Keep the judge pinned
(`harness.json`) so scores stay comparable across model releases: when Fable 5.5
ships it becomes a cell to test, not the new judge, unless you accept re-grading
every stored judge-row answer with it.

## Operating notes

- `run`, `judge`, `grade` and `sanitize` take one exclusive lock
  (`results/.evalkit.lock`); a second concurrent invocation exits with code 2.
  Each run gets its own scratch directory.
- `report` defaults to `--phase screening`, because mixing screening and
  confirmation runs makes cell costs incomparable; `--phase all` warns. Its
  `tasks` column says how many distinct tasks back each cell's numbers.
- `decide` marks a result `(provisional)` when any candidate still has missing
  runs: an unmeasured cell could be the cheaper one. Fill the grid before
  acting on a provisional recommendation.
- `tasks.json` is public: each entry's `pass_rule` is the task's
  `pass_rule_public` if it has one, else `score >= <threshold>`.

## Adding a model (the whole procedure)

1. `cells.json`: add its cells (exact `model_id`, `effort`, dated price).
2. `rows.json`: add the cells to the grids where they compete (`role` says why).
3. `python3 evals/evalkit.py plan` lists exactly the missing runs. Read it.
4. `python3 evals/evalkit.py run` (screening tasks by default; `--phase confirmation` for the second round), then `judge` for judge rows. `grade` re-grades stored answers of code tasks after a grader change, with no model call.
5. `python3 evals/evalkit.py report` and `decide`.
6. Edit the routing table only where `decide` says a row moves; write the dated
   findings to `results/REPORT-<date>.md`.

Alias drift matters: the plugin's pins use `haiku` / `sonnet` / `opus`. When a
release moves an alias, every pin silently changes meaning. The harness records
exact model ids precisely so that is detectable.

## The decision bar (`evalkit.py decide`)

Rows come in two tiers, by what a confident wrong answer costs:

- **silent-damage** (classify/judge, synthesize, don't-guess, adversarial verify):
  a wrong answer spreads unnoticed. A cheaper cell qualifies only if it **passes
  every screening run** and then **passes every run of the confirmation tasks**
  (at least `confirmation_tasks_min` new tasks, `--phase confirmation`, run for
  the candidate only). Confirmation is required whether or not the baseline was
  perfect. Ties and doubt keep the baseline.
- **noticed-immediately** (scan, cleanup, read-and-report): a wrong answer shows
  up fast. A cheaper cell qualifies if its failed screening runs are at most the
  baseline's plus `noticed_extra_misses`, and it does not itself fail its row
  (pass rate at least 0.5).

Shared rules:

- "Cheaper" means strictly lower **measured** mean `cost_usd` per run over the
  row's screening runs, not list price: a lower effort can still cost more if
  the model compensates with more tokens. Equal cost is not cheaper.
- A move must also save at least `decision.min_saving_fraction` (0.25 in
  `harness.json`) of the baseline's measured cost per run, unless the baseline
  itself fails its row. Below that, run-to-run cost noise (about 10% between
  repeats in the 2026-10-06 sweep) and the work of changing and re-validating a
  pin outweigh the saving; such a candidate is reported as `cheaper by only N%`
  and no confirmation runs are spent on it.
- Any non-baseline grid cell is a candidate, whatever its `role`.
- A silent-damage baseline **fails its row** if it misses any screening run; a
  noticed baseline fails if its screening pass rate is below 0.5. Then, if no
  candidate qualifies, the output is `BASELINE_FAILS` naming the cheapest
  measured up-cell (role `up_reference` or `ceiling`) that passes by the same
  standard, or `null` if none does.
- Outputs: `KEEP`, `MOVE_TO <cell>`, `NEEDS_CONFIRMATION <cell> [missing runs]`,
  `BASELINE_FAILS <cell|null>`, `INSUFFICIENT_DATA` (baseline lacks its complete
  screening runs, no candidate is complete, or a run is ungraded).

## Known limits (state these when reporting)

- Three repeats resolve large differences, not small ones. "Passed 3 of 3" is
  evidence, not proof.
- One screening task per row is narrow; confirmation exists for that reason.
- The instrument uses a neutral system prompt and read-only tools, so it
  measures the model and effort on the task shape, not the plugin's agent
  prompts.
- Judge rows depend on the pinned judge; its blind spots are the table's. A judge
  score needs all `judge.repeats` passes; the run passes on a strict majority, so
  a 1-of-2 split fails. The judge grader id hashes `rubric.md` only: if a judge
  row's `grader.py` arithmetic changes, bump the rubric text or delete that
  task's judge scores.
- The grader id covers `grader.py` and the threshold for code tasks, and
  `rubric.md` for judge tasks. It does **not** cover `truth.json`, and for judge
  tasks not `grader.py`, the threshold or the judge system prompt. If you correct a
  truth file or a judge row's arithmetic, delete that task's scores and re-grade.
  Without `private/` the id falls back to a prefix that cannot tell versions apart,
  so keep `private/` backed up.
- Decision-bar choices made after the first sweep, so treat them as fixed from now
  on and not tuned to the data: the 25% materiality threshold, and scan's tier
  (reclassified from noticed to silent-damage because every Sonnet failure there
  was a silently omitted list item). The confirmation tasks for synthesize were
  registered with a one-miss-allowed pass rule that is looser than the screening
  task's all-items rule; the report compares cells on the strict all-items basis as
  well. Confirmation pass rules should never be looser than the screening rule.
- Statistics: repeats on one task are correlated, so what counts is the number of
  tasks, not runs. Zero failures in 9 runs still allows a per-run failure rate of
  about 28% at 95% confidence; zero in 3 tasks allows about 63%. Neither supports a
  95 to 99% reliability claim. The two judge passes come from one judge model and
  agree almost always, so they are one opinion, not two.
- `--restricted` keeps CLAUDE.md out: a 2026-10-05 probe with an 8.5 KB user-level
  CLAUDE.md present had the model report none, and the harness smoke test's canary
  file in a parent directory did not leak. The CLI version is recorded per run.
- A run whose grading crashed or timed out is left **ungraded**, never scored 0
  by default, so a harness fault cannot masquerade as a model failure.
