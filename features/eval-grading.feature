Feature: The evalkit grades runs in a sandboxed child process, judges with a blind pinned cell, reports honest numbers, applies the decision bar, checks its own material and publishes scalar-only results

  # ---------------------------------------------------------------- code grading

  # Backed by: tests/test_evalkit.py::test_grader_runs_in_a_child_process
  Scenario: A code grader runs in a child process, never in evalkit itself
    Given a task "n-1" whose grader.py returns the id of its own process in details.pid
    When evalkit grades the answer "42" of run "rid1"
    Then grading succeeds and one score line is appended with run_id "rid1", score 1.0 and passed true
    And the pid in the score line details is not the pid of the evalkit process

  # Backed by: tests/test_evalkit.py::test_grader_that_prints_does_not_corrupt_the_result
  Scenario: A grader that prints, even a fake result marker, does not corrupt its result
    Given a task "n-1" whose grader.py prints "noise" and writes the line "@@RESULT@@x" to stdout
    And that grader returns score 0.5 with passed false
    When evalkit grades the answer "42"
    Then one score line is appended with score 0.5

  # Backed by: tests/test_evalkit.py::test_default_timeout_is_thirty_seconds
  Scenario: The grader timeout defaults to thirty seconds
    Given the evalkit module is loaded without changes
    Then GRADER_TIMEOUT_S is 30

  # Backed by: tests/test_evalkit.py::test_hanging_grader_times_out_and_leaves_the_run_ungraded
  Scenario: A hanging grader times out and leaves the run ungraded
    Given a task "n-1" whose grader.py sleeps for 120 seconds
    And the grader timeout is 1 second
    When evalkit grades the answer "42"
    Then grading returns false within 15 seconds
    And scores.jsonl has no line
    And stderr contains "warning" and "exceeded 1 s"

  # Backed by: tests/test_evalkit.py::test_raising_grader_leaves_the_run_ungraded
  Scenario: A raising grader leaves the run ungraded instead of recording a failure
    Given a task "n-1" whose grade() raises RuntimeError "grader bug"
    When evalkit grades the answer "42"
    Then grading returns false
    And scores.jsonl has no line
    And stderr contains "grader bug"

  # Backed by: tests/test_evalkit.py::test_invalid_return_values_leave_the_run_ungraded
  Scenario: A grader result of the wrong shape leaves the run ungraded
    Given a task "n-1" whose grade() returns in turn "pass", a dict without passed, score 2.0, score "high", score NaN, passed "yes", score true, details "x", details holding a set, and None
    When evalkit grades the answer "42" under each of them
    Then every grading returns false
    And scores.jsonl has no line

  # Backed by: tests/test_evalkit.py::test_grader_reporting_its_own_error_is_a_fault_not_a_zero
  Scenario: A grader that reports details.error is a harness fault, not a score of zero
    Given a task "n-1" whose grade() returns score 0.0, passed false and details {"error": "bad_truth:KeyError"}
    When evalkit grades the answer "42"
    Then grading returns false
    And scores.jsonl has no line
    And stderr contains "internal error"

  # Backed by: tests/test_evalkit.py::test_grader_without_the_function_is_a_fault
  Scenario: A grader.py without a grade function is a fault
    Given a task "n-1" whose grader.py only sets x = 1
    When evalkit grades the answer "42"
    Then grading returns false

  # Backed by: tests/test_evalkit.py::test_missing_answer_block_is_still_a_scored_failure
  Scenario: A missing answer block scores zero without consulting the grader
    Given a task "n-1" whose grade() raises RuntimeError
    When evalkit grades a run whose answer block is None
    Then grading returns true
    And the only score line has score 0.0 and passed false

  # Backed by: tests/test_evalkit.py::test_run_with_a_raising_grader_stays_ungraded_end_to_end
  Scenario: A run whose grader raises stays ungraded through report and decide
    Given a task "n-1" whose grade() raises RuntimeError
    When I run "evalkit.py run --rows noticed-row --cells base --repeats 3"
    Then runs.jsonl holds 3 valid runs and scores.jsonl is empty
    And stdout contains "UNGRADED" and stderr contains "left ungraded"
    And report prints "3 ungraded run(s) excluded"
    And decide says INSUFFICIENT_DATA for "noticed-row"

  # Backed by: tests/test_evalkit.py::test_hanging_grader_end_to_end_and_regrade_after_a_fix
  Scenario: Grade re-scores stored answers after a grader fix without any model call
    Given a stored valid run of "n-1" on cell "base" whose grader hung and left it ungraded
    And grader.py is fixed to compare against truth.json
    When I run "evalkit.py grade"
    Then stdout contains "graded 1 run(s)"
    And no model call is made
    And runs.jsonl still holds 1 line
    And the only score line has passed true

  # Backed by: tests/test_evalkit.py::test_grade_command_reports_runs_that_stay_ungraded
  Scenario: Grade reports the runs whose new grader still faults
    Given a valid run of "n-1" on cell "base" scored under the first grader.py
    And grader.py is replaced by one that raises
    When I run "evalkit.py grade"
    Then stdout contains "graded 0 run(s); 1 left ungraded"
    And scores.jsonl still holds only the original line

  @gap @wip
  # Backed by: @gap
  Scenario: Grade skips runs already scored under the current grader
    Given a valid run of "n-1" on cell "base" already scored under the current grader.py
    When I run "evalkit.py grade"
    Then stdout contains "graded 0 run(s)"
    And scores.jsonl gains no line

  @gap @wip
  # Backed by: @gap
  Scenario: Editing grader.py gives later score lines a new grader id
    Given a valid run of "n-1" on cell "base" scored with grader id "code:" and eight hex digits
    When grader.py changes by one comment line and I run "evalkit.py grade"
    Then scores.jsonl keeps the first line and gains a second line for the same run_id
    And the grader_id of the second line differs from the first

  @gap @wip
  # Backed by: @gap
  Scenario: Changing only pass_threshold in task.json gives later score lines a new code grader id
    Given a valid run of "n-1" on cell "base" scored with a "code:" grader id
    When pass_threshold in task.json changes while grader.py stays the same and I run "evalkit.py grade"
    Then scores.jsonl keeps the first line and gains a second line for the same run_id
    And the grader_id of the second line differs from the first, because it hashes the grader.py bytes together with the pass_threshold

  @gap @wip
  # Backed by: @gap
  Scenario: Grade skips without a warning a valid run whose stored answer is gone, and ignores judge tasks
    Given a valid unscored run of "n-1" on cell "base" whose private/answers file is gone
    And a valid unjudged run of judge task "j-1"
    When I run "evalkit.py grade"
    Then stdout contains "graded 0 run(s)" and no "left ungraded" text
    And stderr has no warning
    And scores.jsonl gains no line

  # ---------------------------------------------------------------- judge grading

  # Backed by: tests/test_evalkit.py::test_judge_flow_scores_every_pass_blind_to_the_cell
  Scenario: The judge scores every pass with the pinned judge cell and never sees the graded cell
    Given a valid run of judge task "j-1" on cell "cheap" with the answer "42"
    And the harness judge has cell "judge" and repeats 2
    When I run "evalkit.py judge" and the judge replies with score 0.9
    Then claude is launched twice with model "claude-test-judge", an empty tool list, no files and system prompt "You are a strict grader."
    And each prompt contains the task prompt, the rubric and the answer "42"
    And no prompt or working directory contains the cell id "cheap"
    And the two score lines carry grader ids "judge:judge:<sha8 of rubric.md>:0" and ":1"
    And a second "evalkit.py judge" launches claude zero times

  # Backed by: tests/test_evalkit.py::test_rubric_change_triggers_rejudging_not_rerunning
  Scenario: A changed rubric triggers new judging but no new run
    Given judge task "j-1" with one run already judged under its rubric
    When rubric.md is rewritten and I run "evalkit.py judge" again
    Then runs.jsonl still holds 1 line
    And scores.jsonl holds 4 lines

  # Backed by: tests/test_evalkit.py::test_effective_judge_score_is_mean_and_majority_vote
  Scenario: A judged run is scored once every pass is in, as the mean with a majority vote
    Given judge.repeats is 2 and run "r1" has pass 0 with score 0.8 and passed true
    Then the run has no effective score yet
    When pass 1 arrives with score 0.4 and passed false
    Then the effective score is 0.6
    And the effective passed is false because one of two is not a majority

  # Backed by: tests/test_evalkit.py::test_unparseable_judge_reply_is_retried_then_scored
  Scenario: An unparseable judge reply is retried and the cost of failed attempts is kept
    Given judge task "j-1" has one run and every judge call costs $0.02
    And the judge replies in turn with no markers, with "{not json" and with a good judgment, then a good judgment for the second pass
    When I run "evalkit.py judge --jobs 1"
    Then claude is launched 4 times
    And the two score lines have judge_attempts 1 and 3
    And the line with judge_attempts 3 has judge_cost_usd 0.06
    And both lines have passed true
    And stdout does not contain "left missing"

  # Backed by: tests/test_evalkit.py::test_rejected_judgment_shape_is_retried
  Scenario: A judgment the grader rejects is retried like an unparseable one
    Given the judge first replies with the JSON object {"verdict": "fine"} and then with a good judgment
    When I run "evalkit.py judge --jobs 1"
    Then claude is launched 3 times
    And scores.jsonl holds 2 lines

  # Backed by: tests/test_evalkit.py::test_judge_format_fault_after_retries_leaves_the_pass_missing_and_reports_it
  Scenario: A judge format fault after the retries leaves the pass missing, never a failing score
    Given the judge always replies "no markers here" and judge.repeats is 2
    When I run "evalkit.py judge --jobs 1"
    Then claude is launched 6 times, which is 2 passes times 1 try plus 2 retries
    And scores.jsonl is empty
    And stdout contains "2 judge pass(es) left missing"
    And stderr contains "left missing after 3 attempt(s)"
    And status shows the one run of "judge-row" as valid, scored 0 and ungraded 1

  # Backed by: tests/test_evalkit.py::test_partial_judge_failure_keeps_the_good_pass_and_the_run_ungraded
  Scenario: A later judge run fills only the pass that is missing
    Given pass 0 got three unusable replies and pass 1 got a good judgment
    Then scores.jsonl holds 1 line and the run has no effective score
    When I run "evalkit.py judge" again with a good judgment
    Then claude is launched once
    And scores.jsonl holds 2 lines

  # Backed by: tests/test_evalkit.py::test_invalid_judge_call_is_not_a_format_fault_and_not_retried
  Scenario: An invalid judge call is not retried
    Given the judge process reports a model other than "claude-test-judge"
    When I run "evalkit.py judge"
    Then claude is launched twice, once per pass
    And scores.jsonl is empty
    And stderr contains "judge call invalid"

  # Backed by: tests/test_evalkit.py::test_answer_without_block_scores_zero_without_a_model_call
  Scenario: A judge-graded run with no answer block scores zero without a judge call
    Given a valid run of judge task "j-1" whose answer had no block
    When I run "evalkit.py judge"
    Then no model call is made
    And scores.jsonl holds two lines with score 0.0

  # Backed by: tests/test_evalkit.py::test_judge_scores_carry_the_version
  Scenario: Judge score lines record the CLI version
    Given the stub claude reports version "9.9.9 (Fake)"
    When judge task "j-1" is run and judged
    Then both judge score lines have details.cli_version "9.9.9 (Fake)"

  @gap @wip
  # Backed by: @gap
  Scenario: A judge grader that times out is not retried
    Given score_judgment() exceeds the 30 second grader timeout
    When I run "evalkit.py judge --jobs 1"
    Then each affected pass is tried once
    And no score line is appended for it
    And stderr contains "left missing after 1 attempt(s)"

  @gap @wip
  # Backed by: @gap
  Scenario: A judge pass with no stored answer is skipped
    Given a valid run of judge task "j-1" whose private/answers file is gone
    When I run "evalkit.py judge"
    Then no model call is made
    And scores.jsonl gains no line
    And stdout contains "skipped: no stored answer"

  @gap @wip
  # Backed by: @gap
  Scenario: A judge call of unknown cost is flagged on the score line and charged the per-run cap
    Given every judge call reports no total_cost_usd and the per-run budget cap is $1.00
    When I run "evalkit.py judge --jobs 1" on a judged-task run with one good reply per pass
    Then each score line has details.judge_cost_unknown true
    And stdout contains "judge cost" and "call(s) with unknown cost charged at the per-run cap"

  # ---------------------------------------------------------------- status and report

  # Backed by: tests/test_evalkit.py::test_report_numbers_on_a_synthetic_dataset
  Scenario: Report prints pass rate, mean score, mean cost and thinking tokens per cell
    Given row "noticed-row" with 3 runs of "base" scoring true, true, false at $0.10 and 300 thinking tokens
    And 3 passing runs of "cheap" at $0.04 and 60 thinking tokens, and no run of "up"
    When I run "evalkit.py report --rows noticed-row"
    Then the "base" line reads runs 3, valid 3, passed 2, pass rate 66.7%, mean score 0.667, cost $0.1000, thinking 300, tasks 1
    And the "cheap" line reads runs 3, valid 3, passed 3, pass rate 100.0%, mean score 1.000, cost $0.0400, thinking 60, tasks 1
    And the "up" line reads runs 0, valid 0, passed 0, n/a for rate, score and thinking, "$n/a" for cost, and tasks 0

  @gap @wip
  # Backed by: @gap
  Scenario: The report's mean cost averages only the known costs of a cell
    Given 3 passing runs of "cheap" of which two cost $0.04 and one has cost_usd null
    When I run "evalkit.py report --rows noticed-row"
    Then the "cheap" line shows the mean cost "$0.0400" with no marker for the unknown run
    And "evalkit.py decide --json" refuses to compare the cell, with the reason "cost unknown for 1 run(s)"

  @gap @wip
  # Backed by: @gap
  Scenario: Without private/ the report and decide fall back to tasks.json
    Given the evals directory has no private/tasks directory but a tasks.json and stored scores
    When I run "evalkit.py report --rows noticed-row" and "evalkit.py decide --json"
    Then both succeed
    And a code score counts under any grader id starting with "code:" and a judge score under any id starting with "judge:<cell>:"

  # Backed by: tests/test_evalkit.py::test_report_markdown_and_stale_runs_ignored
  Scenario: Report ignores runs made under a changed task prompt and can print markdown
    Given one valid run of "base" on "n-1"
    And the prompt.md of "n-1" is then rewritten
    When I run "evalkit.py report --md --rows noticed-row"
    Then stdout contains the header "| cell | role | runs |"
    And stdout contains the line "| base | baseline | 0 | 0 |"

  # Backed by: tests/test_evalkit.py::test_unknown_cost_is_not_free_in_report_or_decide
  Scenario: An unknown cost is never treated as free in report or decide
    Given 3 passing runs of "base" at $0.10 and 3 passing runs of "cheap" with cost_usd null
    When I run "evalkit.py report --rows noticed-row" and "evalkit.py decide --json"
    Then the "cheap" report line shows the mean cost "$n/a"
    And the recommendation for "noticed-row" is not MOVE_TO
    And the "cheap" candidate reason contains "cost unknown for 3 run(s)"

  # Backed by: tests/test_evalkit.py::test_default_phase_is_screening_only
  Scenario: Report covers the screening phase by default
    Given row "silent-row" with screening task "s-1" at $0.10 and confirmation tasks "s-c1" and "s-c2" at $0.50 for cell "base"
    When I run "evalkit.py report --rows silent-row"
    Then stdout contains "phase: screening; tasks: s-1"
    And the "base" line shows runs 3, valid 3, passed 3, mean cost $0.1000 and tasks 1

  # Backed by: tests/test_evalkit.py::test_confirmation_phase_and_tasks_column
  Scenario: Report with --phase confirmation covers only the confirmation tasks
    Given the same runs of "base" on screening task "s-1" and confirmation tasks "s-c1" and "s-c2"
    When I run "evalkit.py report --rows silent-row --phase confirmation"
    Then stdout contains "phase: confirmation; tasks: s-c1, s-c2"
    And the "base" line shows runs 6, mean cost $0.5000 and tasks 2
    And stdout does not contain "warning"

  # Backed by: tests/test_evalkit.py::test_all_phase_mixes_and_warns_once
  Scenario: Report with --phase all mixes both phases and warns once
    Given the same runs of "base" on screening task "s-1" and confirmation tasks "s-c1" and "s-c2"
    When I run "evalkit.py report --phase all"
    Then the first output line starts with "warning"
    And "cells may cover different task sets" appears exactly once
    And stdout contains "phase: all; tasks: s-1, s-c1, s-c2"
    And the "base" line of "silent-row" shows runs 9 and tasks 3

  # Backed by: tests/test_evalkit.py::test_report_header_names_none_when_a_phase_has_no_tasks
  Scenario: Report names none when the chosen phase has no task for the row
    Given row "noticed-row" has only a screening task
    When I run "evalkit.py report --rows noticed-row --phase confirmation"
    Then stdout contains "phase: confirmation; tasks: none"

  @gap @wip
  # Backed by: @gap
  Scenario: Report refuses an unknown row id
    Given the rows "noticed-row", "silent-row" and "judge-row"
    When I run "evalkit.py report --rows nope"
    Then the exit code is 2
    And stderr contains "unknown row: nope"

  # ---------------------------------------------------------------- decide: noticed rows

  # Backed by: tests/test_evalkit.py::test_noticed_moves_to_cheaper_within_one_extra_miss
  Scenario: A noticed row moves to a cheaper cell that misses at most one more run
    Given row "noticed-row" with noticed_extra_misses 1
    And "base" passes 3 of 3 screening runs at $0.10 and "cheap" passes 2 of 3 at $0.05
    When I run "evalkit.py decide --json"
    Then the recommendation for "noticed-row" is MOVE_TO with cell "cheap"

  # Backed by: tests/test_evalkit.py::test_noticed_two_extra_misses_keeps_baseline
  Scenario: A noticed row keeps the baseline when the cheaper cell misses two more runs
    Given "base" passes 3 of 3 screening runs at $0.10 and "cheap" passes 1 of 3 at $0.05
    When I run "evalkit.py decide --json"
    Then the recommendation for "noticed-row" is KEEP
    And the "cheap" candidate reason contains "2 failures vs baseline 0 + 1"

  @gap @wip
  # Backed by: @gap
  Scenario: A noticed candidate under a 0.5 pass rate fails its own row
    Given "base" passes 0 of 3 screening runs at $0.10 and "cheap" passes 0 of 3 at $0.05
    When I run "evalkit.py decide --json"
    Then the "cheap" candidate has qualifies false
    And the "cheap" candidate reason is "fails its own row"

  @gap @wip
  # Backed by: @gap
  Scenario: A noticed baseline under a 0.5 pass rate fails its row and names the up cell
    Given "base" passes 1 of 3 screening runs at $0.10 and "up", an up_reference, passes 3 of 3 at $0.30
    And "cheap" has no runs
    When I run "evalkit.py decide --json"
    Then the recommendation for "noticed-row" is BASELINE_FAILS with cell "up"

  # Backed by: tests/test_evalkit.py::test_saving_below_the_materiality_threshold_keeps_baseline
  Scenario: A saving under min_saving_fraction keeps the baseline
    Given the harness decision has min_saving_fraction 0.25
    And "base" and "cheap" both pass 3 of 3 screening runs, at $0.10 and $0.09
    When I run "evalkit.py decide --json"
    Then the recommendation for "noticed-row" is KEEP
    And the "cheap" candidate reason contains "cheaper by only 10%"

  # Backed by: tests/test_evalkit.py::test_saving_at_or_above_the_threshold_still_moves
  Scenario: A saving above min_saving_fraction still moves
    Given the harness decision has min_saving_fraction 0.25
    And "base" and "cheap" both pass 3 of 3 screening runs, at $0.10 and $0.07
    When I run "evalkit.py decide --json"
    Then the recommendation for "noticed-row" is MOVE_TO with cell "cheap"

  # Backed by: tests/test_evalkit.py::test_materiality_does_not_apply_when_the_baseline_fails_its_row
  Scenario: The saving threshold is waived when the baseline fails its row
    Given the harness decision has min_saving_fraction 0.25
    And "base" passes 0 of 3 screening runs at $0.10 and "cheap" passes 3 of 3 at $0.095
    When I run "evalkit.py decide --json"
    Then the recommendation for "noticed-row" is MOVE_TO with cell "cheap"

  # Backed by: tests/test_evalkit.py::test_tie_on_measured_cost_keeps_baseline
  Scenario: A tie on measured cost keeps the baseline
    Given "base" and "cheap" both pass 3 of 3 screening runs at $0.10
    When I run "evalkit.py decide --json"
    Then the recommendation for "noticed-row" is KEEP
    And the "cheap" candidate reason contains "not cheaper"

  # Backed by: tests/test_evalkit.py::test_cheaper_is_measured_cost_not_list_price
  Scenario: Cheaper means measured cost per run, not list price
    Given "cheap" has the lowest list price in cells.json
    And "base" and "cheap" both pass 3 of 3 screening runs, at $0.10 and $0.30
    When I run "evalkit.py decide --json"
    Then the recommendation for "noticed-row" is KEEP
    And the "cheap" candidate reason contains "$0.3000 vs baseline $0.1000"

  # Backed by: tests/test_evalkit.py::test_cheapest_qualifying_candidate_wins
  Scenario: The cheapest qualifying candidate wins whatever its role
    Given "base" passes 3 of 3 at $0.10, "cheap" passes 3 of 3 at $0.06 and "up" passes 3 of 3 at $0.04
    When I run "evalkit.py decide --json"
    Then the recommendation for "noticed-row" has cell "up"

  # ---------------------------------------------------------------- decide: silent-damage rows

  # Backed by: tests/test_evalkit.py::test_silent_clean_candidate_needs_confirmation_with_exact_missing_runs
  Scenario: A clean silent-damage candidate needs confirmation and lists the exact missing runs
    Given row "silent-row" with screening task "s-1" and confirmation tasks "s-c1" and "s-c2"
    And "base" and "cheap" both pass 3 of 3 screening runs, at $0.10 and $0.05
    When I run "evalkit.py decide --json"
    Then the recommendation for "silent-row" is NEEDS_CONFIRMATION with cell "cheap"
    And missing_runs holds six entries, repeats 1 to 3 of "cheap" on "s-c1" and on "s-c2"

  # Backed by: tests/test_evalkit.py::test_silent_needs_enough_confirmation_tasks_authored
  Scenario: A silent-damage row needs confirmation_tasks_min confirmation tasks authored
    Given confirmation_tasks_min is 2 and the row has only the confirmation task "s-c1"
    And "base" and "cheap" both pass 3 of 3 screening runs
    When I run "evalkit.py decide --json"
    Then the recommendation for "silent-row" is NEEDS_CONFIRMATION
    And a note contains "1 more confirmation task"

  # Backed by: tests/test_evalkit.py::test_silent_confirmed_candidate_moves
  Scenario: A silent-damage candidate that passes every confirmation run moves
    Given "base" and "cheap" both pass 3 of 3 runs on "s-1", "s-c1" and "s-c2"
    When I run "evalkit.py decide --json"
    Then the recommendation for "silent-row" is MOVE_TO with cell "cheap"

  # Backed by: tests/test_evalkit.py::test_silent_one_screening_miss_disqualifies
  Scenario: One screening miss disqualifies a silent-damage candidate
    Given "base" passes 3 of 3 screening runs and "cheap" passes 2 of 3 at a lower cost
    When I run "evalkit.py decide --json"
    Then the recommendation for "silent-row" is KEEP
    And the "cheap" candidate reason contains "silent-damage needs every run"

  # Backed by: tests/test_evalkit.py::test_silent_candidate_failing_confirmation_is_dropped
  Scenario: A silent-damage candidate that fails a confirmation run is dropped
    Given "base" and "cheap" pass 3 of 3 runs on "s-1" and "s-c1"
    And "cheap" passes 2 of 3 runs on "s-c2"
    When I run "evalkit.py decide --json"
    Then the recommendation for "silent-row" is KEEP
    And the "cheap" candidate reason contains "failed 1 confirmation"

  # Backed by: tests/test_evalkit.py::test_silent_one_failed_confirmation_run_is_final_even_if_others_are_missing
  Scenario: One failed confirmation run is final even while other confirmation runs are missing
    Given "base" and "cheap" pass 3 of 3 screening runs
    And "cheap" has one failed run among the three runs on "s-c1" and no run on "s-c2"
    When I run "evalkit.py decide --json"
    Then the recommendation for "silent-row" is KEEP
    And the "cheap" candidate reason contains "failed 1 confirmation"

  # Backed by: tests/test_evalkit.py::test_silent_candidate_needs_confirmation_even_when_the_baseline_missed_a_run
  Scenario: A candidate still needs confirmation when the baseline missed a screening run
    Given "base" passes 2 of 3 screening runs and "cheap" passes 3 of 3 at a lower cost
    When I run "evalkit.py decide --json"
    Then the recommendation for "silent-row" is NEEDS_CONFIRMATION with cell "cheap"
    And missing_runs holds six entries, all for cell "cheap" on "s-c1" and "s-c2"

  # Backed by: tests/test_evalkit.py::test_silent_missed_baseline_candidate_moves_once_it_passes_confirmation, tests/test_evalkit.py::test_silent_clean_baseline_needs_no_baseline_confirmation_runs
  Scenario: A candidate that passes confirmation moves, and the baseline never needs confirmation runs of its own
    Given "base" passes 2 of 3 screening runs and "cheap" passes 3 of 3 at a lower cost
    And "cheap" passes 3 of 3 runs on "s-c1" and "s-c2" while "base" has no confirmation run
    When I run "evalkit.py decide --json"
    Then the recommendation for "silent-row" is MOVE_TO with cell "cheap"
    And missing_runs is empty
    Given instead "base" passes 3 of 3 screening runs and "cheap" passes 3 of 3 runs on "s-c1" and "s-c2"
    When I run "evalkit.py decide --json"
    Then the recommendation for "silent-row" is MOVE_TO

  # Backed by: tests/test_evalkit.py::test_silent_partial_confirmation_lists_only_the_remaining_candidate_runs
  Scenario: Partial confirmation lists only the remaining runs of the candidate
    Given "base" and "cheap" pass 3 of 3 screening runs
    And "cheap" has 3 passing runs on "s-c1" and 2 passing runs on "s-c2"
    When I run "evalkit.py decide --json"
    Then the recommendation for "silent-row" is NEEDS_CONFIRMATION
    And missing_runs is exactly [{"task": "s-c2", "cell": "cheap", "repeat": 3}]

  # Backed by: tests/test_evalkit.py::test_silent_failed_baseline_candidate_still_needs_confirmation
  Scenario: A candidate beside a baseline that fails every run still needs confirmation
    Given "base" passes 0 of 3 screening runs and "cheap" passes 3 of 3
    When I run "evalkit.py decide --json"
    Then the recommendation for "silent-row" is NEEDS_CONFIRMATION with cell "cheap"

  # Backed by: tests/test_evalkit.py::test_baseline_fails_names_cheapest_passing_up_cell
  Scenario: A failing baseline with no qualifying candidate names the passing up cell
    Given "base" passes 1 of 3 and "cheap" passes 1 of 3 screening runs, at $0.10 and $0.20
    And "up", the only up_reference cell, passes 3 of 3 at $0.30
    When I run "evalkit.py decide --json"
    Then the recommendation for "silent-row" is BASELINE_FAILS with cell "up"

  # Backed by: tests/test_evalkit.py::test_baseline_fails_and_no_up_cell_passes
  Scenario: A failing baseline with no passing up cell gives BASELINE_FAILS with a null cell
    Given "base" and "cheap" pass 0 of 3 screening runs and "up" passes 2 of 3
    When I run "evalkit.py decide --json"
    Then the recommendation for "silent-row" is BASELINE_FAILS with cell null

  # Backed by: tests/test_evalkit.py::test_silent_failed_baseline_and_failed_confirmation_falls_back_to_the_up_cell
  Scenario: A failed confirmation sends a failing baseline back to the up cell
    Given "base" passes 2 of 3 screening runs and "cheap" passes 3 of 3
    And "up" passes 3 of 3 screening runs at $0.30
    And "cheap" passes 2 of 3 runs on "s-c1"
    When I run "evalkit.py decide --json"
    Then the recommendation for "silent-row" is BASELINE_FAILS with cell "up"

  # ---------------------------------------------------------------- decide: insufficient data, ungraded runs, provisional

  # Backed by: tests/test_evalkit.py::test_incomplete_data_is_insufficient
  Scenario: A baseline without its full screening runs gives INSUFFICIENT_DATA
    Given "base" has 2 of 3 screening runs on "s-1"
    When I run "evalkit.py decide --json"
    Then the recommendation for "silent-row" is INSUFFICIENT_DATA
    And missing_runs lists repeat 3
    When "base" has all 3 runs and no other cell has any
    Then the recommendation for "silent-row" is still INSUFFICIENT_DATA

  @gap @wip
  # Backed by: @gap
  Scenario: A row with no screening task gives INSUFFICIENT_DATA
    Given a row whose tasks are all confirmation tasks
    When I run "evalkit.py decide --json"
    Then the recommendation for that row is INSUFFICIENT_DATA
    And a note is "no screening tasks"

  @gap @wip
  # Backed by: @gap
  Scenario: A baseline with unknown run costs cannot be compared
    Given "base" has 3 scored screening runs with cost_usd null on "n-1"
    When I run "evalkit.py decide --json"
    Then the recommendation for "noticed-row" is INSUFFICIENT_DATA
    And a note contains "baseline has 3 run(s) with unknown cost: costs cannot be compared"

  # Backed by: tests/test_evalkit.py::test_ungraded_baseline_run_is_insufficient_data
  Scenario: An ungraded baseline run gives INSUFFICIENT_DATA
    Given "base" has 2 passing runs and 1 valid run left ungraded, and "cheap" passes 3 of 3 at a lower cost
    When I run "evalkit.py decide --json"
    Then the recommendation for "noticed-row" is INSUFFICIENT_DATA
    And missing_runs is exactly [{"task": "n-1", "cell": "base", "repeat": 3, "ungraded": true}]
    And a note contains "ungraded"

  # Backed by: tests/test_evalkit.py::test_ungraded_candidate_run_makes_the_row_insufficient_even_if_another_candidate_is_complete
  Scenario: An ungraded candidate run holds the row back even when another candidate is complete
    Given "base" passes 3 of 3 at $0.10 and "cheap" has 1 passing run and 2 valid runs left ungraded
    When I run "evalkit.py decide --json"
    Then the recommendation for "noticed-row" is INSUFFICIENT_DATA
    And the "cheap" candidate reason contains "incomplete"
    And missing_runs lists repeats 2 and 3
    When "up" has 3 passing runs at $0.07
    Then the recommendation for "noticed-row" is still INSUFFICIENT_DATA with cell null
    And every missing run is marked ungraded

  # Backed by: tests/test_evalkit.py::test_a_run_that_was_never_made_is_missing_not_ungraded
  Scenario: A run that was never made does not block a complete candidate
    Given "base" passes 3 of 3 at $0.10, "cheap" has only 2 runs at $0.05 and "up" passes 3 of 3 at $0.07
    When I run "evalkit.py decide --json"
    Then the recommendation for "noticed-row" is MOVE_TO with cell "up"

  # Backed by: tests/test_evalkit.py::test_ungraded_confirmation_run_makes_the_row_insufficient
  Scenario: An ungraded confirmation run gives INSUFFICIENT_DATA
    Given "base" and "cheap" pass 3 of 3 screening runs
    And "cheap" has 3 passing runs on "s-c1" and 2 passing plus 1 ungraded run on "s-c2"
    When I run "evalkit.py decide --json"
    Then the recommendation for "silent-row" is INSUFFICIENT_DATA
    And missing_runs is exactly [{"task": "s-c2", "cell": "cheap", "repeat": 3, "ungraded": true}]
    And a note contains "ungraded"

  # Backed by: tests/test_evalkit.py::test_missing_candidate_runs_make_the_recommendation_provisional
  Scenario: A recommendation resting on an incomplete candidate is provisional
    Given "base" passes 3 of 3 at $0.10, "cheap" passes 3 of 3 at $0.04 and "up" has 2 runs
    When I run "evalkit.py decide --json" and "evalkit.py decide"
    Then the result for "noticed-row" is MOVE_TO "cheap" with provisional true
    And a note is "provisional: candidate up has 1 missing run(s)"
    And the text line matches "noticed-row .*: MOVE_TO cheap (provisional)"

  # Backed by: tests/test_evalkit.py::test_unmeasured_candidate_is_provisional_too
  Scenario: A candidate with no runs at all also makes the recommendation provisional
    Given "base" passes 3 of 3 at $0.10, "cheap" passes 3 of 3 at $0.04 and "up" has no run
    When I run "evalkit.py decide --json"
    Then the recommendation for "noticed-row" is MOVE_TO with provisional true
    And a note is "provisional: candidate up has 3 missing run(s)"

  # Backed by: tests/test_evalkit.py::test_complete_grid_is_not_provisional
  Scenario: A complete grid is not provisional
    Given "base", "cheap" and "up" each pass 3 of 3 at $0.10, $0.04 and $0.20
    When I run "evalkit.py decide --json" and "evalkit.py decide"
    Then the result for "noticed-row" is MOVE_TO "cheap" with provisional false
    And no note contains "provisional"
    And the text output for "noticed-row" does not contain "(provisional)"

  # Backed by: tests/test_evalkit.py::test_every_result_carries_the_provisional_flag
  Scenario: Every decide result carries a boolean provisional flag
    Given no run has been made
    When I run "evalkit.py decide --json"
    Then every result has provisional false

  # Backed by: tests/test_evalkit.py::test_exhausted_candidate_runs_are_listed_in_the_notes
  Scenario: A candidate run that used up its retries is named as one that will never complete
    Given "base" passes 3 of 3, "cheap" passes 3 of 3 and "up" has 2 runs
    And run 3 of "up" has 3 invalid attempts, the initial one plus 2 retries
    When I run "evalkit.py decide --json" and "evalkit.py decide"
    Then a note contains "candidate up: run n-1 #3 exhausted its retries (3 invalid attempts)"
    And provisional is true
    And the "up" candidate has exhausted 1
    And the text output contains "never complete"

  # Backed by: tests/test_evalkit.py::test_a_run_still_retryable_is_not_listed_as_exhausted
  Scenario: A candidate run that can still be retried is not listed as exhausted
    Given "base" passes 3 of 3, "cheap" passes 3 of 3 and "up" has 2 runs
    And run 3 of "up" has 2 invalid attempts
    When I run "evalkit.py decide --json"
    Then no note contains "exhausted"

  # Backed by: tests/test_evalkit.py::test_decide_text_output_lists_reasons
  Scenario: Decide prints a text report with the reason per candidate
    Given "base" and "cheap" both pass 3 of 3 screening runs at $0.10
    When I run "evalkit.py decide"
    Then stdout contains "noticed-row", "KEEP" and "not cheaper"

  # ---------------------------------------------------------------- selfcheck

  # Backed by: tests/test_evalkit.py::test_clean_tasks_pass
  Scenario: Selfcheck passes clean tasks
    Given four code tasks and one judge task whose graders accept their perfect fixture and reject their flawed fixture
    When I run "evalkit.py selfcheck"
    Then the exit code is 0
    And stdout contains "5 task(s), 0 problem(s)"

  # Backed by: tests/test_evalkit.py::test_bad_grader_is_caught
  Scenario: Selfcheck catches a grader that does not give the perfect fixture full marks
    Given a grader for "n-1" that always returns score 0.0 and passed false
    When I run "evalkit.py selfcheck"
    Then the exit code is 1
    And stdout contains "perfect.txt scored 0.0"

  # Backed by: tests/test_evalkit.py::test_grader_that_passes_a_flawed_fixture_is_caught
  Scenario: Selfcheck catches a grader that passes a flawed fixture
    Given a grader for "n-1" that always returns score 1.0 and passed true
    When I run "evalkit.py selfcheck"
    Then stdout contains "flawed_a.txt passed but is flawed"

  # Backed by: tests/test_evalkit.py::test_selfcheck_reports_a_crashing_grader_instead_of_dying
  Scenario: Selfcheck reports a crashing grader instead of dying
    Given a grader for "n-1" whose grade() raises
    When I run "evalkit.py selfcheck"
    Then the exit code is 1
    And stdout contains "grader failed on fixtures"

  # Backed by: tests/test_evalkit.py::test_code_grader_rejecting_a_flawed_fixture_is_still_a_problem
  Scenario: A code grader may not reject a flawed fixture through details.error
    Given a code grader for "n-1" that returns details.error on the answer "41"
    When I run "evalkit.py selfcheck"
    Then the exit code is 1
    And stdout contains "grader failed on fixtures"

  # Backed by: tests/test_evalkit.py::test_judge_grader_may_reject_a_malformed_flawed_fixture
  Scenario: A judge grader may reject a malformed flawed fixture through details.error
    Given a judge grader for "j-1" that returns details.error for a judgment without a score
    And a fixture judgment_flawed_malformed.json holding {}
    When I run "evalkit.py selfcheck"
    Then stdout contains "0 problem(s)"

  # Backed by: tests/test_evalkit.py::test_ok_fixture_that_fails_is_caught
  Scenario: Selfcheck requires every ok fixture of a code task to pass
    Given "n-1" has the ok fixture ok_a.txt "  42  " and the ok fixture ok_b.txt "41"
    When I run "evalkit.py selfcheck"
    Then the exit code is 1
    And stdout contains "n-1: ok_b.txt is an ok fixture but did not pass"
    And stdout does not contain "ok_a.txt"

  # Backed by: tests/test_evalkit.py::test_judge_ok_fixtures_are_checked
  Scenario: Selfcheck requires every ok fixture of a judge task to pass
    Given "j-1" has the ok fixtures ok_a.json {"score": 0.8} and ok_b.json {"score": 0.3}
    When I run "evalkit.py selfcheck"
    Then stdout contains "j-1: ok_b.json is an ok fixture but did not pass"

  # Backed by: tests/test_evalkit.py::test_planted_fake_secret_is_caught
  Scenario: Selfcheck's secret scan catches an API-key-shaped string in task material
    Given "n-1" has a material file notes.txt containing "token = sk-ant-api03-" and a long filler
    When I run "evalkit.py selfcheck"
    Then the exit code is 1
    And stdout contains "notes.txt matches secret pattern"

  # Backed by: tests/test_evalkit.py::test_env_file_and_private_key_are_caught
  Scenario: Selfcheck's secret scan catches an env file and a PEM header
    Given "n-1" has the material file ".env.local" and "s-1" has the material file "k.pem" starting with "-----BEGIN RSA PRIVATE KEY-----"
    When I run "evalkit.py selfcheck"
    Then stdout contains ".env.local is an env file"
    And stdout contains "k.pem matches secret pattern"

  @gap @wip
  # Backed by: @gap
  Scenario: Selfcheck's secret scan skips the fixtures directory
    Given "n-1" has an extra file fixtures/notes.txt containing "sk-ant-api03-" and a long filler
    When I run "evalkit.py selfcheck"
    Then the exit code is 0
    And stdout contains "0 problem(s)"

  # Backed by: tests/test_evalkit.py::test_missing_task_fields_are_caught
  Scenario: Selfcheck reports a task.json with missing fields
    Given the task.json of "n-1" is {"id": "n-1"}
    When I run "evalkit.py selfcheck"
    Then stdout contains "missing fields"

  # Backed by: tests/test_evalkit.py::test_pass_threshold_must_match_truth_when_truth_has_one
  Scenario: Selfcheck requires task.json and truth.json to agree on pass_threshold
    Given the task.json of "n-1" has pass_threshold 0.7
    And its truth.json has no pass_threshold, which passes selfcheck
    When truth.json gets pass_threshold 0.9 and I run "evalkit.py selfcheck"
    Then the exit code is 1
    And stdout contains "n-1: task.json pass_threshold 0.7 != truth.json pass_threshold 0.9"

  @gap @wip
  # Backed by: @gap
  Scenario: Selfcheck reports a task without its perfect fixture
    Given "n-1" has no fixtures/perfect.txt
    When I run "evalkit.py selfcheck"
    Then the exit code is 1
    And stdout contains "n-1: fixtures/perfect.txt missing"

  @gap @wip
  # Backed by: @gap
  Scenario: Selfcheck reports a task without a flawed fixture
    Given "n-1" has no file matching fixtures/flawed_*.txt
    When I run "evalkit.py selfcheck"
    Then the exit code is 1
    And stdout contains "n-1: no flawed fixtures"

  @gap @wip
  # Backed by: @gap
  Scenario: Selfcheck reports a task whose row is unknown
    Given the task.json of "n-1" names the row "ghost-row"
    When I run "evalkit.py selfcheck"
    Then the exit code is 1
    And stdout contains "n-1: unknown row 'ghost-row'"

  @gap @wip
  # Backed by: @gap
  Scenario: Selfcheck reports a delivery that does not match the material
    Given the task.json of "n-1" says delivery "inline" while material/ holds data.txt
    When I run "evalkit.py selfcheck"
    Then the exit code is 1
    And stdout contains "n-1: delivery 'inline' does not match material/ contents"

  @gap @wip
  # Backed by: @gap
  Scenario: Selfcheck reports a task directory whose name differs from its id
    Given the directory of task "n-1" is renamed "n-one"
    When I run "evalkit.py selfcheck"
    Then the exit code is 1
    And stdout contains "n-one: directory name differs from id 'n-1'"

  @gap @wip
  # Backed by: @gap
  Scenario: Selfcheck reports a judge task without its rubric
    Given judge task "j-1" has no rubric.md
    When I run "evalkit.py selfcheck"
    Then the exit code is 1
    And stdout contains "j-1: rubric.md missing"

  @gap @wip
  # Backed by: @gap
  Scenario: Selfcheck without private material stops with an explanation
    Given the evals directory has no private/tasks directory
    When I run "evalkit.py selfcheck"
    Then the exit code is 2
    And stderr contains "private/ holds the task prompts, material and graders"

  # ---------------------------------------------------------------- manifest and public results

  # Backed by: tests/test_evalkit.py::test_manifest_is_sorted_and_deterministic
  Scenario: The manifest is sorted by task id, deterministic and carries a fixed key list
    Given the five synthetic tasks
    When I run "evalkit.py manifest" twice
    Then tasks.json is byte for byte the same both times
    And its entries are sorted by id
    And the keys of the first entry are id, row, phase, title, delivery, grading_type, pass_rule, pass_threshold, task_hash in that order

  # Backed by: tests/test_evalkit.py::test_pass_rule_public_is_used_when_present
  Scenario: The manifest publishes pass_rule_public instead of the private pass rule
    Given the task.json of "n-1" has a private pass_rule and a pass_rule_public "no invented answers, at most one miss"
    When I run "evalkit.py manifest"
    Then the manifest entry of "n-1" has pass_rule "no invented answers, at most one miss"
    And that entry has no key "pass_rule_public"

  # Backed by: tests/test_evalkit.py::test_generic_rule_replaces_the_private_text_when_there_is_no_public_one
  Scenario: Without a public rule the manifest publishes a generic threshold rule
    Given the task.json of "n-1" has a private pass_rule naming trap items and pass_threshold 0.85
    When I run "evalkit.py manifest"
    Then the manifest entry of "n-1" has pass_rule "score >= 0.85"
    And tasks.json does not contain the private words

  # Backed by: tests/test_evalkit.py::test_blank_public_rule_falls_back_to_the_generic_one
  Scenario: A blank pass_rule_public falls back to the generic rule
    Given the task.json of "n-1" has pass_rule_public "   " and pass_threshold 0.7
    When I run "evalkit.py manifest"
    Then the manifest entry of "n-1" has pass_rule "score >= 0.7"

  # Backed by: tests/test_evalkit.py::test_task_hash_is_not_affected_by_the_pass_rule
  Scenario: Editing the pass rule does not change the task hash
    Given the task hash of "n-1"
    When its pass_rule and pass_rule_public are rewritten
    Then the task hash of "n-1" is unchanged

  @gap @wip
  # Backed by: @gap
  Scenario: Manifest without private material stops with an explanation
    Given the evals directory has no private/tasks directory
    When I run "evalkit.py manifest"
    Then the exit code is 2
    And stderr contains "private/ holds the task prompts, material and graders"

  # Backed by: tests/test_evalkit.py::test_score_line_keeps_only_short_scalars
  Scenario: A score line keeps only short scalar details
    Given details with n 3, ratio 0.5, ok true, a 40 character label, a 41 character string, null, NaN, infinity, a dict, a list and a tuple
    And extra details {"extra": 1, "extra_map": {"a": 1}}
    When score_line builds the line
    Then details is exactly {"n": 3, "ratio": 0.5, "ok": true, "label": <the 40 characters>, "extra": 1}

  # Backed by: tests/test_evalkit.py::test_code_grader_details_are_reduced_end_to_end
  Scenario: A code grader's structured details are reduced to scalars on the way to scores.jsonl
    Given a grader for "n-1" returning scalar details plus a per-question map, a missed list and a findings list
    When a run is graded, and again after grader.py changes by one comment line and I run "evalkit.py grade"
    Then both score lines have details {"checked": 1, "exact": true, "ratio": 0.5, "label": "short"}
    And scores.jsonl does not contain "q7"

  # Backed by: tests/test_evalkit.py::test_judge_details_are_reduced_end_to_end
  Scenario: A judge grader's structured details are reduced to scalars on the way to scores.jsonl
    Given a score_judgment for "j-1" returning points plus a verdicts map and a found list
    When "j-1" is run and judged
    Then every score line details value is a number, a boolean or a string
    And details.points is 2 and details has judge_cost_usd
    And scores.jsonl does not contain "verdicts"

  # Backed by: tests/test_evalkit.py::test_sanitize_rewrites_existing_lines_and_is_idempotent
  Scenario: Sanitize rewrites leaky score lines in place and a second run changes nothing
    Given scores.jsonl with a line whose details hold a map, a list, a 41 character string and a null
    And a clean line, a torn line and a line whose details is a list
    When I run "evalkit.py sanitize"
    Then stdout contains "sanitize: 2 line(s) changed"
    And the leaky line keeps only its scalar details {"checked": 1, "ok": "short"}
    And the list-details line gets details {}
    And the clean line and the torn line are kept byte for byte
    And the file keeps its trailing newline, its mode 0644 and leaves no .tmp file
    And a second "evalkit.py sanitize" prints "sanitize: 0 line(s) changed" and leaves the file byte for byte unchanged

  # Backed by: tests/test_evalkit.py::test_sanitize_without_a_scores_file_is_a_no_op
  Scenario: Sanitize without a scores file is a no-op
    Given no results/scores.jsonl
    When I run "evalkit.py sanitize"
    Then stdout contains "0 line(s) changed"
    And results/scores.jsonl still does not exist

  # Backed by: tests/test_evalkit.py::test_sanitize_keeps_scores_usable
  Scenario: Sanitize keeps the scores themselves usable
    Given two score lines with passed true and passed false, the first with details {"per_q": {"q1": true}, "n": 1}
    When I run "evalkit.py sanitize"
    Then the score lines still read passed true then passed false
    And the first line has details {"n": 1}
