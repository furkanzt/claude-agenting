# Pre-registered rules: Fable 5.2 on "think first" jobs (2026-11-13)

Written 2026-11-13T12:50Z and committed before any task material was chosen, before any task was
built and before any model output existed for these jobs. Claude Code 2.1.323. The owner approved
every threshold below in a question round on the same day; nothing here may be edited after the
first run. Corrections go in a dated addendum at the end, never in place.

## 1. Question

Claude Fable 5.2 (`claude-fable-5-2`, $8 / $40 per MTok, released 2026-11-09) costs twice Opus 5.5
per token. On the seven existing rows Opus 5.5 already passes every stored run where it is used, so
Fable is not tested there. The question is narrower: on work where a model **designs or decides
first** and cheaper models then build, does Fable 5.2 beat Opus 5.5 `xhigh` by enough to earn the
job in the `quality` or `balanced` disposition? `fast` never gets Fable.

Two new rows:

| Row id | Job | Graded by |
|---|---|---|
| `design-decision` | Decide an architecture or approach that later work is built on | Two judge models against a fixed checklist |
| `ux-design` | Design a UI/UX solution for a prototype, a new screen or a new flow, which a cheaper model then builds | The owner, blind, plus two judge models against a fixed checklist |

## 2. What is fixed for both rows

- **Built once.** Each task is built to the design in this file, reviewed by independent reviewers
  for correctness of the ground truth, and then frozen. No task is rebuilt, hardened or dropped
  after any model output for it exists. A task found to be broken (wrong truth, leaked answer) is
  reported and excluded as a whole, for every cell; it is not repaired and re-run in this round.
