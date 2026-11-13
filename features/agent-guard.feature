Feature: The Agent routing guard denies an agent that would start on the main chat's tier by accident
  The agent routing guard (hooks/agent-routing-guard.py) is a PreToolUse hook on the Agent tool. It denies a start with no model or no effort, stays silent for forks, agenting: agents, agent files that pin both and calls that carry the routing: inherit line, and never emits an allow or ask decision. A teammate (a named start with agent teams on) takes its effort only from an agent file, measured 2026-11-13 on Claude Code 2.1.323.

  # Backed by: tests/test_agent_guard.py::test_routed_subagent_passes_silently
  Scenario: An Agent call with model sonnet and effort low gets no output
    Given an Agent call with model "sonnet" and effort "low" and no name
    When the agent routing guard runs
    Then the exit code is 0
    And stdout is empty

  # Backed by: tests/test_agent_guard.py::test_no_model_and_no_effort_is_denied
  Scenario: An Agent call with no model and no effort is denied
    Given an Agent call with description "trace it" and no model, no effort and no subagent_type
    When the agent routing guard runs
    Then permissionDecision is "deny"
    And the reason contains 'Agent start "trace it" has no model and no effort'
    And the reason contains 'model: "sonnet", effort: "low"' and '"routing: inherit"'
    And systemMessage is "agenting: an agent start had no model or effort; Claude is retrying with both set"
    And the reason says "Do not work around this by inheriting." and offers "routing: inherit" only when the user asked

  # Backed by: tests/test_agent_guard.py::test_effort_only_missing_is_denied
  Scenario: An Agent call with a model but no effort is denied for the effort
    Given an Agent call with model "sonnet" and no effort
    When the agent routing guard runs
    Then permissionDecision is "deny"
    And the reason contains "has no effort. Its effort would come from the settings default for that model"
    And the reason does not contain "has no model"

  # Backed by: tests/test_agent_guard.py::test_model_only_missing_is_denied
  Scenario: An Agent call with an effort but no model is denied for the model
    Given an Agent call with effort "low" and no model
    When the agent routing guard runs
    Then permissionDecision is "deny"
    And the reason contains "has no model." and "Add one from the routing table"
    And the reason does not contain "no effort"

  # Backed by: tests/test_agent_guard.py::test_agenting_agent_with_no_call_fields_passes
  Scenario: An agenting: agent needs no model or effort on the call
    Given an Agent call with subagent_type "agenting:coder" and no model and no effort
    When the agent routing guard runs
    Then stdout is empty

  # Backed by: tests/test_agent_guard.py::test_fork_passes
  Scenario: A fork is never denied
    Given an Agent call with subagent_type "fork" and no model and no effort
    When the agent routing guard runs
    Then stdout is empty

  # Backed by: tests/test_agent_guard.py::test_inherit_mark_passes
  Scenario: A line that is exactly routing: inherit lets an unrouted call through
    Given an unrouted Agent call whose prompt holds a line "routing: inherit", or "// Routing: Inherit", or "  # routing:inherit  "
    When the agent routing guard runs
    Then stdout is empty

  # Backed by: tests/test_agent_guard.py::test_inherit_words_inside_a_sentence_still_denied
  Scenario: The words routing: inherit inside a sentence are not the mark
    Given an unrouted Agent call whose prompt is "Explain why routing: inherit is risky and when it is fine."
    When the agent routing guard runs
    Then permissionDecision is "deny"

  # Backed by: tests/test_agent_guard.py::test_model_inherit_in_agent_file_counts_as_not_set
  Scenario: An agent file with model inherit pins no model
    Given ~/.claude/agents/pinless.md with "model: inherit" and "effort: low"
    And an Agent call with subagent_type "pinless" and no model and no effort
    When the agent routing guard runs
    Then permissionDecision is "deny"
    And the reason contains "has no model."

  # Backed by: tests/test_agent_guard.py::test_long_description_is_cut_to_60_characters
  Scenario: A long description is cut to 60 characters in the reason
    Given an unrouted Agent call whose description is 100 letters "x"
    When the agent routing guard runs
    Then the reason contains 'Agent start "' followed by exactly 60 "x" and then '" has no model'

  # Backed by: tests/test_agent_guard.py::test_a_named_start_with_teams_off_is_an_ordinary_subagent
  Scenario: A named start with agent teams off is judged as an ordinary subagent
    Given CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS is not set
    And an Agent call with name "worker", model "sonnet" and effort "low"
    When the agent routing guard runs
    Then stdout is empty
    And the same call without an effort is denied with 'Agent start "d" has no effort'

  # Backed by: tests/test_agent_guard.py::test_a_named_start_with_isolation_is_an_ordinary_subagent
  Scenario: A named start with isolation is judged as an ordinary subagent even with agent teams on
    Given CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS is "1"
    And an Agent call with name "worker", isolation "worktree", model "sonnet" and effort "low"
    When the agent routing guard runs
    Then stdout is empty

  # Backed by: tests/test_agent_guard.py::test_teammate_without_a_file_is_denied_even_with_model_and_effort
  Scenario: A teammate with no agent file is denied even when the call carries model and effort
    Given CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS is "1"
    And an Agent call with name "worker", model "sonnet", effort "low" and no subagent_type
    When the agent routing guard runs
    Then permissionDecision is "deny"
    And the reason contains 'Teammate "worker" cannot be given an effort on the call' and "measured 2026-11-13, CLI 2.1.323"
    And the reason contains "agenting:reviewer opus/xhigh"
    And the reason does not contain "has no model"

  # Backed by: tests/test_agent_guard.py::test_teams_env_true_is_read_case_insensitively
  Scenario: The agent teams switch is read case-insensitively
    Given CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS is "True"
    And an Agent call with name "worker", model "sonnet", effort "low"
    When the agent routing guard runs
    Then the reason contains "Teammate"

  # Backed by: tests/test_agent_guard.py::test_teammate_without_a_file_and_without_a_model_says_so
  Scenario: A teammate with no agent file and no model is told about both gaps
    Given CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS is "1"
    And an Agent call with name "worker" and no model, no effort, no subagent_type
    When the agent routing guard runs
    Then the reason contains 'Teammate "worker" has no model, and cannot be given an effort on the call'

  # Backed by: tests/test_agent_guard.py::test_teammate_with_a_file_effort_but_no_model_gets_the_model_text
  Scenario: A teammate whose file sets an effort but no model is told only about the model
    Given CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS is "1"
    And ~/.claude/agents/modelless.md with "effort: low" and no model
    And an Agent call with name "worker" and subagent_type "modelless"
    When the agent routing guard runs
    Then the reason contains 'Teammate "worker" has no model.'
    And the reason does not contain "cannot be given an effort"

  # Backed by: tests/test_agent_guard.py::test_teammate_from_an_agenting_agent_passes
  Scenario: A teammate started from an agenting: agent passes
    Given CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS is "1"
    And an Agent call with name "worker", subagent_type "agenting:coder" and no model, no effort
    When the agent routing guard runs
    Then stdout is empty

  # Backed by: tests/test_agent_guard.py::test_teammate_with_a_differing_call_effort_passes_with_a_note
  Scenario: A teammate whose call effort differs from its file gets a note and no decision
    Given CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS is "1"
    And an Agent call with name "worker", subagent_type "agenting:coder" (file effort "low") and effort "xhigh"
    When the agent routing guard runs
    Then there is no permissionDecision
    And hookEventName is "PreToolUse"
    And additionalContext contains 'effort "xhigh" written on the call is ignored' and '"low"'

  # Backed by: tests/test_agent_guard.py::test_teammate_with_the_same_call_effort_as_its_file_is_silent
  Scenario: A teammate whose call effort equals its file effort gets no note
    Given CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS is "1"
    And an Agent call with name "worker", subagent_type "agenting:coder" (file effort "low") and effort "low"
    When the agent routing guard runs
    Then stdout is empty

  # Backed by: tests/test_agent_guard.py::test_user_agent_file_that_pins_both_passes
  Scenario: A user agent file that pins model and effort lets a bare call through
    Given ~/.claude/agents/mine.md with "model: haiku" and "effort: medium"
    And an Agent call with subagent_type "mine" and no model, no effort
    When the agent routing guard runs
    Then stdout is empty

  # Backed by: tests/test_agent_guard.py::test_user_agent_file_that_pins_only_the_model_is_denied_for_effort
  Scenario: A user agent file that pins only a model is denied for the effort
    Given ~/.claude/agents/half.md with "model: haiku" and no effort
    And an Agent call with subagent_type "half" and no model, no effort
    When the agent routing guard runs
    Then permissionDecision is "deny"
    And the reason contains "has no effort"

  # Backed by: tests/test_agent_guard.py::test_project_agent_file_under_cwd_is_found
  Scenario: A project agent file under the working directory is found
    Given <cwd>/.claude/agents/local.md with "model: sonnet" and "effort: high"
    And an Agent call with subagent_type "local" and no model, no effort
    When the agent routing guard runs
    Then stdout is empty

  # Backed by: tests/test_agent_guard.py::test_a_built_in_type_has_no_file_and_still_needs_routing
  Scenario: A built-in agent type has no file and still needs routing
    Given an Agent call with subagent_type "general-purpose" and no model, no effort
    When the agent routing guard runs
    Then permissionDecision is "deny"

  # Backed by: tests/test_agent_guard.py::test_a_built_in_type_with_its_own_model_is_asked_for_an_effort_only
  Scenario: A built-in type that brings its own model is asked for an effort only
    Given an Agent call with subagent_type "claude-code-guide" and no model, no effort
    When the agent routing guard runs
    Then permissionDecision is "deny"
    And the reason says "has no effort" and does not say "has no model"
    And the same call with effort "medium" leaves stdout empty

  # Backed by: tests/test_agent_guard.py::test_explore_and_plan_bring_no_model_of_their_own
  Scenario: Explore and Plan are asked for a model like any other start
    Given an Agent call with subagent_type "Explore" and effort "medium" and no model
    When the agent routing guard runs
    Then permissionDecision is "deny"
    And the reason says "has no model"

  # Backed by: tests/test_agent_guard.py::test_another_plugins_agent_file_is_found_in_the_plugin_cache
  Scenario: Another plugin's agent file is read from the plugin cache
    Given HOME holds .claude/plugins/cache/market/otherplug/1.2.0/agents/helper.md pinning model "sonnet" and effort "medium"
    And an Agent call with subagent_type "otherplug:helper" and no model, no effort
    When the agent routing guard runs
    Then stdout is empty

  # Backed by: tests/test_agent_guard.py::test_every_plugin_agent_file_pins_model_and_effort
  Scenario: Every agents/*.md of this plugin pins both a model and an effort
    Given the files under agents/
    When their frontmatter is read
    Then each has a "model:" of opus, sonnet, haiku or fable
    And each has an "effort:" of low, medium, high, xhigh or max

  # Backed by: tests/test_agent_guard.py::test_garbage_stdin_exits_zero_silently
  Scenario: Unreadable or wrongly shaped stdin exits 0 with no output
    Given stdin "", "not json", "[]", "null", "42", "{" or a tool_input that is a string or a list
    When the agent routing guard runs
    Then the exit code is 0
    And stdout is empty

  # Backed by: tests/test_agent_guard.py::test_odd_field_types_exit_zero_without_a_decision
  Scenario: Fields of the wrong type exit 0 with nothing on stderr
    Given an Agent call whose model is 3, effort is a list, name is 9, prompt is 1 and cwd is 5
    When the agent routing guard runs
    Then the exit code is 0
    And stderr is empty

  # Backed by: tests/test_agent_guard.py::test_another_tool_is_silent
  Scenario: A tool other than Agent gets no output
    Given a PreToolUse payload for tool "Bash" or "Workflow" whose tool_input has no model and no effort
    When the agent routing guard runs
    Then stdout is empty

  # Backed by: tests/test_agent_guard.py::test_deny_json_never_contains_allow_or_ask
  Scenario: A denial never contains allow or ask
    Given a missing-routing call, a model-only call and a teammate call
    When the agent routing guard runs
    Then permissionDecision is "deny"
    And stdout holds neither "allow" nor "ask" as a quoted value

  # Backed by: tests/test_agent_guard.py::test_reason_names_the_chat_tier_when_the_transcript_has_one
  Scenario: The reason names the main chat's tier from the transcript
    Given a transcript whose last main-thread assistant record is model "claude-fable-5-2" with effort "max"
    And later records that are a sidechain record and a "<synthetic>" record
    And an unrouted Agent call
    When the agent routing guard runs
    Then the reason contains "It would run on this chat's tier (claude-fable-5-2/max)."

  # Backed by: tests/test_agent_guard.py::test_reason_falls_back_when_there_is_no_transcript
  Scenario: The reason falls back to a plain phrase when no tier can be read
    Given an unrouted Agent call with no transcript_path, an empty transcript, or a missing transcript file
    When the agent routing guard runs
    Then the reason contains "It would run on this chat's tier." with no parentheses

  # Backed by: tests/test_agent_guard.py::test_the_hook_is_wired_in_hooks_json_for_the_agent_tool
  Scenario: The guard is wired as a second PreToolUse hook with matcher Agent
    Given hooks/hooks.json
    When the PreToolUse entries are read
    Then exactly one entry has matcher "Agent"
    And its command runs python3 on "${CLAUDE_PLUGIN_ROOT}/hooks/agent-routing-guard.py" with timeout 10
    And exactly one entry still has matcher "Workflow"

  # ---------------------------------------------------------------- workers work alone (advisor)

  # Backed by: tests/test_agent_guard.py::test_advisor_off_leaves_every_output_unchanged
  Scenario: With the advisor off the agent guard's output is byte for byte what it was
    Given CLAUDE_CODE_DISABLE_ADVISOR_TOOL is "1" and the local, project and user settings each name an advisorModel
    And a general-purpose start, an unrouted start, a teammate start, a routing: inherit start and an Explore start
    When the agent routing guard runs with and without those settings files
    Then both runs print the same stdout
    And stdout does not contain "advisor"

  # Backed by: tests/test_agent_guard.py::test_each_settings_file_turns_the_rule_on_in_the_order_local_project_user
  Scenario: The settings files turn the rule on in the order local, project, user
    Given the user file names "user-model", then the project file "project-model", then the local file "local-model"
    When the agent routing guard runs on a routed general-purpose start with no sentence after each file is added
    Then the reason names "user-model", then "project-model", then "local-model"

  # Backed by: tests/test_agent_guard.py::test_a_bad_settings_file_is_skipped_for_the_next_one
  Scenario: A settings file that is not JSON or holds no usable advisorModel is skipped
    Given the local file is "{not json", the project file holds an empty string or a list, and the user file names "user-model"
    When the agent routing guard runs on a routed general-purpose start with no sentence
    Then the reason names "user-model"

  # Backed by: tests/test_agent_guard.py::test_the_environment_switch_wins_over_the_settings_files
  Scenario: CLAUDE_CODE_DISABLE_ADVISOR_TOOL wins over every settings file
    Given all three settings files name an advisorModel
    When the environment switch is "1", "true" or "YES" the agent routing guard runs on a routed general-purpose start
    Then stdout is empty
    And with the switch "0" the start is denied for the advisor

  # Backed by: tests/test_agent_guard.py::test_without_any_settings_file_the_advisor_is_off
  Scenario: With no advisor setting anywhere a routed start passes
    Given the environment switch is not set and no settings file names an advisorModel
    When the agent routing guard runs on a routed general-purpose start
    Then stdout is empty

  # Backed by: tests/test_agent_guard.py::test_general_purpose_and_explore_without_the_sentence_are_denied_with_the_fix
  Scenario: A built-in or untyped start with no work-alone sentence is denied with the exact sentence
    Given the session has advisorModel "claude-fable-5-2"
    And a routed start of type general-purpose, Explore, Plan, claude-code-guide, statusline-setup or no type, with no sentence
    When the agent routing guard runs
    Then permissionDecision is "deny"
    And the reason contains "advisor (claude-fable-5-2)" and the sentence with its backticks around advisor
    And the reason names "advisor: allowed" and says the user, or the skill's design step, asked for it
    And the reason does not mention a missing model or effort

  # Backed by: tests/test_agent_guard.py::test_the_denial_has_its_own_system_message
  Scenario: The advisor denial carries its own system message
    Given the session has an advisor and a routed general-purpose start with no sentence
    When the agent routing guard runs
    Then systemMessage is "agenting: an agent start had no work-alone sentence while the session has an advisor; Claude is retrying with it"

  # Backed by: tests/test_agent_guard.py::test_a_prompt_with_the_sentence_passes
  Scenario: A prompt that carries the sentence passes
    Given the session has an advisor
    When the agent routing guard runs on a routed general-purpose start whose prompt holds the sentence, the sentence without backticks, or "WORK ALONE. the Advisor ..."
    Then stdout is empty

  # Backed by: tests/test_agent_guard.py::test_a_sentence_with_the_advisor_word_too_far_or_on_the_next_line_does_not_count
  Scenario: A sentence whose advisor word is more than 40 characters away or on the next line does not count
    Given the session has an advisor
    When the prompt is "Work alone." and 41 spaces and "advisor", or "Work alone." and "advisor" on two lines, or "Work alone, the advisor ..."
    Then the start is denied for the advisor

  # Backed by: tests/test_agent_guard.py::test_an_advisor_allowed_line_passes_and_the_same_words_in_a_sentence_do_not
  Scenario: A whole prompt line "advisor: allowed" passes and the same words in a sentence do not
    Given the session has an advisor
    When the prompt has a line "advisor: allowed", "// Advisor: Allowed" or "  # advisor:allowed  "
    Then stdout is empty
    And a prompt "Explain why advisor: allowed is risky." is denied for the advisor

  # Backed by: tests/test_agent_guard.py::test_agenting_types_a_fork_and_other_plugins_agents
  Scenario: agenting: agents and forks pass and another plugin's agents do not
    Given the session has an advisor
    When the agent routing guard runs on subagent_type "agenting:coder", "agenting:reviewer" with a model, "fork" and "otherplug:helper"
    Then the first three get no output and "otherplug:helper" is denied for the advisor

  # Backed by: tests/test_agent_guard.py::test_a_teammate_falls_under_the_rule
  Scenario: A teammate falls under the rule
    Given the session has an advisor and agent teams on
    And a named start from a user agent file that pins model sonnet and effort low
    When the agent routing guard runs with no sentence, then with the sentence, then as agenting:coder
    Then the first is denied with 'Teammate "worker" would inherit this session's advisor' and the other two get no output

  # Backed by: tests/test_agent_guard.py::test_a_start_with_a_routing_gap_and_no_sentence_gets_one_denial_with_both
  Scenario: A routing gap and a missing sentence share one denial, routing first
    Given the session has an advisor and a general-purpose start with no model, no effort and no sentence
    When the agent routing guard runs
    Then one denial contains 'has no model and no effort' before the sentence
    And the systemMessage contains "it also needs the work-alone sentence"

  # Backed by: tests/test_agent_guard.py::test_a_teammate_with_an_effort_gap_and_no_sentence_gets_one_denial_with_both
  Scenario: A teammate's effort gap and a missing sentence share one denial
    Given the session has an advisor, agent teams on, and a named start with a model and an effort on the call but no agent file
    When the agent routing guard runs
    Then the reason contains "cannot be given an effort on the call" and the sentence

  # Backed by: tests/test_agent_guard.py::test_the_routing_inherit_line_escapes_routing_only
  Scenario: The routing: inherit line escapes the routing check but not the advisor rule
    Given the session has an advisor and a prompt with the line "routing: inherit" and no sentence
    When the agent routing guard runs
    Then the reason contains the sentence and not "no model"
    And the same prompt with the sentence added gets no output

  # Backed by: tests/test_agent_guard.py::test_a_non_string_prompt_is_denied_without_a_crash
  Scenario: A prompt that is not a string counts as carrying no sentence
    Given the session has an advisor and a routed general-purpose start whose prompt is the number 5
    When the agent routing guard runs
    Then the start is denied for the advisor

  # Backed by: tests/test_agent_guard.py::test_the_advisor_denial_never_says_allow_or_ask
  Scenario: The advisor rule never emits allow or ask
    Given the session has an advisor
    When the agent routing guard runs on denied and passing starts
    Then stdout never contains "allow" or "ask" as a quoted value
