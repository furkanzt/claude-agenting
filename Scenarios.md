# Scenarios — the executable BDD catalogue

Index to `features/*.feature`, this project's executable behaviour catalogue, governed by [TDD.md](TDD.md) and [BDD.md](BDD.md).

**1478 scenarios** across 22 domains — **1230 ARMED**, **248 GAP**. Full breakdown: [docs/scenarios/coverage-matrix.md](docs/scenarios/coverage-matrix.md).

| Feature | Scenarios | ARMED | GAP | What it pins |
|---|--:|--:|--:|---|
| [`advisor-pairs-analysis.feature`](features/advisor-pairs-analysis.feature) | 38 | 38 | 0 |  |
| [`advisor.feature`](features/advisor.feature) | 5 | 5 | 0 |  |
| [`agent-guard.feature`](features/agent-guard.feature) | 51 | 51 | 0 |  |
| [`architecture-analysis.feature`](features/architecture-analysis.feature) | 27 | 27 | 0 |  |
| [`cache-tripwire.feature`](features/cache-tripwire.feature) | 47 | 15 | 32 |  |
| [`cleanrun.feature`](features/cleanrun.feature) | 106 | 87 | 19 |  |
| [`code-bench-analysis.feature`](features/code-bench-analysis.feature) | 51 | 51 | 0 |  |
| [`code-bench.feature`](features/code-bench.feature) | 125 | 125 | 0 |  |
| [`e1-analysis.feature`](features/e1-analysis.feature) | 11 | 11 | 0 |  |
| [`e1b-analysis.feature`](features/e1b-analysis.feature) | 25 | 25 | 0 |  |
| [`effort-probe.feature`](features/effort-probe.feature) | 6 | 6 | 0 |  |
| [`eval-grading.feature`](features/eval-grading.feature) | 115 | 92 | 23 |  |
| [`eval-runs.feature`](features/eval-runs.feature) | 93 | 76 | 17 |  |
| [`fanout-view.feature`](features/fanout-view.feature) | 98 | 98 | 0 |  |
| [`finish-check.feature`](features/finish-check.feature) | 30 | 14 | 16 |  |
| [`plugin-docs.feature`](features/plugin-docs.feature) | 72 | 43 | 29 |  |
| [`routing-guard.feature`](features/routing-guard.feature) | 159 | 131 | 28 |  |
| [`session-continuity.feature`](features/session-continuity.feature) | 97 | 71 | 26 |  |
| [`setup-check.feature`](features/setup-check.feature) | 66 | 20 | 46 |  |
| [`think-first-analysis.feature`](features/think-first-analysis.feature) | 48 | 48 | 0 |  |
| [`tokenomics.feature`](features/tokenomics.feature) | 68 | 56 | 12 |  |
| [`ux-blind.feature`](features/ux-blind.feature) | 140 | 140 | 0 |  |

## Conventions

- **`# Backed by:`** — a comment above each scenario naming the test that proves it. `@gap` (with `@wip` while developing) means no test yet — that is the TDD backlog.
- **Regenerate this file + the matrix** — `python3 scripts/quality/build_coverage_matrix.py`.

