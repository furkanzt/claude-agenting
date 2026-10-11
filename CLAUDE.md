# agenting (Claude Code plugin)

Routing gate and cost tools for Claude Code Workflows: Python hooks (`hooks/`), scripts
(`scripts/`), a model-and-effort eval harness (`evals/`), tiered agent definitions (`agents/`)
and the routing skill (`skills/agenting/`). English throughout (code, comments, docs, commits).
No server, no UI.

## Commands

| What | Command |
|---|---|
| Whole test suite (about 65 s) | `python3 -m pytest tests -q` |
| Plugin health check (end to end) | `python3 scripts/check-setup.py` |
| Eval harness self-check | `python3 evals/evalkit.py selfcheck` |
| Regenerate the scenario matrix | `python3 scripts/quality/build_coverage_matrix.py` |
| Dev dependencies | `python3 -m pip install -r requirements-dev.txt` |

## Spec harness: every behaviour is a scenario

Observable behaviour is described in Gherkin under `features/` (one file per domain) and bound to
a real test by a `# Backed by: tests/<file>.py::<test_function>` comment that
`tests/test_catalogue_integrity.py` checks on every run. Read [TDD.md](TDD.md) and [BDD.md](BDD.md)
for the commands, the seams and the glossary before changing behaviour. The rules:

- **One commit** for a behaviour change: the code, its scenario in `features/`, its test and the
  regenerated matrix (`python3 scripts/quality/build_coverage_matrix.py`; never hand-edit
  `Scenarios.md` or `docs/scenarios/coverage-matrix.md`). A scenario that lies is worse than none.
- **A scenario with no proof yet** is tagged `@gap @wip` with `# Backed by: @gap`, and only while it
  is actively being developed. A bare `@gap` fails CI. Bare gaps stay at zero.
- **ARMED means the cited test exists**, which a machine checks. Whether it suffices is for an audit.
  The guard checks scenario to test, never code to scenario: code shipped with no scenario keeps CI
  green, so adding the scenario is your job.
- **Red-proof every new test**: invert the branch it guards, confirm the test fails, revert. Only then
  cite it.
- **Unit tests stay off the network and away from real models and `~/.claude`.** `claude` is replaced
  by the stubs in `tests/fixtures/`; hook tests use `HookTestCase` and `AGENTING_STATE_DIR`. The only
  commands that spend money are `evals/evalkit.py run|judge` and `scripts/cleanrun.py run`.
- **Every production bug** gets a regression test and a scenario before the fix ships.

Maintenance loop: find the covering scenario in `features/` (or add one as `@gap @wip`), write the
red test, make it green, red-proof it, replace the `@gap @wip` with the citation, regenerate the
matrix, commit everything together. `scripts/quality/apply_backed_by.py` applies a batch of
scenario-to-test mappings from JSON.

## Eval harness and the routing table

The routing table in `skills/agenting/SKILL.md` is changed only where `evals/evalkit.py decide`
and the vetting in `evals/README.md` say so; the findings go to `evals/results/REPORT-<date>.md`.
`evals/private/` holds real task material and ground truth and is gitignored: never commit it, never
copy from it into a test or fixture, and keep `evals/results/*.jsonl` to scalar counts.
`evals/tasks.json` is generated (`python3 evals/evalkit.py manifest`).

## Releases

A version bump is its own commit (`.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json`
move together, plus a `CHANGELOG.md` entry). Pushing is the owner's decision.
