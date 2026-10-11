Feature: The subagent-effort reader reports the effort each subagent transcript records and flags a pin that was not applied

  The reader (evals/probes/read_effort.py) turns the effort, perTurnEffort and requestedModel carried by
  every assistant record of a subagent transcript into a per-group table, so "was my pinned effort
  applied" is read directly. It is a development tool for after a Claude Code update, not a hook.

  # Backed by: tests/test_effort_probe.py::test_reads_the_recorded_effort_model_and_thinking_time
  Scenario: An agent's recorded effort, model and thinking time are read from its assistant records
    Given a transcript for the agent labelled "low-1" whose two assistant records record effort low, model claude-haiku-5-5 and 2500 ms of thinking each
    When the reader reads the directory
    Then it reports one agent with efforts ["low"], models ["claude-haiku-5-5"], 2 turns and 5000 ms of thinking

  # Backed by: tests/test_effort_probe.py::test_groups_repeats_by_label_and_averages_thinking_time
  Scenario: Repeats are grouped by label without the repeat number and their thinking time is averaged
    Given agents labelled "high-1" and "high-2" with 2000 ms and 6000 ms of total thinking and an agent labelled "low-1"
    When the reader summarizes the directory
    Then the group "high" has 2 agents and a mean thinking time of 4000 ms, and the group "low" records effort ["low"]

  # Backed by: tests/test_effort_probe.py::test_ignores_non_assistant_and_unparseable_lines
  Scenario: Records that are not assistant records, and lines that are not JSON objects, are ignored
    Given a transcript with a user record, a line that is not JSON and a JSON array among its lines
    When the reader reads it
    Then only the assistant records are counted as turns

  # Backed by: tests/test_effort_probe.py::test_a_pin_that_was_not_applied_is_reported
  Scenario: A group that recorded a different effort than expected, or is missing, is reported
    Given a group "xhigh" whose agent recorded effort medium
    When the expectations "xhigh=xhigh" and "high=high" are checked
    Then the first is reported as expected xhigh but recorded ["medium"], the second as no agents found, and "xhigh=medium" is accepted

  # Backed by: tests/test_effort_probe.py::test_the_cli_exits_nonzero_on_a_mismatch_and_zero_otherwise
  Scenario: The command line exits 1 with a MISMATCH line when an expectation fails and 0 when it holds
    Given a directory with one agent labelled "low-1" that recorded effort low
    When the reader runs with --expect low=low and then with --expect low=high
    Then the first exits 0 and the second exits 1 and prints "MISMATCH low: expected effort high"

  # Backed by: tests/test_effort_probe.py::test_an_empty_directory_is_an_error
  Scenario: A directory with no agent transcripts is an error
    Given an empty directory
    When the reader runs on it
    Then it exits 2
