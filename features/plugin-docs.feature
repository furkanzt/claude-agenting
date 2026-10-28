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
  Scenario: The skill description keeps its five original trigger phrases
    Given the "description:" line of skills/agenting/SKILL.md
    When it is searched for "writing or editing a Workflow script", "choosing a model or effort for an agent() or Agent call", "opts in to workflows for this chat", "agenting/AGENTING.md" and "switches agenting mode (auto/manual) or disposition (fast/balanced/quality)"
    Then all five are present

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
    When it is searched for the file names tasks.jsonl, rules.md, schema.json and check.py, the {"path", "as"} entry, the full plan command with its flags, "run --max-usd N", "status --out-dir out", "two levels above this skill's base directory" and "reference/fan-outs.md"
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
    Then plan exits 0 and says "2 to run" with a cost bound, run is accepted and writes summary.json (exit 0 or 1, never a usage error), and status exits as run did and reports the last run

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
    Then both use "auto-disposition-default" with the values fast, balanced or quality

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
  Scenario: The relative links in SKILL.md that leave skills/agenting resolve
    Given the links in skills/agenting/SKILL.md to ../../evals/README.md, ../../evals/research/2026-10-06-sonnet-vs-opus-open-book.md and ../../evals/results/PREREGISTERED-2026-10-09.md
    When each link is resolved from skills/agenting/
    Then every target file exists

  @gap @wip
  # Backed by: @gap
  Scenario: plugin.json declares the MIT license and the same homepage and repository
    Given .claude-plugin/plugin.json
    When its "license", "homepage" and "repository" fields are read
    Then the license is "MIT" and homepage and repository both equal "https://github.com/furkanzt/claude-agenting"
