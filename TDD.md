# TDD in this repo

How tests are written and run here. The product is a Claude Code plugin: Python hooks
that Claude Code runs on events, Python scripts, an eval harness, agent definitions and
skill docs. There is no server and no UI. The behaviour is described as scenarios in
`features/` (see [BDD.md](BDD.md)); this file is about the tests that prove them.

## Where tests live

| Layer | Location | What it proves |
|---|---|---|
| Hook pipe tests | `tests/test_routing_guard.py`, `tests/test_session_continuity.py`, `tests/test_finish_check.py` | Each hook runs as a subprocess with JSON on stdin, the way Claude Code runs it, and its stdout JSON / exit code is asserted |
| Script tests | `tests/test_tokenomics.py` (meter and the cache tripwire's prices), `tests/test_cleanrun.py`, `tests/test_evalkit.py` | The CLIs' behaviour with `claude -p` replaced by a stub |
| Doc and pin invariants | `tests/test_skill_docs.py` | Wording and pins that other code relies on (description length, list-price caveats, no local paths) |
| Isolation proof | `tests/test_real_state_untouched.py` | The `AGENTING_STATE_DIR` override keeps the real `~/.claude` state unchanged |
| Meta-guard | `tests/test_catalogue_integrity.py` | The scenario catalogue still matches the tests it cites (see BDD.md) |
| Live layer | none yet; `scripts/quality/` is where `check_*` functions would go | Behaviour unit tests cannot prove (real process boot, real model) |

Shared helpers: `tests/_util.py` (`HookTestCase`, script paths). Stubs: `tests/fixtures/fake_claude.py`
(evalkit) and `tests/fixtures/fake_claude_cleanrun.py` (cleanrun). Journals for the finish check:
`tests/fixtures/journal_*.jsonl`.

## Rules (non-negotiable)

1. **Red, then green, then refactor.** For a bug fix the regression test is the red. A behaviour
   change lands with its scenario, its test and the regenerated matrix in one commit.
2. **No network and no real model in a test.** `claude` is replaced by the stubs above. The only
   commands that spend money are `evals/evalkit.py run|judge` and `scripts/cleanrun.py run`; they are
   tools, never tests.
3. **Never touch the real `~/.claude` state.** Hook tests extend `HookTestCase`, which points
   `AGENTING_STATE_DIR` at a fresh temporary directory. `test_real_state_untouched.py` guards this.
4. **Temp dirs only.** No test writes inside the repo tree; evalkit tests build their own tiny tasks.
5. **One-shot commands, never watch mode.**
6. **Private eval material stays private.** `evals/private/` is gitignored; no test or fixture may
   copy from it. Fixtures are synthetic.
7. **Independent facts.** A test that checks a price, a model id or a date takes the figure from the
   source (the price page, recorded in the test's own table), never from the code under test.
8. **Red-proof every new test.** Invert the branch it guards, confirm the test fails, revert. A test
   that survives the inversion is vacuous and does not earn a citation. After the revert, delete the
   `__pycache__` next to the file you mutated: a same-length inversion (`!=` to `==`) made within the
   same second can leave a stale `.pyc` that makes a correct file look broken.

## Commands

| What | Command |
|---|---|
| Whole suite (about 65 s) | `python3 -m pytest tests -q` |
| One file | `python3 -m pytest tests/test_routing_guard.py -q` |
| One test | `python3 -m pytest tests/test_tokenomics.py -k long_prompt -q` |
| Plugin health (end to end, not config reading) | `python3 scripts/check-setup.py` |
| Eval harness self-check (graders on fixtures, secret scan) | `python3 evals/evalkit.py selfcheck` |
| Regenerate the scenario matrix | `python3 scripts/quality/build_coverage_matrix.py` |
| Apply scenario to test mappings | `python3 scripts/quality/apply_backed_by.py <mappings.json>` |
| Dev dependencies | `python3 -m pip install -r requirements-dev.txt` |

There is no CI configuration in this repo. The suite above is the gate; run it before a commit.
`gherkin-official` must be installed or the meta-guard's Gherkin-parse check silently skips.

## Mocking policy

The seams are the `claude` binary (stubbed), the state directory (`AGENTING_STATE_DIR`), the home
directory and the clock-free parts of transcripts (fixtures). Mock at the seam in the consumer's
namespace, never inside the code under test. Hooks are exercised through their real entry point
(subprocess, stdin JSON), not by importing their functions, unless a pure helper has its own unit test.

## Definition of done

- the whole suite is green, including the meta-guard;
- the new or changed behaviour has a scenario in `features/` that cites a test that exists;
- the test survived its red-proof;
- the matrix is regenerated and committed with the change;
- `CHANGELOG.md` has an entry when the change is user-visible.

## Anti-patterns

- Asserting a value against the code's own table (a price compared with the price constant).
- A test that passes with the guarded branch inverted.
- Sleeping to wait for a subprocess; use the subprocess timeout and exit codes.
- Reading `evals/private/` or the real `~/.claude` from a test.
- Two scenarios citing the same single test for different behaviours.
