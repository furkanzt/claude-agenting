Feature: Session continuity carries mode, disposition and workflows opt-in across compaction of one chat
  hooks/session-continuity.py keeps a session record per session_id in .agenting-session-state.json and re-injects it as one [agenting] line on every SessionStart.

  # ---- SessionStart: seeding and the [agenting] line ----

  # Backed by: tests/test_session_continuity.py::test_new_session_is_seeded_with_defaults
  Scenario: A session id seen for the first time is seeded with the defaults
    Given an empty state directory
    When SessionStart fires for session "11111111-2222-3333-4444-555555555555" with source "startup"
    Then the session record for that id has mode "auto"
    And the session record has disposition "balanced"
    And the session record has workflows null

  # Backed by: tests/test_session_continuity.py::test_message_is_one_short_line
  Scenario: The [agenting] line is a single short line carrying the state, the session id and the record command
    Given an empty state directory
    When SessionStart fires for session "11111111-2222-3333-4444-555555555555" with source "startup"
    Then the additionalContext has no newline
    And it starts with "[agenting] mode=auto · disposition=balanced · workflows=not opted in"
    And it contains "(session 11111111-2222-3333-4444-555555555555)"
    And it contains python3 "<absolute path of session-continuity.py>" --record --session 11111111-2222-3333-4444-555555555555
    And it contains "[--workflows on|off]"
    And it contains "Load the agenting skill before authoring a Workflow."
    And everything except the script path and the two session ids is shorter than 300 characters

  # Backed by: tests/test_session_continuity.py::test_message_never_asks
  Scenario: The [agenting] line never asks the user anything
    Given an empty state directory
    When SessionStart fires for session "11111111-2222-3333-4444-555555555555" with source "startup"
    Then the additionalContext does not contain "AskUserQuestion"
    And the additionalContext does not contain "?"

  @gap @wip
  # Backed by: @gap
  Scenario: The hook output names the SessionStart event
    Given an empty state directory
    When SessionStart fires for session "s1" with source "startup"
    Then the exit code is 0
    And stdout is JSON whose hookSpecificOutput.hookEventName is "SessionStart"

  # Backed by: tests/test_session_continuity.py::test_record_survives_compaction
  Scenario: Compaction re-injects the recorded mode and disposition
    Given session "11111111-2222-3333-4444-555555555555" was seeded and then recorded with mode manual and disposition fast
    When SessionStart fires for that session with source "compact"
    Then the additionalContext contains "mode=manual · disposition=fast"

  # Backed by: tests/test_session_continuity.py::test_workflows_on_persists_across_compaction
  Scenario: The workflows opt-in survives compaction and is spelled out in the line
    Given session "11111111-2222-3333-4444-555555555555" was seeded and then recorded with workflows on
    When SessionStart fires for that session with source "compact"
    Then the session record has workflows "on"
    And the additionalContext contains "workflows=on"
    And it contains "opted in for this chat"
    And it contains "without re-asking"
    And --status for that session contains "workflows=on"

  # Backed by: tests/test_session_continuity.py::test_workflows_off
  Scenario: A resumed session reports a withdrawn workflows opt-in as workflows=off
    Given session "11111111-2222-3333-4444-555555555555" was recorded with workflows on and then with workflows off
    When SessionStart fires for that session with source "resume"
    Then the additionalContext contains "workflows=off"

  @gap @wip
  # Backed by: @gap
  Scenario: A startup of a session that already has a record keeps that record
    Given session "s1" was recorded with mode manual and workflows on
    When SessionStart fires for session "s1" with source "startup"
    Then the additionalContext starts with "[agenting] mode=manual · disposition=balanced · workflows=on"

  # Backed by: tests/test_session_continuity.py::test_clear_starts_a_fresh_continuum
  Scenario: A clear drops the recorded values and starts again from the defaults
    Given session "11111111-2222-3333-4444-555555555555" was recorded with mode manual and workflows on
    When SessionStart fires for that session with source "clear"
    Then the additionalContext contains "mode=auto"
    And it contains "workflows=not opted in"

  @gap @wip
  # Backed by: @gap
  Scenario: A SessionStart payload with no session_id is recorded under the id "unknown"
    Given an empty state directory
    When the hook receives "{}" on stdin
    Then the exit code is 0
    And the additionalContext contains "(session unknown)"
    And the state file has an entry for "unknown" with mode "auto"

  @gap @wip
  # Backed by: @gap
  Scenario: Empty or malformed stdin still produces a defaults line and exit code 0
    Given an empty state directory
    When the hook receives "garbage" on stdin
    Then the exit code is 0
    And the additionalContext starts with "[agenting] mode=auto · disposition=balanced · workflows=not opted in"

  # ---- --record ----

  # Backed by: tests/test_session_continuity.py::test_record_then_status
  Scenario: Recording a mode and a disposition in one call applies both
    Given an empty state directory
    When --record is run for session "11111111-2222-3333-4444-555555555555" with --mode manual --disposition quality
    Then the exit code is 0
    And stdout contains "mode=manual"
    And stdout contains "disposition=quality"
    And --status for that session prints "session 11111111-2222-3333-4444-555555555555: mode=manual · disposition=quality · workflows=not opted in"

  # Backed by: tests/test_session_continuity.py::test_workflows_flag_leaves_mode_and_disposition_alone
  Scenario: Recording only workflows leaves the recorded mode and disposition alone
    Given session "11111111-2222-3333-4444-555555555555" was recorded with mode manual and disposition quality
    When --record is run for that session with --workflows on
    Then the session record has mode "manual"
    And the session record has disposition "quality"

  @gap @wip
  # Backed by: @gap
  Scenario: Recording one option on an unseen session fills the other values with the defaults
    Given an empty state directory
    When --record is run for session "s5" with --workflows on
    Then the session record for "s5" has mode "auto"
    And the session record has disposition "balanced"
    And the session record has workflows "on"

  @gap @wip
  # Backed by: @gap
  Scenario: Recording stamps the record with a UTC updated time
    Given an empty state directory
    When --record is run for session "s1" with --mode manual
    Then the session record for "s1" has an updated value matching YYYY-MM-DDTHH:MM:SSZ

  @gap @wip
  # Backed by: @gap
  Scenario: A session with no record is not affected by another session's record
    Given session "A" was recorded with mode manual
    When --status is run for session "B"
    Then stdout starts with "no state recorded for session B"

  @gap @wip
  # Backed by: @gap
  Scenario: Recording without --session uses the id "unknown"
    Given an empty state directory
    When --record is run with --mode manual and no --session
    Then stdout starts with "recorded: session unknown: mode=manual"

  # Backed by: tests/test_session_continuity.py::test_record_needs_a_value
  Scenario: A record call that names no option is refused
    Given an empty state directory
    When --record is run for session "11111111-2222-3333-4444-555555555555" with no --mode, --disposition or --workflows
    Then the exit code is not 0

  @gap @wip
  # Backed by: @gap
  Scenario: A refused empty record call exits with code 1, says what to pass and writes no state
    Given an empty state directory
    When --record is run for session "s2" with no --mode, --disposition or --workflows
    Then the exit code is 1
    And stderr is "nothing to record: pass --mode, --disposition and/or --workflows"
    And no state file exists

  # Backed by: tests/test_session_continuity.py::test_semi_auto_is_no_longer_a_valid_mode
  Scenario: The legacy mode semi-auto is rejected by --record
    Given an empty state directory
    When --record is run for session "11111111-2222-3333-4444-555555555555" with --mode semi-auto
    Then the exit code is not 0

  @gap @wip
  # Backed by: @gap
  Scenario: A disposition outside fast, balanced and quality is rejected and writes nothing
    Given an empty state directory
    When --record is run for session "s2" with --disposition turbo
    Then the exit code is 2
    And no state file exists

  @gap @wip
  # Backed by: @gap
  Scenario: A workflows value other than on or off is rejected and writes nothing
    Given an empty state directory
    When --record is run for session "s2" with --workflows maybe
    Then the exit code is 2
    And no state file exists

  @gap @wip
  # Backed by: @gap
  Scenario: A rejected value leaves an existing record byte-for-byte unchanged
    Given session "s3" was recorded with mode manual
    When --record is run for session "s3" with --mode bogus
    Then the exit code is 2
    And the state file is identical to its content before the call

  # Backed by: tests/test_session_continuity.py::test_suggestion_flag_is_gone
  Scenario: The old --suggestion flag alone is refused
    Given an empty state directory
    When --record is run for session "11111111-2222-3333-4444-555555555555" with --suggestion on
    Then the exit code is not 0

  @gap @wip
  # Backed by: @gap
  Scenario: An unrecognised flag next to a valid option is ignored and the valid option is recorded
    Given an empty state directory
    When --record is run for session "s4" with --suggestion on and --mode manual
    Then the exit code is 0
    And the session record for "s4" has mode "manual"
    And the session record has no "suggestion" key

  @gap @wip
  # Backed by: @gap
  Scenario: Passing --record and --status together runs --record only
    Given an empty state directory
    When --record --status is run for session "z" with --mode manual
    Then stdout starts with "recorded: session z: mode=manual"
    And the state file has an entry for "z"

  # ---- --status ----

  # Backed by: tests/test_session_continuity.py::test_status_without_state_reports_defaults
  Scenario: Status for a session with no record reports the defaults
    Given an empty state directory
    When --status is run for session "11111111-2222-3333-4444-555555555555"
    Then stdout contains "no state recorded"
    And stdout contains "mode=auto · disposition=balanced · workflows=not opted in"

  @gap @wip
  # Backed by: @gap
  Scenario: Status is read-only and never creates the state file
    Given an empty state directory
    When --status is run for session "zz"
    Then the exit code is 0
    And no state file exists

  @gap @wip
  # Backed by: @gap
  Scenario: Status without --session reports on the session "unknown"
    Given an empty state directory
    When --status is run with no --session
    Then stdout starts with "no state recorded for session unknown (defaults: "

  # ---- legacy and malformed state ----

  # Backed by: tests/test_session_continuity.py::test_legacy_semi_auto_reads_as_manual
  Scenario: A legacy semi-auto entry is read as manual, never as auto
    Given the state file holds session "11111111-2222-3333-4444-555555555555" with mode "semi-auto"
    When SessionStart fires for that session with source "compact"
    Then the additionalContext contains "mode=manual"
    And it does not contain "semi-auto"
    And --status for that session contains "mode=manual"

  # Backed by: tests/test_session_continuity.py::test_legacy_suggestion_is_not_mapped_to_workflows
  Scenario: A legacy suggestion key is not mapped to the workflows opt-in
    Given the state file holds session "11111111-2222-3333-4444-555555555555" with mode "semi-auto" and suggestion "on"
    When SessionStart fires for that session with source "compact"
    Then the additionalContext contains "workflows=not opted in"

  # Backed by: tests/test_session_continuity.py::test_record_rewrites_legacy_entry
  Scenario: Recording over a legacy entry rewrites it in the current vocabulary
    Given the state file holds session "11111111-2222-3333-4444-555555555555" with mode "semi-auto" and suggestion "on"
    When --record is run for that session with --disposition fast
    Then the session record has mode "manual"
    And the session record has no "suggestion" key

  # Backed by: tests/test_session_continuity.py::test_unreadable_mode_reads_as_manual
  Scenario: An entry whose mode is unreadable is read as manual
    Given the state file holds session "11111111-2222-3333-4444-555555555555" with mode "???"
    When SessionStart fires for that session with source "compact"
    Then the additionalContext contains "mode=manual"

  @gap @wip
  # Backed by: @gap
  Scenario: Unreadable disposition and workflows values fall back to balanced and not opted in
    Given the state file holds session "s" with mode "auto", disposition "turbo" and workflows "maybe"
    When --status is run for session "s"
    Then stdout is "session s: mode=auto · disposition=balanced · workflows=not opted in"

  # Backed by: tests/test_session_continuity.py::test_corrupt_state_file_does_not_crash
  Scenario: A state file that is not valid JSON is treated as empty
    Given the state file contains "{not json"
    When SessionStart fires for session "11111111-2222-3333-4444-555555555555" with source "startup"
    Then the exit code is 0
    And the additionalContext contains "mode=auto"

  # Backed by: tests/test_session_continuity.py::test_non_dict_entry_does_not_crash
  Scenario: A session entry that is not an object is replaced by the defaults
    Given the state file holds session "11111111-2222-3333-4444-555555555555" with the value "garbage"
    When SessionStart fires for that session with source "startup"
    Then the exit code is 0
    And the additionalContext contains "mode=auto"

  @gap @wip
  # Backed by: @gap
  Scenario: A state file whose top level is a list is treated as empty and then overwritten
    Given the state file contains "[1,2]"
    When --record is run for session "s" with --mode manual
    Then the exit code is 0
    And the state file is a JSON object whose "s" entry has mode "manual"

  @gap @wip
  # Backed by: @gap
  Scenario: An empty entry is read as auto but an entry with other keys and no mode is read as manual
    Given the state file holds session "e" with the value {} and session "f" with only disposition "fast"
    When --status is run for session "e" and for session "f"
    Then the "e" status line starts with "session e: mode=auto"
    And the "f" status line starts with "session f: mode=manual · disposition=fast"

  # ---- state directory, eviction and bounds ----

  # Backed by: tests/test_real_state_untouched.py::test_override_keeps_real_files_unchanged
  Scenario: AGENTING_STATE_DIR redirects the state file away from ~/.claude
    Given AGENTING_STATE_DIR points at a temporary directory
    When SessionStart fires and --record is run for session "real-state-probe"
    Then the temporary directory holds .agenting-session-state.json
    And ~/.claude/.agenting-session-state.json is unchanged

  @gap @wip
  # Backed by: @gap
  Scenario: A state directory that does not exist yet is created on the first write
    Given AGENTING_STATE_DIR points at a path whose directories do not exist
    When --record is run for session "s" with --mode manual
    Then the exit code is 0
    And the new directory holds .agenting-session-state.json
    And it holds no .tmp file

  @gap @wip
  # Backed by: @gap
  Scenario: An unwritable state directory does not break --record
    Given AGENTING_STATE_DIR points below a regular file
    When --record is run for session "s" with --mode manual
    Then the exit code is 0
    And stdout starts with "recorded: session s: mode=manual"
    And --status for session "s" prints "no state recorded for session s"

  @gap @wip
  # Backed by: @gap
  Scenario: An unwritable state directory does not break the SessionStart hook
    Given AGENTING_STATE_DIR points below a regular file
    When SessionStart fires for session "s" with source "startup"
    Then the exit code is 0
    And the additionalContext starts with "[agenting] mode=auto"

  @gap @wip
  # Backed by: @gap
  Scenario: Exactly 20 sessions are all kept
    Given the state file holds 19 sessions with distinct updated times
    When --record is run for a 20th session "n" with --mode manual
    Then the state file has 20 entries
    And the oldest of them is still present

  @gap @wip
  # Backed by: @gap
  Scenario: A 21st session evicts the session with the oldest updated time
    Given the state file holds 20 sessions "s00" to "s19" with updated times 2026-01-01 to 2026-01-20
    When --record is run for a new session "new" with --mode manual
    Then the state file has 20 entries
    And "s00" is absent
    And "s01" and "new" are present

  @gap @wip
  # Backed by: @gap
  Scenario: Seeding a new session from the hook also evicts the oldest session
    Given the state file holds 20 sessions "s00" to "s19" with updated times 2026-01-01 to 2026-01-20
    When SessionStart fires for a new session "newer" with source "startup"
    Then the state file has 20 entries
    And "s00" is absent
    And "newer" is present

  @gap @wip
  # Backed by: @gap
  Scenario: SessionStart does not refresh the updated time of an existing record
    Given the state file holds session "old" with mode "manual" and updated "2026-01-01T00:00:00Z"
    When SessionStart fires for session "old" with source "resume"
    Then the session record for "old" still has updated "2026-01-01T00:00:00Z"
