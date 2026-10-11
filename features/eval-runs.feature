Feature: The evalkit runner plans only the missing runs, executes each as its own claude -p process, decides run validity from the output, and keeps one writer at a time

  # ---------------------------------------------------------------- run id and hashes

  # Backed by: tests/test_evalkit.py::test_run_id_is_stable
  Scenario: The run id is the first 16 hex digits of a sha1 over five fields
    Given harness version 1, task id "t", task hash "h", cell hash "abcd1234" and repeat 1
    When the run id is computed
    Then it equals the first 16 hex digits of sha1 of "1|t|h|abcd1234|1"
    And computing it a second time gives the same value

  # Backed by: tests/test_evalkit.py::test_run_id_changes_with_each_input
  Scenario: Changing any one of the five run id inputs gives a different run id
    Given harness version 1, task id "t", task hash "h", cell hash "c" and repeat 1
    When exactly one of the harness version, task id, task hash, cell hash or repeat is changed
    Then the run id differs from the original in every one of the five cases

  # Backed by: tests/test_evalkit.py::test_cell_hash_is_sha8_of_the_canonical_identity
  Scenario: The cell hash covers cell id, model id, effort and system_append but not the price
    Given a cell "c" with model_id "m", effort "low" and a price of 1 dollar per MTok input
    When the cell hash is computed
    Then it is the first 8 hex digits of the sha256 of the canonical JSON of cell_id, model_id, effort and system_append
    And a missing system_append hashes the same as an empty one
    And changing the price to 99 leaves the hash unchanged
    And changing effort to "high" or null, the model_id to "m2", the system_append to "Think." or the cell id to "c2" changes the hash

  # Backed by: tests/test_evalkit.py::test_task_hash_follows_prompt_and_material
  Scenario: The task hash follows the prompt, the delivery and the material files
    Given a task "n-1" with delivery "files" and one material file "data.txt"
    When the delivery is read as "inline" instead
    Then the task hash changes
    And changing the content of "data.txt" changes it
    And changing the prompt.md text changes it
    And recomputing the hash on unchanged inputs returns the same value

  @gap @wip
  # Backed by: @gap
  Scenario: A .DS_Store file in the material does not change the task hash
    Given a task "n-1" with material "data.txt"
    When a file ".DS_Store" is added to the material directory
    Then the task hash is unchanged, because material_files skips files named ".DS_Store"

  @gap @wip
  # Backed by: @gap
  Scenario: A task directory without prompt.md stops the command with exit code 2
    Given a task directory "n-1" whose prompt.md is deleted
    When I run evalkit.py plan
    Then the exit code is 2
    And stderr contains "n-1: prompt.md is missing"

  # ---------------------------------------------------------------- plan

  # Backed by: tests/test_evalkit.py::test_fresh_plan_expands_grid_tasks_repeats
  Scenario: A fresh plan expands every grid cell, screening task and repeat as a missing run
    Given the row "noticed-row" with a grid of cells "base", "cheap" and "up" and one screening task
    And no runs recorded and harness repeats_default 3
    When I run evalkit.py plan --json --rows noticed-row
    Then items holds 9 entries, each with reason "missing"
    And counts is {"base": 3, "cheap": 3, "up": 3}
    And the items are sorted by row, task, cell and repeat

  # Backed by: tests/test_evalkit.py::test_confirmation_tasks_only_with_phase_or_task_filter
  Scenario: Confirmation tasks are planned only with --phase all or an explicit --tasks filter
    Given the row "silent-row" with one screening task and two confirmation tasks
    When I run evalkit.py plan --json --rows silent-row
    Then items holds 9 entries
    And with --phase all it holds 27 entries
    And with --tasks s-c1 --cells base it holds 3 entries

  # Backed by: tests/test_evalkit.py::test_plan_skips_valid_runs
  Scenario: A repeat that already has a valid run is not planned again
    Given evalkit.py run has completed repeats 1 and 2 of "n-1" on cell "cheap"
    When I run evalkit.py plan --json --rows noticed-row --cells cheap --repeats 3
    Then the planned repeats are exactly [3]

  # Backed by: tests/test_evalkit.py::test_plan_replans_when_task_changes
  Scenario: Rewording a task prompt re-plans that task's stored runs
    Given a valid run of "n-1" on cell "base" repeat 1 and an empty plan for it
    When the text of private/tasks/n-1/prompt.md is changed
    Then evalkit.py plan lists 1 run for "n-1" on cell "base"

  # Backed by: tests/test_evalkit.py::test_plan_replans_when_model_id_or_harness_changes
  Scenario: A changed model id or a new harness version re-plans a stored run
    Given a valid run of "n-1" on cell "base" repeat 1 and an empty plan for it
    When the model_id of "base" is changed to "claude-test-base-2"
    Then evalkit.py plan lists 1 run
    And restoring the model_id gives an empty plan again
    And setting harness_version to 2 lists 1 run

  # Backed by: tests/test_evalkit.py::test_cell_identity_change_replans_that_cell_only
  Scenario: Changing a cell's effort, model id or system_append re-plans that cell only
    Given valid runs of "n-1" on cells "base", "cheap" and "up" at repeat 1
    When the effort of "cheap" is changed to "medium"
    Then evalkit.py plan lists exactly one run, on cell "cheap" repeat 1
    And the same holds when the model_id of "cheap" is changed to "claude-test-cheap-2"
    And the same holds when the system_append of "cheap" is set to "Think first."
    And restoring cells.json gives an empty plan, reusing the stored runs

  # Backed by: tests/test_evalkit.py::test_cell_identity_change_gives_a_new_run_id
  Scenario: A cell identity change gives the cell a new run id and leaves the other cells' ids alone
    Given the run ids of "n-1" repeat 1 on cells "base", "cheap" and "up"
    When the effort of "cheap" is changed to "medium"
    Then the run id of "cheap" differs from before
    And the run ids of "base" and "up" are identical to before

  # Backed by: tests/test_evalkit.py::test_invalid_runs_retry_up_to_the_cap
  Scenario: An invalid run is planned as a retry until max_retries_invalid is used up
    Given harness max_retries_invalid 2 and a claude that always exits 1
    When I run evalkit.py run for "n-1" on cell "base" repeat 1 three times, planning between the runs
    Then after the first and second attempt the plan item has reason "retry"
    And after the third attempt items is empty and exhausted is 1
    And a fourth run launches nothing, so runs.jsonl holds exactly 3 lines

  @gap @wip
  # Backed by: @gap
  Scenario: A valid run after earlier invalid attempts ends the retries
    Given two invalid runs and then one valid run for the same run id in runs.jsonl, the valid line carrying the cell's current model_id as model_id_expected
    When I run evalkit.py plan --json --tasks n-1 --cells base --repeats 1
    Then items is empty and exhausted is 0

  @gap @wip
  # Backed by: @gap
  Scenario: The plain-text plan names the run count and the exhausted count
    Given one run of "n-1" on cell "base" repeat 1 that has used up its retries and no other missing run
    When I run evalkit.py plan --tasks n-1 --cells base --repeats 1 without --json
    Then the first line of stdout is "0 run(s) to do; 1 exhausted their retries"

  # Backed by: tests/test_evalkit.py::test_unknown_filters_fail_clearly
  Scenario: An unknown cell id in a filter stops the command with exit code 2
    Given the cells "base", "cheap", "up" and "judge"
    When I run evalkit.py plan --cells nope
    Then the exit code is 2
    And stderr contains "unknown cell: nope"

  # Backed by: tests/test_evalkit.py::test_missing_private_is_tolerated_with_manifest_and_explained_without
  Scenario: Without private/ plan falls back to tasks.json, run refuses, and with neither plan says there are no tasks
    Given tasks.json built by the manifest command and the private directory removed
    When I run evalkit.py plan --json --rows noticed-row
    Then items holds 9 entries
    And evalkit.py run --rows noticed-row exits 2 with "private" in stderr
    And after tasks.json is deleted too, evalkit.py plan prints "no tasks" on stderr

  # ---------------------------------------------------------------- the claude process

  # Backed by: tests/test_evalkit.py::test_command_shape_stdin_cwd_and_cleanup
  Scenario: Each run launches claude with the cell's model, effort, tools and system prompt and the prompt on stdin
    Given a files task "n-1" and the cells "cheap" (effort "low") and "base" (effort null)
    When I run evalkit.py run for each cell at repeat 1
    Then the call for "cheap" carries model "claude-test-cheap", effort "low", tools "Read,Grep,Glob" and system prompt "Be careful."
    And the call for "base" has no "--effort" in its argument list
    And the prompt text "Do task n-1" arrives on stdin and appears nowhere in the argument list
    And the working directory held only "data.txt"

  # Backed by: tests/test_evalkit.py::test_system_append_goes_after_the_harness_prompt_with_two_newlines
  Scenario: A cell's system_append follows the harness system prompt after two newlines
    Given the cell "cheap" has system_append "Think the problem through."
    When I run evalkit.py run on "cheap" and on "base"
    Then the system prompt of the "cheap" call is "Be careful.\n\nThink the problem through."
    And the system prompt of the "base" call is "Be careful."

  @gap @wip
  # Backed by: @gap
  Scenario: The harness flags and the per-run budget are appended to every claude command
    Given harness flags "--restricted" and "--output-format json" and max_budget_usd_per_run 6
    When I run evalkit.py run --dry-run for one planned run
    Then the printed command contains the flags in order followed by "--tools", "--system-prompt" and "--max-budget-usd 6"

  # Backed by: tests/test_evalkit.py::test_every_run_gets_its_own_work_directory
  Scenario: Every run gets a fresh work directory holding a copy of the task material
    Given a files task "n-1" with material "data.txt" containing "forty two"
    When two work directories are prepared for the same run id "abc123"
    Then the two paths differ and both names start with "abc123"
    And both sit directly under private/work and both hold "data.txt" with "forty two"
    And removing the first leaves the second intact

  # Backed by: tests/test_evalkit.py::test_inline_delivery_gets_no_tools_and_empty_cwd
  Scenario: An inline task is run with an empty tool list in an empty directory
    Given an inline task "n-2" in "noticed-row"
    When I run evalkit.py run --tasks n-2 --cells cheap --repeats 1
    Then the claude call has tools ""
    And the working directory of the call holds no files

  # Backed by: tests/test_evalkit.py::test_timeout_kills_and_is_invalid
  Scenario: A run that outlives timeout_s is killed, logged invalid and its work directory is removed
    Given harness runner timeout_s 1 and a claude that sleeps 60 seconds
    When I run evalkit.py run for "n-1" on cell "cheap" repeat 1
    Then the whole command finishes in under 20 seconds
    And runs.jsonl holds one line with valid false and invalid_reason "timeout"
    And private/work is empty afterwards

  # ---------------------------------------------------------------- run validity

  # Backed by: tests/test_evalkit.py::test_valid_run_record_answer_file_and_code_score
  Scenario: A valid run is logged with its usage, saved as an answer file and graded at once
    Given a claude that answers with cost 0.02, 77 thinking tokens and an answer block holding "42"
    When I run evalkit.py run for "n-1" on cell "cheap" repeat 1
    Then runs.jsonl holds one line with valid true, model_id_expected and model_id_observed both "claude-test-cheap", cost_usd 0.02, thinking_tokens 77 and effort "low"
    And that line carries run_id, harness_version, task_id, task_hash, cell_id, cell_hash, repeat, input_tokens, output_tokens, cache_read_tokens, duration_ms, num_turns and ts
    And private/answers/<run_id>.json holds block "42"
    And scores.jsonl holds one line for that run_id with score 1.0, passed true and a grader_id starting with "code:"

  # Backed by: tests/test_evalkit.py::test_run_record_carries_the_cell_hash_and_run_id_uses_it
  Scenario: The run record's run id is derived from the record's own cell hash
    Given the cell "cheap" has system_append "Think."
    When I run evalkit.py run for "n-1" on cell "cheap" repeat 1
    Then the record's cell_hash equals the cell hash of "cheap"
    And its run_id equals the first 16 hex digits of sha1 of "1|n-1|<task_hash>|<cell_hash>|1"

  # Backed by: tests/test_evalkit.py::test_wrong_model_is_invalid_and_not_graded
  Scenario: A run whose modelUsage names a different model is invalid and is neither graded nor saved as an answer file
    Given a claude whose modelUsage names a model other than the requested "claude-test-cheap"
    When I run evalkit.py run for "n-1" on cell "cheap" repeat 1
    Then runs.jsonl holds one line with valid false and an invalid_reason containing "model_mismatch"
    And scores.jsonl is empty
    And private/answers does not exist

  # Backed by: tests/test_evalkit.py::test_alias_drift_is_invalid
  Scenario: A drifted model id such as "claude-test-cheap-next" is invalid
    Given a claude whose modelUsage names "claude-test-cheap-next" for a request of "claude-test-cheap"
    When I run evalkit.py run for "n-1" on cell "cheap" repeat 1
    Then runs.jsonl holds one line with valid false
    And its model_id_observed contains "claude-test-cheap-next"

  # Backed by: tests/test_evalkit.py::test_error_and_bad_json_are_invalid
  Scenario Outline: A failing process or unparseable output is invalid with a named reason
    Given a claude that <behaviour>
    When I run evalkit.py run for "n-1" on cell "cheap" repeat 1
    Then runs.jsonl holds a line with valid false and invalid_reason "<reason>"

    Examples:
      | behaviour                                | reason      |
      | exits 1 with is_error true               | exit_code=1 |
      | prints "this is not json" and exits 0    | json_parse  |

  @gap @wip
  # Backed by: @gap
  Scenario: A zero exit with is_error true in the JSON is invalid with reason "is_error"
    Given a claude that exits 0 and prints JSON with is_error true and the requested model in modelUsage
    When I run evalkit.py run for "n-1" on cell "cheap" repeat 1
    Then runs.jsonl holds a line with valid false and invalid_reason "is_error"

  @gap @wip
  # Backed by: @gap
  Scenario: A claude binary that cannot be started is an invalid run that cost nothing
    Given harness runner claude_bin names a program that does not exist
    When I run evalkit.py run for "n-1" on cell "cheap" repeat 1
    Then runs.jsonl holds a line with valid false and an invalid_reason starting with "spawn failed"
    And that line has cost_usd 0.0 and no cost_unknown field

  # Backed by: tests/test_evalkit.py::test_missing_block_is_a_graded_failure_not_invalid
  Scenario: An answer without the answer block is a valid run scored 0, never an invalid run
    Given a claude that replies "I think the answer is 42." with no ===ANSWER=== block
    When I run evalkit.py run for "n-1" on cell "cheap" repeat 1
    Then runs.jsonl holds one line with valid true
    And scores.jsonl holds one line with score 0.0, passed false and details no_block true

  # Backed by: tests/test_evalkit.py::test_extract_block_last_wins_and_requires_both_markers
  Scenario: The answer block is the last start-to-end pair and needs both markers
    Given the markers "===ANSWER===" and "===END==="
    When the text holds two complete blocks "A" and then " B " and a stray inline start marker between them
    Then the extracted answer is "B"
    And text with a start marker but no end marker yields no block
    And empty text yields no block

  # Backed by: tests/test_evalkit.py::test_wrong_answer_is_scored_failed
  Scenario: A wrong answer is a valid run scored as a failure
    Given a claude whose answer block holds "41" while the truth is 42
    When I run evalkit.py run for "n-1" on cell "cheap" repeat 1
    Then scores.jsonl holds one line with passed false

  # ---------------------------------------------------------------- budget and cost

  # Backed by: tests/test_evalkit.py::test_budget_cap_stops_launching
  Scenario: run --max-usd stops launching once the spend reaches the cap
    Given nine planned runs of "noticed-row" costing $0.01 each and one job
    When I run evalkit.py run --rows noticed-row --max-usd 0.025 --jobs 1
    Then runs.jsonl holds 3 lines, the third taking the spend to $0.03
    And 6 runs are still planned afterwards

  # Backed by: tests/test_evalkit.py::test_invalid_run_cost_counts_toward_budget
  Scenario: The cost of an invalid run counts toward the --max-usd cap
    Given a claude that reports the wrong model with a cost of $0.01 per run
    When I run evalkit.py run --rows noticed-row --max-usd 0.015 --jobs 1
    Then runs.jsonl holds 2 lines

  @gap @wip
  # Backed by: @gap
  Scenario: A run skipped for the budget is named in the progress output and logs nothing
    Given nine planned runs and a cap already reached by the first run
    When I run evalkit.py run --max-usd 0.005 --jobs 1
    Then each remaining progress line ends with "skipped (budget)"
    And runs.jsonl holds exactly 1 line

  # Backed by: tests/test_evalkit.py::test_unparseable_output_logs_null_cost_and_charges_the_cap
  # Backed by: tests/test_evalkit.py::test_budget_charges_the_cap_for_unknown_cost
  Scenario: A run with unparseable output has a null cost, is flagged unknown and is charged at the per-run cap
    Given max_budget_usd_per_run 1 and a claude that prints text that is not JSON
    When I run evalkit.py run --rows noticed-row --max-usd 1.5 --jobs 1
    Then runs.jsonl holds 2 lines, each with cost_usd null, cost_unknown true and valid false
    And stdout contains "cost unknown"
    And stdout contains "spent $2.0000 of $1.5 (2 run(s) with unknown cost"

  # Backed by: tests/test_evalkit.py::test_a_timeout_logs_null_cost
  Scenario: A run killed on timeout has a null cost and cost_unknown true
    Given harness runner timeout_s 1 and a claude that sleeps 60 seconds
    When I run evalkit.py run for "n-1" on cell "cheap" repeat 1
    Then the runs.jsonl line has invalid_reason "timeout", cost_usd null and cost_unknown true

  # Backed by: tests/test_evalkit.py::test_a_known_cost_stays_a_number_without_the_flag
  Scenario: A cost of zero reported by a failed process stays a known number
    Given a claude that exits 1 and reports total_cost_usd 0.0
    When I run evalkit.py run for "n-1" on cell "cheap" repeat 1
    Then the runs.jsonl line has valid false and cost_usd 0.0
    And it has no cost_unknown field

  # ---------------------------------------------------------------- the CLI version

  # Backed by: tests/test_evalkit.py::test_runs_record_the_version_and_it_is_fetched_once_per_invocation
  Scenario: The claude version is read once per invocation and recorded on every run
    Given a claude whose --version prints "9.9.9 (Fake)"
    When I run evalkit.py run --rows noticed-row --cells cheap, which executes 3 runs
    Then claude --version was called exactly once
    And every runs.jsonl line has cli_version "9.9.9 (Fake)"
    And only 3 model calls were made

  # Backed by: tests/test_evalkit.py::test_invalid_runs_carry_the_version_too
  Scenario: An invalid run also records the claude version
    Given a claude that exits 1 and whose --version prints "9.9.9 (Fake)"
    When I run evalkit.py run for "n-1" on cell "cheap" repeat 1
    Then the runs.jsonl line has valid false and cli_version "9.9.9 (Fake)"

  # Backed by: tests/test_evalkit.py::test_version_does_not_change_run_id_or_cell_hash
  Scenario: A new claude version re-plans nothing and never enters the run id or the cell hash
    Given stored valid runs of "n-1" on cell "cheap", repeat 1 recorded under version "9.9.9 (Fake)" and repeat 2 under "10.0.0"
    When I run evalkit.py plan --json for repeats 1 and 2 in an environment whose claude --version prints "11.0.0"
    Then the stored run_id and cell_hash of repeat 1 equal those computed from the inputs alone
    And items is empty

  # Backed by: tests/test_evalkit.py::test_a_long_version_string_is_capped_for_the_public_record
  Scenario: A version string longer than 40 characters is cut to 40
    Given a claude whose --version prints "1.2.3 " followed by 80 "x"
    When I run evalkit.py run for "n-1" on cell "cheap" repeat 1
    Then the cli_version of the runs.jsonl line is 40 characters long

  # Backed by: tests/test_evalkit.py::test_dry_run_and_empty_plan_do_not_ask_for_the_version
  Scenario: A dry run does not call claude --version
    Given a claude that logs every --version call
    When I run evalkit.py run --rows noticed-row --dry-run
    Then the version log file is never created

  @gap @wip
  # Backed by: @gap
  Scenario: An unreadable claude version records null and warns on stderr
    Given a claude whose --version exits 1
    When I run evalkit.py run for "n-1" on cell "cheap" repeat 1
    Then stderr contains "could not read the claude version"
    And the runs.jsonl line has cli_version null

  # ---------------------------------------------------------------- dry run and interruption

  # Backed by: tests/test_evalkit.py::test_dry_run_calls_nothing
  Scenario: A dry run prints the planned run count and launches nothing
    Given nine planned runs for "noticed-row"
    When I run evalkit.py run --rows noticed-row --dry-run
    Then stdout contains "9 run(s) planned"
    And no claude call is made and runs.jsonl holds no line

  # Backed by: tests/test_evalkit.py::test_sigint_exits_130_without_half_written_lines
  Scenario: Ctrl-C during a run exits 130 and logs no run
    Given two claude processes in flight that would sleep 60 seconds
    When SIGINT is sent to evalkit.py run
    Then the exit code is 130
    And reading runs.jsonl yields no run

  # Backed by: tests/test_evalkit.py::test_a_run_that_finishes_as_ctrl_c_lands_is_still_logged
  Scenario: A run that finished while Ctrl-C landed is still logged, answered and graded
    Given a claude call that returns a complete valid result with exit status 0 while the stop flag is set
    When execute_one handles the run
    Then it returns a record rather than nothing
    And runs.jsonl holds one valid line, scores.jsonl one passed score and private/answers the answer file

  # Backed by: tests/test_evalkit.py::test_a_run_killed_by_the_stop_is_not_logged
  Scenario: A run killed by the stop request writes nothing
    Given a claude call that returns exit status -9 while the stop flag is set
    When execute_one handles the run
    Then it returns nothing
    And runs.jsonl and scores.jsonl hold no line

  # Backed by: tests/test_evalkit.py::test_concurrent_appends_never_interleave
  Scenario: Eight threads appending 40 lines each leave 320 intact JSON lines
    Given eight threads that each append 40 objects with 500 "é" characters to one jsonl file
    When all threads finish
    Then reading the file yields exactly 320 parseable lines

  @gap @wip
  # Backed by: @gap
  Scenario: A garbled line in runs.jsonl is skipped with a warning instead of stopping the command
    Given runs.jsonl holds one valid line and one line "not json"
    When I run evalkit.py plan
    Then the exit code is 0
    And stderr contains "unreadable line skipped"

  # ---------------------------------------------------------------- the exclusive lock

  # Backed by: tests/test_evalkit.py::test_writers_refuse_while_the_lock_is_held_and_do_nothing
  Scenario: While another process holds the lock, run, judge, grade and sanitize exit 2 and change nothing
    Given another process holds an exclusive flock on results/.evalkit.lock
    When I run evalkit.py run --rows noticed-row, judge, grade and sanitize in turn
    Then each exits with code 2 and stderr contains "already writing results"
    And no claude call is made and runs.jsonl and scores.jsonl are unchanged

  # Backed by: tests/test_evalkit.py::test_read_only_commands_and_dry_run_do_not_lock
  Scenario: Status, plan, report, decide, selfcheck and run --dry-run work while the lock is held
    Given another process holds an exclusive flock on results/.evalkit.lock
    When I run evalkit.py status, plan, report, decide, selfcheck and run --rows noticed-row --dry-run
    Then every command exits 0

  # Backed by: tests/test_evalkit.py::test_lock_is_released_when_the_invocation_ends
  Scenario: The lock is released when the invocation ends
    Given evalkit.py run on cell "base" has finished
    Then results/.evalkit.lock exists
    And a following run on cell "cheap" and a sanitize are not refused

  # Backed by: tests/test_evalkit.py::test_a_second_live_invocation_is_refused
  Scenario: A second live run is refused and launches nothing
    Given evalkit.py run on cell "base" is in flight with one claude call made
    When I start evalkit.py run on cell "cheap"
    Then the second command exits 2 with "already writing results" in stderr
    And the log still holds exactly 1 claude call

  @gap @wip
  # Backed by: @gap
  Scenario: The refusal message names the pid of the process holding the lock
    Given another process holds an exclusive flock on results/.evalkit.lock and the file contains "4242"
    When I start evalkit.py run
    Then stderr contains "pid 4242"

  # Backed by: tests/test_evalkit.py::test_a_second_valid_line_for_a_run_id_is_never_appended
  Scenario: A second valid result for a run id is dropped with a warning
    Given runs.jsonl already holds a valid line for the run id of "n-1" on cell "cheap" repeat 1
    When execute_one finishes another valid run with the same run id
    Then it reports the run as a duplicate and stderr contains "already has a valid line"
    And runs.jsonl still holds only the seeded line and scores.jsonl only the seeded score
    And no answer file is written and private/work is empty

  # ---------------------------------------------------------------- status

  # Backed by: tests/test_evalkit.py::test_status_counts_and_total_cost
  Scenario: Status prints per-row counts and the total cost, judge cost included
    Given two valid scored runs of "n-1" on cell "base" costing $0.50 each
    And a judge score line whose details carry judge_cost_usd 0.25
    When I run evalkit.py status
    Then the "noticed-row" line reads tasks "1/1", cells 3, valid 2, invalid 0, scored 2, ungraded 0
    And stdout contains "total cost so far: $1.2500"

  # Backed by: tests/test_evalkit.py::test_status_counts_ungraded_and_report_excludes_them
  Scenario: Status counts a valid run without a score as ungraded
    Given three valid runs of "n-1" on cell "base" of which one has a score
    When I run evalkit.py status
    Then the header line contains "ungraded"
    And the "noticed-row" line reads valid 3, invalid 0, scored 1, ungraded 2

  # Backed by: tests/test_evalkit.py::test_status_sums_known_costs_and_counts_unknown_runs
  Scenario: Status leaves unknown-cost runs out of the total and counts them
    Given two valid runs at $0.50 and one valid run with cost_usd null
    When I run evalkit.py status
    Then stdout contains "total cost so far: $1.0000"
    And stdout contains "1 run(s) with unknown cost"

  # Backed by: tests/test_evalkit.py::test_status_without_unknown_costs_prints_no_unknown_line
  Scenario: Status prints no unknown-cost line when every cost is known
    Given one valid run at $0.50
    When I run evalkit.py status
    Then stdout does not contain "unknown cost"

  @gap @wip
  # Backed by: @gap
  Scenario: Status ignores a stored run whose task hash no longer matches the task
    Given a valid run of "n-1" on cell "base" recorded before the prompt of "n-1" was reworded
    When I run evalkit.py status
    Then the "noticed-row" line reads valid 0, invalid 0 and scored 0

  # ---------------------------------------------------------------- filters, validity edges and output

  @gap @wip
  # Backed by: @gap
  Scenario Outline: An unknown row or task id in a filter stops the command with exit code 2
    Given the rows and tasks of the fixture
    When I run evalkit.py plan <filter> nope
    Then the exit code is 2
    And stderr contains "<message>"

    Examples:
      | filter  | message           |
      | --rows  | unknown row: nope |
      | --tasks | unknown task: nope |

  @gap @wip
  # Backed by: @gap
  Scenario: An empty plan makes run skip the claude --version call
    Given every planned run of "noticed-row" on cell "cheap" is already stored as valid
    And a claude that logs every --version call
    When I run evalkit.py run --rows noticed-row --cells cheap
    Then stdout contains "0 run(s) planned"
    And the version log file is never created

  @gap @wip
  # Backed by: @gap
  Scenario Outline: Output that parses but cannot be a result, or breaks a precedence rule, is invalid with a named reason
    Given a claude that <behaviour>
    When I run evalkit.py run for "n-1" on cell "cheap" repeat 1
    Then runs.jsonl holds a line with valid false and invalid_reason starting with "<reason>"

    Examples:
      | behaviour                                                                           | reason         |
      | exits 0 and prints the JSON array "[]"                                              | json_parse     |
      | exits 0 with modelUsage naming the requested model plus a second model             | model_mismatch |
      | exits 1 with is_error true and modelUsage naming a different model                  | exit_code=1    |

  @gap @wip
  # Backed by: @gap
  Scenario: A valid run of a judge-graded task stores the answer but writes no score
    Given a judge-graded task "j-1" and a claude that answers with a complete answer block
    When I run evalkit.py run for "j-1" on cell "cheap" repeat 1
    Then runs.jsonl holds one valid line
    And private/answers/<run_id>.json exists
    And scores.jsonl holds no line, because scoring is left to judge

  @gap @wip
  # Backed by: @gap
  Scenario: The material is copied only for files delivery, including subdirectories
    Given a files task with material "sub/deep.txt" and an inline task with a material directory
    When a run of each starts
    Then the files task work directory holds "sub/deep.txt"
    And the inline task work directory is empty