- **Who builds and marks.** Builders and reviewers are Opus 5.5 and Sonnet 5.5 agents. No Fable
  model builds a task, reviews a task or writes a checklist. The judge models are
  `fable-5-1@high` (the harness's pinned judge) and `opus-5-5@high`.
- **Same instrument for every cell.** `claude -p --restricted` through `evals/evalkit.py` or the
  probe tools, all runs on Claude Code 2.1.323 or later, every cell fresh on the new tasks.
- **Cells.** `fable-5-2@low`, `fable-5-2@medium`, `fable-5-2@high` (new), `opus-5-5@xhigh`,
  `opus-5-5@high`, `sonnet-5-5@xhigh`, and `sonnet-5-5@medium` as the builder in `ux-design`.
- **A failed run.** A run with no valid answer after the harness's retries counts as failed. For a
  Fable cell, a run slot in which any attempt was refused by a safety classifier, or was answered by
  a different model than the cell names, counts as failed even if a later attempt succeeded.
- **Spending ceiling.** $300 at list price for everything in this round: device checks, building and
  reviewing tasks, runs, both judges and the UI stages. Work stops and is reported when it is reached.

## 3. Row `design-decision`

### Tasks

Two tasks, `design-01` and `design-02`, each a real decision from the history of one of the owner's
projects, from two different repositories.

- **Material.** The project's files as they were at the commit before the decision was made,
  extracted read-only by commit id. 20k to 70k tokens. Nothing written after the decision. The
  material is searched for any trace of the later outcome before the task is frozen.
- **Prompt.** The decision question as it stood, asking for a design: the decision, the reasons, the
  options rejected and why, **at most six risks** in order of importance, each with a mitigation,
  and what to verify. The prompt does not say this is a test and does not hint at what happened.
- **Checklist (the ground truth).** Written before any model output:
  - **C items, binding constraints:** 4 to 6 rules stated in the material that a design must not
    violate, each with the file and line where the material states it.
  - **P items, foreseeable pitfalls:** 4 to 6 problems that really happened after the real decision
    (the evidence stays in the private truth file). An independent reviewer confirms for each that
    the material alone holds the facts needed to foresee it; an item that fails this is removed
    before the freeze. A design handles a P item when its decision avoids the problem by
    construction, or when it names the problem among its risks with a mitigation specific to this
    project.
- **Pass rule for one run under one judge pass:** the design violates no C item **and** handles
  all but at most one P item.

### Judging

Each run is judged four times: two passes by `fable-5-1@high` and two passes by `opus-5-5@high`.
A judge sees the task prompt, the checklist and one answer, never the material's later history and
never which cell wrote the answer.

- **Solid fail.** Under one judge model, a run is a *solid fail* when both of that judge's passes
  fail it. A split (one pass, one fail) is not a solid fail. This is deliberately stricter evidence
  than the harness's `decide`, which fails a run on a split: the rule below counts failures, so a
  failure must be reproducible. A run with no answer block is a solid fail.
- **Both judges must agree on the rule.** Every count below is computed twice, once per judge
  model. A rule fires only if it fires under both.

### Runs

Stage 1: every cell runs each task 3 times (36 runs), and `opus-5-5@xhigh` runs repeats 4 to 6 as
well (6 more), so the Opus `xhigh` count is always out of 12.

Stage 2, only where it can still matter:

- A Fable cell runs repeats 4 to 6 only if it has no solid fail in stage 1 under either judge
  **and** `opus-5-5@xhigh` has at least 4 solid fails of 12 under both judges.
- `opus-5-5@high` and `sonnet-5-5@xhigh` run repeats 4 to 6 only if they have no solid fail in
  stage 1 under either judge.

### Rules

There are no older tasks for this row, so "all tasks" means these two.

- **Rule Q (`quality`).** A Fable cell takes the row in `quality` if it has 0 solid fails in its 12
  runs and `opus-5-5@xhigh` has at least 4 solid fails in its 12 runs.
- **Rule B (`balanced`).** A Fable cell takes the row in `balanced` if it has 0 solid fails in its
  12 runs and `opus-5-5@xhigh` has at least 6 solid fails in its 12 runs, with at least one on each
  task.
- **Which Fable effort.** Among the Fable cells that qualify, the one with the lowest measured mean
  cost per run.
- **`fast`.** The cheapest by measured mean cost per run of `opus-5-5@high` and `sonnet-5-5@xhigh`
  that has 0 solid fails in 12 runs; if neither does, `opus-5-5@xhigh`. Never a Fable cell.
- **Otherwise** the row is `opus-5-5@xhigh` in `balanced` and `quality`, and the table says
  "Fable 5.2 measured, not adopted".
- **Both fail.** If `opus-5-5@xhigh` has at least 4 solid fails and no Fable cell reaches 0 solid
  fails, nothing moves; the row stays `opus-5-5@xhigh`, marked "no cell passed these tasks".
- **A cheaper non-Fable cell for `balanced`** is not decided in this round: the plugin's bar needs
  two confirmation tasks beyond a screening task, and this row has two tasks in all. The numbers
  are reported.

## 4. Row `ux-design`

### Briefs

Four briefs, `ux-01` to `ux-04`, each a prototype, new screen or new flow for one of the owner's
real games, described in a few sentences the way the owner would describe it, with at least three
UI/UX choices that depend on each other. Each brief carries the description, the game's conventions
and existing style as material, and a checklist of 8 yes/no items written before any model output.

### Arms

| Arm | Design pass | Builder |
|---|---|---|
| F | `fable-5-2@high` writes a design brief | `sonnet-5-5@medium` builds one HTML page from that brief |
| O | `opus-5-5@xhigh` writes a design brief | the same builder, same instructions |
| D | none | the same builder builds straight from the description |

The design brief has a fixed shape: the screens and what is on each, the flow, every state, the
words, the main action, the assumptions made. Every arm's builder gets the same description and
material. Each built page is one self-contained HTML file with no network requests. Before the
owner sees a page, comments, titles and generator marks are removed so that nothing names its arm.

Only `fable-5-2@high` is tested as the Fable designer: each further effort level would cost the
owner another 12 pairs.

### Pairs

24 pairs, each of two pages built from the same brief, and no page appears in more than one pair:

- **Block 1, 12 pairs: F against O** (3 per brief).
- **Block 2, 12 pairs: F against D** (3 per brief, from separate F runs).

So the round needs 24 F pages, 12 O pages and 12 D pages. The 24 pairs are shown in one shuffled
order with left and right chosen at random per pair; the order and sides are stored privately. The
owner picks the better page in every pair, with no tie option. A session that does not cover all
24 pairs gives no verdict.

### Checklist score

Each block-1 page is read (as HTML source, with the description and the brief's checklist) once by
`fable-5-1@high` and once by `opus-5-5@high`. An item is credited when both say yes. A page's score
is credited items divided by 8; an arm's score is the mean over its 12 block-1 pages. Arm F's score
is "not below" arm O's when `mean_F >= mean_O - 0.05`.

### Rules

- **Rule UQ (`quality`).** `fable-5-2@high` is the UI/UX designer in `quality` if the owner prefers
  the F page in at least 10 of the 12 block-1 pairs **and** F's checklist score is not below O's.
- **Rule UB (`balanced`).** The same in `balanced` at 11 of 12 or more, with the same checklist
  condition.
- **Otherwise** the designer is `opus-5-5@xhigh` in both.
- **`fast`** uses the Opus designer at `xhigh`. No cheaper designer was tested and none is claimed.
- **Rule UD (the design pass itself).** A design pass before the build is the default for UI
  prototypes if the owner prefers the F page in at least 10 of the 12 block-2 pairs. If the designer
  by rule UQ or UB is Opus, the default design pass uses Opus, on the assumption that a design the
  owner did not prefer less than Fable's also beats no design pass. If rule UD fails, the design
  pass is not a default; it stays available on request, and the docs say no benefit was measured.

## 5. What these rules cannot show

- Twelve runs or twelve pairs show a large gap only. By chance alone, 0 against 4 solid fails
  happens about one time in twenty, and 10 of 12 blind preferences about one time in fifty.
- Two decision tasks and four briefs, all from one owner's projects, are a narrow sample.
- Both judge models come from one vendor; the owner's blind choice is the only judgment from
  outside it, and it covers `ux-design` only.
- The instrument is a clean, read-only run with a neutral system prompt. A real design agent in a
  session has more context and tools.
- The session that wrote these rules and orchestrates the round runs on Fable 5.2. That is why no
  Fable model builds or marks anything, and why the rules were fixed before the tasks existed.

## Addendum 1, 2026-11-13T13:35Z: clarifications made before the first run

Written before any task was installed and before any model output existed for these rows. Each
point says how a rule above is carried out; none changes a threshold.

1. **How a refusal is recognised.** By the CLI's own result fields, checked on Claude Code 2.1.323:
   `stop_reason` equal to `refusal`, or `safety_stops` above 0. An API error, a rate limit, a
   usage limit or a timeout is not a refusal: the attempt is invalid and retried, and it does not
   fail a slot by itself. "Answered by a different model" is the harness's `model_mismatch`.
2. **A failed Fable slot in `ux-design`.** Section 2 applies to the designer runs of arm F. A pair
   whose F page comes from a failed F slot counts as "F not preferred" in its block, whatever the
   owner picked. The owner's raw count and the counted number are both reported; rules UQ, UB and
   UD use the counted number.
3. **"Not below".** `mean_F >= mean_O - 0.05` is computed with exact fractions, not floats.
4. **A builder rule added for every arm alike.** Pages are shown in frames sandboxed without
   same-origin, where browser storage throws. The builder prompt therefore forbids browser storage,
   and a page that uses it is rejected and rebuilt, like a page with a network request.
5. **Blinding check.** A built page that names a model or the vendor is rejected and rebuilt.
6. **Counting for the rules of section 3.** A cell's fail count under a judge is its solid fails
   under that judge plus its failed slots; a failed slot counts under both judges. A cell with any
   fail under either judge is out of rules Q, B and `fast`. A disposition is reported only when
   every cell that could still take it has all 12 slots decided.
