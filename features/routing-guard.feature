Feature: The Workflow routing gate denies unrouted agent() calls and asks for plan approval in manual mode
  The routing guard (hooks/workflow-routing-guard.py) is a PreToolUse hook on Workflow: Stage 1 denies any agent() call with no model/agentType or no effort, and Stage 2 asks the user to approve the routing plan in manual mode while stepping aside with a system message in auto mode.

  # ---------------------------------------------------------------- wiring

  @gap @wip
  # Backed by: @gap
  Scenario: The guard is wired as a PreToolUse hook with matcher Workflow
    Given hooks/hooks.json
    When the PreToolUse entries are read
    Then exactly one entry has matcher "Workflow"
    And its command runs python3 on "${CLAUDE_PLUGIN_ROOT}/hooks/workflow-routing-guard.py" with timeout 10

  # ---------------------------------------------------------------- pass-through

  # Backed by: tests/test_routing_guard.py::test_non_workflow_tool_is_silent
  Scenario: A tool other than Workflow gets no output
    Given a PreToolUse payload for tool "Bash" whose script holds an unrouted agent() call
    When the routing guard runs
    Then the exit code is 0
    And stdout is empty

  # Backed by: tests/test_routing_guard.py::test_agent_inside_string_is_ignored
  Scenario: The word agent( inside a string literal is not a call
    Given a Workflow script "const doc = 'call agent(p) to spawn'"
    When the routing guard runs
    Then stdout is empty

  @gap @wip
  # Backed by: @gap
  Scenario: An agent( call inside a comment is not a call
    Given a Workflow script whose only agent( text sits in a "//" comment and a "/* */" comment
    When the routing guard runs
    Then stdout is empty

  @gap @wip
  # Backed by: @gap
  Scenario: A method call named agent is not counted as a call site
    Given a Workflow script "await client.agent('x', {schema:S})"
    When the routing guard runs
    Then stdout is empty

  @gap @wip
  # Backed by: @gap
  Scenario: A script with no agent() calls gets no output
    Given a Workflow script "const n = 1 + 1"
    When the routing guard runs
    Then stdout is empty

  # Backed by: tests/test_routing_guard.py::test_malformed_input_is_silent
  Scenario: Stdin that is not JSON is silent and exits 0
    Given stdin "{not json"
    When the routing guard runs
    Then the exit code is 0
    And stdout is empty

  @gap @wip
  # Backed by: @gap
  Scenario: A script that cannot be inspected is not blocked
    Given a Workflow payload whose scriptPath points at a file that does not exist
    When the routing guard runs
    Then the exit code is 0
    And stdout is empty

  @gap @wip
  # Backed by: @gap
  Scenario: A named workflow with no script text is not blocked
    Given a Workflow payload whose tool_input is {"name": "recon"} with no script and no scriptPath
    When the routing guard runs
    Then the exit code is 0
    And stdout is empty

  @gap @wip
  # Backed by: @gap
  Scenario: A script given by scriptPath is inspected like an inline script
    Given a Workflow payload whose scriptPath points at a readable file holding "await agent('x', {schema:S})"
    When the routing guard runs
    Then permissionDecision is "deny"
    And the reason contains "STAGE 1/2"
    And the reason contains "scriptPath"

  # ---------------------------------------------------------------- Stage 1

  # Backed by: tests/test_routing_guard.py::test_unrouted_call_is_denied
  Scenario: A call with no model and no effort is denied at Stage 1
    Given a Workflow script "await agent('x', {schema:S})"
    When the routing guard runs
    Then permissionDecision is "deny"
    And the reason contains "STAGE 1/2"
    And the reason points the writer to the agenting skill

  # Backed by: tests/test_routing_guard.py::test_model_without_effort_is_denied
  Scenario: A call with a model but no effort is denied at Stage 1
    Given a Workflow script "await agent('x', {model:'opus'})"
    When the routing guard runs
    Then the reason contains "STAGE 1/2"

  # Backed by: tests/test_routing_guard.py::test_plugin_agent_type_without_effort_is_denied
  Scenario: A call with an agentType but no effort is denied at Stage 1
    Given a Workflow script "await agent('x', {agentType:'agenting:scanner'})"
    When the routing guard runs
    Then the reason contains "STAGE 1/2"

  # Backed by: tests/test_routing_guard.py::test_model_word_inside_prompt_is_not_routing
  Scenario: The word model inside the prompt text is not routing
    Given a Workflow script "await agent('model: opus', {schema:S})"
    When the routing guard runs
    Then the reason contains "STAGE 1/2"

  # Backed by: tests/test_routing_guard.py::test_routing_keys_before_a_nested_schema_pass_stage_one
  Scenario: Routing keys before a nested schema object pass Stage 1
    Given a Workflow script "await agent('x', {model:'haiku', effort:'low', schema:{type:'object', properties:{ok:{type:'boolean'}}}})"
    When the routing guard runs
    Then the reason contains "STAGE 2/2" and not "STAGE 1/2"

  # Backed by: tests/test_routing_guard.py::test_routing_keys_after_a_nested_schema_pass_stage_one
  Scenario: Routing keys after a nested schema object pass Stage 1
    Given a Workflow script "await agent('x', {schema:{type:'object', properties:{ok:{type:'boolean'}}}, model:'haiku', effort:'low'})"
    When the routing guard runs
    Then the reason does not contain "STAGE 1/2"

  # Backed by: tests/test_routing_guard.py::test_options_spread_over_lines_with_a_nested_schema_pass_stage_one
  Scenario: Options spread over several lines with a nested schema pass Stage 1 and the plan names the model
    Given a Workflow script whose agent() options span several lines with label, model, effort and a nested schema
    When the routing guard runs
    Then the reason contains "STAGE 2/2" and "haiku"

  # Backed by: tests/test_routing_guard.py::test_a_nested_schema_on_both_sides_of_the_routing_keys_passes_stage_one
  Scenario: A nested object on both sides of the routing keys passes Stage 1
    Given a Workflow script whose options hold a nested object, then model and effort, then another nested object
    When the routing guard runs
    Then the reason does not contain "STAGE 1/2"

  # Backed by: tests/test_routing_guard.py::test_model_and_effort_keys_inside_a_nested_object_are_not_routing
  Scenario: Model and effort keys inside a nested object are not routing
    Given Workflow scripts "await agent('x', {schema:{model:'x', effort:'y'}})" and "await agent('x', {opts:{model:'haiku', effort:'low'}})"
    When the routing guard runs on each
    Then each reason contains "STAGE 1/2"

  # Backed by: tests/test_routing_guard.py::test_the_tiers_in_the_plan_come_from_the_top_level_keys
  Scenario: The plan lists the top-level model and effort, not same-named keys inside a schema
    Given the session record for "guard-test-session" has mode manual
    And a Workflow script whose options are {schema:{properties:{model:'opus', effort:'low'}}, model:'sonnet', effort:'high'}
    When the routing guard runs
    Then the reason contains "STAGE 2/2" and the plan signature "sonnet/highx1"

  # Backed by: tests/test_routing_guard.py::test_an_object_in_the_prompt_expression_is_not_the_options
  Scenario: An object literal inside the prompt expression is not the options object
    Given Workflow scripts "await agent(build({a:1}), {model:'haiku', effort:'low'})" and "await agent(build({model:'haiku', effort:'low'}), {schema:S})"
    When the routing guard runs on each
    Then the first does not reach "STAGE 1/2" and the second is denied at "STAGE 1/2"

  # Backed by: tests/test_routing_guard.py::test_the_options_are_the_last_top_level_object_of_the_call
  Scenario: The options are the last top-level object argument of the call
    Given Workflow scripts "await agent({a:1}, {model:'haiku', effort:'low'})" and "await agent({model:'haiku', effort:'low'}, {schema:S})"
    When the routing guard runs on each
    Then the first does not reach "STAGE 1/2" and the second is denied at "STAGE 1/2"

  # Backed by: tests/test_routing_guard.py::test_a_name_inside_a_value_expression_is_not_a_key
  Scenario: A variable named model inside a value expression is not a model key
    Given a Workflow script "await agent('x', {effort: pick ? model : 'low', schema:S})"
    When the routing guard runs
    Then the reason contains "STAGE 1/2"

  # Backed by: tests/test_routing_guard.py::test_a_repeated_key_takes_the_last_value_as_javascript_does
  Scenario: A repeated key takes its last value, as JavaScript does
    Given the session record for "guard-test-session" has mode manual
    And a Workflow script "await agent('x', {model:'haiku', model:'opus', effort:'low'})"
    When the routing guard runs
    Then the plan signature is "opus/lowx1"

  # Backed by: tests/test_routing_guard.py::test_options_passed_as_a_variable_are_not_inspected_and_are_unrouted
  Scenario: Options passed as a variable cannot be inspected and are treated as unrouted
    Given a Workflow script "await agent('x', opts)"
    When the routing guard runs
    Then the reason contains "STAGE 1/2"

  # Backed by: tests/test_routing_guard.py::test_an_effort_without_a_model_is_reported_as_no_model
  Scenario: A call with an effort but no model is reported as "no model"
    Given a Workflow script "await agent('x', {effort:'low', schema:S})"
    When the routing guard runs
    Then the reason contains "line    1  [no model]"
    And the reason does not contain "no effort"

  # Backed by: tests/test_routing_guard.py::test_routing_inside_a_spread_is_named_in_the_stage_one_cause
  Scenario: Routing inside a spread is named in the Stage 1 cause, with the explicit-keys fix
    Given a Workflow script whose line 2 is "await pipeline(LENSES, (lens) => agent(lens.prompt, { label: `inspect:${lens.key}`, phase: 'Inspect', schema: CLAIMS, ...lens.route }))"
    When the routing guard runs
    Then the reason contains "STAGE 1/2"
    And the reason contains "line    2  [no model, no effort; the guard cannot read ...lens.route]"
    And the reason contains "agentType: lens.agentType, model: lens.model, effort: lens.effort"

  # Backed by: tests/test_routing_guard.py::test_a_spread_inside_a_nested_object_is_not_named
  Scenario: A spread inside a nested object is not named as routing
    Given a Workflow script "await agent('x', {schema: {...base, type:'object'}})"
    When the routing guard runs
    Then the reason contains "line    1  [no model, no effort]"
    And the reason does not contain "cannot read"

  # Backed by: tests/test_routing_guard.py::test_explicit_routing_keys_pass_stage_one_next_to_a_spread
  Scenario: Explicit routing keys pass Stage 1 next to a spread, before or after it
    Given Workflow scripts "await agent('x', {...common, model:'haiku', effort:'low'})" and "await agent('x', {model:'haiku', effort:'low', ...extra})"
    When the routing guard runs on each
    Then neither reason contains "STAGE 1/2"

  # Backed by: tests/test_routing_guard.py::test_a_literal_undefined_or_null_value_is_not_routing
  Scenario: A key whose value is the literal undefined or null is not routing
    Given Workflow scripts "await agent('x', {model: undefined, effort:'low'})" and one whose options span lines with "model: 'haiku'" and "effort: null"
    When the routing guard runs on each
    Then the first reason contains "line    1  [model is undefined]"
    And the second reason contains "line    1  [effort is null]"
    And "await agent('x', {model: undefined ?? 'haiku', effort:'low'})" does not reach "STAGE 1/2"

  # Backed by: tests/test_routing_guard.py::test_an_agent_type_beside_model_undefined_passes_stage_one
  Scenario: An agentType passes Stage 1 beside model: undefined
    Given a Workflow script "await agent('x', {agentType:'agenting:researcher', model: undefined, effort:'medium'})"
    When the routing guard runs
    Then the reason contains "STAGE 2/2"
    And the reason contains "agent:agenting:researcher"

  # Backed by: tests/test_routing_guard.py::test_every_spread_is_named_and_nothing_after_it_leaks_in
  Scenario: Every top-level spread is named, and the key after a spread is not part of its name
    Given a Workflow script "await agent('x', {...a, schema: S, ...b})"
    When the routing guard runs
    Then the reason contains "line    1  [no model, no effort; the guard cannot read ...a, ...b]"

  # Backed by: tests/test_routing_guard.py::test_a_spread_name_drops_a_trailing_comment_and_is_capped
  Scenario: A spread's name drops a trailing comment and is capped at 40 characters
    Given a Workflow script whose options are "...lens.route // per-lens routing" on a line of their own
    And a Workflow script whose options spread a call with twelve arguments
    When the routing guard runs on each
    Then the first reason contains "[no model, no effort; the guard cannot read ...lens.route]"
    And the second names the spread's start, ends it with "…" and keeps it within 40 characters after "..."

  # Backed by: tests/test_routing_guard.py::test_a_destructured_fan_out_forwarding_shorthand_keys_passes_stage_one
  Scenario: A destructured fan-out that forwards shorthand model and effort keys passes Stage 1
    Given the session record for "guard-test-session" has mode manual
    And a Workflow script "await pipeline(LENSES, ({prompt, model, effort}) => agent(prompt, {label: 'l', model, effort}))"
    When the routing guard runs
    Then the reason contains "STAGE 2/2"
    And the reason contains "Plan signature: ?/?x1"
    # {model, effort} is {model: model, effort: effort}: presence only, like any variable value.

  # Backed by: tests/test_routing_guard.py::test_shorthand_and_explicit_keys_mix_and_a_spread_is_not_blamed
  Scenario: Shorthand and explicit routing keys mix, on one line or several, and a spread beside them is not blamed
    Given Workflow scripts "await agent('x', {model, effort: 'low'})", "await agent('x', {agentType: 'agenting:scanner', effort})", "await agent('x', {model, effort, ...extra})" and one whose options hold "model," and "effort" on lines of their own
    When the routing guard runs on each
    Then each reason contains "STAGE 2/2"
    And no reason contains "cannot read"

  # Backed by: tests/test_routing_guard.py::test_a_shorthand_name_that_is_not_a_routing_key_is_still_unrouted
  Scenario: A shorthand key that is not model, agentType or effort is not routing
    Given a Workflow script "await agent('x', {label, schema})"
    When the routing guard runs
    Then the reason contains "line    1  [no model, no effort]"

  # Backed by: tests/test_routing_guard.py::test_unrouted_is_denied_even_in_auto_mode
  Scenario: Stage 1 is denied even when the session is in mode auto
    Given the session record for "guard-test-session" has mode auto
    And a Workflow script "await agent('x', {schema:S})"
    When the routing guard runs
    Then permissionDecision is "deny"
    And the reason contains "STAGE 1/2"

  # Backed by: tests/test_routing_guard.py::test_escape_hatch_counts_as_routed
  Scenario: A "routing: inherit" comment on the line above counts as routed
    Given a Workflow script "// routing: inherit" followed by "await agent('x', {schema:S})" on the next line
    When the routing guard runs
    Then the reason contains "STAGE 2/2"

  @gap @wip
  # Backed by: @gap
  Scenario: A "routing: inherit" comment on the same line counts as routed
    Given a Workflow script "await agent('x', {schema:S}) // routing: inherit"
    When the routing guard runs
    Then the reason contains "STAGE 2/2"
    And the plan table lists one call site at model "inherit" with effort "inherit"

  @gap @wip
  # Backed by: @gap
  Scenario: A "routing: inherit" comment two lines above does not excuse the call
    Given a Workflow script "// routing: inherit", a blank line, then "await agent('x', {schema:S})"
    When the routing guard runs
    Then the reason contains "STAGE 1/2"

  # Backed by: tests/test_routing_guard.py::test_stage_one_reports_each_unrouted_call_by_line_and_cause
  Scenario: Stage 1 reports each unrouted call by line number and cause
    Given a Workflow script whose line 1 is "const a = 1", line 2 is "await agent('x', {schema:S})" and line 3 is "await agent('y', {model:'opus'})"
    When the routing guard runs
    Then the reason contains "line    2  [no model, no effort]"
    And the reason contains "line    3  [no effort]"
    And the reason contains "2 agent() call(s) specify no model/effort"

  @gap @wip
  # Backed by: @gap
  Scenario: One unrouted call among routed calls still denies at Stage 1
    Given a Workflow script with 3 calls routed to {model:'haiku', effort:'low'} and 1 call with {schema:S}
    When the routing guard runs
    Then the reason contains "STAGE 1/2"
    And the reason contains "1 agent() call(s) specify no model/effort"

  @gap @wip
  # Backed by: @gap
  Scenario: Stage 1 lists at most 12 unrouted calls and counts the rest
    Given a Workflow script with 15 calls of "await agent('x', {schema:S})"
    When the routing guard runs
    Then the reason contains "15 agent() call(s) specify no model/effort"
    And the reason contains "… and 3 more"

  @gap @wip
  # Backed by: @gap
  Scenario: The Stage 1 denial carries a visible system message
    Given a Workflow script "await agent('x', {schema:S})"
    When the routing guard runs
    Then systemMessage is "Workflow stopped (1/2): 1 agent() call(s) have no routing."

  # ---------------------------------------------------------------- agentType form

  # Backed by: tests/test_routing_guard.py::test_prefixed_agent_type_passes_stage_one
  Scenario: A prefixed agentType with an effort passes Stage 1 and is listed as agent:<type>
    Given a Workflow script "await agent('trace it', {agentType:'agenting:researcher', effort:'medium'})"
    And no mode is recorded for the session
    When the routing guard runs
    Then the reason contains "STAGE 2/2"
    And the reason contains "agent:agenting:researcher"

  # Backed by: tests/test_routing_guard.py::test_prefixed_agent_type_runs_in_auto_mode
  Scenario: A prefixed agentType with an effort runs in mode auto
    Given the session record for "guard-test-session" has mode auto
    And a Workflow script "await agent('trace it', {agentType:'agenting:researcher', effort:'medium'})"
    When the routing guard runs
    Then there is no permissionDecision
    And the output has a systemMessage

  @gap @wip
  # Backed by: @gap
  Scenario: An agentType without the agenting prefix also counts as routed
    Given a Workflow script "await agent('x', {agentType:'custom-reviewer', effort:'low'})"
    When the routing guard runs
    Then the reason contains "STAGE 2/2"
    And the reason contains "agent:custom-reviewer"

  # ---------------------------------------------------------------- Stage 2, manual mode

  # Backed by: tests/test_routing_guard.py::test_missing_state_requires_approval
  Scenario: A fully routed plan with no recorded mode is denied at Stage 2
    Given a Workflow script "await agent('x', {model:'haiku', effort:'low'})"
    And the state directory holds no session record
    When the routing guard runs
    Then permissionDecision is "deny"
    And the reason contains "STAGE 2/2"

  # Backed by: tests/test_routing_guard.py::test_manual_requires_approve_then_passes
  Scenario: The --approve command in the denial records the plan and the next run is silent
    Given the session record for "guard-test-session" has mode manual
    And a routed Workflow script "await agent('x', {model:'haiku', effort:'low'})" was denied at Stage 2
    When the printed command 'python3 "<guard path>" --approve <plan hash> --session guard-test-session' is run
    Then its exit code is 0
    And the file ".routing-approvals.json" exists in the state directory
    And running the guard on the same script again produces empty stdout

  @gap @wip
  # Backed by: @gap
  Scenario: The --approve command prints a one-line confirmation
    Given a state directory with no approvals
    When the guard is run with "--approve abc123def456 --session s1"
    Then stdout is "approved: plan abc123def456 (session s1)"
    And the exit code is 0

  @gap @wip
  # Backed by: @gap
  Scenario: Recording the same approval twice stores it once
    Given the guard was run with "--approve abc123def456 --session s1"
    When the guard is run again with "--approve abc123def456 --session s1"
    Then ".routing-approvals.json" lists "abc123def456" once under "s1"

  @gap @wip
  # Backed by: @gap
  Scenario: Approval without --session is recorded under the session "unknown"
    Given a state directory with no approvals
    When the guard is run with "--approve abc123def456"
    Then stdout is "approved: plan abc123def456 (session unknown)"
    And ".routing-approvals.json" has the key "unknown"

  @gap @wip
  # Backed by: @gap
  Scenario: An approval is scoped to the session it was recorded for
    Given the plan hash of "await agent('x', {model:'haiku', effort:'low'})" is approved for session "s1"
    And no mode is recorded for session "s2"
    When the routing guard runs for session "s2" on that script
    Then permissionDecision is "deny"
    And the reason contains "STAGE 2/2"

  @gap @wip
  # Backed by: @gap
  Scenario: Only the last 20 session keys in the approvals file are kept
    Given ".routing-approvals.json" holds approvals for 20 sessions "s1" to "s20"
    When the guard is run with "--approve abc123def456 --session s21"
    Then ".routing-approvals.json" has 20 keys
    And "s1" is no longer a key and "s21" is

  @gap @wip
  # Backed by: @gap
  Scenario: A corrupt approvals file is treated as no approvals
    Given ".routing-approvals.json" holds "{not json"
    And the session record for "guard-test-session" has mode manual
    When the routing guard runs on "await agent('x', {model:'haiku', effort:'low'})"
    Then the reason contains "STAGE 2/2"

  # Backed by: tests/test_routing_guard.py::test_changed_plan_asks_again
  Scenario: Changing a tier after approval asks again
    Given the session record for "guard-test-session" has mode manual
    And the plan "await agent('x', {model:'haiku', effort:'low'})" is approved
    When the script changes to "await agent('x', {model:'opus', effort:'xhigh'})"
    Then the reason contains "STAGE 2/2"

  @gap @wip
  # Backed by: @gap
  Scenario: The plan hash does not depend on the order of the calls
    Given the session record for "guard-test-session" has mode manual
    And "await agent('a', {model:'haiku', effort:'low'}); await agent('b', {model:'opus', effort:'high'})" is approved
    When the guard runs on the same two calls in the opposite order
    Then stdout is empty

  # Backed by: tests/test_routing_guard.py::test_plan_counts_call_sites_and_says_runs_can_be_more
  Scenario: The manual plan counts call sites and says runs can be more
    Given the session record for "guard-test-session" has mode manual
    And a Workflow script with two agent() call sites inside one pipeline() call
    When the routing guard runs
    Then the reason contains "2 agent() call sites"
    And the reason contains "not runs"
    And the reason does not contain "agents total"

  @gap @wip
  # Backed by: @gap
  Scenario: The manual plan table groups call sites by model and effort and lists the larger group first
    Given the session record for "guard-test-session" has mode manual
    And a Workflow script with 2 calls at {model:'opus', effort:'high'} and 1 call at {model:'haiku', effort:'low'}
    When the routing guard runs
    Then the reason contains "Plan signature: haiku/lowx1|opus/highx2"
    And the table row with 2 call sites is listed before the row with 1 call site

  # Backed by: tests/test_routing_guard.py::test_deny_names_why_it_is_asking
  Scenario: The Stage 2 denial states why it is asking
    Given the session record for "guard-test-session" has mode manual
    And no mode is recorded for session "never-seen"
    When the routing guard runs on a routed script for each session
    Then the reason for "guard-test-session" contains "mode is manual"
    And the reason for "never-seen" contains "no agenting mode is recorded"

  # Backed by: tests/test_routing_guard.py::test_legacy_semi_auto_is_treated_as_manual
  Scenario: The legacy mode semi-auto still asks for approval
    Given the session record for "guard-test-session" has mode "semi-auto"
    When the routing guard runs on a routed script
    Then permissionDecision is "deny"
    And the reason contains "STAGE 2/2"

  @gap @wip
  # Backed by: @gap
  Scenario: The Stage 2 denial carries a visible system message
    Given the session record for "guard-test-session" has mode manual
    When the routing guard runs on one routed call site
    Then systemMessage is "Workflow stopped (2/2): a routing plan with 1 agent() call site is awaiting approval."

  @gap @wip
  # Backed by: @gap
  Scenario: A corrupt session state file makes the guard ask
    Given ".agenting-session-state.json" holds "{not json"
    When the routing guard runs on a routed script
    Then the reason contains "STAGE 2/2"
    And the reason contains "no agenting mode is recorded"

  # ---------------------------------------------------------------- Stage 2, auto mode

  # Backed by: tests/test_routing_guard.py::test_auto_drops_stage_two_with_system_message_only
  Scenario: Mode auto steps aside with a system message and no permission opinion
    Given the session record for "guard-test-session" has mode auto
    When the routing guard runs on a routed script
    Then the output has a systemMessage
    And the output has no hookSpecificOutput
    And the output text does not contain "permissionDecision"

  # Backed by: tests/test_routing_guard.py::test_auto_note_counts_call_sites_not_agents
  Scenario: The auto note counts a call inside a loop as one call site
    Given the session record for "guard-test-session" has mode auto
    And a script with one agent() call inside a for loop and one agent() call after it
    When the routing guard runs
    Then the systemMessage contains "2 agent() call sites"
    And the systemMessage does not contain "2 agents"
    And the output has no hookSpecificOutput

  @gap @wip
  # Backed by: @gap
  Scenario: The auto note names the plan hash and says the user's own permission settings still apply
    Given the session record for "guard-test-session" has mode auto
    When the routing guard runs on one routed call site
    Then the systemMessage contains "Workflow routing auto-approved (1 agent() call site, auto mode, plan "
    And the systemMessage contains "Your own Claude Code permission settings, if any, still apply"

  # Backed by: tests/test_routing_guard.py::test_seeded_session_is_auto
  Scenario: A session seeded by the SessionStart hook is in mode auto
    Given the SessionStart hook ran for "guard-test-session" with source startup
    When the routing guard runs on a routed script
    Then the output has no hookSpecificOutput

  # Backed by: tests/test_routing_guard.py::test_auto_for_another_session_does_not_leak
  Scenario: Mode auto recorded for another session does not apply
    Given the session record for "other-session" has mode auto
    And no mode is recorded for "guard-test-session"
    When the routing guard runs for "guard-test-session" on a routed script
    Then permissionDecision is "deny"

  # ---------------------------------------------------------------- mode lookup for a resumed or forked chat

  # Backed by: tests/test_routing_guard.py::test_new_id_follows_the_original_id_recorded_as_auto
  Scenario: A resumed chat follows the original session id recorded as auto
    Given the session record for "original-id" has mode auto
    And no record exists for "resumed-id"
    And the transcript of "resumed-id" holds a SessionStart line "[agenting] mode=auto ... (session original-id)"
    When the routing guard runs for "resumed-id" with that transcript_path
    Then the output has a systemMessage that contains "original-id"
    And the output has no hookSpecificOutput

  # Backed by: tests/test_routing_guard.py::test_new_id_follows_the_original_id_recorded_as_manual
  Scenario: The live record of the original id beats the mode printed in the line
    Given the session record for "original-id" has mode manual
    And the transcript of "resumed-id" holds a SessionStart line "[agenting] mode=auto ... (session original-id)"
    When the routing guard runs for "resumed-id" with that transcript_path
    Then permissionDecision is "deny"
    And the reason contains "STAGE 2/2"

  # Backed by: tests/test_routing_guard.py::test_evicted_original_id_uses_the_mode_in_the_line
  Scenario: With the original id evicted an auto mode printed in the line is used
    Given the state file has a record for "someone-else" only
    And the transcript of "resumed-id" holds a SessionStart line "[agenting] mode=auto ... (session original-id)"
    When the routing guard runs for "resumed-id" with that transcript_path
    Then there is no permissionDecision

  # Backed by: tests/test_routing_guard.py::test_evicted_original_id_uses_the_mode_in_the_line
  Scenario: With the original id evicted a manual mode printed in the line is used
    Given the state file has a record for "someone-else" only
    And the transcript of "resumed-id" holds a SessionStart line "[agenting] mode=manual ... (session original-id)"
    When the routing guard runs for "resumed-id" with that transcript_path
    Then permissionDecision is "deny"

  @gap @wip
  # Backed by: @gap
  Scenario: The Stage 2 denial for a resumed manual chat names the session it was carried over from
    Given the session record for "original-id" has mode manual
    And the transcript of "resumed-id" holds a SessionStart line naming "original-id"
    When the routing guard runs for "resumed-id" with that transcript_path
    Then the reason contains "mode is manual, carried over from session original-id"

  # Backed by: tests/test_routing_guard.py::test_the_last_line_in_the_transcript_names_the_id_to_follow
  Scenario: The last SessionStart line in the transcript names the id to follow
    Given the session record for "first-id" has mode auto
    And the session record for "middle-id" has mode manual
    And the transcript holds SessionStart lines for "first-id" and then "middle-id"
    When the routing guard runs for "resumed-id" with that transcript_path
    Then permissionDecision is "deny"

  # Backed by: tests/test_routing_guard.py::test_own_entry_wins_over_the_transcript
  Scenario: A session's own record wins over the transcript
    Given the session record for "original-id" has mode auto
    And the session record for "resumed-id" has mode manual
    And the transcript holds a SessionStart line naming "original-id"
    When the routing guard runs for "resumed-id" with that transcript_path
    Then permissionDecision is "deny"

  # Backed by: tests/test_routing_guard.py::test_no_line_in_the_transcript_still_asks
  Scenario: A transcript with no SessionStart line still asks
    Given the session record for "original-id" has mode auto
    And the transcript of "resumed-id" holds no SessionStart line
    When the routing guard runs for "resumed-id" with that transcript_path
    Then permissionDecision is "deny"
    And the reason contains "could not be found"

  # Backed by: tests/test_routing_guard.py::test_missing_or_unreadable_transcript_still_asks
  Scenario: A missing, unreadable or absent transcript_path still asks
    Given the session record for "original-id" has mode auto
    When the routing guard runs for "resumed-id" with a transcript_path that does not exist, with one that is a directory, and with no transcript_path
    Then permissionDecision is "deny" in all three runs

  # Backed by: tests/test_routing_guard.py::test_text_that_only_quotes_the_line_is_not_a_session_start
  Scenario: An assistant message that merely quotes the line is not a SessionStart line
    Given the session record for "original-id" has mode auto
    And the transcript of "resumed-id" holds only an assistant text record quoting "[agenting] mode=auto ... (session original-id)"
    When the routing guard runs for "resumed-id" with that transcript_path
    Then permissionDecision is "deny"

  # Backed by: tests/test_routing_guard.py::test_a_line_naming_an_unrelated_id_does_not_borrow_another_sessions_auto
  Scenario: An unrelated session recorded as auto does not apply when the transcript line names a different, unrecorded id
    Given the session record for "unrelated" has mode auto
    And the transcript of "resumed-id" holds a SessionStart line "[agenting] mode=manual ... (session original-id)"
    When the routing guard runs for "resumed-id" with that transcript_path
    Then permissionDecision is "deny"

  @gap @wip
  # Backed by: @gap
  Scenario: Transcript lines that are not valid JSON are skipped
    Given the transcript of "resumed-id" holds the text "[agenting] mode=auto garbage" on one line and a valid SessionStart line "[agenting] mode=auto ... (session original-id)" on the next
    And the session record for "original-id" has mode auto
    When the routing guard runs for "resumed-id" with that transcript_path
    Then the output has a systemMessage that contains "original-id"

  # ---------------------------------------------------------------- gaps found in review

  @gap @wip
  # Backed by: @gap
  Scenario: Valid JSON that is not an object is silent and exits 0
    Given stdin "[]"
    When the routing guard runs
    Then the exit code is 0
    And stdout is empty

  # Backed by: tests/test_routing_guard.py::test_variable_routing_values_pass_on_presence_and_show_question_marks
  Scenario: A call whose model and effort are variables passes Stage 1 and shows "?" in the plan
    Given the session record for "guard-test-session" has mode manual
    And Workflow scripts "await agent('x', {model:M, effort:E})" and a pipeline() call whose options are {..., agentType: lens.agentType, model: lens.model, effort: lens.effort}
    When the routing guard runs on each
    Then each reason contains "STAGE 2/2"
    And each reason contains "Plan signature: ?/?x1"
    # Presence only: the guard cannot know what a variable holds at run time, so an item whose
    # effort is undefined still inherits the session tier. The Stage 1 text says so.

  # Backed by: tests/test_routing_guard.py::test_options_passed_as_a_variable_are_reported_by_line_and_cause
  Scenario: A call whose options are a variable is denied at Stage 1
    Given a Workflow script "await agent('x', opts)"
    When the routing guard runs
    Then the reason contains "STAGE 1/2"
    And the reason contains "line    1  [no model, no effort]"

  @gap @wip
  # Backed by: @gap
  Scenario: The Stage 2 denial offers the user three directions
    Given the session record for "guard-test-session" has mode manual
    When the routing guard runs on a routed script
    Then the reason contains "[as proposed]"
    And the reason contains "[cheaper/faster]"
    And the reason contains "[higher quality]"

  @gap @wip
  # Backed by: @gap
  Scenario: The auto note names the session the mode was carried over from
    Given the session record for "original-id" has mode auto
    And the transcript of "resumed-id" holds a SessionStart line "[agenting] mode=auto ... (session original-id)"
    When the routing guard runs for "resumed-id" with that transcript_path
    Then the systemMessage contains "auto mode, mode carried over from session original-id"
