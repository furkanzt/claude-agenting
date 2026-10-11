Feature: The finish check reads a completed Workflow's journal and warns when agents are missing
  When a Workflow finishes, the UserPromptSubmit hook counts the agents that started against the agents that returned, stays silent when all returned, and otherwise adds one warning line per incomplete Workflow without ever blocking the prompt.

  # Backed by: tests/test_finish_check.py::test_complete_run_is_silent
  Scenario: A Workflow whose three agents all returned produces no output
    Given a Workflow notification whose journal has 3 started agents and 3 results, with keys v2:k0, v2:k1 and v2:k2
    When the finish check receives the prompt
    Then it exits 0 and prints nothing on stdout

  # Backed by: tests/test_finish_check.py::test_restarted_agents_that_returned_are_not_missing
  Scenario: Agents restarted under the same key count as returned
    Given a journal with 23 started lines and 18 result lines, where 5 agentIds were interrupted and restarted under the same key
    And every one of the 18 keys has a result
    When the finish check receives the Workflow notification
    Then it exits 0 and prints nothing on stdout

  # Backed by: tests/test_finish_check.py::test_incomplete_run_warns_with_counts_and_labels
  Scenario: Missing agents are reported as R of N with their labels
    Given a Workflow "Phase 4 classify" whose journal has 18 logical agents and 13 results
    And the 5 agents without a result are classify:MAT.7.1-1, classify:MAT.7.2, verify:MAT.7.4-1, verify:MAT.7.6 and verify:MAT.7.7
    When the finish check receives the Workflow notification
    Then hookSpecificOutput.hookEventName is "UserPromptSubmit"
    And additionalContext starts with '[agenting] Workflow "Phase 4 classify": 13 of 18 agents returned; missing: '
    And additionalContext names all 5 missing labels
    And additionalContext contains "Read" followed by the journal path and "and report the real count"

  @gap @wip
  # Backed by: @gap
  Scenario: A missing agent with no retry says the Workflow's own summary was built without it
    Given a journal with agents "one" (key k1) and "two" (key k2) where only k1 has a result
    When the finish check receives the Workflow notification
    Then additionalContext contains "1 of 2 agents returned; missing: two. The workflow's own summary was built without them."
    And additionalContext does not contain "later attempt"

  # Backed by: tests/test_finish_check.py::test_label_list_is_capped_at_eight
  Scenario: More than eight missing labels are capped with an "and N more" suffix
    Given a journal with 12 started agents labelled part:0 to part:11 and a result only for part:0
    When the finish check receives the Workflow notification
    Then additionalContext contains "1 of 12 agents returned"
    And additionalContext lists part:8 but not part:9
    And additionalContext contains "… and 3 more"

  # Backed by: tests/test_finish_check.py::test_path_with_spaces
  Scenario: A journal path containing spaces is still found
    Given the notification names a journal at ".../dir with spaces/journal.jsonl" holding 18 agents of which 13 returned
    When the finish check receives the Workflow notification
    Then additionalContext contains "13 of 18"

  # Backed by: tests/test_finish_check.py::test_every_notification_in_one_prompt_is_checked
  Scenario: A complete Workflow notification does not hide a later incomplete one
    Given a prompt holding a notification for Workflow "A" with a complete journal and one for Workflow "B" with an incomplete journal
    When the finish check receives the prompt
    Then additionalContext contains 'Workflow "B"'
    And additionalContext does not contain 'Workflow "A"'

  # Backed by: tests/test_finish_check.py::test_agent_without_key_falls_back_to_agent_id
  Scenario: A started agent without a key is counted by its agentId
    Given a journal with started agents a1 "one" and a2 "two", neither with a key, and a result for a1 only
    When the finish check receives the Workflow notification
    Then additionalContext contains "1 of 2 agents returned; missing: two."

  @gap @wip
  # Backed by: @gap
  Scenario: A result carrying only an agentId covers the started agent with that agentId
    Given a journal with one started agent (key k1, agentId a1) and a result line with agentId a1 and no key
    When the finish check receives the Workflow notification
    Then it exits 0 and prints nothing on stdout

  @gap @wip
  # Backed by: @gap
  Scenario: A started line with neither key nor agentId is not counted as an agent
    Given a journal with one started line carrying only the label "ghost", and one started agent (key k1, agentId a1, label "one") that returned
    When the finish check receives the Workflow notification
    Then it exits 0 and prints nothing on stdout

  @gap @wip
  # Backed by: @gap
  Scenario: A missing agent without a label is named by its agentId
    Given a journal with started agents a1 (key k1) and a2 (key k2), neither with a label, and a result for k1 only
    When the finish check receives the Workflow notification
    Then additionalContext contains "1 of 2 agents returned; missing: a2."

  # Backed by: tests/test_finish_check.py::test_a_retry_under_a_changed_key_is_named_not_hidden
  Scenario: A retry under a changed key is still counted missing but named as a probable retry
    Given a journal where verify:A and verify:B each have a first attempt with no result under one key and a later attempt under a new key that returned
    And classify:A returned
    When the finish check receives the Workflow notification
    Then additionalContext contains "3 of 5 agents returned; missing: verify:A, verify:B."
    And additionalContext contains "Every one of them has a later attempt with the same label that returned"
    And additionalContext contains "real failures"
    And additionalContext contains "Read" followed by the journal path

  # Backed by: tests/test_finish_check.py::test_label_reuse_keeps_real_failures_visible
  Scenario: A label reused for different items keeps the unretried failure visible
    Given a journal where the label verify:render:0 is used by three agents, the first failed, the second returned and the third failed
    And verify:timing:1 returned
    When the finish check receives the Workflow notification
    Then additionalContext contains "2 of 4 agents returned; missing: verify:render:0, verify:render:0."
    And additionalContext contains "1 of them have a later attempt with the same label that returned"
    And additionalContext contains "The others have no result under any attempt"

  @gap @wip
  # Backed by: @gap
  Scenario: A later returned attempt under the same label but a different phase is not a retry
    Given a journal with agent "x" in phase P1 (key k1, no result) and agent "x" in phase P2 (key k2, returned)
    When the finish check receives the Workflow notification
    Then additionalContext contains "1 of 2 agents returned; missing: x."
    And additionalContext contains "The workflow's own summary was built without them."
    And additionalContext does not contain "later attempt"

  @gap @wip
  # Backed by: @gap
  Scenario: A notification without a Workflow summary line is reported as unnamed
    Given an incomplete journal and a notification block with a diagnostics line but no <summary>Dynamic workflow "..."</summary>
    When the finish check receives the prompt
    Then additionalContext starts with '[agenting] Workflow "(unnamed)": '

  @gap @wip
  # Backed by: @gap
  Scenario: A notification block that is never closed is still checked
    Given an incomplete journal and a notification that opens <task-notification> but has no closing tag
    When the finish check receives the prompt
    Then additionalContext contains "0 of 1 agents returned; missing: one."

  @gap @wip
  # Backed by: @gap
  Scenario: Two incomplete Workflows in one prompt give two lines
    Given a prompt holding notifications for Workflows "A" and "B", each with an incomplete journal
    When the finish check receives the prompt
    Then additionalContext holds two lines separated by a newline, the first starting '[agenting] Workflow "A"' and the second '[agenting] Workflow "B"'

  @gap @wip
  # Backed by: @gap
  Scenario: An unreadable second journal does not suppress the first Workflow's warning
    Given a prompt holding an incomplete Workflow "A" and a Workflow "B" whose journal path does not exist
    When the finish check receives the prompt
    Then additionalContext contains 'Workflow "A"' and does not contain 'Workflow "B"'

  # Backed by: tests/test_finish_check.py::test_non_workflow_prompt_is_silent
  Scenario: An ordinary prompt produces no output
    Given the prompt "please fix the failing test in foo.py"
    When the finish check receives the prompt
    Then it exits 0 and prints nothing on stdout

  # Backed by: tests/test_finish_check.py::test_other_task_notification_is_silent
  Scenario: A task notification for a background command is ignored
    Given a notification with the summary 'Background command "npm test" completed' and no "Per-agent results:" line
    When the finish check receives the prompt
    Then it exits 0 and prints nothing on stdout

  # Backed by: tests/test_finish_check.py::test_unreadable_journal_is_silent
  Scenario: A journal path that does not exist yields silence
    Given a Workflow notification whose journal path points to a file that does not exist
    When the finish check receives the prompt
    Then it exits 0 and prints nothing on stdout

  # Backed by: tests/test_finish_check.py::test_journal_without_started_lines_is_silent
  Scenario: A journal with no started agents yields silence
    Given a journal holding only {"type":"launched"} and a line that is not JSON
    When the finish check receives the Workflow notification
    Then it exits 0 and prints nothing on stdout

  @gap @wip
  # Backed by: @gap
  Scenario: A corrupt journal line is skipped and the remaining lines are still counted
    Given a journal with started agent "one" (returned), a line "{bad json", a line "[1,2]", and started agent "two" without a result
    When the finish check receives the Workflow notification
    Then additionalContext contains "1 of 2 agents returned; missing: two."

  # Backed by: tests/test_finish_check.py::test_malformed_stdin_is_silent
  Scenario: Malformed stdin is ignored
    Given the stdin text "{not json"
    When the finish check runs
    Then the exit code is 0 and stdout is empty

  @gap @wip
  # Backed by: @gap
  Scenario Outline: Other unusable stdin shapes are ignored like malformed stdin
    Given the stdin text <stdin>
    When the finish check runs
    Then the exit code is 0 and stdout is empty

    Examples:
      | stdin          |
      | (empty)        |
      | [1]            |
      | {"prompt": 5}  |

  @gap @wip
  # Backed by: @gap
  Scenario Outline: A Workflow notification is checked whatever its status word
    Given an incomplete journal and a Workflow notification whose status and summary say "<status>"
    When the finish check receives the prompt
    Then additionalContext contains "1 of 2 agents returned; missing: two."

    Examples:
      | status    |
      | failed    |
      | stopped   |

  @gap @wip
  # Backed by: @gap
  Scenario: A returned attempt that comes before the missing one is not a retry
    Given a journal with agent "x" in phase P (key k0) that returned, followed by agent "x" in phase P (key k1) with no result
    When the finish check receives the Workflow notification
    Then additionalContext contains "1 of 2 agents returned; missing: x. The workflow's own summary was built without them."
    And additionalContext does not contain "later attempt"

  @gap @wip
  # Backed by: @gap
  Scenario Outline: The "and N more" suffix appears only above eight missing labels
    Given a journal with <started> started agents labelled p:0 to p:<last> and a result only for p:0
    When the finish check receives the Workflow notification
    Then additionalContext contains "missing: <shown>"

    Examples:
      | started | last | shown                                                  |
      | 9       | 8    | p:1, p:2, p:3, p:4, p:5, p:6, p:7, p:8.                |
      | 10      | 9    | p:1, p:2, p:3, p:4, p:5, p:6, p:7, p:8, … and 1 more.  |

  @gap @wip
  # Backed by: @gap
  Scenario: A result with only an agentId covers every attempt restarted under the same key
    Given a journal where key k1 was started under agentId a1 and again under a2, and only a2 has a result line with no key
    When the finish check receives the Workflow notification
    Then it exits 0 and prints nothing on stdout

  @gap @wip
  # Backed by: @gap
  Scenario: A journal path that does not end in .jsonl is ignored
    Given an incomplete journal and a notification whose "Per-agent results:" line names "/x/journal.txt"
    When the finish check receives the prompt
    Then it exits 0 and prints nothing on stdout
