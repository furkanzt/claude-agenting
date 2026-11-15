Feature: Session continuity carries mode, disposition and workflows opt-in across compaction of one chat
  hooks/session-continuity.py keeps a session record per session_id in .agenting-session-state.json and re-injects it as one [agenting] line on every SessionStart. A new chat starts in the disposition of the account's plan (fast on Pro, balanced on Max) when the plan can be read, and the user is told once.

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
    And it contains "Load the agenting skill before moving bulk work off this chat or starting an agent, teammate or Workflow."
    And everything except the script path and the two session ids is shorter than 450 characters

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
    When --record is run for session "11111111-2222-3333-4444-555555555555" with --mode manual --disposition fast
    Then the exit code is 0
    And stdout contains "mode=manual"
    And stdout contains "disposition=fast"
    And --status for that session prints "session 11111111-2222-3333-4444-555555555555: mode=manual · disposition=fast · workflows=not opted in"

  # Backed by: tests/test_session_continuity.py::test_workflows_flag_leaves_mode_and_disposition_alone
  Scenario: Recording only workflows leaves the recorded mode and disposition alone
    Given session "11111111-2222-3333-4444-555555555555" was recorded with mode manual and disposition fast
    When --record is run for that session with --workflows on
    Then the session record has mode "manual"
    And the session record has disposition "fast"

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
  Scenario: A disposition outside fast and balanced (and the removed quality) is rejected and writes nothing
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

  # ---- teammates status and the standing Workflows default ----

  # Backed by: tests/test_session_continuity.py::test_teammates_on_from_the_environment
  Scenario: The line says teammates=on when the environment variable is true
    Given CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS is "TRUE" in the hook's environment
    When SessionStart fires for session "11111111-2222-3333-4444-555555555555" with source "startup"
    Then the additionalContext contains " · teammates=on · advisor=off (session"
    And it does not contain "teammates=off"

  # Backed by: tests/test_session_continuity.py::test_teammates_off_when_absent_everywhere
  Scenario: The line says teammates=off when no environment variable or settings file names it
    Given CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS is absent from the environment and from the user, project and local settings files
    When SessionStart fires for a new session with source "startup"
    Then the additionalContext contains "teammates=off"
    And it does not contain "teammates=on"

  # Backed by: tests/test_session_continuity.py::test_teammates_off_note_text
  Scenario: The teammates=off note tells Claude to explain once how to turn teammates on
    Given teammates are off
    When SessionStart fires for session "11111111-2222-3333-4444-555555555555" with source "startup"
    Then the additionalContext contains "workflows=not opted in · teammates=off (when a job fits teammates, tell the user once in this chat how to turn them on; see the skill's teammates section) · advisor=off (session 11111111-2222-3333-4444-555555555555)"
    And it has no newline and does not contain "?"

  # Backed by: tests/test_session_continuity.py::test_teammates_on_from_the_user_settings_file
  Scenario: Teammates are on when only ~/.claude/settings.json sets the variable to 1 in its env object
    Given the environment lacks CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS and $HOME/.claude/settings.json has {"env": {"CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"}}
    When SessionStart fires for a new session with source "startup"
    Then the additionalContext contains " · teammates=on · advisor=off (session"

  # Backed by: tests/test_session_continuity.py::test_teammates_on_from_the_project_local_settings_file
  Scenario: Teammates are on when only the project's .claude/settings.local.json sets the variable
    Given the environment lacks the variable and <cwd>/.claude/settings.local.json has {"env": {"CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "true"}}
    When SessionStart fires with that cwd
    Then the additionalContext contains " · teammates=on · advisor=off (session"

  # Backed by: tests/test_session_continuity.py::test_environment_variable_beats_the_settings_files
  Scenario: A present environment variable decides even when a settings file says otherwise
    Given the environment variable is "0" and $HOME/.claude/settings.json sets it to "1"
    When SessionStart fires for a new session with source "startup"
    Then the additionalContext contains "teammates=off"

  # Backed by: tests/test_session_continuity.py::test_non_object_settings_file_counts_as_absent
  Scenario: An unreadable or non-object settings file is ignored
    Given the environment lacks the variable, the user settings file holds a JSON list, the project settings file is not JSON and the local settings file has an env that is a list
    When SessionStart fires for a new session with source "startup"
    Then the exit code is 0
    And the additionalContext contains "teammates=off"

  # Backed by: tests/test_session_continuity.py::test_status_prints_the_teammates_value
  Scenario: --status prints the teammates value
    Given the variable is absent from every source
    When --status is run for a session
    Then the output contains "teammates=off"
    And with the variable set to "1" in the environment it contains "teammates=on"

  # ---- advisor state ----

  # Backed by: tests/test_session_continuity.py::test_advisor_is_off_when_nothing_names_one
  Scenario: The line says advisor=off when no switch or settings file names an advisor
    Given CLAUDE_CODE_DISABLE_ADVISOR_TOOL is absent and no settings file has an advisorModel
    When SessionStart fires for session "11111111-2222-3333-4444-555555555555" with source "startup"
    Then the additionalContext contains " · advisor=off (session 11111111-2222-3333-4444-555555555555)"
    And the advisor part comes right after the teammates part
    And it has no newline

  # Backed by: tests/test_session_continuity.py::test_advisor_line_carries_the_model_and_the_work_alone_note
  Scenario: The line names the advisor model and reminds the lead that workers work alone
    Given $HOME/.claude/settings.json has {"advisorModel": "fable-5.2"}
    When SessionStart fires for session "11111111-2222-3333-4444-555555555555" with source "startup"
    Then the additionalContext contains " · advisor=fable-5.2 (agents you start inherit it; workers work alone: put the work-alone sentence in each agent prompt, agenting: agents carry it; see the skill) (session 11111111-2222-3333-4444-555555555555)"
    And it does not contain "advisor=off"
    And it has no newline and does not contain "?"

  # Backed by: tests/test_session_continuity.py::test_advisor_from_each_settings_file
  Scenario: Each of the three settings files can name the advisor
    Given only <cwd>/.claude/settings.local.json, only <cwd>/.claude/settings.json, or only $HOME/.claude/settings.json has an advisorModel
    When SessionStart fires with that cwd
    Then the additionalContext contains "advisor=" followed by that file's model and " (agents"

  # Backed by: tests/test_session_continuity.py::test_advisor_settings_files_are_read_local_then_project_then_user
  Scenario: The advisor settings files are read in the order local, project, user
    Given all three settings files have an advisorModel
    When SessionStart fires with that cwd
    Then the advisor is the project file's model while the local file has none
    And the advisor is the local file's model once it has one

  # Backed by: tests/test_session_continuity.py::test_environment_switch_beats_every_settings_file
  Scenario: CLAUDE_CODE_DISABLE_ADVISOR_TOOL wins over every settings file
    Given all three settings files have an advisorModel
    When SessionStart fires with the variable set to "1", "true", "YES" or " True "
    Then the additionalContext contains " · advisor=off (session"
    And with the variable set to "0" it names the settings model again

  # Backed by: tests/test_session_continuity.py::test_invalid_json_and_non_string_values_are_skipped
  Scenario: A settings file that is not JSON, or an advisorModel that is not a non-empty string, is skipped
    Given the local settings file is not JSON, the project file has advisorModel 7, and the user file has advisorModel "" and a nested env.advisorModel
    When SessionStart fires with that cwd
    Then the additionalContext contains " · advisor=off (session"
    And a later valid advisorModel in a lower-priority file is still found

  # Backed by: tests/test_session_continuity.py::test_status_prints_the_advisor_value
  Scenario: --status prints the advisor value between the teammates part and the standing default
    Given no advisor is configured
    When --status is run for a session with a cwd
    Then the output contains " · advisor=off · standing default: workflows=unset"
    And with a project advisorModel "fable-5.2" it contains "advisor=fable-5.2 (agents you start inherit it"
    And with the environment switch set to "1" it contains "advisor=off"

  # Backed by: tests/test_session_continuity.py::test_default_is_recorded_and_shown_by_status
  Scenario: --record-default stores the standing Workflows default under _defaults and --status shows it
    Given an empty state directory
    When --record-default --workflows on is run with no --session
    Then the state file key "_defaults" is {"workflows": "on"}
    And --status with and without --session prints "standing default: workflows=on"

  # Backed by: tests/test_session_continuity.py::test_new_session_is_seeded_from_the_default_and_labelled_standing
  Scenario: A session seen for the first time takes the standing default and the line labels it standing
    Given the standing default is workflows on
    When SessionStart fires for a new session with source "startup"
    Then the session record has workflows "on" and workflows_source "default"
    And the additionalContext contains "workflows=on (standing: the user set this for all chats; run Workflows for substantive tasks without re-asking)"
    And a later compact SessionStart prints the same standing text

  # Backed by: tests/test_session_continuity.py::test_existing_session_is_untouched_by_a_later_default
  Scenario: A session that already has a record is never changed by a later default
    Given session "11111111-2222-3333-4444-555555555555" has a record with workflows null
    When --record-default --workflows on is run
    Then that record still has workflows null
    And a resume SessionStart prints "workflows=not opted in" without "standing"

  # Backed by: tests/test_session_continuity.py::test_per_chat_record_clears_the_standing_mark
  Scenario: --record --workflows in a seeded session clears the standing mark
    Given the standing default is workflows on and a session was seeded from it
    When --record --session <id> --workflows off is run
    Then the session record has workflows "off" and no workflows_source key
    And the next SessionStart line does not contain "standing"

  # Backed by: tests/test_session_continuity.py::test_unset_removes_the_default
  Scenario: --record-default --workflows unset removes the standing default
    Given the standing default is workflows on
    When --record-default --workflows unset is run
    Then the state file has no "_defaults" key
    And --status prints "standing default: workflows=unset"
    And a new session is seeded with "workflows=not opted in"

  # Backed by: tests/test_session_continuity.py::test_defaults_key_survives_pruning_and_is_not_a_session
  Scenario: The _defaults key survives pruning and is not counted as a session
    Given the standing default is workflows on
    When --record is run for 25 distinct sessions
    Then the state file still has "_defaults" {"workflows": "on"}
    And it has exactly 20 other entries

  # Backed by: tests/test_session_continuity.py::test_record_default_needs_no_session_and_rejects_bad_values
  Scenario: The standing default accepts only on, off or unset, and unset is not a per-chat value
    When --record-default --workflows maybe is run
    Then the exit code is not 0
    And --record-default with no --workflows also exits non-zero and writes no state file
    And --record --session <id> --workflows unset also exits non-zero

  # ---- the cheapest disposition (3.7.0) ----

  # Backed by: tests/test_session_continuity.py::test_cheapest_is_recorded_and_carried_across_compaction
  Scenario: The cheapest disposition is recorded and carried across compaction
    Given an empty state directory
    When --record --disposition cheapest is run for a session
    Then the output contains "mode=auto · disposition=cheapest · workflows=not opted in" and the session record has disposition "cheapest"
    And SessionStart with source "compact" for that session says "mode=auto · disposition=cheapest · "
    And --status for that session shows "disposition=cheapest"

  # Backed by: tests/test_session_continuity.py::test_no_plan_starts_a_chat_in_cheapest
  Scenario Outline: No plan starts a chat in cheapest
    Given .claude.json whose oauthAccount has organizationType "<organizationType>"
    When SessionStart fires for a new session
    Then the additionalContext does not contain "disposition=cheapest"
    And the session record's disposition is "fast" or "balanced"

    Examples:
      | organizationType |
      | claude_pro       |
      | claude_max       |

  # Backed by: tests/test_session_continuity.py::test_choosing_cheapest_replaces_the_plans_start
  Scenario: Choosing cheapest replaces the plan's start
    Given a Pro plan and a session whose line says "disposition=fast (set for the Pro plan)"
    When --record --disposition cheapest is run for that session
    Then SessionStart with source "compact" says "mode=auto · disposition=cheapest · " and does not contain "set for"
    And the session record has no "disposition_source"

  # Backed by: tests/test_session_continuity.py::test_both_first_start_lines_name_the_three_modes
  Scenario Outline: Both first-start lines name the three modes
    Given a fresh state file and .claude.json whose oauthAccount has organizationType "<organizationType>"
    When SessionStart fires for a new session
    Then the systemMessage ends with "<lead>/agenting-mode [cheapest|fast|balanced]"

    Examples:
      | organizationType | lead                        |
      | claude_pro       | Change mode:                |
      | claude_max       | To save usage, change mode: |

  # Backed by: tests/test_session_continuity.py::test_the_tip_names_a_model_an_effort_and_the_cost_of_switching
  Scenario: The main-chat tip names a model, an effort and the cost of switching
    Given the hook's one-line MAIN_CHAT_TIP constant
    Then it contains "Sonnet at high effort (/model sonnet, then /effort high)", "Opus at xhigh effort" and "do not switch back and forth"
    And on a Pro plan the systemMessage of a new session contains " Tip: <the tip>. Change mode: " and is one line

  # Backed by: tests/test_session_continuity.py::test_an_unknown_disposition_is_refused
  Scenario: A disposition the plugin does not know is refused
    Given an empty state directory
    When --record --disposition cheap is run for a session
    Then the command exits non-zero and no state file is written

  # ---- the removed quality setting ----

  # Backed by: tests/test_session_continuity.py::test_the_line_offers_three_dispositions
  Scenario: The [agenting] line offers three dispositions
    Given an empty state directory
    When SessionStart fires for a new session
    Then the additionalContext contains "[--disposition cheapest|fast|balanced] "
    And it does not contain "quality"

  # Backed by: tests/test_session_continuity.py::test_recording_quality_records_balanced_and_says_what_to_say_instead
  Scenario: Recording the removed quality setting records balanced and says what to say instead
    Given an empty state directory
    When --record is run for a session with --disposition quality
    Then stdout contains 'disposition=balanced · workflows=not opted in (the quality setting is gone: say "critical" for one job that needs the careful models)'
    And the session record has disposition "balanced"
    And the next [agenting] line of that session does not contain "quality"

  # Backed by: tests/test_session_continuity.py::test_a_chat_recorded_as_quality_reads_as_balanced_and_the_line_says_so
  Scenario: A chat that was recorded as quality reads as balanced and the line says so
    Given a session record with disposition "quality" written by an older version
    When SessionStart fires for that session with source "compact"
    Then the additionalContext contains 'mode=auto · disposition=balanced (the quality setting is gone: say "critical" for one job that needs the careful models) · workflows=not opted in'
    And --status prints the same note
    And after any --record for that session the record has disposition "balanced" and the line no longer mentions quality

  # ---- the account's plan ----

  # Backed by: tests/test_session_continuity.py::test_no_plan_file_changes_nothing
  Scenario: Without a readable plan nothing changes
    Given a home folder with no .claude.json
    When SessionStart fires for a new session
    Then the output has no systemMessage
    And the additionalContext starts with "[agenting] mode=auto · disposition=balanced · workflows=not opted in" and does not contain "plan"
    And the state file has no "_plan" key

  # Backed by: tests/test_session_continuity.py::test_a_pro_plan_starts_a_new_chat_in_fast_and_tells_the_user
  Scenario: On a Pro plan a new chat starts in fast and the user is told
    Given .claude.json whose oauthAccount has organizationType "claude_pro"
    When SessionStart fires for a new session
    Then the systemMessage is "[agenting] plan=Pro · mode=fast (set for your plan: cheaper models, fewer agents)." followed by " Tip: <the main-chat tip>." when the hook has one, then " Change mode: /agenting-mode [cheapest|fast|balanced]"
    And the additionalContext starts with "[agenting] mode=auto · disposition=fast (set for the Pro plan) · workflows=not opted in" and contains " · advisor=off · plan=Pro (session <id>). "
    And the session record has disposition "fast", disposition_source "plan" and plan "Pro"
    And the state file's "_plan" record says "Pro"
    And --status for that session shows "disposition=fast (set for the Pro plan)"

  # Backed by: tests/test_session_continuity.py::test_a_max_plan_starts_in_balanced_and_tells_the_user
  Scenario: On a Max plan a new chat starts in balanced and the user is told
    Given .claude.json whose oauthAccount has organizationType "claude_max"
    When SessionStart fires for a new session
    Then the systemMessage is "[agenting] plan=Max · mode=balanced (set for your plan). To save usage, change mode: /agenting-mode [cheapest|fast|balanced]"
    And the additionalContext contains "mode=auto · disposition=balanced (set for the Max plan) · " and " · plan=Max (session "

  # Backed by: tests/test_session_continuity.py::test_the_user_is_told_at_the_first_start_of_a_chat_only
  Scenario: The user is told at the first SessionStart of a chat only
    Given a Pro plan and a session that has already started
    When SessionStart fires again for it with source "compact" and then "resume"
    Then neither output has a systemMessage and both lines still say "disposition=fast (set for the Pro plan)"
    And a SessionStart with source "clear", or for another session id, has the systemMessage again

  # Backed by: tests/test_session_continuity.py::test_the_users_own_choice_replaces_the_plans_start
  Scenario: The user's own choice of disposition replaces the plan's start
    Given a Pro plan and a session the plan started in fast
    When --record is run for it with --workflows on, then --mode manual, then --mode auto
    Then the line still says "disposition=fast (set for the Pro plan)"
    When --record is run for it with --disposition balanced
    Then the line says "mode=auto · disposition=balanced · workflows=on" with no "set for", there is no systemMessage, and the record has no disposition_source and no plan
    And choosing --disposition fast afterwards also shows no "set for"

  # Backed by: tests/test_session_continuity.py::test_a_plan_change_is_told_once_at_the_next_new_chat
  Scenario: A plan change is told once, at the next new chat
    Given a chat that started on a Pro plan, and the plan is Max now
    When SessionStart fires for the old chat with source "compact"
    Then it has no systemMessage and still says "disposition=fast (set for the Pro plan)"
    When SessionStart fires for a new session
    Then the systemMessage is "[agenting] plan changed from Pro to Max · new chats now start in balanced." and the line says "disposition=balanced (set for the Max plan)"
    And the new session after that gets the ordinary Max notice
    And after the plan goes back to Pro the next new session gets "[agenting] plan changed from Max to Pro · new chats now start in fast."

  # Backed by: tests/test_session_continuity.py::test_which_fields_name_the_plan
  Scenario Outline: Which fields of the account name the plan
    Given .claude.json whose oauthAccount is <account>
    When SessionStart fires for a new session
    Then the plan on the line is <plan>

    Examples:
      | account                                                                 | plan |
      | organizationType claude_max                                             | Max  |
      | organizationRateLimitTier default_claude_max_5x                         | Max  |
      | organizationType claude_pro                                             | Pro  |
      | organizationType null, userRateLimitTier default_claude_pro             | Pro  |
      | planDisplayName Pro                                                     | Pro  |
      | organizationType claude_team with a max rate-limit tier                 | none |
      | organizationType claude_enterprise                                      | none |
      | organizationType professional_services, planDisplayName Product         | none |
      | organizationRateLimitTier maximal_tier, planDisplayName Maxwell         | none |
      | organizationType empty, organizationRateLimitTier default_claude_pro    | Pro  |
      | organizationType 7, planDisplayName a list                              | none |
      | billingType pro, seatTier max (not plan fields)                         | none |

  # Backed by: tests/test_session_continuity.py::test_an_unreadable_plan_file_changes_nothing
  Scenario: A plan file that cannot be read changes nothing
    Given .claude.json that is not JSON, or a list, or has no oauthAccount object
    When SessionStart fires for a new session
    Then the output has no systemMessage and the line says "mode=auto · disposition=balanced · workflows=not opted in"

  # Backed by: tests/test_session_continuity.py::test_a_project_that_names_its_own_default_is_not_started_by_the_plan
  Scenario: A project that names its own default is not started by the plan
    Given a Pro plan and a project whose agenting/AGENTING.md has the line "auto-disposition-default: balanced"
    When SessionStart fires for a new session in that project
    Then the output has no systemMessage, the line says "disposition=balanced" with no "set for", and it still carries " · plan=Pro"
    And when the only mention is inside an HTML comment, the plan starts the chat in fast and the user is told

  # Backed by: tests/test_session_continuity.py::test_the_plan_record_is_not_a_session
  Scenario: The plan record is not a session
    Given a Pro plan
    When SessionStart fires for 25 distinct new sessions
    Then the state file still has the "_plan" record and exactly 20 sessions
    And --record --session _plan records under "unknown" and leaves the plan record alone

  # Backed by: tests/test_session_continuity.py::test_a_chat_that_lost_its_record_is_seeded_by_the_plan_without_a_notice
  Scenario Outline: A chat that already existed and has no record is seeded by the plan without a notice
    Given a Pro plan and a session id with no record
    When SessionStart fires for it with source "<source>"
    Then the output has no systemMessage and the line says "disposition=fast (set for the Pro plan)"
    And the state file has no "_plan" record yet, so the next new chat gets the ordinary Pro notice

    Examples:
      | source  |
      | compact |
      | resume  |
      | fork    |

  # Backed by: tests/test_session_continuity.py::test_a_record_for_a_chat_with_no_record_starts_where_the_plan_starts
  Scenario: A --record for a chat with no record starts where the plan starts
    Given a Pro plan and a session id with no record, for which --status shows "disposition=fast (set for the Pro plan)"
    When --record is run for it with --mode manual only
    Then stdout contains "mode=manual · disposition=fast (set for the Pro plan)" and the record has disposition "fast"

  # Backed by: tests/test_session_continuity.py::test_a_chat_in_a_project_with_its_own_default_does_not_swallow_the_plan_change
  Scenario: A chat in a project with its own default does not swallow the plan-change notice
    Given a chat that started on a Pro plan, and the plan is Max now
    When the next new chat starts in a project whose AGENTING.md names its own default
    Then it has no systemMessage
    And the new chat after it, in a project without one, gets "[agenting] plan changed from Pro to Max · new chats now start in balanced."

  # Backed by: tests/test_session_continuity.py::test_the_plan_change_is_still_told_after_the_plan_could_not_be_read_for_a_while
  Scenario: A plan change is still told after the plan could not be read for a while
    Given a chat that started on a Pro plan, then new chats while the plan file was not JSON
    When the file is readable again and still says Pro
    Then the next new chat gets the ordinary Pro notice
    When it becomes unreadable again and then says Max
    Then the next new chat gets "[agenting] plan changed from Pro to Max · new chats now start in balanced."

  # Backed by: tests/test_session_continuity.py::test_the_project_file_is_found_from_a_folder_inside_the_project
  Scenario: The project's rules file is found from a folder inside the project
    Given a Pro plan, a project root with .git and agenting/AGENTING.md that says "**auto-disposition-default:** `Balanced`", and a session whose cwd is src/deep inside it
    When SessionStart fires for a new session
    Then the output has no systemMessage and the line says "disposition=balanced"
    And a session whose cwd is a nested folder with its own .git is started by the plan, because the search stops at .git

  # Backed by: tests/test_session_continuity.py::test_what_counts_as_a_project_default
  Scenario Outline: What counts as a project default
    Given a Pro plan and agenting/AGENTING.md with the line <line>
    When SessionStart fires for a new session
    Then the plan <effect> the chat

    Examples:
      | line                                         | effect          |
      | - `auto-disposition-default: balanced`       | does not start  |
      | auto-disposition-default : fast              | does not start  |
      | - **auto-disposition-default:** quality      | does not start  |
      | `auto-disposition-default`: `fast`           | does not start  |
      | auto-disposition-default: cheapest           | does not start  |
      | auto-disposition-default: and a new line     | starts          |
      | auto-disposition-default: TBD                | starts          |
      | the key inside an HTML comment               | starts          |
      | nothing here                                 | starts          |

  # Backed by: tests/test_session_continuity.py::test_an_odd_stored_plan_value_never_stops_the_hook
  Scenario: An odd stored plan value never stops the hook
    Given a state file whose "_plan" holds a list, one session whose plan mark holds an object, and one whose plan mark does not fit its stored disposition
    When SessionStart fires for each of those sessions and for a new one
    Then each gets its line: the first two without "set for", and the new chat with the ordinary Pro notice
    And the "_plan" record is "Pro" again and a later --record prints "recorded: session"

  # Backed by: tests/test_session_continuity.py::test_a_reserved_key_is_never_a_session_id
  Scenario Outline: A reserved key is never a session id
    Given a Pro plan and a state file with a "_plan" record
    When SessionStart fires with session_id "<key>"
    Then the line says "(session unknown)" and the "_plan" record is untouched

    Examples:
      | key       |
      | _plan     |
      | _defaults |

  # Backed by: tests/test_session_continuity.py::test_the_plan_file_is_read_from_the_config_folder_when_one_is_set
  Scenario: The plan file is read from the config folder when one is set
    Given CLAUDE_CONFIG_DIR names a folder whose .claude.json says Pro, while the home folder's says Max
    When SessionStart fires for a new session
    Then the line carries " · plan=Pro"
    And with CLAUDE_CONFIG_DIR naming a folder that has no .claude.json, the line carries no plan

  # Backed by: tests/test_session_continuity.py::test_the_line_with_a_plan_or_the_quality_note_stays_short_asks_nothing_and_is_read_by_the_guard
  Scenario: The line with a plan, or with the quality note, stays short, asks nothing and is read by the Workflow guard
    Given a new chat on a Pro plan, and an older chat recorded as manual and quality
    When SessionStart fires for each
    Then neither line has a newline, a question mark or "AskUserQuestion", nor has the notice
    And each line, without the script path and the two session ids, is shorter than 560 characters
    And the Workflow guard's SESSION_LINE_RE reads the mode and the session id from each line

