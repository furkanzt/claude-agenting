Feature: The coding analysis tool applies the pre-registered rules for who writes the tests and who writes the code, from the public record only

  evals/probes/code_bench_analysis.py reads the public record of code_bench.py (results/code-runs.jsonl, or
  --results) and applies the section "Rules" of evals/results/PREREGISTERED-2026-11-14-coding.md: the clause "In
  every question", question 1 (bulk coding, arm B), question 2 (tests first), question 3 (who writes the tests,
  haiku-5-5@high arms B and C), question 4 (plan and tests, step T and cross) and "Missing and invalid runs". A
  run is read from its final incarnation (from its last model line with try 1 and attempt 1); check lines with
  result check_infra are ignored. --cut names what the spend rule cut; --stop-usd is the spend stop (224). The
  tests build synthetic record lines in memory or in a temp file and never read the real record or
  evals/private. Exit code 0 when everything planned has ended and cross is complete, 3 when something is
  PENDING, 2 when the record or an option cannot be read.

  # Backed by: tests/test_code_bench_analysis.py::test_the_planned_runs_are_the_rules_tables
  Scenario: The planned runs are the rules' tables
    Given the analysis module
    When an empty record is analysed
    Then 48 step-T runs and 180 step-C runs are planned (66 in arm A, 90 in B, 24 in C), the cells, arms, runs, thresholds 15 and 30, the $224 stop and the $6 charge are the rules' own

  # Backed by: tests/test_code_bench_analysis.py::test_an_empty_record_runs_and_says_what_is_pending
  Scenario: An empty or missing record runs and says what is pending
    Given an empty record, then a record file that does not exist
    When the tool runs
    Then it exits 3, prints "step T: 48 run(s) not ended", "step C: 180 run(s) not ended", the six tasks with no given suite, a spend of $0.00, and every question PENDING

  # Backed by: tests/test_code_bench_analysis.py::test_an_unreadable_record_exits_2_without_a_path
  Scenario: An unreadable record exits 2 without a path
    Given a record whose second line is not JSON, then one whose line is a JSON list
    When the tool runs
    Then it exits 2 with "code_bench_analysis: error: line 2 of the record is not JSON" and no path

  # Backed by: tests/test_code_bench_analysis.py::test_a_complete_record_is_decided_and_exits_0
  Scenario: A complete record is decided and exits 0
    Given every planned run ended, every suite scored, a given suite per task and every cross line
    When the tool runs, as text and as --json
    Then it exits 0 with "Status: DECIDED" and no PENDING

  # Backed by: tests/test_code_bench_analysis.py::test_a_cell_with_no_run_in_the_arm_is_never_named_and_a_cut_cell_is_not_pending
  Scenario: A cell with no run in the arm a rule reads is never named, and a cut cell is not pending
    Given arm-B runs of three cells and sonnet-5-5@medium cut by --cut
    When question 1 is applied
    Then it is decided, sonnet-5-5@medium is named by no verdict and "no run in arm B; never named", its 18 runs are listed as cut; without --cut the question is PENDING

  # Backed by: tests/test_code_bench_analysis.py::test_a_cell_with_no_correct_run_is_never_named_and_the_report_says_no_cell
  Scenario: A cell with no correct run is never named, and the report says when no cell can be named
    Given four cells none of whose arm-B runs is correct
    When question 1 is applied
    Then fast and balanced both read "no cell from this experiment"

  # Backed by: tests/test_code_bench_analysis.py::test_a_question_whose_set_of_tasks_is_empty_is_not_measured
  Scenario: A question whose set of tasks is empty is "not measured"
    Given no task with a given suite
    When the rules are applied
    Then questions 1, 2 and 3 are "not measured" and the 114 runs of arms B and C are left out

  # Backed by: tests/test_code_bench_analysis.py::test_runs_never_started_because_of_the_spend_stop_are_left_out_listed_and_not_counted
  Scenario: Runs never started because of the spend stop are left out of every share and listed
    Given a spend of $226 and 12 of haiku-5-5@medium's 24 arm-B runs never started
    When question 1 is applied
    Then the cell has 12 runs, all correct (share 100%), the 12 others are listed as stopped, nothing is pending, and with a $500 stop the question is PENDING

  # Backed by: tests/test_code_bench_analysis.py::test_q1_share_of_correct_runs_and_cost_per_correct_task
  Scenario: Question 1: the share of correct runs and the cost per correct task
    Given haiku-5-5@medium with 12 runs correct at try 1 ($0.25) and 12 not finished after three tries ($0.75)
    When question 1 is applied
    Then its share is 50% and its cost per correct task is $12 / 12 = $1.00

  # Backed by: tests/test_code_bench_analysis.py::test_q1_a_cell_is_usable_when_at_least_half_of_its_arm_b_runs_are_correct
  Scenario: Question 1: a cell is usable when at least half of its arm-B runs are correct
    Given one cell with 12 of 24 correct and one with 11 of 24
    When question 1 is applied
    Then the first is "usable for bulk coding" and the second "not usable for bulk coding"

  # Backed by: tests/test_code_bench_analysis.py::test_q1_fast_is_the_cheapest_usable_cell_whose_escaped_runs_are_at_most_one_in_ten_finished
  Scenario: Question 1: fast is the cheapest usable cell whose escaped runs are at most 1 in 10 finished
    Given the cheapest cell escaping 3 of 24 finished runs and the next escaping exactly 2 of 20
    When question 1 is applied
    Then fast is haiku-5-5@high, the second

  # Backed by: tests/test_code_bench_analysis.py::test_q1_fast_on_a_tie_of_cost_per_correct_takes_the_higher_share
  Scenario: Question 1: on a tie of cost per correct task fast takes the higher share of correct runs
    Given haiku-5-5@medium and haiku-5-5@high at $0.50 per correct task, with 18 and 24 of 24 correct
    When question 1 is applied
    Then fast is haiku-5-5@high

  # Backed by: tests/test_code_bench_analysis.py::test_q1_balanced_is_the_cheapest_cell_whose_arm_b_runs_are_all_correct
  Scenario: Question 1: balanced is the cheapest cell whose arm-B runs are all correct
    Given two clean cells, sonnet-5-5@low at $0.50 and sonnet-5-5@medium at $1.00 per correct task
    When question 1 is applied
    Then balanced is sonnet-5-5@low

  # Backed by: tests/test_code_bench_analysis.py::test_q1_balanced_with_no_clean_cell_takes_the_highest_share_then_the_lower_cost_and_says_so
  Scenario: Question 1: with no clean cell balanced takes the highest share, the lower cost on a tie, and says no cell was clean
    Given no clean cell and two cells at 50% correct, haiku-5-5@high the cheaper per correct task
    When question 1 is applied
    Then balanced is haiku-5-5@high and the notes say "no cell was clean"

  # Backed by: tests/test_code_bench_analysis.py::test_q1_when_no_cell_qualifies_for_fast_fast_takes_the_cell_of_balanced_and_says_so
  Scenario: Question 1: when no cell qualifies for fast, fast takes the cell of balanced and says so
    Given four cells each below half correct
    When question 1 is applied
    Then fast and balanced are haiku-5-5@medium and the notes say fast takes the cell of balanced

  # Backed by: tests/test_code_bench_analysis.py::test_q1_escaped_runs_are_reported_per_task
  Scenario: Question 1: escaped runs are reported per task
    Given escaped runs on code-03 (1), code-04 (2), code-05 (1) and code-06 (1)
    When the tool prints
    Then it prints "escaped per task: code-01 0; code-02 0; code-03 1; code-04 2; code-05 1; code-06 1"

  # Backed by: tests/test_code_bench_analysis.py::test_q2_difference_is_first_try_share_in_b_minus_share_in_a_over_tasks_with_both_arms
  Scenario: Question 2: the difference is the share correct at the first try in arm B minus the share correct in arm A, over the tasks with both arms
    Given haiku-5-5@medium on five tasks with a given suite (code-06 has none): 10 of 20 correct in arm A and 13 of 20 correct at try 1 in arm B; then arm-B runs correct only at try 2
    When question 2 is applied
    Then the tasks are code-01 to code-05 and the difference is +15 points; with runs correct only at try 2 it is -50

  # Backed by: tests/test_code_bench_analysis.py::test_q2_tests_first_helps_a_haiku_cell_at_15_points_when_arm_b_is_ahead_on_more_tasks
  Scenario: Question 2: tests first helps a Haiku cell at 15 points when arm B is ahead on more tasks
    Given a difference of exactly 15 points with arm B ahead on 3 tasks and arm A on none, then the same difference with each ahead on 2
    When question 2 is applied
    Then the first is "tests first helps" and the second "no effect shown"

  # Backed by: tests/test_code_bench_analysis.py::test_q2_the_sonnet_cell_needs_30_points
  Scenario: Question 2: the Sonnet cell needs 30 points
    Given sonnet-5-5@low cut to 2 runs a task and a difference of 20, then 30 points with arm B ahead
    When question 2 is applied
    Then 20 points is "no effect shown" and 30 is "tests first helps"

  # Backed by: tests/test_code_bench_analysis.py::test_q2_tests_first_hurts_at_minus_15_when_arm_a_is_ahead_on_more_tasks
  Scenario: Question 2: tests first hurts at -15 points when arm A is ahead on more tasks
    Given haiku-5-5@high with 13 of 20 correct in arm A and 10 of 20 at try 1 in arm B, arm A ahead on 3 tasks
    When question 2 is applied
    Then it is "tests first hurts"

  # Backed by: tests/test_code_bench_analysis.py::test_q2_otherwise_no_effect_shown
  Scenario: Question 2: otherwise no effect shown
    Given a difference of +10 points
    When question 2 is applied
    Then it is "no effect shown"

  # Backed by: tests/test_code_bench_analysis.py::test_q2_what_tries_2_and_3_add_in_arm_b_is_reported
  Scenario: Question 2: what tries 2 and 3 add in arm B is reported
    Given arm-B runs of which half are correct at try 2 and none at try 1
    When the tool prints
    Then it prints "tries 2 and 3 in arm B add +50.0 points"

  # Backed by: tests/test_code_bench_analysis.py::test_q3_arm_c_is_acceptable_when_every_condition_holds_at_its_bound
  Scenario: Question 3: arm C is acceptable when every condition holds, each at its bound
    Given arm C with 20 of 20 finished, 2 escaped (1 in 10), 90% correct against arm B's 100% (10 points below) and behind on two tasks
    When question 3 is applied
    Then it is "acceptable"

  # Backed by: tests/test_code_bench_analysis.py::test_q3_fewer_than_half_of_arm_c_runs_finished_is_not_acceptable
  Scenario: Question 3: fewer than half of arm C's runs finished is not acceptable
    Given 8 of 20 arm-C runs finished, then 10 of 20
    When question 3 is applied
    Then the first is "not acceptable: the tests must come from a stronger model" and the second "acceptable"

  # Backed by: tests/test_code_bench_analysis.py::test_q3_a_share_correct_more_than_10_points_below_arm_b_is_not_acceptable
  Scenario: Question 3: a share correct more than 10 points below arm B's is not acceptable
    Given arm B 90% correct and arm C 80%, then 75%
    When question 3 is applied
    Then the correctness condition holds at 80% and fails at 75%

  # Backed by: tests/test_code_bench_analysis.py::test_q3_escaped_runs_above_one_in_ten_finished_are_not_acceptable
  Scenario: Question 3: escaped runs above 1 in 10 of the finished runs are not acceptable
    Given arm C with 3 of 20 finished runs escaped and the same share correct as arm B
    When question 3 is applied
    Then it is not acceptable for the escaped runs alone

  # Backed by: tests/test_code_bench_analysis.py::test_q3_behind_arm_b_on_more_than_two_tasks_is_not_acceptable
  Scenario: Question 3: behind arm B on more than two tasks is not acceptable
    Given arm C behind arm B on 3 tasks with every other condition met, then on 2
    When question 3 is applied
    Then the first fails on "behind" alone and the second is acceptable

  # Backed by: tests/test_code_bench_analysis.py::test_q3_with_fewer_than_four_tasks_with_both_arms_is_too_few_tasks_to_tell
  Scenario: Question 3: with fewer than four tasks with both arms the answer is "too few tasks to tell"
    Given three tasks with arms B and C, then four
    When question 3 is applied
    Then three is "too few tasks to tell" and four is decided

  # Backed by: tests/test_code_bench_analysis.py::test_q3_is_not_measured_when_arm_c_was_cut
  Scenario: Question 3 is not measured when arm C was cut
    Given --cut C
    When question 3 is applied
    Then it is "not measured" and says arm C was cut

  # Backed by: tests/test_code_bench_analysis.py::test_q4_per_cell_fit_suites_mean_cost_and_time_and_cost_per_fit_suite
  Scenario: Question 4: per cell the fit suites of its 12, the mean cost and time per suite and the cost per fit suite
    Given sonnet-5-5@high with 10 fit suites of 12, each run $1.00 and 60 s
    When question 4 is applied
    Then it has 10 of 12 fit, a mean cost of $1.00, a mean time of 60 s and a cost per fit suite of $12 / 10

  # Backed by: tests/test_code_bench_analysis.py::test_q4_a_suite_catches_a_wrong_copy_it_fails_on_and_wrongly_rejects_a_right_one
  Scenario: Question 4: a suite catches a wrong copy it fails on and wrongly rejects a right one, pooled over pairs
    Given 12 fit suites, 9 failing on the 11 wrong copies of their task and 3 failing on the 4 right ones
    When question 4 is applied
    Then catches is 99 of 132 (75%) and wrongly rejects 12 of 48 (25%)

  # Backed by: tests/test_code_bench_analysis.py::test_q4_a_load_error_on_a_copy_counts_as_failing_and_unchanged_or_arm_b_copies_are_left_out
  Scenario: Question 4: a load error counts as failing; copies with an unchanged source and arm-B copies are left out
    Given one fit suite whose failures are load errors, a cross line on an arm-B copy and one copy marked unchanged
    When question 4 is applied
    Then the suite catches 10 of 10 wrong copies and the right copies are 4

  # Backed by: tests/test_code_bench_analysis.py::test_q4_a_rate_over_fewer_than_10_pairs_is_too_few_to_tell_and_its_bound_is_not_applied
  Scenario: Question 4: a rate over fewer than 10 pairs is "too few to tell" and its bound is not applied
    Given 2 fit suites that reject all 8 right copies, then 3 that reject all 12
    When question 4 is applied
    Then 8 pairs are "too few to tell" and the bound holds; 12 pairs are measured and the bound fails

  # Backed by: tests/test_code_bench_analysis.py::test_q4_fast_is_the_cheapest_cell_with_10_fit_suites_that_catches_80_and_rejects_at_most_10
  Scenario: Question 4: fast is the cheapest cell with at least 10 fit suites that catches at least 80% and wrongly rejects at most 10%
    Given sonnet-5-5@high with 10 fit suites catching exactly 80% and rejecting exactly 10%, a cheaper cell catching 75%, one with 9 fit suites and one rejecting 25%
    When question 4 is applied
    Then fast is sonnet-5-5@high

  # Backed by: tests/test_code_bench_analysis.py::test_q4_fast_when_no_cell_qualifies_takes_the_most_fit_suites_within_10_percent_cheaper_on_a_tie
  Scenario: Question 4: when no cell qualifies, fast takes the most fit suites among those within 10%, the cheaper on a tie
    Given no cell with 10 fit suites, two with 9 within 10% (opus-5-5@medium cheaper) and one rejecting everything
    When question 4 is applied
    Then fast is opus-5-5@medium and the notes say so

  # Backed by: tests/test_code_bench_analysis.py::test_q4_fast_when_no_cell_stays_within_10_percent_takes_the_lowest_rate_of_wrong_rejections
  Scenario: Question 4: when no cell stays within 10%, fast takes the cell with the lowest rate of wrong rejections
    Given four cells rejecting 50%, 25%, 33% and 100% of the right copies
    When question 4 is applied
    Then fast is sonnet-5-5@xhigh (25%) and the notes say so

  # Backed by: tests/test_code_bench_analysis.py::test_q4_balanced_is_the_cheapest_cell_with_12_fit_suites_and_both_bounds
  Scenario: Question 4: balanced is the cheapest cell with 12 fit suites and both bounds
    Given the cheapest cell with 11 fit suites, opus-5-5@medium with 12 at $0.90 a run, and a cell with 12 catching 75%
    When question 4 is applied
    Then balanced is opus-5-5@medium and fast is the cheaper sonnet-5-5@high

  # Backed by: tests/test_code_bench_analysis.py::test_q4_balanced_fallbacks_most_fit_within_both_bounds_then_most_fit_cheaper_on_a_tie
  Scenario: Question 4: balanced falls back to the most fit suites within both bounds, then to the most fit suites, the cheaper on a tie
    Given no cell with 12 fit suites and both bounds, two with 11 within both (opus-5-5@high cheaper); then no cell within the catch bound, two with 11 (opus-5-5@medium cheaper)
    When question 4 is applied
    Then balanced is opus-5-5@high, then opus-5-5@medium, and the notes name each fallback

  # Backed by: tests/test_code_bench_analysis.py::test_q4_a_cell_with_no_fit_suite_is_never_named
  Scenario: Question 4: a cell with no fit suite is never named
    Given no fit suite in any cell
    When question 4 is applied
    Then fast, balanced and the tip read "no cell from this experiment"

  # Backed by: tests/test_code_bench_analysis.py::test_q4_the_tip_names_the_fast_cell_and_says_a_long_chat_rereads_the_conversation
  Scenario: Question 4: the tip for the main chat of a $20 plan names the fast cell and says a long chat re-reads the conversation
    Given fast is sonnet-5-5@xhigh
    When the tool prints
    Then the tip names sonnet-5-5@xhigh and says that a long chat re-reads the whole conversation every turn, so the cheaper input price weighs more there

  # Backed by: tests/test_code_bench_analysis.py::test_q4_waits_for_every_copy_line_and_every_pair_of_cross
  Scenario: Question 4 waits for every copy line and every pair of cross
    Given a complete record without the copy lines of sonnet-5-5@low on code-02, then without one cross line
    When question 4 is applied
    Then it is PENDING with 3 and then 1 cross item missing

  # Backed by: tests/test_code_bench_analysis.py::test_an_api_error_is_an_attempt_not_a_try
  Scenario: An API or infrastructure error is an attempt, not a try
    Given an arm-B run whose try 1 has two infra attempts and a third that passes
    When the run is read
    Then it ended after 1 try, correct at the first try, with 3 processes

  # Backed by: tests/test_code_bench_analysis.py::test_after_three_failed_attempts_a_step_c_run_ends_not_correct_not_finished_and_is_listed
  Scenario: After three failed attempts a step-C run ends, not correct and not finished, and is listed
    Given an arm-B run whose try 2 has three infra attempts after a try 1 whose hidden tests passed
    When the run is read
    Then it ended on infra, not correct, not finished, correct at the first try, and is listed

  # Backed by: tests/test_code_bench_analysis.py::test_after_three_failed_attempts_a_step_t_suite_is_not_fit_and_is_listed
  Scenario: After three failed attempts a step-T suite is not fit and is listed
    Given a step-T run with three infra attempts at try 1
    When the record is analysed
    Then the suite is scored not fit, not pending, and listed

  # Backed by: tests/test_code_bench_analysis.py::test_a_process_whose_cost_is_unknown_is_charged_6_dollars
  Scenario: A process whose cost is unknown is charged the $6 cap
    Given one arm-B process of haiku-5-5@medium with unknown cost
    When the record is analysed
    Then $6 is counted for it in the spend and in the cell's cost

  # Backed by: tests/test_code_bench_analysis.py::test_a_run_cut_by_the_spend_stop_and_made_again_is_read_from_its_final_incarnation
  Scenario: A run cut by the spend stop and made again is read from its final incarnation
    Given an arm-B run with two failed tries at $1 each, then the same run again from try 1, correct at $1
    When the run is read
    Then it has 1 try, correct at the first try, a cost of $1.00, one cut incarnation of $2.00, and a spend of $3.00

  # Backed by: tests/test_code_bench_analysis.py::test_a_run_interrupted_between_its_model_line_and_its_hidden_line_is_read_from_its_final_incarnation
  Scenario: A run interrupted between its model line and its hidden line is read from its final incarnation
    Given an arm-A model line with no hidden line, then the run again with its hidden line
    When the run is read
    Then it ended after 1 try, correct, at the second incarnation's cost; the cut incarnation alone has not ended

  # Backed by: tests/test_code_bench_analysis.py::test_check_infra_lines_are_ignored
  Scenario: Check lines whose result is check_infra are ignored
    Given a hidden line and a fit_start line with result check_infra
    When the record is read
    Then the run has not ended and the suite has no fit line

  # Backed by: tests/test_code_bench_analysis.py::test_a_repeated_fit_scoring_or_cross_pair_is_read_from_its_last_lines
  Scenario: A repeated fit scoring or cross pair is read from its last lines
    Given a fit scoring cut after a failed reference run and scored again, and a cross pair written twice
    When the record is read
    Then the suite is fit and the pair's result is the last one

  # Backed by: tests/test_code_bench_analysis.py::test_cut_lists_what_the_spend_rule_cut_and_refuses_anything_else
  Scenario: --cut lists what the spend rule cut and refuses anything else
    Given --cut opus-5-5@high,sonnet-5-5@medium, C, haiku-5-5@medium:3 and sonnet-5-5@low:2
    When an empty record is analysed
    Then 6, 18, 24, 12 and 12 runs are cut and none is pending; an unknown cell, a run count that is not below the plan or an unknown arm exits 2

  # Backed by: tests/test_code_bench_analysis.py::test_json_gives_the_same_verdicts_as_the_text
  Scenario: --json gives the same verdicts as the text
    Given the question-1 record whose fast cell is haiku-5-5@high and balanced cell sonnet-5-5@low
    When the tool runs with and without --json
    Then both name the same cells and the status is PENDING with exit 3
