Feature: The think-first analysis tool applies the pre-registered Fable 5.2 rules to the stored design-decision runs and prints cell ids, counts and rule names, never answer text

  evals/probes/think_first_analysis.py reads results/runs.jsonl and results/scores.jsonl, counts per cell the
  solid fails under each of two judge models (fable-5-1@high and opus-5-5@high, two passes each), and applies
  sections 2 and 3 of evals/results/PREREGISTERED-2026-11-13-think-first.md: which stage-2 runs are warranted,
  Rule Q (quality), Rule B (balanced), the choice of Fable effort, fast, "otherwise" and "both fail". A rule
  fires only when it fires under both judges. The count a rule reads is the solid fails plus the failed slots.
  A run counts as a solid fail under a judge when both of that judge's passes fail it; a split does not. The
  tests build synthetic lines in memory and never read the real results or evals/private. Exit code 0 when
  quality, balanced and fast are all decided; 2 when a judge pass is missing, a disposition is pending, or the
  data cannot be analysed.

  # Backed by: tests/test_think_first_analysis.py::test_the_constants_name_the_tasks_judges_and_cells_of_the_pre_registration
  Scenario: The constants name the two tasks, the two judges with passes 0 and 1, the six cells and 12 slots per cell
    Given the think-first analysis module
    When its constants are read
    Then the tasks are design-01 and design-02, the judges are fable-5-1@high and opus-5-5@high with pass indexes 0 and 1, the Fable cells are fable-5-2@low, @medium and @high, stage 1 is repeats 1 to 3, and a cell has 12 slots

  # Backed by: tests/test_think_first_analysis.py::test_a_split_is_not_a_solid_fail
  Scenario: A run that one judge passes once and fails once is not a solid fail
    Given a run of opus-5-5@xhigh whose two passes under each judge are one pass and one fail
    When the cell is counted
    Then it has 0 solid fails and 0 fails under both judges

  # Backed by: tests/test_think_first_analysis.py::test_two_failing_passes_are_a_solid_fail_under_that_judge_only
  Scenario: A run whose two passes under a judge both fail is a solid fail under that judge only
    Given a run that fable-5-1@high fails twice and opus-5-5@high passes twice
    When the cell is counted
    Then it has 1 solid fail under fable-5-1@high and 0 under opus-5-5@high

  # Backed by: tests/test_think_first_analysis.py::test_a_run_with_no_answer_block_is_a_solid_fail_under_every_judge_without_judge_passes
  Scenario: A run with a no_block score line is a solid fail under every judge and owes no judge passes
    Given a valid run with one score line whose details.no_block is true
    When the cell is counted
    Then it has 1 solid fail under both judges and no judge pass is reported missing

  # Backed by: tests/test_think_first_analysis.py::test_the_latest_line_for_a_pass_index_wins
  Scenario: When several score lines exist for one pass index the latest one counts
    Given a run failed twice by a judge and then re-graded with two passes under the same rubric
    When the cell is counted
    Then the run is not a solid fail under that judge

  # Backed by: tests/test_think_first_analysis.py::test_a_fable_attempt_with_stop_reason_refusal_fails_the_slot_even_after_a_valid_retry
  Scenario: A Fable attempt whose run line has stop_reason "refusal" fails the slot even after a valid retry
    Given a fable-5-2@low slot with one invalid attempt carrying stop_reason "refusal" and then a valid run
    When the cell is counted
    Then it has 1 failed slot and 1 fail under both judges

  # Backed by: tests/test_think_first_analysis.py::test_a_fable_attempt_with_safety_stops_fails_the_slot_valid_or_not
  Scenario: A Fable attempt with safety_stops above 0, or an invalid_reason starting with "refusal", fails the slot, valid or not
    Given three Fable slots: an invalid attempt with safety_stops 1 then a valid run, a valid run with safety_stops 2, and an invalid attempt with invalid_reason "refusal: classifier" then a valid run
    When the cells are counted
    Then each Fable cell has 1 failed slot

  # Backed by: tests/test_think_first_analysis.py::test_a_fable_attempt_that_is_only_an_error_such_as_a_rate_limit_does_not_fail_the_slot
  Scenario: A Fable attempt that is only an error, such as a rate limit, does not fail the slot when a later attempt is valid
    Given Fable slots whose earlier attempt had invalid_reason "is_error" with stop_reason "end_turn" and api_error_status 429, "exit_code=1" with safety_stops 0, and bare "is_error", each followed by a valid run
    When the cells are counted
    Then each Fable cell has 0 failed slots and 0 fails under both judges

  # Backed by: tests/test_think_first_analysis.py::test_the_same_refusal_marks_on_an_opus_cell_do_not_fail_its_slot
  Scenario: The same refusal marks on an Opus cell do not fail its slot
    Given opus-5-5@xhigh and opus-5-5@high slots with stop_reason "refusal" or safety_stops 1 on an attempt
    When the cells are counted
    Then each has 0 failed slots and 0 fails

  # Backed by: tests/test_think_first_analysis.py::test_a_run_line_without_stop_reason_and_safety_stops_is_read_as_not_refused
  Scenario: A run line without stop_reason and safety_stops is read as not refused
    Given Fable slots whose valid run lines lack both fields, or carry stop_reason null and safety_stops 0
    When the cells are counted
    Then they have 0 failed slots and 0 refused attempts

  # Backed by: tests/test_think_first_analysis.py::test_a_different_model_answering_fails_a_fable_slot_but_a_timeout_does_not
  Scenario: A different answering model fails a Fable slot, a timeout does not, and neither fails an Opus slot
    Given Fable slots whose earlier attempt had invalid_reason "model_mismatch: observed [...]" and "timeout", and an Opus slot with "model_mismatch: observed [...]", each followed by a valid run
    When the cells are counted
    Then only the Fable slot with the model mismatch is failed

  # Backed by: tests/test_think_first_analysis.py::test_a_slot_whose_attempts_are_all_invalid_is_failed_on_any_cell
  Scenario: A slot whose attempts are all invalid is a failed slot on any cell and is decided without judge passes
    Given opus-5-5@xhigh and sonnet-5-5@xhigh slots with three invalid attempts and no valid run
    When the cells are counted
    Then each has 1 failed slot, opus-5-5@xhigh has 1 fail under fable-5-1@high and 1 slot decided

  # Backed by: tests/test_think_first_analysis.py::test_a_slot_with_no_attempt_is_not_decided
  Scenario: A slot with no attempt at all is not decided
    Given no run lines
    When opus-5-5@xhigh is counted
    Then it has 0 slots decided and 0 failed slots

  # Backed by: tests/test_think_first_analysis.py::test_a_missing_judge_pass_gives_incomplete_names_it_and_exits_2_without_a_verdict
  Scenario: A counted run lacking one of its four judge passes gives INCOMPLETE, names the pass and exits 2 with no verdict
    Given a full set of runs and scores except one pass of opus-5-5@high for one fable-5-2@low run
    When the tool runs, as text and with --json
    Then the exit code is 2, the text lists that cell, task, repeat, judge and pass index, contains no "Dispositions" section, and the JSON status is "INCOMPLETE"

  # Backed by: tests/test_think_first_analysis.py::test_a_failed_slot_needs_no_judge_passes
  Scenario: A failed slot needs no judge passes
    Given a Fable slot with all attempts invalid and a Fable slot whose first attempt had stop_reason "refusal" and then a valid run that was never judged
    When the analysis runs
    Then no judge pass is reported missing

  # Backed by: tests/test_think_first_analysis.py::test_rule_q_fires_at_four_of_twelve_and_not_at_three
  Scenario: Rule Q fires with 4 solid fails of 12 for opus-5-5@xhigh and not with 3
    Given clean Fable cells and opus-5-5@xhigh with 4 failing slots of 12 under both judges, then with 3
    When the dispositions are decided
    Then with 4 quality is the cheapest Fable cell by "rule Q", and with 3 quality is opus-5-5@xhigh by "otherwise" with "Fable 5.2 measured, not adopted"

  # Backed by: tests/test_think_first_analysis.py::test_rule_q_needs_both_judges_four_under_one_and_three_under_the_other_does_not_move
  Scenario: Rule Q needs opus-5-5@xhigh at 4 or more under both judges
    Given opus-5-5@xhigh with 4 solid fails under fable-5-1@high and 3 under opus-5-5@high
    When the dispositions are decided
    Then quality is opus-5-5@xhigh by "otherwise"

  # Backed by: tests/test_think_first_analysis.py::test_the_cheapest_qualifying_fable_effort_is_chosen_by_measured_cost_not_by_effort_name
  Scenario: Among qualifying Fable cells the one with the lowest measured mean cost per run is chosen
    Given three clean Fable cells with mean costs 3.0, 2.0 and 5.0 for low, medium and high, then 1.0, 2.0 and 0.5
    When quality is decided with opus-5-5@xhigh at 4 fails
    Then it is fable-5-2@medium, then fable-5-2@high

  # Backed by: tests/test_think_first_analysis.py::test_a_fable_cell_with_one_solid_fail_under_one_judge_cannot_qualify
  Scenario: A Fable cell with one solid fail under either judge cannot qualify, even when it is the cheapest
    Given the cheapest Fable cell with one solid fail under one judge only, then all three Fable cells with one
    When quality is decided with opus-5-5@xhigh at 4 fails
    Then the first case takes the next cheapest clean Fable cell and the second keeps opus-5-5@xhigh

  # Backed by: tests/test_think_first_analysis.py::test_a_split_does_not_disqualify_a_fable_cell
  Scenario: A split on a Fable run does not disqualify the cell
    Given the cheapest Fable cell with one split run and no solid fail
    When quality is decided with opus-5-5@xhigh at 4 fails
    Then that cell is chosen

  # Backed by: tests/test_think_first_analysis.py::test_a_failed_slot_counts_against_a_fable_cell
  Scenario: A failed slot counts as a fail for a Fable cell
    Given the cheapest Fable cell with 11 clean slots and one slot whose attempts all failed
    When quality is decided with opus-5-5@xhigh at 4 fails
    Then the next cheapest clean Fable cell is chosen

  # Backed by: tests/test_think_first_analysis.py::test_rule_b_needs_six_fails_with_one_on_each_task
  Scenario: Rule B needs 6 solid fails for opus-5-5@xhigh with at least one on each task
    Given opus-5-5@xhigh with 6 solid fails on both tasks under both judges, then with 5
    When the dispositions are decided
    Then with 6 balanced is the cheapest Fable cell by "rule B", and with 5 balanced is opus-5-5@xhigh while quality still moves by "rule Q"

  # Backed by: tests/test_think_first_analysis.py::test_six_fails_on_one_task_only_do_not_move_balanced
  Scenario: Six solid fails all on one task do not move balanced
    Given opus-5-5@xhigh with 6 solid fails, all on design-01
    When the dispositions are decided
    Then balanced is opus-5-5@xhigh by "otherwise" and quality is a Fable cell by "rule Q"

  # Backed by: tests/test_think_first_analysis.py::test_rule_b_needs_both_judges
  Scenario: Rule B needs 6 or more solid fails under both judges
    Given opus-5-5@xhigh with 6 solid fails under fable-5-1@high and 5 under opus-5-5@high
    When the dispositions are decided
    Then balanced is opus-5-5@xhigh

  # Backed by: tests/test_think_first_analysis.py::test_both_fail_when_opus_has_four_and_every_fable_cell_has_a_fail_under_both_judges
  Scenario: Both fail when opus-5-5@xhigh has 4 fails and every Fable cell has a fail under both judges
    Given opus-5-5@xhigh with 4 solid fails and each Fable cell with one solid fail under both judges
    When the dispositions are decided
    Then quality and balanced are opus-5-5@xhigh by "both fail" with the text "no cell passed these tasks"

  # Backed by: tests/test_think_first_analysis.py::test_a_fable_cell_with_zero_fails_under_one_judge_only_is_not_both_fail
  Scenario: A Fable cell with no fail under one of the judges keeps the verdict at "otherwise", not "both fail"
    Given opus-5-5@xhigh with 4 solid fails and one Fable cell failing under only one judge
    When the dispositions are decided
    Then quality is opus-5-5@xhigh by "otherwise"

  # Backed by: tests/test_think_first_analysis.py::test_fast_is_the_cheaper_candidate_with_zero_fails
  Scenario: Fast is the cheaper of opus-5-5@high and sonnet-5-5@xhigh when both have 0 fails
    Given both candidates clean in 12 runs, first with sonnet cheaper, then with opus-5-5@high cheaper
    When fast is decided
    Then it is sonnet-5-5@xhigh, then opus-5-5@high

  # Backed by: tests/test_think_first_analysis.py::test_fast_skips_a_candidate_with_a_fail_even_when_it_is_cheaper
  Scenario: Fast skips a candidate that has a fail even when it is cheaper
    Given sonnet-5-5@xhigh cheaper but with one solid fail and opus-5-5@high clean
    When fast is decided
    Then it is opus-5-5@high by "rule fast"

  # Backed by: tests/test_think_first_analysis.py::test_fast_falls_back_to_opus_xhigh_when_neither_candidate_has_zero_fails_and_is_never_fable
  Scenario: Fast falls back to opus-5-5@xhigh when neither candidate has 0 fails and is never a Fable cell
    Given one fail on each candidate under at least one judge and very cheap Fable cells
    When fast is decided
    Then it is opus-5-5@xhigh

  # Backed by: tests/test_think_first_analysis.py::test_rules_that_need_twelve_slots_are_pending_until_all_twelve_are_decided
  Scenario: A rule that needs 12 slots says PENDING until all 12 are decided, and the exit code is 2
    Given stage 1 only for the clean cells (6 slots each) and opus-5-5@xhigh complete at 4 fails
    When the dispositions are decided and the tool runs
    Then quality, balanced and fast are "pending", the text says "PENDING" and the exit code is 2

  # Backed by: tests/test_think_first_analysis.py::test_opus_xhigh_counts_stay_pending_until_its_own_twelve_slots_are_decided
  Scenario: Counts for opus-5-5@xhigh are pending until its own 12 slots are decided
    Given opus-5-5@xhigh with 6 of 12 slots decided, 4 of them failing, and every Fable cell with a fail
    When the dispositions are decided
    Then quality and balanced are "pending" with the reason "opus-5-5@xhigh has 6/12"

  # Backed by: tests/test_think_first_analysis.py::test_a_complete_world_exits_0_and_prints_one_line_per_disposition
  Scenario: With all 12 slots decided everywhere the tool exits 0 and prints one line per disposition
    Given all six cells with 12 decided slots and opus-5-5@xhigh at 4 fails
    When the tool runs
    Then the exit code is 0 and the text has the lines "quality: fable-5-2@medium", "balanced: opus-5-5@xhigh" and "fast: ", with "rule Q" named

  # Backed by: tests/test_think_first_analysis.py::test_stage_2_lines_are_printed_only_for_the_cells_the_rules_warrant
  Scenario: Stage-2 run lines are printed only for the cells the rules warrant
    Given stage 1 with opus-5-5@xhigh at 4 fails, a stage-1 fail on fable-5-2@medium and on sonnet-5-5@xhigh, and mean costs 2.0, 9.0 and 4.0 for the Fable cells, 1.0 for the candidates
    When the stage-2 plan is made
    Then it prints the run line for fable-5-2@low,fable-5-2@high with "--repeats 6 --max-usd 54", the run line for opus-5-5@high with "--max-usd 9", and notes that the other two are not warranted

  # Backed by: tests/test_think_first_analysis.py::test_no_fable_stage_2_when_opus_xhigh_has_fewer_than_four_fails_and_none_when_nothing_is_warranted
  Scenario: No Fable stage 2 when opus-5-5@xhigh has fewer than 4 fails, and the text says so when nothing at all is warranted
    Given opus-5-5@xhigh at 3 fails, then also a stage-1 fail on both candidates
    When the stage-2 plan is made and the tool runs
    Then the first plan lists only opus-5-5@high and sonnet-5-5@xhigh, and the second prints "none are warranted" and no run line

  # Backed by: tests/test_think_first_analysis.py::test_a_cell_with_a_stage_1_fail_under_either_judge_gets_no_stage_2
  Scenario: A cell with a stage-1 fail under either judge gets no stage 2
    Given fable-5-2@low with one solid fail under fable-5-1@high only in stage 1 and opus-5-5@xhigh at 4 fails
    When the stage-2 plan is made
    Then fable-5-2@low is not in it

  # Backed by: tests/test_think_first_analysis.py::test_stage_2_that_has_already_been_run_prints_no_line
  Scenario: A stage 2 that was already run prints no run line
    Given all 12 slots of every cell and opus-5-5@xhigh at 4 fails
    When the stage-2 plan is made
    Then it has no run line and a note saying "already run"

  # Backed by: tests/test_think_first_analysis.py::test_mixed_rubric_hashes_for_one_task_and_judge_stop_with_an_error_naming_the_task
  Scenario: More than one rubric hash for one task and judge stops the analysis with an error naming the task
    Given scores for design-02 under fable-5-1@high with two different rubric hashes
    When the tool runs
    Then the exit code is 2, stderr names design-02 and not design-01, and stdout is empty

  # Backed by: tests/test_think_first_analysis.py::test_two_judges_with_different_rubric_hashes_are_not_mixed_gradings
  Scenario: Different rubric hashes under two different judges are not a mixed grading
    Given the same task graded by fable-5-1@high under one hash and by opus-5-5@high under another
    When the analysis runs
    Then there is no error

  # Backed by: tests/test_think_first_analysis.py::test_attempts_outside_the_counted_cells_tasks_and_repeats_are_ignored
  Scenario: Attempts on other cells, other tasks or repeats above 6 are not counted
    Given refused attempts on a different Fable model, on a task that is not design-01 or design-02, and at repeat 7
    When the analysis runs
    Then the Fable refused, wrong-model and other-invalid counts are all 0 and fable-5-2@low has 0 slots decided

  # Backed by: tests/test_think_first_analysis.py::test_a_missing_results_file_is_an_error_exit_2
  Scenario: A missing results file is an error with exit code 2
    Given a runs path that does not exist
    When the tool runs
    Then the exit code is 2 and stderr says "does not exist"

  # Backed by: tests/test_think_first_analysis.py::test_json_holds_no_strings_beyond_cell_ids_rule_names_and_status_words
  Scenario: The --json output holds only cell ids, rule names and status words as strings
    Given an empty set of results, a stage-1 set, a both-fail set and a complete set
    When the tool runs with --json
    Then every string value is a cell id, one of "rule Q", "rule B", "rule fast", "otherwise", "both fail", or a status word, and the complete set has status "VERDICT", quality fable-5-2@medium and balanced by "rule B"
