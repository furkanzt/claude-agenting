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
