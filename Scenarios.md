# Scenarios — the executable BDD catalogue

Index to `features/*.feature`, this project's executable behaviour catalogue, governed by [TDD.md](TDD.md) and [BDD.md](BDD.md).

**571 scenarios** across 10 domains — **311 ARMED**, **260 GAP**. Full breakdown: [docs/scenarios/coverage-matrix.md](docs/scenarios/coverage-matrix.md).

| Feature | Scenarios | ARMED | GAP | What it pins |
|---|--:|--:|--:|---|
| [`cache-tripwire.feature`](features/cache-tripwire.feature) | 37 | 2 | 35 |  |
| [`cleanrun.feature`](features/cleanrun.feature) | 64 | 44 | 20 |  |
| [`eval-grading.feature`](features/eval-grading.feature) | 108 | 85 | 23 |  |
| [`eval-runs.feature`](features/eval-runs.feature) | 68 | 51 | 17 |  |
| [`finish-check.feature`](features/finish-check.feature) | 30 | 14 | 16 |  |
| [`plugin-docs.feature`](features/plugin-docs.feature) | 39 | 9 | 30 |  |
| [`routing-guard.feature`](features/routing-guard.feature) | 63 | 31 | 32 |  |
| [`session-continuity.feature`](features/session-continuity.feature) | 46 | 20 | 26 |  |
| [`setup-check.feature`](features/setup-check.feature) | 50 | 1 | 49 |  |
| [`tokenomics.feature`](features/tokenomics.feature) | 66 | 54 | 12 |  |

## Conventions

- **`# Backed by:`** — a comment above each scenario naming the test that proves it. `@gap` (with `@wip` while developing) means no test yet — that is the TDD backlog.
- **Regenerate this file + the matrix** — `python3 scripts/quality/build_coverage_matrix.py`.

