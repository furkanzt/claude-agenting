# Scenarios — the executable BDD catalogue

Index to `features/*.feature`, this project's executable behaviour catalogue, governed by [TDD.md](TDD.md) and [BDD.md](BDD.md).

**1057 scenarios** across 17 domains — **808 ARMED**, **249 GAP**. Full breakdown: [docs/scenarios/coverage-matrix.md](docs/scenarios/coverage-matrix.md).

| Feature | Scenarios | ARMED | GAP | What it pins |
|---|--:|--:|--:|---|
| [`agent-guard.feature`](features/agent-guard.feature) | 34 | 34 | 0 |  |
| [`cache-tripwire.feature`](features/cache-tripwire.feature) | 47 | 15 | 32 |  |
| [`cleanrun.feature`](features/cleanrun.feature) | 105 | 86 | 19 |  |
| [`e1-analysis.feature`](features/e1-analysis.feature) | 11 | 11 | 0 |  |
| [`e1b-analysis.feature`](features/e1b-analysis.feature) | 25 | 25 | 0 |  |
| [`effort-probe.feature`](features/effort-probe.feature) | 6 | 6 | 0 |  |
| [`eval-grading.feature`](features/eval-grading.feature) | 112 | 89 | 23 |  |
| [`eval-runs.feature`](features/eval-runs.feature) | 69 | 52 | 17 |  |
| [`fanout-view.feature`](features/fanout-view.feature) | 98 | 98 | 0 |  |
| [`finish-check.feature`](features/finish-check.feature) | 30 | 14 | 16 |  |
| [`plugin-docs.feature`](features/plugin-docs.feature) | 53 | 23 | 30 |  |
| [`routing-guard.feature`](features/routing-guard.feature) | 139 | 111 | 28 |  |
| [`session-continuity.feature`](features/session-continuity.feature) | 61 | 35 | 26 |  |
| [`setup-check.feature`](features/setup-check.feature) | 60 | 14 | 46 |  |
| [`think-first-analysis.feature`](features/think-first-analysis.feature) | 41 | 41 | 0 |  |
| [`tokenomics.feature`](features/tokenomics.feature) | 68 | 56 | 12 |  |
| [`ux-blind.feature`](features/ux-blind.feature) | 98 | 98 | 0 |  |

## Conventions

- **`# Backed by:`** — a comment above each scenario naming the test that proves it. `@gap` (with `@wip` while developing) means no test yet — that is the TDD backlog.
- **Regenerate this file + the matrix** — `python3 scripts/quality/build_coverage_matrix.py`.

