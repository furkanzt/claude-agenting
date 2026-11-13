Feature: Workers work alone and the advisor belongs to the decider: every agent file except the design agent carries the work-alone sentence

  # Backed by: tests/test_advisor_rule.py::test_every_worker_agent_carries_the_work_alone_sentence_once
  Scenario: Every worker agent file carries the work-alone sentence exactly once
    Given the agent files in agents/ except the exception set {"system-architect"}
    When each file is searched for "Work alone. The `advisor` tool belongs to the lead that started you, so do not call it: ..."
    Then each file holds the sentence exactly once

  # Backed by: tests/test_advisor_rule.py::test_the_design_agent_does_not_carry_the_sentence
  Scenario: The design agent does not carry the work-alone sentence
    Given the exception set is {"system-architect"}
    When agents/system-architect.md is searched for the sentence
    Then the sentence appears 0 times

  # Backed by: tests/test_advisor_rule.py::test_an_exception_name_with_no_file_is_reported
  Scenario: A name in the exception set with no agent file is reported
    Given a folder holding the agent "worker" with the sentence and no file "system-architect.md"
    When the folder is checked with the exception set {"system-architect"}
    Then the problem list is exactly ["exception system-architect has no file"]

  # Backed by: tests/test_advisor_rule.py::test_a_worker_without_the_sentence_is_reported
  Scenario: A worker agent file without the sentence is reported
    Given a folder holding the agent "worker" without the sentence and the agent "system-architect"
    When the folder is checked with the exception set {"system-architect"}
    Then the problem list is exactly ["worker: sentence appears 0 times, expected 1"]

  # Backed by: tests/test_advisor_rule.py::test_every_agent_front_matter_still_has_model_and_effort
  Scenario: Every agent file keeps model and effort in its front matter
    Given the agent files in agents/
    When the keys of each front matter are read
    Then each front matter has a "model" key and an "effort" key
