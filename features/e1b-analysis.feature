Feature: The E1b analysis tool applies the pre-registered Opus-versus-Sonnet and Haiku-xhigh rules to the stored runs and prints counts, never question text

  evals/probes/e1b_analysis.py re-grades every stored E1b answer with the task's own grader (through
  e1_analysis.py), keeps the per-question outcomes, and applies Rule A (move balanced to opus/xhigh, with the
  leave-one-item-out check), Rule B (admit haiku/xhigh to fast), Rule D (defective items) and Rule E (short of
  6 runs per task keeps both rows) of evals/results/PREREGISTERED-E1b-2026-10-10.md. Its output is public, so
  it carries counts, item ids and kinds only. The tests cut the data down to 2 repeats and one task; the rules
  are the same.

  # Backed by: tests/test_e1b_analysis.py::test_the_decision_cells_are_the_ones_the_rules_name_and_rule_d_reads_the_same_two
  Scenario: The decision cells are opus, sonnet and haiku at xhigh, the reference is haiku at high
    Given the E1b analysis module
    When its cell constants are read
    Then the decision cells are opus-5-5@xhigh, sonnet-5-5@xhigh and haiku-5-5@xhigh, the reference is haiku-5-5@high, and Rule D reads sonnet as the baseline and opus as the reference

  # Backed by: tests/test_e1b_analysis.py::test_counts_per_cell_and_hallucinations_by_task_and_item_with_kinds
  Scenario: Hallucinations are counted per cell, per task and per item with the item kind
    Given a cell with three runs over two tasks, with invented answers to an intent item and a partial item, and a wrong answer and a miss on the answerable item
    When the cell is aggregated and the hallucinated items are listed
    Then H is 3, W is 1, M is 1, the task counts are 2 and 1, and each item row carries its kind and its hallucinated runs over its runs

  # Backed by: tests/test_e1b_analysis.py::test_invalid_runs_and_repeats_above_equal_n_are_not_counted
  Scenario: Invalid runs and repeats beyond the compared repeats are not counted
    Given a cell with one invalid run, one run at repeat 3 and one valid run at repeat 2 while 2 repeats are compared
    When the cell is aggregated
    Then it has exactly 1 run

  # Backed by: tests/test_e1b_analysis.py::test_rule_a_moves_balanced_when_every_condition_holds
  Scenario: Rule A moves balanced to opus/xhigh when all five conditions hold
    Given sonnet hallucinates 4 times on 2 items, opus never does, neither answers an answerable item wrongly and opus answers all of them correctly
    When the decision is computed
    Then conditions (i) to (v) are all true and the verdict is "MOVE balanced to opus/xhigh"

  # Backed by: tests/test_e1b_analysis.py::test_rule_a_i_needs_sonnet_at_one_percent_or_more_of_the_unanswerable_item_runs
  Scenario: Sonnet must hallucinate on at least 1 percent of the unanswerable item-runs for a measurable baseline
    Given 100 unanswerable item-runs per cell and sonnet hallucinating once, then not at all, then once in 102 item-runs
    When Rule A (i) is evaluated for each
    Then it holds for 1 of 100, fails for none and fails for 1 of 102, and a clean sonnet keeps balanced on sonnet/xhigh

  # Backed by: tests/test_e1b_analysis.py::test_rule_a_ii_opus_may_have_at_most_a_fifth_of_sonnets_hallucinations
  Scenario: Opus may hallucinate at most a fifth as often as sonnet
    Given opus hallucinates once and sonnet hallucinates 5 times, or 4 times
    When Rule A (ii) is evaluated
    Then it holds at 5 and fails at 4, and the verdict at 4 keeps balanced on sonnet/xhigh

  # Backed by: tests/test_e1b_analysis.py::test_rule_a_iii_opus_may_not_answer_answerable_items_wrongly_more_often_than_sonnet
  Scenario: Opus may not give more confident wrong answers than sonnet
    Given opus and sonnet each answer one answerable item wrongly, or only opus does
    When Rule A (iii) is evaluated
    Then it holds when they are equal and fails when opus has more, and the second verdict keeps balanced on sonnet/xhigh

  # Backed by: tests/test_e1b_analysis.py::test_rule_a_iv_opus_needs_95_percent_of_the_answerable_item_runs_correct
  Scenario: Opus must answer at least 95 percent of the answerable item-runs correctly
    Given opus abstains on the answerable item in half of the answerable item-runs
    When Rule A (iv) is evaluated
    Then it fails and the verdict keeps balanced on sonnet/xhigh

  # Backed by: tests/test_e1b_analysis.py::test_rule_a_iv_is_exactly_at_95_percent
  Scenario: Exactly 95 percent of the answerable item-runs is enough
    Given opus answers 38 of 40 answerable item-runs correctly and every other condition holds
    When Rule A (iv) is evaluated
    Then it holds and the verdict is "MOVE balanced to opus/xhigh"

  # Backed by: tests/test_e1b_analysis.py::test_rule_a_one_failing_condition_alone_keeps_balanced_on_sonnet
  Scenario: Any single failed Rule A condition keeps balanced on sonnet/xhigh
    Given every Rule A condition holds except one, in turn a wrong answer by opus (iii) and 3 misses by opus (iv)
    When the decision is computed
    Then the verdict is "KEEP balanced on sonnet/xhigh" each time, with only the named condition false

  # Backed by: tests/test_e1b_analysis.py::test_rule_a_v_one_item_that_carries_the_result_keeps_balanced_on_sonnet
  Scenario: A result that one item carries does not move balanced
    Given sonnet hallucinates 5 times on 3 items (one of them twice as often as the rest) and opus once, so condition (ii) holds
    When each of sonnet's items is removed in turn from every cell
    Then removing the most frequent one leaves sonnet at 3 and opus at 1, condition (v) is false and the verdict keeps balanced on sonnet/xhigh

  # Backed by: tests/test_e1b_analysis.py::test_rule_a_v_a_sonnet_problem_that_is_one_item_leaves_nothing_to_measure_and_fails
  Scenario: A sonnet problem that is a single item leaves nothing to measure after its removal and fails the robustness check
    Given sonnet hallucinates twice, both times on one item, and opus never does
    When that item is removed from every cell
    Then sonnet has no hallucination left, the row is marked as having nothing left of the sonnet signal, condition (v) is false by the conservative reading and the verdict keeps balanced on sonnet/xhigh

  # Backed by: tests/test_e1b_analysis.py::test_rule_b_admits_haiku_xhigh_when_every_condition_holds
  Scenario: Rule B admits haiku/xhigh to fast when all four conditions hold
    Given haiku xhigh and sonnet each hallucinate once in 120 unanswerable item-runs and neither answers wrongly or abstains on answerable items
    When the decision is computed
    Then conditions (i) to (iv) are true and the verdict is "ADMIT haiku/xhigh to fast", while one hallucination in 60 item-runs is above 1 percent and keeps fast on sonnet/xhigh

  # Backed by: tests/test_e1b_analysis.py::test_rule_b_i_haiku_xhigh_may_not_hallucinate_more_than_sonnet
  Scenario: Haiku xhigh may not hallucinate more than sonnet even below 1 percent
    Given haiku xhigh hallucinates once in 120 unanswerable item-runs and sonnet never does
    When Rule B is evaluated
    Then (ii) holds, (i) fails and the verdict keeps fast on sonnet/xhigh

  # Backed by: tests/test_e1b_analysis.py::test_rule_b_ii_haiku_xhigh_may_hallucinate_at_most_one_percent_of_item_runs
  Scenario: Haiku xhigh may hallucinate on at most 1 percent of the unanswerable item-runs
    Given 100 unanswerable item-runs per cell, haiku xhigh and sonnet each hallucinating once, or each twice
    When Rule B (ii) is evaluated
    Then exactly 1 percent holds, 2 percent fails although haiku xhigh only ties sonnet, and the verdict keeps fast on sonnet/xhigh

  # Backed by: tests/test_e1b_analysis.py::test_rule_b_iii_and_iv_haiku_xhigh_needs_no_more_wrong_answers_and_95_percent_correct
  Scenario: Haiku xhigh may not answer wrongly more often than sonnet and must answer 95 percent of answerable items correctly
    Given haiku xhigh answers the answerable item wrongly in one run, or abstains on it in one run
    When Rule B is evaluated
    Then the first fails (iii), the second fails (iv), and each keeps fast on sonnet/xhigh

  # Backed by: tests/test_e1b_analysis.py::test_rule_b_one_failing_condition_alone_keeps_fast_on_sonnet
  Scenario: Any single failed Rule B condition keeps fast on sonnet/xhigh, and exactly 95 percent still qualifies
    Given every Rule B condition holds except one, in turn a wrong answer (iii) and 3 misses in 40 answerable item-runs (iv), then 2 misses in 40
    When the decision is computed
    Then the first two keep fast on sonnet/xhigh and the third admits haiku/xhigh to fast

  # Backed by: tests/test_e1b_analysis.py::test_the_two_rules_are_independent
  Scenario: Rule A and Rule B are decided independently
    Given opus is clean, sonnet hallucinates 4 times on 2 items and haiku xhigh once in 120 unanswerable item-runs
    When the decision is computed
    Then balanced moves to opus/xhigh and haiku/xhigh is admitted to fast

  # Backed by: tests/test_e1b_analysis.py::test_a_decision_cell_short_of_the_repeats_gives_the_conservative_verdict_for_both_rows
  Scenario: A decision cell short of the repeats keeps both rows as they are
    Given each of opus, sonnet and haiku xhigh in turn has one repeat fewer than the others
    When the decision is computed
    Then the result is not complete, the verdict starts with INCOMPLETE, and both balanced and fast stay on sonnet/xhigh

  # Backed by: tests/test_e1b_analysis.py::test_a_shortfall_of_the_reference_cell_alone_does_not_block_the_decision
  Scenario: A shortfall of the reference cell alone does not block the decision
    Given haiku at high has one repeat and the three decision cells are complete
    When the decision is computed
    Then the result is complete

  # Backed by: tests/test_e1b_analysis.py::test_a_task_without_runs_or_truth_is_incomplete
  Scenario: A task with no truth file or no runs makes the decision incomplete
    Given the rules expect two tasks and only one has data
    When the decision is computed
    Then the result is not complete and names the missing task

  # Backed by: tests/test_e1b_analysis.py::test_rule_d_flags_items_failed_by_sonnet_and_opus_and_exclusion_removes_them
  Scenario: Rule D flags an item that sonnet and opus both fail, and an exclusion removes it from every cell
    Given an item that both sonnet and opus hallucinate on in every run
    When the defective candidates are listed and the item is then excluded
    Then it is listed once, sonnet's hallucination count falls to 0, the hallucinated items of sonnet are empty and the list is empty

  # Backed by: tests/test_e1b_analysis.py::test_the_reference_cell_is_reported_and_never_decides
  Scenario: The reference cell is reported and never decides
    Given haiku at high hallucinates on the same items as sonnet and opus is clean
    When the report is rendered
    Then it has a row for haiku-5-5@high and the Rule A verdict is still decided only by opus and sonnet

  # Backed by: tests/test_e1b_analysis.py::test_the_rendered_report_carries_no_question_text_and_lists_item_ids_with_kinds
  Scenario: The rendered report carries counts, item ids and kinds but no question text
    Given truth files whose questions hold a sentinel text and runs that are incomplete
    When the report is rendered with an extra table
    Then the sentinel does not appear, the hallucinated item is listed by id and kind, the extra table is titled as reported only and the INCOMPLETE verdict is printed

  # Backed by: tests/test_e1b_analysis.py::test_the_command_line_prints_the_report_and_fails_cleanly_without_tasks
  Scenario: The command line prints the report, and exits 2 when no E1b task is found
    Given a private directory with the E1b task and runs, and another path that does not exist
    When the tool is run on each
    Then the first prints the Rule A lines and exits 0 and the second exits 2
