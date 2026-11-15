Feature: The architecture analysis tool applies the pre-registered rules of 2026-11-15 to the stored design-decision runs of Opus xhigh and Sonnet xhigh, and prints cell ids, task ids and counts, never answer text

  evals/probes/architecture_analysis.py reads results/runs.jsonl and results/scores.jsonl and applies
  evals/results/PREREGISTERED-2026-11-15-architecture.md: opus-5-5@xhigh against sonnet-5-5@xhigh on design-01
  (6 runs a cell), design-02 (12) and design-03 (12). A run is a solid fail under a judge model when both of
  that judge's passes fail it; a slot with no valid answer is a failed slot; a cell's fails are the two
  together. Every count is made once per judge model (fable-5-1@high and opus-5-5@high) and a rule fires only
  when it fires under both. The tests build synthetic lines in memory and never read the real results or
  evals/private. Exit code 0 when all 60 slots are decided; 2 when a run or a judge pass is missing, or the
  data cannot be analysed.

  # Backed by: tests/test_architecture_analysis.py::test_the_constants_name_the_cells_the_tasks_and_30_slots_a_cell
  Scenario: The constants name the two cells, the three tasks with their targets, the two judges and the margins
    Given the architecture analysis module
    When its constants are read
    Then the cells are opus-5-5@xhigh and sonnet-5-5@xhigh, the targets are 6 runs on design-01 and 12 on design-02 and on design-03, 30 a cell, the judges are fable-5-1@high and opus-5-5@high, the fast margin is 2 and the clearly-worse margin is 5

  # ---- counting ----

  # Backed by: tests/test_architecture_analysis.py::test_fails_are_counted_per_cell_task_and_judge
  Scenario: Fails are counted per cell, task and judge
    Given both cells with all 30 slots judged, where Opus has 4 failing runs on design-02 and 5 on design-03 and Sonnet 6 and 3
    When the record is analysed
    Then each judge counts those fails per task, and 9 in total for each cell

  # Backed by: tests/test_architecture_analysis.py::test_a_split_is_not_a_fail
  Scenario: A run that a judge passes once and fails once is not a fail
    Given a Sonnet run whose two passes under each judge are one pass and one fail
    When the record is analysed
    Then Sonnet has 0 fails under both judges

  # Backed by: tests/test_architecture_analysis.py::test_a_run_failed_by_one_judge_only_counts_under_that_judge_only
  Scenario: A run that one judge fails twice counts under that judge only
    Given a Sonnet run that fable-5-1@high fails twice and opus-5-5@high passes twice
    When the record is analysed
    Then Sonnet has 1 fail under fable-5-1@high and 0 under opus-5-5@high

  # Backed by: tests/test_architecture_analysis.py::test_a_slot_with_no_valid_answer_is_a_fail_under_both_judges
  Scenario: A slot with no valid answer is a fail under both judges
    Given a Sonnet slot whose three attempts all timed out
    When the record is analysed
    Then Sonnet has 1 fail under both judges, 1 failed slot, and the status is DECIDED

  # Backed by: tests/test_architecture_analysis.py::test_a_run_that_called_an_advisor_is_a_failed_slot_and_is_listed
  Scenario: A run that called an advisor is a failed slot and is listed
    Given a valid Opus run on design-03 whose run line says advisor_called, judged as passing
    When the record is analysed
    Then Opus has 1 fail under both judges and the run is listed among the advisor runs

  # Backed by: tests/test_architecture_analysis.py::test_a_slot_whose_first_run_reported_a_second_model_is_a_failed_slot_even_when_the_retry_is_valid
  Scenario: A slot whose first run reported a second model is a failed slot, even when the retry is valid
    Given a Sonnet slot on design-03 whose first attempt is invalid with the reason "model_mismatch: observed ..." and whose second attempt is valid and passes every judge pass
    When the record is analysed
    Then Sonnet has 1 fail under both judges, 1 failed slot, the slot is listed with "a run reported a second model; counted as a failed slot", and the status is DECIDED
    And a slot whose first attempt timed out and whose retry passes is an ordinary pass and is not listed

  # Backed by: tests/test_architecture_analysis.py::test_a_repeat_beyond_the_tasks_target_is_not_counted
  Scenario: A repeat beyond the task's target is not counted
    Given a failing Sonnet run at repeat 7 of design-01 and one at repeat 13 of design-02
    When the record is analysed
    Then Sonnet has 0 fails under both judges

  # Backed by: tests/test_architecture_analysis.py::test_other_cells_and_other_tasks_are_ignored
  Scenario: Other cells and other tasks are ignored
    Given a failing run of opus-5-5@high on design-02 and a failing Sonnet run on design-04
    When the record is analysed
    Then Sonnet has 0 fails and the status is DECIDED

  # ---- the rules ----

  # Backed by: tests/test_architecture_analysis.py::test_equal_fails_give_sonnet_both_modes
  Scenario: Equal fails give Sonnet the row in fast and in balanced
    Given Opus and Sonnet each with 6 fails on design-02 and 4 on design-03
    When the rules are applied
    Then fast is sonnet-5-5@xhigh and balanced is sonnet-5-5@xhigh

  # Backed by: tests/test_architecture_analysis.py::test_two_more_fails_in_total_keep_fast_and_lose_balanced
  Scenario: Two more fails in total keep fast and lose balanced
    Given Opus with 6 and 4 fails and Sonnet with 7 and 5
    When the rules are applied
    Then fast is sonnet-5-5@xhigh and balanced is opus-5-5@xhigh

  # Backed by: tests/test_architecture_analysis.py::test_one_more_fail_in_total_loses_balanced_even_when_behind_on_one_task_only
  Scenario: One more fail in total loses balanced even when Sonnet is behind on one task only
    Given Opus with 6 and 4 fails and Sonnet with 6 and 5
    When the rules are applied
    Then fast is sonnet-5-5@xhigh, balanced is opus-5-5@xhigh, and the reason says "11 fails against 10"

  # Backed by: tests/test_architecture_analysis.py::test_three_more_fails_in_total_lose_fast
  Scenario: Three more fails in total lose fast
    Given Opus with 6 and 4 fails and Sonnet with 8 and 5
    When the rules are applied
    Then fast is opus-5-5@xhigh and balanced is opus-5-5@xhigh

  # Backed by: tests/test_architecture_analysis.py::test_three_more_fails_on_one_task_lose_fast_even_when_the_total_is_within_two
  Scenario: Three more fails on one task lose fast even when the total is within two
    Given Opus with 6 and 4 fails and Sonnet with 3 and 7
    When the rules are applied
    Then fast is opus-5-5@xhigh and the reason names design-03

  # Backed by: tests/test_architecture_analysis.py::test_no_more_fails_in_total_but_behind_on_two_tasks_loses_balanced
  Scenario: No more fails in total but behind on two tasks loses balanced
    Given Opus with 0, 8 and 2 fails on the three tasks and Sonnet with 1, 5 and 3
    When the rules are applied
    Then fast is sonnet-5-5@xhigh, balanced is opus-5-5@xhigh, and the reason says it is behind on 2 tasks

  # Backed by: tests/test_architecture_analysis.py::test_behind_on_one_task_only_and_no_more_fails_in_total_takes_balanced
  Scenario: Behind on one task only, with no more fails in total, takes balanced
    Given Opus with 8 and 2 fails and Sonnet with 6 and 3
    When the rules are applied
    Then balanced is sonnet-5-5@xhigh

  # Backed by: tests/test_architecture_analysis.py::test_a_rule_fires_only_when_it_fires_under_both_judges
  Scenario: A rule fires only when it fires under both judges
    Given equal fails under fable-5-1@high, and three more Sonnet fails under opus-5-5@high only
    When the rules are applied
    Then fast is opus-5-5@xhigh and balanced is opus-5-5@xhigh

  # Backed by: tests/test_architecture_analysis.py::test_more_than_five_extra_fails_is_reported_as_clearly_worse
  Scenario: More than five extra fails are reported as clearly worse
    Given Opus with 2 fails and Sonnet with 8
    When the rules are applied
    Then Sonnet is reported as clearly worse
    And with 7 Sonnet fails against 2 it is not

  # Backed by: tests/test_architecture_analysis.py::test_critical_and_cheapest_are_never_moved
  Scenario: The critical cell and the cheapest cell are never moved
    Given any decided record
    When the rules are applied
    Then critical is opus-5-5@xhigh and cheapest is sonnet-5-5@xhigh

  # ---- pending, incomplete, errors ----

  # Backed by: tests/test_architecture_analysis.py::test_a_slot_that_was_never_run_keeps_every_rule_pending
  Scenario: A slot that was never run keeps every rule pending
    Given Sonnet with 11 of its 12 runs on design-03
    When the record is analysed
    Then the status is PENDING, there is no verdict, and 1 run is missing for Sonnet on design-03

  # Backed by: tests/test_architecture_analysis.py::test_a_missing_judge_pass_is_incomplete
  Scenario: A missing judge pass makes the record incomplete
    Given an Opus run that lacks the second pass of opus-5-5@high
    When the record is analysed
    Then the status is INCOMPLETE, there is no verdict, and 1 judge pass is missing

  # Backed by: tests/test_architecture_analysis.py::test_a_slot_lost_to_api_errors_is_pending_not_failed
  Scenario: A slot lost to API errors is pending, not failed
    Given a Sonnet slot whose only attempt ended on a rate limit with no output
    When the record is analysed
    Then the status is PENDING and Sonnet has 0 fails

  # Backed by: tests/test_architecture_analysis.py::test_two_rubric_hashes_for_one_task_and_judge_are_an_error
  Scenario: Two rubric hashes for one task and judge are an error
    Given scores of one judge for design-02 under two different rubric hashes
    When the record is analysed
    Then an analysis error is raised

  # ---- the command line ----

  # Backed by: tests/test_architecture_analysis.py::test_a_decided_record_prints_the_table_and_the_verdicts_and_exits_0
  Scenario: A decided record prints the table and the verdicts and exits 0
    Given a decided record where Sonnet has two more fails than Opus and Opus costs $2.00 a run
    When "python3 evals/probes/architecture_analysis.py --runs <file> --scores <file>" runs
    Then the output has "fast: sonnet-5-5@xhigh", "balanced: opus-5-5@xhigh", "design-03 alone", "$2.00" and "Status: DECIDED"
    And the exit code is 0

  # Backed by: tests/test_architecture_analysis.py::test_a_pending_record_names_what_is_missing_and_exits_2
  Scenario: A pending record names what is missing and exits 2
    Given a record where two Sonnet runs on design-03 were never made
    When the tool runs
    Then the output has "Status: PENDING" and "sonnet-5-5@xhigh design-03: 2 run(s) missing" and no "fast:" line
    And the exit code is 2

  # Backed by: tests/test_architecture_analysis.py::test_json_output_carries_counts_and_cell_ids_only
  Scenario: The JSON output carries counts and cell ids only
    Given a decided record
    When the tool runs with --json
    Then the output parses as JSON with status "DECIDED" and the fast verdict's cell, and holds no answer text

  # Backed by: tests/test_architecture_analysis.py::test_an_unreadable_file_exits_2
  Scenario: An unreadable results file exits 2
    Given paths to files that do not exist
    When the tool runs
    Then the exit code is 2
