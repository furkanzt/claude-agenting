Feature: Plugin packaging, agent pins and doc invariants stay consistent, because hooks, users and the routing guard rely on them

  # ---- agent pins -------------------------------------------------------------

  @gap @wip
  # Backed by: @gap
  Scenario: Every agent definition pins a model
    Given the 20 files in agents/
    When the frontmatter of each file is read
    Then each has a "model:" line whose value is one of "haiku", "sonnet" or "opus"

  @gap @wip
  # Backed by: @gap
  Scenario: Every agent definition pins an effort
    Given the 20 files in agents/
    When the frontmatter of each file is read
    Then each has an "effort:" line whose value is one of "low", "medium", "high" or "xhigh"

  @gap @wip
  # Backed by: @gap
  Scenario: An agent's name field equals its file name
    Given the file agents/security-architect.md
    When its frontmatter is read
    Then "name:" is "security-architect", and the same holds for all 20 files in agents/

  @gap @wip
  # Backed by: @gap
  Scenario: Pins are model aliases, not full model ids
    Given the 20 files in agents/
    When the "model:" value of each is read
    Then none contains a "claude-" prefix or a date, so the alias follows the newest model of its family

  @gap @wip
  # Backed by: @gap
  Scenario: The scanner is the only Haiku agent
    Given the 20 files in agents/
    When the "model:" values are counted
    Then exactly one file, agents/scanner.md, has "model: haiku" and "effort: medium"

  @gap @wip
  # Backed by: @gap
  Scenario: Opus is pinned only on orchestration, review, architecture, security and incident agents
    Given the 20 files in agents/
    When the files with "model: opus" are listed
    Then the list is coordinator, swarm-coordinator, reviewer, security-architect, system-architect and incident-responder

  @gap @wip
  # Backed by: @gap
  Scenario: The scanner, reviewer, security-architect and system-architect list no Write or Edit tool
    Given the files agents/scanner.md, agents/reviewer.md, agents/security-architect.md and agents/system-architect.md
    When the "tools:" line of each is read
    Then none lists "Write" or "Edit"

  # ---- the SKILL.md tier table ------------------------------------------------

  @gap @wip
  # Backed by: @gap
  Scenario: The SKILL.md agent tier table agrees with every agent's frontmatter
    Given the tier table in skills/agenting/SKILL.md, whose rows are "haiku/medium", "sonnet/low", "sonnet/medium", "sonnet/high", "opus/high" and "opus/xhigh"
    When each agent listed in a row is looked up in agents/
    Then its "model:" and "effort:" equal the row's tier, for all 20 agents

  @gap @wip
  # Backed by: @gap
  Scenario: The SKILL.md agent tier table lists every shipped agent exactly once
    Given the tier table in skills/agenting/SKILL.md with 1, 4, 5, 4, 2 and 4 agents per row
    When the agent names in the table are compared with the file names in agents/
    Then the two sets are equal and have 20 members, with no name repeated

  @gap @wip
  # Backed by: @gap
  Scenario: The README roster table matches the SKILL.md agent tier table
    Given the roster table under "The shipped roster" in README.md
    When its rows are compared with the agent tier table in skills/agenting/SKILL.md
    Then every tier row lists the same agents

  @gap @wip
  # Backed by: @gap
  Scenario: The agent count stated in the docs equals the number of agent files
    Given README.md, .claude-plugin/plugin.json and .claude-plugin/marketplace.json each say "20 tiered agent definitions"
    When the files matching agents/*.md are counted
    Then the count is 20

  @gap @wip
  # Backed by: @gap
  Scenario: The SKILL.md routing table has seven task-shape rows
    Given the "Routing table" in skills/agenting/SKILL.md
    When its data rows are counted
    Then there are 7, from "List files, count pages" to "Adversarial verify / refute a finding"

  @gap @wip
  # Backed by: @gap
  Scenario: Every file the SKILL.md links to exists
    Given the relative links in skills/agenting/SKILL.md, among them reference/modes.md, reference/fan-outs.md, reference/project-rules.md and external-model-options.md
    When each link is resolved from skills/agenting/
    Then every target file exists

  # ---- the SKILL.md description -----------------------------------------------

  # Backed by: tests/test_skill_docs.py::test_every_old_trigger_phrase_is_still_there
  Scenario: The skill description keeps its original trigger phrases and names the two words for one job
    Given the "description:" line of skills/agenting/SKILL.md
    When it is searched for "writing or editing a Workflow script", "choosing a model or effort for an agent() or Agent call", "opts in to workflows for this chat", "agenting/AGENTING.md", "switches agenting mode (auto/manual) or disposition (cheapest/fast/balanced)" and "calls a job critical or throwaway"
    Then all six are present

  # Backed by: tests/test_skill_docs.py::test_planning_a_fan_out_triggers_the_skill
  Scenario: The skill description triggers on planning a fan-out
    Given the "description:" line of skills/agenting/SKILL.md
    When it is searched for "planning a fan-out of many agents"
    Then the phrase is present

  # Backed by: tests/test_skill_docs.py::test_the_description_stays_short
  Scenario: The skill description stays under 420 characters
    Given the "description:" line of skills/agenting/SKILL.md, 347 characters long today
    When its length is measured
    Then the length is below 420, because it sits in the skill listing every generic agent carries

  # ---- the Procedure ----------------------------------------------------------

  # Backed by: tests/test_skill_docs.py::test_a_clean_run_step_comes_before_drafting
  Scenario: The Procedure asks whether a clean run applies before it asks for a draft
    Given the "Procedure: before calling Workflow" section of skills/agenting/SKILL.md
    When its numbered, bold-titled steps are read in order
    Then a step whose title contains "clean run" comes before the step whose title starts with "Draft", and the step numbers run from 1 without a gap

  # Backed by: tests/test_skill_docs.py::test_the_clean_run_step_carries_the_four_conditions_and_the_default
  Scenario: The clean-run step names the four conditions and the cleanrun.py default
    Given the "Clean run or Workflow?" step of the Procedure
    When it is searched for "self-contained", "no tool beyond Read", "do not coordinate", "checked in code" and "cleanrun.py plan"
    Then all five phrases are present

  # Backed by: tests/test_skill_docs.py::test_the_clean_run_step_shows_the_files_and_the_commands
  Scenario: The clean-run step shows the four files and the commands to type
    Given the "Clean run or Workflow?" step of the Procedure, line breaks read as spaces
    When it is searched for the file names tasks.jsonl, rules.md, schema.json and check.py, the {"path", "as"} entry, the full plan command with its flags, "--tools Read" (tasks that list files need a tool that reads them), "run --max-usd N", "status --out-dir out", "two levels above this skill's base directory" and "reference/fan-outs.md"
    Then every one of them is present

  # Backed by: tests/test_skill_docs.py::test_it_names_all_four_files_and_three_commands
  Scenario: The worked example in fan-outs.md names its four files and its three commands
    Given the "A worked example" section of reference/fan-outs.md
    When its labelled blocks and its command block are read
    Then the files are check.py, rules.md, schema.json and tasks.jsonl, and the commands are plan, run and status in that order

  # Backed by: tests/test_skill_docs.py::test_every_task_line_and_the_schema_are_json_and_one_task_uses_an_as_entry
  Scenario: The worked example's task lines and schema are valid JSON and one task uses an as entry
    Given the "tasks.jsonl" and "schema.json" blocks of the worked example
    When each task line and the schema are parsed as JSON
    Then the task ids are t1 and t2, one task has a files entry holding exactly "path" and "as", and the schema is an object schema

  # Backed by: tests/test_skill_docs.py::test_the_commands_run_as_written_against_the_stub
  Scenario: The worked example's commands run as written against the stub
    Given a folder holding the example's four files, page.txt and reports/q3.txt, and the claude stub
    When the plan, run and status lines are run with the plugin's cleanrun.py in place of the plugin path
    Then plan exits 0 and says "2 to run" and "tools 'Read'" with a cost bound, run is accepted and writes summary.json (exit 0 or 1, never a usage error), and status exits as run did and reports the last run

  # ---- list-price caveats and evidence discipline -----------------------------

  # Backed by: tests/test_skill_docs.py::test_every_saving_is_a_list_price_and_the_window_caveat_travels_with_it
  Scenario: Fan-out guidance contains both the list-price and usage-window phrases
    Given reference/fan-outs.md and the "Fan-outs" section of skills/agenting/SKILL.md
    When each is searched
    Then each contains "list price" and "usage-window effect was not measured" somewhere in its text; the test does not check that the caveat sits next to each saving figure

  # Backed by: tests/test_skill_docs.py::test_clean_run_guidance_says_the_saving_is_list_price_only
  Scenario: The clean-run guidance says its saving is list price only
    Given the "Clean runs" section of reference/fan-outs.md
    When it is searched
    Then it contains "list-price only", "window effect is not measured" and "refuses aliases"

  # Backed by: tests/test_skill_docs.py::test_the_read_heavy_clean_run_saving_is_reported_with_its_confound_and_its_source
  Scenario: The clean-run guidance reports the read-heavy saving as observed on one unit, with its confound and its source
    Given the "Clean runs" section of reference/fan-outs.md, line breaks read as spaces
    When it is searched
    Then it says the read-heavy saving was "observed on one unit", "about half on that unit, not 63%" and "observed, not measured"
    And it says "most of the saving is fewer turns and not a smaller start-up" and "The Workflow side is a single run"
    And it names evals/research/2026-10-28-clean-run-read-heavy-unit.md, and that file exists

  # Backed by: tests/test_skill_docs.py::test_no_withdrawn_or_single_observation_figures
  Scenario: Withdrawn and single-observation figures stay out of the docs
    Given reference/fan-outs.md and skills/agenting/SKILL.md
    When each is searched for "PDF page", "$0.54", "$0.16", "$1.86" and "$0.56"
    Then none of the five strings appears in either file

  # Backed by: tests/test_skill_docs.py::test_levers_carry_an_evidence_tag
  Scenario: Every numbered lever in the fan-out guidance carries an evidence tag
    Given the numbered levers under "Levers" in reference/fan-outs.md
    When each bold lever title is read
    Then each bold lever title found by the test (single-digit numbers only; today 3) contains one of those four words as a substring, and the test passes vacuously if no lever is found

  # Backed by: tests/test_skill_docs.py::test_advisor_is_stated_as_a_fact_not_a_proposal
  Scenario: The advisor is stated as a fact, not offered as a proposal
    Given reference/fan-outs.md
    When it is searched for "do not raise it"
    Then the phrase is present

  # Backed by: tests/test_skill_docs.py::test_text_is_english_and_has_no_local_paths
  Scenario: The fan-out guidance and the skill carry no local paths
    Given reference/fan-outs.md and skills/agenting/SKILL.md
    When each is searched for "/Users/" and "/private/"
    Then neither string appears in either file

  @gap @wip
  # Backed by: @gap
  Scenario: README, agents, commands and hooks.json carry no local paths
    Given README.md, agents/*.md, commands/*.md, templates/AGENTING.md and hooks/hooks.json
    When each is searched for "/Users/" and "/private/"
    Then no file contains either string

  # ---- plugin manifests -------------------------------------------------------

  @gap @wip
  # Backed by: @gap
  Scenario: plugin.json and the marketplace entry carry the same plugin version
    Given .claude-plugin/plugin.json with "version": "3.2.2"
    When the version of the plugin "agenting" in .claude-plugin/marketplace.json is read
    Then it is "3.2.2" too

  @gap @wip
  # Backed by: @gap
  Scenario: The marketplace top-level version is a separate field that is not compared against plugin.json
    Given .claude-plugin/marketplace.json with a top-level "version": "1" and a plugin entry with "version": "3.2.2"
    When the top-level version is read
    Then it is the string "1" and only the plugin entry's version has to equal the "version" in plugin.json

  @gap @wip
  # Backed by: @gap
  Scenario: Both manifests name the plugin "agenting" and the marketplace points at the repo root
    Given .claude-plugin/plugin.json and .claude-plugin/marketplace.json
    When their names and the marketplace plugin source are read
    Then both names are "agenting" and the plugin "source" is "."

  @gap @wip
  # Backed by: @gap
  Scenario: plugin.json, marketplace.json and hooks.json parse as JSON
    Given .claude-plugin/plugin.json, .claude-plugin/marketplace.json and hooks/hooks.json
    When each is parsed as JSON
    Then all three parse without error

  # ---- hooks.json wiring ------------------------------------------------------

  @gap @wip
  # Backed by: @gap
  Scenario: The routing guard is wired to PreToolUse on the Workflow tool
    Given hooks/hooks.json
    When the "PreToolUse" entries are read
    Then there is exactly one, with "matcher": "Workflow", running hooks/workflow-routing-guard.py with "timeout": 10

  @gap @wip
  # Backed by: @gap
  Scenario: The cache tripwire and the finish check are wired to UserPromptSubmit
    Given hooks/hooks.json
    When the "UserPromptSubmit" entries are read
    Then one entry with an empty matcher runs hooks/cache-tripwire.py and then hooks/workflow-finish-check.py, each with "timeout": 5

  @gap @wip
  # Backed by: @gap
  Scenario: Session continuity is wired to SessionStart on startup, resume, compact and clear
    Given hooks/hooks.json
    When the "SessionStart" entries are read
    Then one entry has "matcher": "startup|resume|compact|clear" and runs hooks/session-continuity.py with "timeout": 5

  @gap @wip
  # Backed by: @gap
  Scenario: Every hook command is addressed through CLAUDE_PLUGIN_ROOT and names an existing script
    Given the hook commands in hooks/hooks.json
    When each command string is read
    Then it starts with python3 "${CLAUDE_PLUGIN_ROOT}/hooks/", and the named .py file exists in hooks/

  @gap @wip
  # Backed by: @gap
  Scenario: hooks.json wires no event other than PreToolUse, UserPromptSubmit and SessionStart
    Given hooks/hooks.json
    When the keys under "hooks" are read
    Then they are exactly PreToolUse, UserPromptSubmit and SessionStart

  # ---- project template and commands ------------------------------------------

  @gap @wip
  # Backed by: @gap
  Scenario: The project template has a Rules section and a Config section with the balanced default
    Given templates/AGENTING.md
    When its headings and Config lines are read
    Then it has "## Rules" and "## Config", and the Config holds "auto-disposition-default: balanced"

  @gap @wip
  # Backed by: @gap
  Scenario: The template's Config key is the one the project-rules reference documents
    Given templates/AGENTING.md and skills/agenting/reference/project-rules.md
    When the Config key names in both are compared
    Then both use "auto-disposition-default" with the values fast or balanced

  @gap @wip
  # Backed by: @gap
  Scenario: The plugin ships the two slash commands agenting-check and agenting-mode
    Given the commands/ directory
    When its files are listed
    Then they are agenting-check.md and agenting-mode.md, and agenting-check.md runs scripts/check-setup.py through CLAUDE_PLUGIN_ROOT

  # ---- further invariants confirmed from the files ----------------------------

  @gap @wip
  # Backed by: @gap
  Scenario: Every agent definition starts with a frontmatter block that carries a description
    Given the 20 files in agents/
    When each file is matched against the frontmatter pattern ^---\n(.*?)\n---\n, the one scripts/check-setup.py uses
    Then each matches and its frontmatter has a "description:" line

  @gap @wip
  # Backed by: @gap
  Scenario: Only the coordinator lists the WebFetch tool
    Given the 20 files in agents/
    When the "tools:" line of each is read
    Then only agents/coordinator.md lists "WebFetch"

  @gap @wip
  # Backed by: @gap
  Scenario: The relative links in SKILL.md and reference/evidence.md that leave skills/agenting resolve
    Given the link in skills/agenting/SKILL.md to ../../evals/README.md
    And the links in skills/agenting/reference/evidence.md to ../../../evals/README.md, ../../../evals/research/2026-10-06-sonnet-vs-opus-open-book.md and ../../../evals/results/PREREGISTERED-2026-10-09.md
    When each link is resolved from the folder of its file
    Then every target file exists

  @gap @wip
  # Backed by: @gap
  Scenario: plugin.json declares the MIT license and the same homepage and repository
    Given .claude-plugin/plugin.json
    When its "license", "homepage" and "repository" fields are read
    Then the license is "MIT" and homepage and repository both equal "https://github.com/furkanzt/claude-agenting"

  # --- Where the work runs: the skill's delegation rules agree with the hooks ---

  # Backed by: tests/test_skill_docs.py::test_the_skill_says_agent_starts_are_checked_and_the_hook_is_wired
  Scenario: The skill describes the agent guard that hooks.json wires
    Given skills/agenting/SKILL.md and hooks/hooks.json
    When the docs test reads them
    Then SKILL.md names "agent-routing-guard.py" and does not say "is not gated"
    And hooks.json has exactly 1 PreToolUse entry with matcher "Agent" running agent-routing-guard.py

  # Backed by: tests/test_skill_docs.py::test_the_bulk_thresholds_are_the_same_in_the_skill_and_the_reference
  Scenario: The bulk thresholds read the same in SKILL.md and reference/delegation.md
    Given the "Where the work runs" section of SKILL.md and reference/delegation.md
    When the docs test compares them
    Then both contain "about 5 or more similar items", "about 10 or more files or 20k or more tokens" and "2 or more independent parts"
    And both contain "Time alone never decides"

  # Backed by: tests/test_skill_docs.py::test_the_four_vehicles_are_named_in_the_same_order_in_both_files
  Scenario: The four vehicles are listed cheapest first in both files
    Given the vehicle tables of SKILL.md and reference/delegation.md
    When the docs test reads their first column
    Then each lists One agent, Clean run, Workflow, Teammates in that order

  # Backed by: tests/test_skill_docs.py::test_the_teammates_switch_has_one_name_in_the_docs_and_the_hooks
  Scenario: The teammates switch has one name in the docs and the hooks
    Given reference/delegation.md, hooks/session-continuity.py and hooks/agent-routing-guard.py
    When the docs test searches them
    Then each contains "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS"

  # Backed by: tests/test_skill_docs.py::test_the_teammate_effort_rule_is_stated_where_a_teammate_is_started
  Scenario: The skill states that a teammate takes its effort only from an agent file
    Given the "Agent starts" section of SKILL.md
    When the docs test reads it
    Then it contains "its effort **only from an agent file**" and "TaskStop"

  # Backed by: tests/test_skill_docs.py::test_the_standing_default_is_documented_with_the_flag_the_recorder_accepts
  Scenario: reference/modes.md documents the standing default with the recorder's own flag
    Given reference/modes.md and hooks/session-continuity.py
    When the docs test reads them
    Then modes.md contains "--record-default --workflows on" and the recorder defines "--record-default"

  # Backed by: tests/test_skill_docs.py::test_the_delegation_reference_has_no_local_paths
  Scenario: reference/delegation.md carries no local path
    Given reference/delegation.md
    When the docs test searches it
    Then it contains neither "/Users/" nor "/private/"

  # --- Workers work alone: the advisor is for the decider ---

  # Backed by: tests/test_skill_docs.py::test_the_skill_carries_the_work_alone_sentence_once_in_its_own_section
  Scenario: SKILL.md carries the work-alone sentence once, in its own short section between "Where the work runs" and the routing table
    Given skills/agenting/SKILL.md
    When the docs test reads the section "The advisor is for the decider"
    Then the exact sentence "Work alone. The `advisor` tool belongs to the lead that started you, ..." appears once in the whole file, inside that section, on one line that matches the hooks' pattern
    And the section names "// advisor: allowed" and "const ALONE", and has at most 16 non-blank lines
    And it sits after "Where the work runs" and before "Routing table"

  # Backed by: tests/test_skill_docs.py::test_the_delegation_reference_carries_the_sentence_or_names_the_skill_as_its_source
  Scenario: reference/delegation.md holds the advisor evidence and names SKILL.md as the source of the sentence
    Given the "The advisor" section of reference/delegation.md
    When the docs test reads it
    Then it carries the sentence or names SKILL.md and the section "The advisor is for the decider"
    And it quotes "Subagents inherit the configured advisor" and names "CLAUDE_CODE_DISABLE_ADVISOR_TOOL", "advisor: allowed" and "--disallowedTools"
    And the section comes before "What was not measured", which names the "--advisor" flag as a limit

  # Backed by: tests/test_skill_docs.py::test_the_readme_names_the_allow_mark_and_the_environment_variable
  Scenario: The README names the advisor allow mark and the switch that turns the advisor off
    Given README.md
    When the docs test searches it
    Then it contains "advisor: allowed" and "CLAUDE_CODE_DISABLE_ADVISOR_TOOL"

  # Backed by: tests/test_skill_docs.py::test_the_advisor_docs_carry_no_local_paths
  Scenario: SKILL.md, delegation.md and the README carry no "/Users/" path
    Given skills/agenting/SKILL.md, skills/agenting/reference/delegation.md and README.md
    When the docs test searches each
    Then none contains "/Users/"

  # ---------------------------------------------------------------- think first (2026-11-13)

  # Backed by: tests/test_skill_docs.py::test_the_think_first_step_states_its_three_conditions_and_its_two_design_agents
  Scenario: The skill's third step says when one model decides before the builders start, and who
    Given the step "3. Think first?" of skills/agenting/SKILL.md, which follows "2. Which vehicle?"
    When the docs test reads it
    Then it states the three conditions: later work is built on the choice, at least two options would work, and a wrong choice is expensive to undo
    And it says "Otherwise just build"
    And it names "agenting:system-architect" and "agenting:ux-designer" as the design agents
    And it says a design pass for a UI prototype "is not the default" and that Fable 5.2 thinks first "only when the user asks for it"

  # Backed by: tests/test_skill_docs.py::test_the_think_first_rows_are_opus_xhigh_except_the_architecture_row_in_cheapest
  Scenario: The think-first rows are opus at xhigh, except the architecture row in cheapest
    Given the routing table of SKILL.md and the disposition table of reference/modes.md
    When the docs test reads the rows for the architecture decision and the UI/UX design
    Then each row of the routing table has the model "opus" and the effort "xhigh"
    And the UI/UX row of the disposition table has "opus/xhigh" under cheapest, fast, balanced and in the "critical" column
    And the architecture row has "sonnet/xhigh" under cheapest and "opus/xhigh" in the other three

  # Backed by: tests/test_skill_docs.py::test_the_disposition_table_has_the_four_columns_and_every_cell_the_owner_decided
  Scenario: The disposition table has four columns and every cell the owner decided
    Given the disposition table of reference/modes.md
    When the docs test reads its header and its rows
    Then the columns are "cheapest", "fast", "balanced" and "critical"
    And its twelve rows hold exactly the cells the owner decided on 2026-11-15, written in the test and not read from the docs: the nine document rows and the three build rows (plan and tests, bulk coding, review)

  # Backed by: tests/test_skill_docs.py::test_the_review_row_follows_the_verify_row_in_every_column
  Scenario: The review row follows the verify row in every column
    Given the disposition table of reference/modes.md
    Then the cells of "Review a build" equal the cells of "Adversarial verify/refute" under every column

  # Backed by: tests/test_skill_docs.py::test_the_routing_table_is_the_balanced_column_for_the_changed_rows
  Scenario Outline: The routing table carries the balanced cell of each row that changed in 3.7.0
    Given the routing table of SKILL.md
    Then the row "<row>" has the model "<model>" and the effort "<effort>"

    Examples:
      | row                                                            | model  | effort |
      | Decide under a "don't guess" constraint (BELİRSİZ)             | haiku  | xhigh  |
      | Plan a build and write its tests, before cheaper workers code  | opus   | high   |
      | Bulk coding against tests that exist                           | haiku  | medium |
      | Review a build before it is called done                        | sonnet | high   |

  # Backed by: tests/test_skill_docs.py::test_what_cheapest_gives_up_is_written_down_row_by_row
  Scenario: What cheapest gives up is written down row by row
    Given the part of reference/modes.md that starts "What `cheapest` gives up"
    Then it names classify on Haiku xhigh with "4.1% wrong labels", verify on Haiku xhigh with "1 false "confirmed" in 384", that review follows verify and was not measured itself, and that the architecture decision on Sonnet xhigh rests on few runs
    And it says cheapest means "cheaper at list price, not quicker"

  # Backed by: tests/test_skill_docs.py::test_no_plan_starts_in_cheapest_and_the_docs_say_so
  Scenario: The docs say that no plan starts a chat in cheapest
    Given reference/modes.md and SKILL.md
    Then modes.md says "No plan starts a chat in `cheapest`." and quotes "Change mode: /agenting-mode [cheapest|fast|balanced]"
    And the skill's session-settings section says a new chat starts in the plan's, never in cheapest

  # Backed by: tests/test_skill_docs.py::test_the_bulk_coder_is_haiku_medium_never_changes_tests_and_stops_after_three_failed_checks
  Scenario: The bulk-coder agent is Haiku at medium, never changes the tests and stops after three failed checks
    Given agents/bulk-coder.md
    Then its front matter pins the model "haiku" and the effort "medium"
    And its text says never to change, delete, skip or weaken a given test file or the runner's configuration, to check only with the command it was given, to stop after at most three failed checks, and never to write "pass" without having seen the check pass
    And it carries the work-alone sentence, and SKILL.md names "agenting:bulk-coder"

  # Backed by: tests/test_skill_docs.py::test_no_cell_of_the_routing_table_or_the_disposition_table_names_fable
  Scenario: No cell of the routing table or of the disposition table names Fable
    Given every row of the routing table of SKILL.md and of the disposition table of reference/modes.md
    When the docs test searches each row
    Then none contains "fable"

  # Backed by: tests/test_skill_docs.py::test_the_agent_tables_list_every_agent_file_once_at_the_tier_its_front_matter_pins
  Scenario: The skill's and the README's agent tables list every agent file once, at the tier its front matter pins
    Given every file in agents/ with the model and effort of its front matter
    When the docs test reads the agent table of SKILL.md and the roster table of README.md
    Then each table lists exactly those agents, each once, under its own model and effort
    And "ux-designer" is among them
    And the README states the number of agent definitions that the folder holds

  # Backed by: tests/test_skill_docs.py::test_the_ux_designer_is_read_only_on_opus_xhigh_and_returns_the_six_part_brief
  Scenario: The ux-designer agent is read-only, runs on opus at xhigh and returns the six-part brief
    Given agents/ux-designer.md
    When the docs test reads its front matter and body
    Then the model is "opus", the effort is "xhigh" and the tools are "Read, Grep, Glob"
    And the body names the sections Screens, Flow, States, Words, Main action and Assumptions
    And it says "write no code"

  # ---- fast: fewer agents; prototypes: throwaway or keep ----

  # Backed by: tests/test_skill_docs.py::test_the_fast_thresholds_are_twice_the_usual_ones_in_the_skill_and_the_reference
  Scenario: In fast the bar for leaving the main chat is twice as high, and bulk coding is kept
    Given the "Where the work runs" section of SKILL.md and the "In fast" section of reference/delegation.md
    When both are searched for "about 10 or more similar items", "about 20 or more files or 40k or more tokens of reading", "4 or more independent parts" and "only when the user asks for one"
    Then all four are in both
    And the skill says "Bulk coding still leaves the chat", and the reference says "Bulk coding is not cut", "fewer than 5 agents" and "/advisor off"

  # Backed by: tests/test_skill_docs.py::test_the_prototype_rule_names_both_paths_and_what_each_mode_does
  Scenario: The prototype rule names both paths and says what each mode does
    Given step 4 of "Where the work runs" in SKILL.md, after the think-first step
    When it is read
    Then it says a throwaway uses the cheapest cells and has no tests, no review and no design pass in any disposition, and that keeping it means building it again on the keep path
    And it says the user's word decides, manual mode asks once before building, auto mode decides and says in one line which path it took, and "Unclear: keep."
    And the reference's example table has five rows whose paths are Throwaway, Throwaway, Keep, Keep, Keep, the last one "Unclear, so keep"

