Feature: The E1 analysis tool applies the pre-registered don't-guess rules to the stored runs and prints counts, never question text

  evals/probes/e1_analysis.py re-grades every stored E1 answer with the task's own grader, keeps the
  per-question outcomes, and applies Rule A (balanced), Rule B (fast) and Rule D (defective items) of
  evals/results/PREREGISTERED-E1-2026-10-10.md. Its output is public, so it carries counts, item ids and
  kinds only.

  # Backed by: tests/test_e1_analysis.py::test_counts_hallucinations_wrong_and_missed_per_cell
  Scenario: Hallucinations, wrong answers, misses and correct answers are counted per cell with the item kinds
    Given a cell with two runs, one that invents answers to a sibling item and a training item and answers an answerable item wrongly, and one that abstains on the answerable item
    When the cell is aggregated
    Then H is 2, W is 1, M is 1, A is 0, there are 6 unanswerable and 2 answerable item-runs and the hallucinations are one per kind sibling and training

  # Backed by: tests/test_e1_analysis.py::test_rule_a_adopts_when_the_candidate_is_no_worse_than_the_baseline
  Scenario: Rule A adopts haiku/high for balanced when it is no worse than the baseline
    Given the candidate and the baseline both abstain on every unanswerable item and answer every answerable item correctly
    When the decision is computed
    Then the verdict is "ADOPT haiku/high for balanced"

  # Backed by: tests/test_e1_analysis.py::test_rule_a_keeps_sonnet_on_one_extra_hallucination
  Scenario: One hallucination more than the baseline keeps balanced on sonnet/xhigh
    Given the candidate hallucinates once per run and the baseline never does
    When the decision is computed
    Then Rule A (i) is false and the verdict is "KEEP balanced on sonnet/xhigh"

  # Backed by: tests/test_e1_analysis.py::test_rule_a_adopts_on_a_tie_of_hallucinations_and_keeps_on_more_wrong_answers
  Scenario: A tie of hallucinations does not block the adoption
    Given the candidate and the baseline hallucinate on the same item in every run
    When the decision is computed
    Then Rule A (i) holds because the comparison is less than or equal, and the verdict is "ADOPT haiku/high for balanced"

  # Backed by: tests/test_e1_analysis.py::test_rule_a_adopts_on_a_tie_of_hallucinations_and_keeps_on_more_wrong_answers
  Scenario: More confident wrong answers than the baseline keep balanced on sonnet/xhigh
    Given the candidate answers an answerable item wrongly in every run and the baseline never does
    When the decision is computed
    Then Rule A (ii) is false and the verdict is "KEEP balanced on sonnet/xhigh"

  # Backed by: tests/test_e1_analysis.py::test_rule_a_needs_95_percent_of_answerable_items_correct
  Scenario: A candidate that abstains on too many answerable items does not qualify
    Given the candidate abstains on the answerable item in every run
    When the decision is computed
    Then Rule A (iii) is false because fewer than 95 percent of the answerable item-runs are correct, and the verdict keeps balanced on sonnet/xhigh

  # Backed by: tests/test_e1_analysis.py::test_rule_b_reverts_fast_above_one_percent_and_keeps_it_below
  Scenario: Rule B keeps fast on haiku/high at or below 1 percent hallucinations and reverts it above
    Given a candidate that hallucinates once in 120 unanswerable item-runs, and another that hallucinates twice in 120
    When Rule B is applied to each
    Then the first keeps haiku/high for fast and the second reverts fast to sonnet/xhigh

  # Backed by: tests/test_e1_analysis.py::test_incomplete_data_gives_the_conservative_verdict
  Scenario: Incomplete data gives the conservative verdict
    Given the candidate and the baseline each have fewer runs than 6 per task
    When the decision is computed
    Then the result is not complete and the verdict starts with INCOMPLETE and says to keep balanced on Sonnet and fast as it is

  # Backed by: tests/test_e1_analysis.py::test_rule_d_flags_items_failed_by_baseline_and_reference_and_exclusion_removes_them
  Scenario: Rule D flags an item that the baseline and the reference both fail, and an exclusion removes it from every cell
    Given an item that both the baseline and the reference hallucinate on in every run
    When the defective candidates are listed and the item is then excluded
    Then it is listed once, the baseline's hallucination count falls from 2 to 0 with the exclusion, and the list is empty

  # Backed by: tests/test_e1_analysis.py::test_a_missing_answer_block_is_a_failure_and_not_a_hallucination
  Scenario: A run with no answer block is a failure on every question and not a hallucination
    Given a stored answer whose block is missing
    When the cell is aggregated
    Then H is 0, every question counts as another failure and the run is not passed

  # Backed by: tests/test_e1_analysis.py::test_the_rendered_report_carries_no_question_text
  Scenario: The rendered report carries counts, item ids and kinds but no question text
    Given a truth file whose questions hold a sentinel text
    When the report is rendered
    Then the sentinel does not appear and the hallucinations are listed as item-runs over distinct items per kind
