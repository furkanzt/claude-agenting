Feature: The advisor-pairs analysis tool applies the pre-registered rules for two advisor pairs against Opus alone and prints counts, means and rule words, never answer text

  evals/probes/advisor_pairs_analysis.py reads results/runs.jsonl, results/scores.jsonl, tasks.json, harness.json
  and, when present, private/answers/<run_id>.json under an evals folder (--evals-dir), and applies
  evals/results/PREREGISTERED-2026-11-14-advisor-pairs.md: question 1 (opus-5-5@xhigh+fable-advisor on design-02:
  better, worse, no difference shown or not decided, plus the second look of opus-5-5@high+fable-advisor) and
  question 2 (each Sonnet pair with an Opus advisor, per row: cheaper, faster, near, decided, does what the owner
  asked), against the stored valid runs of opus-5-5@xhigh, opus-5-5@high and sonnet-5-5@xhigh. design-02 is
  scored by fable-5-1@high and opus-5-5@high, two passes each; synthesis by fable-5-1@high, two passes. Every
  threshold comes from the unrounded stored mean. The tests build synthetic lines and answer files in memory or in
  a temp evals folder and never read the real results or evals/private. Exit code 0 when every slot is decided
  and scored, 3 when something is PENDING, 2 when an input cannot be read.

  # Backed by: tests/test_advisor_pairs_analysis.py::test_the_constants_name_the_cells_tasks_runs_and_judges_of_the_pre_registration
  Scenario: The plan names the four cells, the 33 runs, the two rows, the judges and the three stored cells
    Given the advisor-pairs analysis module
    When its constants are read
    Then opus-5-5@xhigh+fable-advisor has 6 design-02 runs, opus-5-5@high+fable-advisor 3, each Sonnet pair 3 on design-02 and 3 on each of synthesize-01, -02 and -03, 33 in all, design-02 has two judges and synthesis one, and the baselines are opus-5-5@xhigh, opus-5-5@high and sonnet-5-5@xhigh

  # Backed by: tests/test_advisor_pairs_analysis.py::test_baselines_and_thresholds_come_from_the_stored_runs_and_use_the_unrounded_mean
  Scenario: Baselines and thresholds come from the stored runs and use the unrounded mean
    Given stored opus-5-5@xhigh design-02 runs that handle 4, 4, 4, 4, 4 and 5 pitfalls and cost $2.00 five times and $2.60 once, at 600 s each
    When the analysis runs
    Then the stored mean handled is 25/6, the better threshold is 25/6 + 1.0 (not the rounded 4.17 + 1.0), the cheaper threshold is 75% of $2.10, faster is at most 540 s and slower is above 660 s

  # Backed by: tests/test_advisor_pairs_analysis.py::test_before_any_run_of_the_four_cells_the_tool_prints_baselines_thresholds_and_pending
  Scenario: Before any run of the four cells the tool prints the baselines, the thresholds and PENDING
    Given only the stored baseline runs
    When the tool runs
    Then it exits 3, prints "handled 4.17; 2 of 6 pass" and the Q1 better threshold, says PENDING and prints evalkit run commands that all carry --tasks

  # Backed by: tests/test_advisor_pairs_analysis.py::test_runs_with_an_old_task_hash_are_not_counted
  Scenario: A run with an old task hash is not counted
    Given the stored baselines and one more opus-5-5@xhigh design-02 run under an old task hash that handles 0 pitfalls
    When the baselines are summed
    Then the stored mean handled is still 25/6

  # Backed by: tests/test_advisor_pairs_analysis.py::test_q1_is_better_when_handled_is_at_least_one_above_the_unrounded_mean_four_pass_and_none_violates
  Scenario: Question 1 is "better, cause not separated" at exactly 1.0 above the unrounded stored mean with 4 passing and no violation
    Given six pair runs with mean handled 31/6, which is exactly the stored 25/6 + 1.0, 4 of them passing, none violating, the advisor answering in all six
    When question 1 is decided
    Then the verdict is "better, cause not separated"

  # Backed by: tests/test_advisor_pairs_analysis.py::test_q1_is_no_difference_just_under_plus_one_or_with_three_passing_or_one_violation
  Scenario: Question 1 is "no difference shown" just under +1.0, with only 3 passing, or with one violating run
    Given three sets of six pair runs: mean just under the better threshold with all passing; mean 6 with 3 passing; mean 6 with all passing and one run violating
    When question 1 is decided for each
    Then each verdict is "no difference shown"

  # Backed by: tests/test_advisor_pairs_analysis.py::test_q1_is_worse_at_exactly_one_below_the_stored_mean_and_not_just_above_it
  Scenario: Question 1 is "worse" at exactly 1.0 below the stored mean and not just above that line
    Given six pair runs whose mean handled is exactly 1.0 below the stored mean, and a set just above that line
    When question 1 is decided
    Then the first is "worse" and the second "no difference shown", also on means exact in binary (3.0 against 4.0, and 3.25 against 4.0)

  # Backed by: tests/test_advisor_pairs_analysis.py::test_q1_is_worse_with_two_violating_runs_and_not_with_one
  Scenario: Question 1 is "worse" with two violating runs whatever the mean, and not with one
    Given six pair runs with mean handled 6 and all passing, two of them violating a constraint; and a set with one violating
    When question 1 is decided
    Then the first is "worse" and the second "no difference shown"

  # Backed by: tests/test_advisor_pairs_analysis.py::test_q1_is_not_decided_when_the_advisor_answered_in_three_of_six_even_when_better_holds
  Scenario: Question 1 is "not decided" when the advisor answered in 3 of 6 runs, even when better holds
    Given six pair runs that meet every condition of better, the advisor answering in only 3
    When question 1 is decided
    Then the verdict is "not decided" naming "3 of 6", and with the advisor answering in 4 it is "better, cause not separated"

  # Backed by: tests/test_advisor_pairs_analysis.py::test_the_second_look_supports_a_better_at_the_stored_high_mean_plus_one_and_changes_no_verdict
  Scenario: The second look supports a better at the stored opus-5-5@high mean plus 1.0 and changes no verdict
    Given three opus-5-5@high+fable-advisor runs with mean handled 13/3, exactly the stored 10/3 + 1.0, and question 1 at "no difference shown"
    When the second look is read
    Then it supports a better, question 1 stays "no difference shown", and a mean just under the line does not support

  # Backed by: tests/test_advisor_pairs_analysis.py::test_a_violation_counts_only_when_one_judge_says_so_in_both_of_its_passes
  Scenario: A run violates a constraint only when one judge says so in both of its passes
    Given one run that each judge marks as violating in one pass only, and one run that opus-5-5@high marks as violating in both passes
    When the runs are scored
    Then exactly 1 run violates

  # Backed by: tests/test_advisor_pairs_analysis.py::test_a_design_run_passes_unless_one_judge_fails_it_in_both_passes_and_handled_is_the_mean_of_four
  Scenario: A design-02 run passes unless one judge fails it in both passes, and its handled value is the mean of the four passes
    Given a run each judge fails once, a run opus-5-5@high fails twice, and a run handled 6, 3, 3 and 4 in its four passes
    When the runs are scored
    Then the first passes, the second does not, and the third has handled 4.0 and 4.5 under fable-5-1@high

  # Backed by: tests/test_advisor_pairs_analysis.py::test_a_synthesis_run_passes_when_both_passes_pass_misses_by_the_lower_found_and_invents_on_either_pass
  Scenario: A synthesis run passes when both passes pass, misses by the lower found count and invents an item when either pass says so
    Given a synthesis run found 6 and 4 of 6 with the second pass failing, and a run whose second pass reports 1 fabricated item
    When the runs are scored
    Then 1 run passes, 2 items are missed and 1 run invents an item

  # Backed by: tests/test_advisor_pairs_analysis.py::test_cost_is_cheaper_at_75_percent_cheaper_by_less_than_a_quarter_up_to_100_and_not_cheaper_above
  Scenario: Cost is "cheaper" up to 75% of Opus, "cheaper by less than a quarter" up to 100% and "not cheaper" above
    Given Opus's synthesis mean cost of $2.40 and a Sonnet pair at $1.80, $1.81, $2.40 and $2.41
    When question 2 is decided
    Then the cost words are cheaper, cheaper by less than a quarter, cheaper by less than a quarter and not cheaper

  # Backed by: tests/test_advisor_pairs_analysis.py::test_time_is_faster_at_90_percent_about_the_same_up_to_110_and_slower_above
  Scenario: Time is "faster" up to 90% of Opus, "about the same" up to 110% and "slower" above
    Given Opus's synthesis mean time of 500 s and a Sonnet pair at 450, 451, 550 and 551 s
    When question 2 is decided
    Then the time words are faster, about the same, about the same and slower

  # Backed by: tests/test_advisor_pairs_analysis.py::test_near_on_synthesis_needs_every_run_to_pass_no_invention_and_at_most_one_missed
  Scenario: Near on synthesis needs every run to pass, no invented item and at most 1 item missed over the 9 runs
    Given Sonnet pair synthesis runs with 1 item missed; with 2 missed; with one run inventing an item; with one run failing a pass
    When question 2 is decided
    Then only the first is near

  # Backed by: tests/test_advisor_pairs_analysis.py::test_near_on_design_needs_handled_at_most_half_below_the_unrounded_mean_and_no_violation
  Scenario: Near on design-02 needs mean handled at least 0.5 below the unrounded Opus mean and no violation
    Given Opus's stored mean 25/6 and Sonnet pair design-02 runs with mean 11/3 (exactly 25/6 - 0.5), with mean just under it, and with one violating run
    When question 2 is decided
    Then only the first is near

  # Backed by: tests/test_advisor_pairs_analysis.py::test_a_row_is_not_decided_below_two_thirds_answered_and_its_statements_are_still_reported
  Scenario: A row is "not decided" when the advisor answered in fewer than two thirds of its runs, and its statements are still reported
    Given a Sonnet pair whose advisor answered in 5 of 9 synthesis runs, then 6 of 9, then 1 of 3 and 2 of 3 on design-02
    When question 2 is decided
    Then 5 of 9 is "not decided" with cheaper, faster and near still reported, 6 of 9 decides, 1 of 3 is "not decided" and 2 of 3 decides

  # Backed by: tests/test_advisor_pairs_analysis.py::test_the_pair_does_what_the_owner_asked_only_when_cheaper_faster_and_near_all_hold
  Scenario: The pair does what the owner asked only when cheaper, faster and near all hold on a decided row
    Given a Sonnet pair that is cheaper, faster and near, and three variants that miss one of the three
    When question 2 is decided
    Then only the first "does what the owner asked" and each variant "does not do what the owner asked"

  # Backed by: tests/test_advisor_pairs_analysis.py::test_the_sonnet_high_cell_is_judged_on_its_own_rows
  Scenario: The Sonnet high pair is judged on its own rows
    Given sonnet-5-5@high+opus-advisor runs at $3.00 each
    When question 2 is decided
    Then its design-02 cost word is "not cheaper"

  # Backed by: tests/test_advisor_pairs_analysis.py::test_a_slot_with_three_invalid_attempts_is_a_failed_run_at_the_time_limit_with_cost_left_out
  Scenario: A slot with three invalid attempts counts as a failed run at the time limit, with its cost left out
    Given a Sonnet pair design-02 slot with three timeouts and two valid runs at $1.00 and 300 s handling 4
    When the row is summed
    Then it has 1 failed slot, 0 passing, mean handled 8/3, mean time (300 + 300 + 1800)/3 s, mean cost $1.00 over 2 known costs, and the advisor did not answer in it

  # Backed by: tests/test_advisor_pairs_analysis.py::test_a_failed_synthesis_slot_misses_every_reference_item_of_its_task
  Scenario: A failed synthesis slot misses every reference item of its task
    Given a Sonnet pair synthesis slot on synthesize-02 with three timeouts, the task's reference count being 6
    When the row is summed
    Then 6 items are missed and 8 runs pass

  # Backed by: tests/test_advisor_pairs_analysis.py::test_a_slot_with_two_invalid_attempts_is_not_run_yet_and_makes_the_result_pending_exit_3
  Scenario: A slot with two invalid attempts and some API errors is not run yet, makes the result PENDING and exits 3
    Given every slot run and scored except one synthesize-03 slot with two timeouts and three rate-limit errors
    When the tool runs
    Then that row is PENDING, the other rows are decided, the exit code is 3 and the slot and its evalkit run command with --tasks are printed

  # Backed by: tests/test_advisor_pairs_analysis.py::test_a_complete_world_exits_0_with_one_verdict_line_per_rule
  Scenario: With every slot run and scored the tool exits 0 and prints one verdict line per rule
    Given every slot of the test run and scored
    When the tool runs
    Then it exits 0, prints no PENDING and prints six verdict lines: question 1, its second look and four question 2 rows

  # Backed by: tests/test_advisor_pairs_analysis.py::test_a_missing_judge_pass_makes_the_result_pending_names_it_and_prints_the_second_judge_command
  Scenario: A missing judge pass makes the result PENDING, is named, and the second-judge command is printed
    Given every slot scored except pass 1 of opus-5-5@high on opus-5-5@xhigh+fable-advisor design-02 repeat 4
    When the tool runs
    Then question 1 is PENDING, the exit code is 3, the missing pass is named and an evalkit judge command with --tasks design-02 and --judge-cell opus-5-5@high is printed

  # Backed by: tests/test_advisor_pairs_analysis.py::test_scores_of_one_judge_under_two_rubric_hashes_make_the_result_pending
  Scenario: Scores of one judge on one run under two rubric hashes make the result PENDING
    Given every slot scored and one more fable-5-1@high score line on a Sonnet pair design-02 run under a second rubric hash
    When the tool runs
    Then that row is PENDING, the exit code is 3 and the output says "more than one rubric hash"

  # Backed by: tests/test_advisor_pairs_analysis.py::test_a_failed_slot_takes_the_tests_own_time_limit_and_cap_whatever_harness_json_says_now
  Scenario: A failed slot takes the test's own limits, whatever harness.json says when the analysis runs
    Given a slot with three timeouts, and a harness.json that has gone back to 1,200 s and $6 a run
    When the analysis runs
    Then the slot's time is 1,800 s and each attempt of unknown cost is bounded by $10
    And the report says that harness.json now has other limits and that the test's own are used
    And with the same limits in harness.json the note is not printed

  # Backed by: tests/test_advisor_pairs_analysis.py::test_a_failed_slot_lists_the_time_and_reason_of_each_counted_attempt
  Scenario: A failed slot is listed with the time and reason of each attempt that counted
    Given a slot with a timeout, an API error, an unparseable reply and another timeout
    When the analysis runs
    Then the slot is listed with the three counted attempts, each with its reason and time, and without the API error
    And the report asks for each window to be checked against the connection log
    And a test with no failed slot prints no such list

  # Backed by: tests/test_advisor_pairs_analysis.py::test_a_pair_run_judged_under_another_rubric_than_the_stored_baselines_makes_the_result_pending
  Scenario: A run of the four cells judged under another rubric than the stored baselines makes the result PENDING
    Given a complete test in which one judge scored one run under a rubric hash that no stored baseline run of that task carries
    When the analysis runs
    Then that run and that judge are named as "another rubric than the stored baselines", the status is PENDING and the exit code is 3
    And with every run under the baselines' rubric the status is DECIDED

  # Backed by: tests/test_advisor_pairs_analysis.py::test_an_unreadable_input_exits_2
  Scenario: An unreadable results file exits 2
    Given a runs.jsonl whose line is not JSON
    When the tool runs
    Then it exits 2 and says "not JSON"

  # Backed by: tests/test_advisor_pairs_analysis.py::test_the_advisor_answered_when_its_model_shows_in_the_run_usage_whatever_the_text_says
  Scenario: The advisor answered when its model shows in the run's usage, whatever the text says
    Given a run line with advisor_called true and an answer text saying "ADVISOR: failed", and one with no answer file
    When the advisor status is read
    Then both are "answered"

  # Backed by: tests/test_advisor_pairs_analysis.py::test_each_status_line_before_the_answer_block_gives_its_status
  Scenario: Each status line before the answer block gives its status, and a line inside the block does not count
    Given runs with no advisor usage whose text before ===ANSWER=== holds "ADVISOR: failed" or "ADVISOR: not called", and one with "ADVISOR: not called" before the block and "ADVISOR: failed" inside it
    When the advisor status is read
    Then they are "failed", "not called" and "not called"

  # Backed by: tests/test_advisor_pairs_analysis.py::test_answered_in_the_status_line_without_advisor_usage_is_failed_and_counted_as_claimed
  Scenario: "ADVISOR: answered" without advisor usage is a failed call and is counted as claimed
    Given a run with no advisor usage whose status line says "ADVISOR: answered", also in bold
    When the advisor status is read and the row is summed
    Then its status is "failed" and the claimed-answered-without-usage count is 1

  # Backed by: tests/test_advisor_pairs_analysis.py::test_free_text_naming_the_advisor_with_a_failure_word_gives_failed_and_otherwise_not_called
  Scenario: With no status line, a line naming the advisor with a failure word gives failed, anything else not called
    Given texts "The advisor call timed out", "advisor: error 529", "Danışman çağrısı zaman aşımına uğradı" and "The Advisor was unavailable", and texts that name the advisor without a failure word, a failure without the advisor, or nothing
    When the advisor status is read
    Then the first four are "failed" and the others "not called"

  # Backed by: tests/test_advisor_pairs_analysis.py::test_with_no_answer_file_the_status_is_unknown_even_with_no_answers_folder
  Scenario: With no answer file the status is unknown, also when the answers folder is missing
    Given a run with no advisor usage and no answer file, and a temp evals folder with no private/answers folder
    When the advisor status is read and the tool runs
    Then the status is "unknown" and the report counts "answered 1, failed 0, not called 0, unknown 2"

  # Backed by: tests/test_advisor_pairs_analysis.py::test_a_status_line_inside_the_answer_block_is_counted
  Scenario: A status line that slipped inside the answer block is counted
    Given an answer file whose block starts with "ADVISOR: answered", and one whose block has no status line
    When the advisor status is read and the row is summed
    Then the first is counted as a status line inside the block and the second is not

  # Backed by: tests/test_advisor_pairs_analysis.py::test_the_report_never_contains_text_from_an_answer_file
  Scenario: The report never contains text from an answer file
    Given answer files whose result and block carry a marker string
    When the tool prints its text report and its JSON
    Then neither contains the marker, and the JSON still counts 9 failed advisor calls

  # Backed by: tests/test_advisor_pairs_analysis.py::test_the_advisor_share_of_cost_the_status_counts_and_the_spend_are_reported
  Scenario: The advisor share of cost and the spend of the test's attempts are reported
    Given three Sonnet pair runs at $1.00 with $0.30 advisor cost in the two answered ones, one timeout of unknown cost and one invalid attempt at $0.50
    When the analysis runs
    Then the mean advisor cost is $0.30 and its share 30%, the spend is $3.50 known over 5 attempts with 1 unknown, and $13.50 with $10 for the unknown one
