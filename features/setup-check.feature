Feature: The plugin health check runs the hooks end to end and reports PASS, WARN or FAIL, and the AGENTING_STATE_DIR override keeps hook state out of the real ~/.claude

  # --- State isolation -----------------------------------------------------

  # Backed by: tests/test_real_state_untouched.py::test_override_keeps_real_files_unchanged
  Scenario: AGENTING_STATE_DIR redirects the session-continuity and routing-guard state files away from the real ~/.claude
    Given AGENTING_STATE_DIR points at an empty temporary directory
    And the sha256 of ~/.claude/.agenting-session-state.json and ~/.claude/.routing-approvals.json is recorded
    When the session-continuity hook handles a startup for session "real-state-probe"
    And "--record --mode manual --workflows on" is run for that session
    And the routing guard runs "--approve abc123" and then a Workflow call with model haiku and effort low
    Then both real files have the same sha256 as before
    And the temporary directory now holds .agenting-session-state.json and .routing-approvals.json

  @gap @wip
  # Backed by: @gap
  Scenario: The cache tripwire keeps its state file beside the hook and ignores AGENTING_STATE_DIR
    Given AGENTING_STATE_DIR points at an empty temporary directory
    When hooks/cache-tripwire.py writes its state
    Then the state file is hooks/.cache-tripwire-state.json next to the hook script
    And the temporary directory holds no .cache-tripwire-state.json

  @gap @wip
  # Backed by: @gap
  Scenario: With AGENTING_STATE_DIR unset the hooks keep their state in ~/.claude
    Given AGENTING_STATE_DIR is not set
    When the routing guard and the session-continuity hook resolve their state files
    Then the state files are ~/.claude/.agenting-session-state.json and ~/.claude/.routing-approvals.json

  @gap @wip
  # Backed by: @gap
  Scenario: An empty AGENTING_STATE_DIR is treated as unset
    Given AGENTING_STATE_DIR is set to the empty string
    When the routing guard resolves its state directory
    Then the state directory is ~/.claude

  @gap @wip
  # Backed by: @gap
  Scenario: The health check writes its probe sessions under AGENTING_STATE_DIR, not the real state
    Given AGENTING_STATE_DIR points at an empty temporary directory
    When "python3 scripts/check-setup.py" runs
    Then the temporary directory holds .agenting-session-state.json with the keys "setup-check-continuity" and "setup-check-auto-bypass"
    And ~/.claude/.agenting-session-state.json is not written by the probe sessions

  # --- Exit code and output shape ------------------------------------------

  @gap @wip
  # Backed by: @gap
  Scenario: A complete plugin installation exits 0 with a summary of zero failures
    Given CLAUDE_PLUGIN_ROOT is this repository, HOME is an empty temporary directory and AGENTING_STATE_DIR is a temporary directory
    When "python3 scripts/check-setup.py" runs
    Then the exit code is 0
    And a line matches "^  \d+ passed, 0 failed, 0 warnings$"
    And no line contains "FAILED:"

  @gap @wip
  # Backed by: @gap
  Scenario: A plugin root with nothing in it exits 1 and names every failed check
    Given CLAUDE_PLUGIN_ROOT is an empty directory and HOME is an empty directory
    When "python3 scripts/check-setup.py" runs
    Then the exit code is 1
    And the output contains "FAILED:" followed by "guard script found" and "session-continuity.py found"

  @gap @wip
  # Backed by: @gap
  Scenario: A WARN does not change the exit code
    Given HOME is an empty temporary directory
    And CLAUDE_PLUGIN_ROOT is a copy of the plugin whose agents/ all declare model sonnet and effort medium
    When "python3 scripts/check-setup.py" runs
    Then the output contains "WARN:" listing "a low-effort tier exists" and "more than one tier in use"
    And the exit code is 0

  @gap @wip
  # Backed by: @gap
  Scenario: Each check prints one status line and the detail only when it did not pass
    Given CLAUDE_PLUGIN_ROOT and HOME are both empty directories
    When "python3 scripts/check-setup.py" runs
    Then stdout contains the exact line "  [FAIL] guard script found  workflow-routing-guard.py missing"
    And given a full install instead, stdout contains the exact line "  [PASS] guard script found" with nothing after the name

  @gap @wip
  # Backed by: @gap
  Scenario: Colour codes are left out when stdout is not a terminal
    Given the health check output is piped to a file
    When "python3 scripts/check-setup.py" runs
    Then the output contains no ESC character

  # --- Routing guard section -----------------------------------------------

  @gap @wip
  # Backed by: @gap
  Scenario: The guard is found in the plugin copy before the user's copy
    Given hooks/workflow-routing-guard.py exists under both CLAUDE_PLUGIN_ROOT and ~/.claude/hooks
    And the stub under CLAUDE_PLUGIN_ROOT blocks an unrouted Workflow call at Stage 1
    And the stub under ~/.claude/hooks allows every call
    When "python3 scripts/check-setup.py" runs
    Then the check "blocks an UNROUTED agent() call" is PASS

  @gap @wip
  # Backed by: @gap
  Scenario: A missing guard fails "guard script found" and skips the guard probes
    Given neither CLAUDE_PLUGIN_ROOT/hooks nor ~/.claude/hooks holds workflow-routing-guard.py
    When "python3 scripts/check-setup.py" runs
    Then the check "guard script found" is FAIL
    And no "blocks an UNROUTED agent() call" line is printed
    And the check "guard executes without error" is not printed
    And no "passes through non-Workflow tools" line is printed

  @gap @wip
  # Backed by: @gap
  Scenario: An unrouted agent() call is reported as blocked at Stage 1
    Given the script "await agent('x', {schema:S})"
    When the health check feeds it to the routing guard as a Workflow call
    Then the guard's permissionDecisionReason contains "STAGE 1/2"
    And the check "blocks an UNROUTED agent() call" is PASS

  @gap @wip
  # Backed by: @gap
  Scenario: A call with model opus and no effort is reported as blocked at Stage 1
    Given the script "await agent('x', {model:'opus'})"
    When the health check feeds it to the routing guard as a Workflow call
    Then the guard's permissionDecisionReason contains "STAGE 1/2"
    And the check "blocks a call with model but NO effort" is PASS

  @gap @wip
  # Backed by: @gap
  Scenario: A fully routed call is reported as reaching Stage 2
    Given the script "await agent('x', {model:'haiku', effort:'low'})"
    When the health check feeds it to the routing guard as a Workflow call in session "setup-check"
    Then the guard's permissionDecisionReason contains "STAGE 2/2"
    And the check "asks approval for a fully ROUTED plan" is PASS

  @gap @wip
  # Backed by: @gap
  Scenario: agent( inside a string literal is ignored
    Given the script "const doc = 'call agent(p) to spawn'"
    When "python3 scripts/check-setup.py" runs
    Then the check "ignores agent( inside a string literal" is PASS

  @gap @wip
  # Backed by: @gap
  Scenario: The text "model: opus" inside a prompt is not mistaken for routing
    Given the script "await agent('explain model: opus', {schema:S})"
    When "python3 scripts/check-setup.py" runs
    Then the check "does not mistake 'model:' in prompt text for routing" is PASS

  @gap @wip
  # Backed by: @gap
  Scenario: The "// routing: inherit" comment moves an unrouted call on to Stage 2
    Given the script "// routing: inherit" on one line and "await agent('x',{schema:S})" on the next
    When "python3 scripts/check-setup.py" runs
    Then the check "honours the // routing: inherit escape hatch" is PASS

  @gap @wip
  # Backed by: @gap
  Scenario: The "passes through non-Workflow tools" check is a constant PASS once the guard is found
    Given the routing guard is found
    And the guard stub exits 1 on every input
    When "python3 scripts/check-setup.py" runs
    Then the check "passes through non-Workflow tools" is PASS

  # --- Hook wiring ---------------------------------------------------------

  # Backed by: tests/test_check_setup.py::test_should_pass_the_parse_check_when_there_is_no_settings_file
  Scenario: A missing user settings.json is not a failure
    Given HOME is an empty directory with no .claude/settings.json
    When "python3 scripts/check-setup.py" runs
    Then the check "settings.json parses" is PASS

  # Backed by: tests/test_check_setup.py::test_should_fail_the_parse_check_and_exit_1_when_settings_is_not_json
  Scenario: A settings.json that is not valid JSON fails "settings.json parses"
    Given ~/.claude/settings.json contains "{not json"
    When "python3 scripts/check-setup.py" runs
    Then the check "settings.json parses" is FAIL
    And the exit code is 1

  # Backed by: tests/test_check_setup.py::test_should_fail_the_parse_check_and_still_print_a_summary_when_settings_is_not_an_object
  # Backed by: tests/test_check_setup.py::test_should_keep_running_the_later_sections_when_settings_is_not_an_object
  Scenario: A settings.json holding valid JSON that is not an object fails "settings.json parses" and the run continues
    Given ~/.claude/settings.json contains "[]", "null" or "1"
    When "python3 scripts/check-setup.py" runs
    Then the check "settings.json parses" is FAIL with the detail "not a JSON object (list)", "(NoneType)" or "(int)"
    And no traceback is printed on stderr
    And the later sections still run and the summary line is printed
    And the exit code is 1

  # Backed by: tests/test_check_setup.py::test_should_count_a_hooks_list_as_not_registered_without_crashing
  # Backed by: tests/test_check_setup.py::test_should_count_none_as_registered_when_every_entry_has_the_wrong_shape
  # Backed by: tests/test_check_setup.py::test_should_register_the_guard_when_a_valid_entry_sits_beside_bad_ones
  Scenario: Wrong-shaped hooks entries in settings.json are ignored instead of crashing the registration lookup
    Given ~/.claude/settings.json has "hooks" as a list, or a PreToolUse group that is a string, or a group whose "hooks" is not a list, or a hook entry that is not an object, or a "command" that is not a string
    And CLAUDE_PLUGIN_ROOT has no hooks/hooks.json
    When "python3 scripts/check-setup.py" runs
    Then no traceback is printed and the summary line is printed
    And such an entry does not count as registered, so "guard registered on PreToolUse" is FAIL with the detail "not registered anywhere"
    And a well-formed workflow-routing-guard command next to the bad entries still registers the guard

  # Backed by: tests/test_check_setup.py::test_should_not_crash_and_fall_back_to_the_plugin_hooks_json_when_a_group_is_a_string
  Scenario: A wrong-shaped settings.json entry does not hide the plugin's own hooks.json
    Given ~/.claude/settings.json has a PreToolUse group that is the string "workflow-routing-guard"
    And CLAUDE_PLUGIN_ROOT has hooks/hooks.json
    When "python3 scripts/check-setup.py" runs
    Then "guard registered on PreToolUse" is PASS
    And the summary line is printed

  @gap @wip
  # Backed by: @gap
  Scenario: The guard counts as registered when hooks/hooks.json exists
    Given CLAUDE_PLUGIN_ROOT/hooks/hooks.json exists, even when it does not name workflow-routing-guard
    And ~/.claude/settings.json registers no hook
    When "python3 scripts/check-setup.py" runs
    Then the check "guard registered on PreToolUse" is PASS

  @gap @wip
  # Backed by: @gap
  Scenario: The guard is not registered anywhere
    Given no hooks/hooks.json under CLAUDE_PLUGIN_ROOT and no workflow-routing-guard entry under PreToolUse in settings.json
    When "python3 scripts/check-setup.py" runs
    Then the check "guard registered on PreToolUse" is FAIL with the detail "not registered anywhere"

  @gap @wip
  # Backed by: @gap
  Scenario: The guard must exit 0 on a non-Workflow tool call
    Given a Bash tool call with the command "true" in session "setup-check"
    When the health check pipes it to the guard
    Then the guard exits 0
    And the check "guard executes without error" is PASS

  # --- Agents and skill ----------------------------------------------------

  @gap @wip
  # Backed by: @gap
  Scenario: An agent file without effort in its front matter fails the agent check
    Given an agents directory holding a file whose front matter has "name" and "model" but no "effort"
    When "python3 scripts/check-setup.py" runs
    Then the check "every agent declares model AND effort" is FAIL
    And its detail lists "<file>.md:effort"

  @gap @wip
  # Backed by: @gap
  Scenario: The same agent file name in two directories is counted once
    Given agents/sonnet-low.md exists under both CLAUDE_PLUGIN_ROOT and ~/.claude/agents
    When "python3 scripts/check-setup.py" runs
    Then the count line "unique agent(s)" counts sonnet-low.md once

  @gap @wip
  # Backed by: @gap
  Scenario: No agent at low effort is a WARN, not a FAIL
    Given every agent definition declares effort medium or higher
    When "python3 scripts/check-setup.py" runs
    Then the check "a low-effort tier exists" is WARN

  @gap @wip
  # Backed by: @gap
  Scenario: The skill must document upgrades as well as downgrades
    Given skills/agenting/SKILL.md that contains "cheaper" but neither "higher quality" nor "upgrade"
    When "python3 scripts/check-setup.py" runs
    Then the check "skill documents both routing directions" is FAIL

  @gap @wip
  # Backed by: @gap
  Scenario: A missing skills/agenting/SKILL.md fails its check and skips the direction check
    Given neither CLAUDE_PLUGIN_ROOT/skills/agenting/SKILL.md nor ~/.claude/skills/agenting/SKILL.md exists
    When "python3 scripts/check-setup.py" runs
    Then the check "agenting SKILL.md present" is FAIL
    And the check "skill documents both routing directions" is not printed

  # --- Session continuity section ------------------------------------------

  @gap @wip
  # Backed by: @gap
  Scenario: An unseen session id is seeded with a one-line [agenting] status that never asks
    Given session "setup-check-continuity" has no entry in the state file
    When the health check pipes a SessionStart with source startup to session-continuity.py
    Then additionalContext starts with "[agenting] mode=auto"
    And additionalContext contains no newline and no "AskUserQuestion"
    And the check "silently seeds an unseen session_id (never asks)" is PASS

  @gap @wip
  # Backed by: @gap
  Scenario: The seeded disposition is balanced before any record call
    Given session "setup-check-continuity" has just been seeded by a SessionStart with source startup
    When session-continuity.py runs with "--status --session setup-check-continuity"
    Then the state file entry for "setup-check-continuity" has disposition "balanced"
    And stdout is exactly "session setup-check-continuity: mode=auto · disposition=balanced · workflows=not opted in"
    And stdout does not contain "no state recorded"

  @gap @wip
  # Backed by: @gap
  Scenario: Recording manual, quality and workflows on is reported back
    Given session "setup-check-continuity" exists
    When session-continuity.py runs with "--record --mode manual --disposition quality --workflows on"
    Then the exit code is 0
    And stdout contains "mode=manual", "disposition=quality" and "workflows=on"
    And the check "--record persists mode, disposition and the workflows opt-in" is PASS

  @gap @wip
  # Backed by: @gap
  Scenario: A compact SessionStart carries recorded state across compaction
    Given the session record is mode manual, disposition quality, workflows on
    When "python3 scripts/check-setup.py" pipes a SessionStart with source compact for that session
    Then the check "carries recorded state across compaction, still never asks" is PASS

  @gap @wip
  # Backed by: @gap
  Scenario: A clear SessionStart on the same session id does not inherit the recorded state
    Given the session record is mode manual, disposition quality, workflows on
    When "python3 scripts/check-setup.py" pipes a SessionStart with source clear for that session
    Then the check "/clear does not inherit prior state onto the same session_id" is PASS

  @gap @wip
  # Backed by: @gap
  Scenario: Re-running the health check does not inherit probe state from an interrupted run
    Given a state file seeded by the test with a "setup-check-continuity" entry at mode manual, as an interrupted run would leave
    When "python3 scripts/check-setup.py" runs
    Then the check "silently seeds an unseen session_id (never asks)" is PASS
    And the state file no longer carries mode manual for "setup-check-continuity" after the run

  @gap @wip
  # Backed by: @gap
  Scenario: A missing session-continuity.py fails its check
    Given neither CLAUDE_PLUGIN_ROOT/hooks nor ~/.claude/hooks holds session-continuity.py
    When "python3 scripts/check-setup.py" runs
    Then the check "session-continuity.py found" is FAIL
    And none of the session-continuity probe checks are printed
    And none of the four "auto-mode Stage 2 bypass" checks are printed
    And "registered on SessionStart in hooks.json" is still evaluated when hooks/hooks.json exists

  @gap @wip
  # Backed by: @gap
  Scenario: A hooks.json with no SessionStart entry for session-continuity fails registration
    Given CLAUDE_PLUGIN_ROOT/hooks/hooks.json has no SessionStart command naming "session-continuity"
    When "python3 scripts/check-setup.py" runs
    Then the check "registered on SessionStart in hooks.json" is FAIL

  # --- Guard auto-mode bypass section --------------------------------------

  @gap @wip
  # Backed by: @gap
  Scenario: A session with no recorded mode still gets a Stage 2 deny
    Given session "setup-check-auto-bypass" has no record and no approval
    When a Workflow call with model haiku and effort low reaches the guard
    Then the guard's permissionDecision is "deny"

  @gap @wip
  # Backed by: @gap
  Scenario: Mode manual does not get the Stage 2 bypass
    Given session "setup-check-auto-bypass" is recorded with mode manual
    When a Workflow call with model haiku and effort low reaches the guard
    Then the guard's permissionDecision is "deny"

  @gap @wip
  # Backed by: @gap
  Scenario: Mode auto bypasses Stage 2 with a systemMessage and no permissionDecision
    Given session "setup-check-auto-bypass" is recorded with mode auto
    When a Workflow call with model haiku and effort low reaches the guard
    Then the output JSON has a "systemMessage" and no hookSpecificOutput.permissionDecision

  @gap @wip
  # Backed by: @gap
  Scenario: Mode auto still denies an unrouted call at Stage 1
    Given session "setup-check-auto-bypass" is recorded with mode auto
    When the Workflow script "await agent('x', {schema:S})" reaches the guard
    Then the guard's permissionDecision is "deny"

  # --- Rename integrity section --------------------------------------------

  @gap @wip
  # Backed by: @gap
  Scenario: A missing command file fails its existence check
    Given CLAUDE_PLUGIN_ROOT/commands has no agenting-mode.md
    When "python3 scripts/check-setup.py" runs
    Then the check "command /agenting-mode exists" is FAIL

  @gap @wip
  # Backed by: @gap
  Scenario: The old plugin id "agent-routing" in a scanned directory or a top-level file fails the rename check
    Given CLAUDE_PLUGIN_ROOT/README.md contains the text "agent-routing"
    And features/, tests/, docs/ and evals/ under CLAUDE_PLUGIN_ROOT also contain "agent-routing"
    And CHANGELOG.md and AGENTING-PLAN-HANDOFF.md contain "agent-routing"
    When "python3 scripts/check-setup.py" runs
    Then the check 'no stale "agent-routing" string survives the rename' is FAIL
    And its detail names README.md
    And its detail names nothing under features/, tests/, docs/ or evals/ and neither CHANGELOG.md nor AGENTING-PLAN-HANDOFF.md

  @gap @wip
  # Backed by: @gap
  Scenario: Pre-2.1.0 phrasing such as "conversational memory only" outside the exempt files fails the check
    Given a file under CLAUDE_PLUGIN_ROOT/skills contains "conversational memory only"
    When "python3 scripts/check-setup.py" runs
    Then the check 'no pre-2.1.0 "conversational memory only" / "resets to manual" phrasing survives' is FAIL
    And its detail reads "still present in: " followed by "<relative path>: 'conversational memory only'"

  @gap @wip
  # Backed by: @gap
  Scenario: Pre-3.0.0 vocabulary such as "semi-auto" outside the exempt files fails the check
    Given a file under CLAUDE_PLUGIN_ROOT/skills contains "semi-auto"
    When "python3 scripts/check-setup.py" runs
    Then the check "no pre-3.0.0 semi-auto / suggestion / log.csv vocabulary survives" is FAIL

  @gap @wip
  # Backed by: @gap
  Scenario: The AGENTING.md template must carry its Rules and Config sections
    Given templates/AGENTING.md contains no occurrence of the text "## Config"
    When "python3 scripts/check-setup.py" runs
    Then the check "templates/AGENTING.md carries its Rules and Config sections" is FAIL
    And its detail is "missing: ## Config"

  @gap @wip
  # Backed by: @gap
  Scenario: A missing templates/AGENTING.md fails the template check
    Given CLAUDE_PLUGIN_ROOT/templates/AGENTING.md does not exist
    When "python3 scripts/check-setup.py" runs
    Then the check "templates/AGENTING.md carries its Rules and Config sections" is FAIL
    And its detail is "<path to templates/AGENTING.md> missing"

  @gap @wip
  # Backed by: @gap
  Scenario: The Stage 2 message names the running guard's own path for --approve
    Given the routed script "await agent('x', {model:'haiku', effort:'low'})" in session "rename-check"
    When the health check reads the Stage 2 permissionDecisionReason
    Then it contains the absolute path of the guard that ran
    And it does not contain "~/.claude/hooks/workflow-routing-guard.py --approve"

  # --- The /agenting-check command -----------------------------------------

  @gap @wip
  # Backed by: @gap
  Scenario: /agenting-check runs the script from the plugin root and never aborts on a failing exit code
    Given commands/agenting-check.md
    When Claude Code expands the command
    Then the shell line is 'python3 "${CLAUDE_PLUGIN_ROOT}/scripts/check-setup.py" 2>&1 || true'
    And the allowed-tools front matter is "Bash(python3:*)"
